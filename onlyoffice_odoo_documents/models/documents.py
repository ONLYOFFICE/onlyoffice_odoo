# Copyright (C) 2026 Ascensio System SIA

import json
import logging
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from ..controllers.spreadsheet_docbuilder import XLSX_MIMETYPE

_logger = logging.getLogger(__name__)

# OOXML namespaces needed to parse xl/workbook.xml, its rels and worksheet XML.
_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _extract_odoo_metadata_from_xlsx(xlsx_bytes):
    """Read the JSON metadata from the hidden `_OdooMetadata` sheet, if present.

    Returns the parsed dict, or None if the sheet is missing/unparsable.
    """
    with zipfile.ZipFile(BytesIO(xlsx_bytes)) as zf:
        names = zf.namelist()
        if "xl/workbook.xml" not in names:
            return None
        wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets_el = wb_xml.find(f"{{{_MAIN_NS}}}sheets")
        sheet_el = (
            next(
                (s for s in sheets_el.findall(f"{{{_MAIN_NS}}}sheet") if s.get("name") == "_OdooMetadata"),
                None,
            )
            if sheets_el is not None
            else None
        )
        if sheet_el is None:
            return None

        r_id = sheet_el.get(f"{{{_REL_NS}}}id")
        if not r_id or "xl/_rels/workbook.xml.rels" not in names:
            return None
        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rel_el = next((r for r in rels_xml if r.get("Id") == r_id), None)
        if rel_el is None or not rel_el.get("Target"):
            return None
        sheet_path = "xl/" + rel_el.get("Target").lstrip("/")
        if sheet_path not in names:
            return None
        sheet_xml = ET.fromstring(zf.read(sheet_path))

        shared_strings = []
        if "xl/sharedStrings.xml" in names:
            sst_xml = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst_xml.findall(f"{{{_MAIN_NS}}}si"):
                shared_strings.append("".join(t.text or "" for t in si.iter(f"{{{_MAIN_NS}}}t")))

        rows = {}
        for c in sheet_xml.iter(f"{{{_MAIN_NS}}}c"):
            ref_match = re.match(r"^A(\d+)$", c.get("r") or "")
            if not ref_match:
                continue
            cell_type = c.get("t")
            if cell_type == "s":
                v_el = c.find(f"{{{_MAIN_NS}}}v")
                idx = int(v_el.text) if v_el is not None and v_el.text else None
                text = shared_strings[idx] if idx is not None and 0 <= idx < len(shared_strings) else ""
            elif cell_type == "inlineStr":
                is_el = c.find(f"{{{_MAIN_NS}}}is")
                text = "".join(t.text or "" for t in is_el.iter(f"{{{_MAIN_NS}}}t")) if is_el is not None else ""
            else:
                v_el = c.find(f"{{{_MAIN_NS}}}v")
                text = v_el.text or "" if v_el is not None else ""
            rows[int(ref_match.group(1))] = text

        if not rows:
            return None
        return json.loads("".join(rows[i] for i in sorted(rows)))


