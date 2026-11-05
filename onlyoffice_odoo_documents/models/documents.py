# Copyright (C) 2026 Ascensio System SIA

import json
import logging
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree as ET

from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT

from ..controllers.spreadsheet_docbuilder import XLSX_MIMETYPE
from .onlyoffice_odoo_documents import ONLYOFFICE_ONLY_ROLES

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

    _onlyoffice_frozen_not_editable = models.Constraint(
        "CHECK(onlyoffice_frozen IS NOT TRUE OR (access_via_link != 'edit' AND access_internal != 'edit'))",
        "A frozen spreadsheet can not be editable",
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

    def action_onlyoffice_freeze_and_copy(self):
        """Freeze an XLSX with Odoo formulas into a read-only copy, as "Freeze and share" of Odoo Spreadsheet.

        As action_freeze_and_copy of Odoo: the formulas of the copy become their values, computed now with the rights
        of the user; the copy goes into the "Frozen spreadsheets" folder of the folder of the source, with the access
        of the source made view-only. Returns the copy, to open its share panel.
        """
        self.ensure_one()
        self.env["documents.document"].check_access("create")
        self.check_access("read")
        if not self.env.su and self.folder_id and self.folder_id.user_permission != "edit":
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

        content = _docbuilder.freeze_spreadsheet(self)
        # The same folder as for the spreadsheets of Odoo, created the same way.
        folder_sudo = (
            self.env["documents.document"]
            .sudo()
            .search(
                [("folder_id", "=", self.folder_id.id), ("type", "=", "folder"), ("handler", "=", "frozen_folder")],
                limit=1,
            )
        )
        if not folder_sudo:
            folder_sudo = (
                self.env["documents.document"]
                .sudo()
                .create(
                    {
                        "name": _("Frozen spreadsheets"),
                        "type": "folder",
                        "handler": "frozen_folder",
                        "folder_id": self.folder_id.id,
                        "access_via_link": "none",
                        "access_internal": "none",
                        "access_ids": False,
                        "owner_id": False,
                    }
                )
            )
        frozen = self.sudo().copy(
            {
                "name": _(
                    "Frozen at %(date)s: %(name)s",
                    date=fields.Date.today().strftime(DEFAULT_SERVER_DATE_FORMAT),
                    name=self.name,
                ),
                "access_internal": "none" if self.access_internal == "none" else "view",
                "access_via_link": "view",
                "folder_id": folder_sudo.id,
                "is_access_via_link_hidden": True,
                "access_ids": [
                    Command.create(
                        {"partner_id": access.partner_id.id, "role": "view" if access.role == "edit" else access.role}
                    )
                    for access in self.access_ids
                    if access.role
                ],
                "lock_uid": False,
                "onlyoffice_frozen": True,
                "onlyoffice_spreadsheet_source_id": False,
                "onlyoffice_spreadsheet_metadata": False,
                "onlyoffice_spreadsheet_metadata_checked": True,
            }
        )
        frozen.attachment_id.sudo().write({"raw": content, "mimetype": XLSX_MIMETYPE})
        return {"id": frozen.id, "shortcut_document_id": frozen.shortcut_document_id.id}

    def _get_access_update_domain(self):
        """As for the frozen spreadsheets of Odoo: a frozen copy keeps its access when that of its folder changes."""
        return super()._get_access_update_domain() & (
            Domain("id", "in", self.ids) | Domain("onlyoffice_frozen", "=", False)
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
                "display_name": rec.display_name,
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

    def _is_custom_role(self, role):
        if not role:
            return False
        clean_role = role.replace("write_", "") if role.startswith("write_") else role
        return clean_role in ["commenter", "reviewer", "form_filling", "custom_filter"]

    def _convert_custom_role_to_standard(self, role):
        """The right of Odoo behind a custom role: custom filter edits the file, the others view it."""
        if not role:
            return role
        clean_role = role.replace("write_", "") if role.startswith("write_") else role
        if clean_role == "custom_filter":
            return "edit"
        if clean_role in ["commenter", "reviewer", "form_filling"]:
            return "view"
        return role

    def action_update_access_rights(
        self,
        access_internal=None,
        access_via_link=None,
        is_access_via_link_hidden=None,
        partners=None,
        no_propagation=False,
    ):
        """Synchronize roles between documents and ONLYOFFICE modules."""
        original_access_internal = access_internal
        original_access_via_link = access_via_link
        original_partners = partners.copy() if partners else None

        # A frozen copy is only viewed: no role that edits it, in Odoo (edit) or in ONLYOFFICE.
        if any(self.mapped("onlyoffice_frozen")):
            roles = [access_internal, access_via_link]
            roles += [data[0] if isinstance(data, list | tuple) else data for data in (partners or {}).values()]
            if any(role and role not in ("none", "view") for role in roles):
                raise UserError(_("The frozen spreadsheets are readonly."))

        if access_internal:
            access_internal = self._convert_custom_role_to_standard(access_internal)

        if access_via_link:
            access_via_link = self._convert_custom_role_to_standard(access_via_link)

        partners_with_standard_roles = {}
        if partners:
            for partner_id, role_data in partners.items():
                if isinstance(role_data, list | tuple):
                    role, expiration_date = role_data
                    converted_role = self._convert_custom_role_to_standard(role) if role else role
                    partners_with_standard_roles[partner_id] = (converted_role, expiration_date)
                else:
                    converted_role = self._convert_custom_role_to_standard(role_data) if role_data else role_data
                    partners_with_standard_roles[partner_id] = converted_role

        result = super().action_update_access_rights(
            access_internal,
            access_via_link,
            is_access_via_link_hidden,
            partners_with_standard_roles,
            no_propagation,
        )

        self._save_onlyoffice_roles(
            original_access_internal,
            original_access_via_link,
            original_partners,
        )

        return result

    def _save_onlyoffice_roles(self, access_internal, access_via_link, partners):
        def onlyoffice_role(role):
            """The role kept in the ONLYOFFICE rows: none / view / edit are kept by Odoo, so they stay current."""
            role = role.replace("write_", "") if role and role.startswith("write_") else role
            return role if role in ONLYOFFICE_ONLY_ROLES else False

        for document in self:
            user_accesses = []
            users_to_remove = []

            if partners:
                for partner_id, role_data in partners.items():
                    partner = self.env["res.partner"].browse(int(partner_id))
                    if partner.exists():
                        if isinstance(role_data, list | tuple):
                            role, expiration_date = role_data
                        else:
                            role = role_data

                        if not onlyoffice_role(role):
                            users_to_remove.append(partner.id)
                        else:
                            user_accesses.append(
                                {
                                    "user_id": partner.id,
                                    "role": onlyoffice_role(role),
                                }
                            )

            access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)], limit=1)
            # A right left unchanged keeps its ONLYOFFICE role.
            internal_to_save = onlyoffice_role(access_internal) if access_internal else access.internal_users
            link_to_save = onlyoffice_role(access_via_link) if access_via_link else access.link_access

            if access or internal_to_save or link_to_save or user_accesses or users_to_remove:
                vals = {
                    "document_id": document.id,
                    "internal_users": internal_to_save,
                    "link_access": link_to_save,
                    "user_accesses": user_accesses,
                    "users_to_remove": users_to_remove,
                }
                self.env["onlyoffice.odoo.documents"].advanced_share_save(vals)
