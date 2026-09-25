# Copyright (C) 2026 Ascensio System SIA

import json
import logging
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from odoo import api, fields, models
from odoo.exceptions import AccessError

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
        """Build the base domain matching any XLSX document, regardless of folder."""
        base_domain = [
            ("type", "=", "binary"),
            ("mimetype", "=", XLSX_MIMETYPE),
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