class Document(models.Model):
    _inherit = "documents.document"

    onlyoffice_spreadsheet_source_id = fields.Many2one(
        "documents.document",
        string="Spreadsheet Source",
        help="Reference to the original Odoo spreadsheet if this is an XLSX copy",
        ondelete="set null",
    )

    onlyoffice_spreadsheet_metadata = fields.Text(
        string="Spreadsheet Metadata",
        help="JSON metadata from original spreadsheet (lists, pivots, filters) for XLSX copies",
    )

    onlyoffice_spreadsheet_metadata_checked = fields.Boolean(
        default=False,
        help="True once we looked for embedded ODOO metadata in this file's hidden sheet",
    )

    onlyoffice_frozen = fields.Boolean(
        string="Frozen by ONLYOFFICE",
        readonly=True,
        copy=False,
        help="A read-only copy of an XLSX with Odoo data: the values of its formulas, frozen by 'Freeze and share'",
    )

    onlyoffice_can_freeze = fields.Boolean(
        compute="_compute_onlyoffice_can_freeze",
        help="An XLSX that may have Odoo formulas (or not looked at yet), and not a frozen copy",
    )

    @api.depends(
        "type",
        "mimetype",
        "onlyoffice_frozen",
        "onlyoffice_spreadsheet_metadata",
        "onlyoffice_spreadsheet_source_id",
        "onlyoffice_spreadsheet_metadata_checked",
    )
    def _compute_onlyoffice_can_freeze(self):
        for document in self:
            has_odoo_data = (
                document.onlyoffice_spreadsheet_metadata
                or document.onlyoffice_spreadsheet_source_id
                or not document.onlyoffice_spreadsheet_metadata_checked
            )
            document.onlyoffice_can_freeze = bool(
                document.type == "binary"
                and document.mimetype == XLSX_MIMETYPE
                and not document.onlyoffice_frozen
                and has_odoo_data
            )

    def write(self, vals):
        # As Odoo for a frozen spreadsheet: the file of a frozen copy is not replaced.
        if not self.env.su and {"datas", "raw", "attachment_id"} & set(vals) and any(self.mapped("onlyoffice_frozen")):
            raise UserError(_("You can not edit a frozen spreadsheet"))
        return super().write(vals)

    def action_onlyoffice_freeze_and_copy(self, time_zone=None):
        """Freeze an XLSX with Odoo formulas into a read-only copy, as "Freeze and share" of Odoo Spreadsheet.

        The formulas of the copy become their values, computed now with the rights of the user; ``time_zone`` is
        that of the browser, for the dates and times of lists, as Odoo freezes in the browser. The copy goes into
        the child workspace "Frozen spreadsheets" of the workspace of the source, readable by whoever reads that one,
        writable by nobody (Documents managers aside). Returns the copy and its workspace, to share it.
        """
        self.ensure_one()
        self.env["documents.document"].check_access_rights("create")
        self.check_access_rights("read")
        self.check_access_rule("read")
        if not self.folder_id.has_write_access:
            raise AccessError(
                _("You are not allowed to freeze spreadsheets in %(folder)s", folder=self.folder_id.display_name)
            )
        if self.onlyoffice_frozen:
            raise UserError(_("A frozen spreadsheet can not be frozen again"))
        if self.type != "binary" or self.mimetype != XLSX_MIMETYPE:
            raise UserError(_("Only an XLSX file with Odoo data can be frozen"))
        # Metadata of a file not opened yet; a technical field, read from the file itself.
        self.sudo()._ensure_onlyoffice_spreadsheet_metadata()
        if not (self.onlyoffice_spreadsheet_metadata or self.onlyoffice_spreadsheet_source_id):
            raise UserError(_("This file has no Odoo data to freeze"))

        from ..controllers.controllers import _docbuilder  # noqa: PLC0415 - the controllers import this module

        content = _docbuilder.freeze_spreadsheet(self, time_zone)
        folder = self._get_onlyoffice_frozen_folder()
        name = _(
            "Frozen at %(date)s: %(name)s",
            date=fields.Date.today().strftime(DEFAULT_SERVER_DATE_FORMAT),
            name=self.name,
        )
        frozen = (
            self.env["documents.document"]
            .sudo()
            .create(
                {
                    "name": name,
                    "folder_id": folder.id,
                    "owner_id": self.env.user.id,
                    "partner_id": self.partner_id.id,
                    "raw": content,
                    "mimetype": XLSX_MIMETYPE,
                    "onlyoffice_frozen": True,
                    "onlyoffice_spreadsheet_metadata_checked": True,
                }
            )
        )
        return {"id": frozen.id, "folder_id": folder.id}

    def _get_onlyoffice_frozen_folder(self):
        """The child workspace "Frozen spreadsheets" of the workspace of the document, created once.

        Readable by the groups that read or write the source workspace (everybody when it has none), writable by
        nobody but Documents managers: Documents 17 gives rights by workspace only.
        """
        source = self.folder_id
        Folder = self.env["documents.folder"].sudo()
        folder = Folder.search([("parent_folder_id", "=", source.id), ("onlyoffice_frozen_folder", "=", True)], limit=1)
        if folder:
            return folder
        readers = source.group_ids | source.read_group_ids or self.env.ref("base.group_user")
        return Folder.create(
            {
                "name": _("Frozen spreadsheets"),
                "parent_folder_id": source.id,
                "company_id": source.company_id.id,
                "read_group_ids": [(6, 0, readers.ids)],
                "group_ids": [(5, 0, 0)],
                "onlyoffice_frozen_folder": True,
            }
        )

    def _ensure_onlyoffice_spreadsheet_metadata(self):
        """Recover metadata from the hidden `_OdooMetadata` sheet, once per document.

        A re-uploaded XLSX (previously downloaded from an ONLYOFFICE conversion)
        has no `onlyoffice_spreadsheet_metadata`/`onlyoffice_spreadsheet_source_id`,
        so `has_odoo_formulas` stays false and ODOO_* functions never load.
        This checks the file itself and restores the field. Called lazily,
        right before opening the editor, so bulk uploads never trigger it.
        """
        self.ensure_one()
        if self.onlyoffice_spreadsheet_metadata_checked:
            return
        if self.onlyoffice_spreadsheet_metadata or self.onlyoffice_spreadsheet_source_id:
            return
        if self.mimetype != XLSX_MIMETYPE or not self.attachment_id or not self.attachment_id.raw:
            return

        try:
            metadata = _extract_odoo_metadata_from_xlsx(self.attachment_id.raw)
        except Exception as ex:
            _logger.debug("Could not extract embedded ODOO metadata from %s: %s", self.name, ex)
            metadata = None

        vals = {"onlyoffice_spreadsheet_metadata_checked": True}
        if metadata:
            vals["onlyoffice_spreadsheet_metadata"] = json.dumps(metadata)
        try:
            self.write(vals)
        except AccessError as ex:
            # No write access (e.g. read-only share): skip, retry on next open.
            _logger.debug("Could not persist embedded metadata for document %s: %s", self.id, ex)

    def _get_onlyoffice_spreadsheets_domain(self, domain=None):
        """Build the base domain matching any XLSX document, regardless of folder; a frozen copy is read-only."""
        base_domain = [
            ("type", "=", "binary"),
            ("mimetype", "=", XLSX_MIMETYPE),
            ("onlyoffice_frozen", "=", False),
        ]
        if domain:
            base_domain += domain
        return base_domain

    @api.model
    def get_onlyoffice_spreadsheets_to_display(self, domain=None, offset=0, limit=0):
        """Return XLSX documents available for the ONLYOFFICE insert-sheet tab."""
        records = self.search(
            self._get_onlyoffice_spreadsheets_domain(domain),
            offset=offset,
            limit=limit or None,
            order="write_date desc, id desc",
        )
        return [
            {
                "id": rec.id,
                "name": rec.name,
                "thumbnail": rec.thumbnail or False,
            }
            for rec in records
        ]

    @api.model
    def get_onlyoffice_spreadsheets_count(self, domain=None):
        """Return count of XLSX documents available for the ONLYOFFICE insert-sheet tab."""
        return self.search_count(self._get_onlyoffice_spreadsheets_domain(domain))

    @api.depends("checksum")
    def _compute_thumbnail(self):
        res = super()._compute_thumbnail()

        for record in self:
            if record.mimetype == "application/pdf":
                record.thumbnail = False
                record.thumbnail_status = False
        return res


class Folder(models.Model):
    _inherit = "documents.folder"

    onlyoffice_frozen_folder = fields.Boolean(
        readonly=True,
        copy=False,
        help="The workspace of the spreadsheets frozen by ONLYOFFICE 'Freeze and share' in its parent workspace",
    )
