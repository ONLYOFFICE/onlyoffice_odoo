# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_documents.models.documents import _extract_odoo_metadata_from_xlsx

from .common import XLSX_MIMETYPE, DocumentsCase, blank, make_xlsx, xlsx_with_metadata

METADATA = {"lists": {"1": {"model": "res.partner", "columns": ["name"]}}, "globalFilters": []}


@tagged("post_install", "-at_install")
class TestAccessRoles(DocumentsCase, TransactionCase):
    """The ONLYOFFICE roles stored next to the standard Documents access rights."""

    def test_available_roles_depend_on_the_file_type(self):
        roles = self.env["onlyoffice.odoo.documents"]._get_available_roles
        all_roles = {"none", "view", "commenter", "reviewer", "edit", "form_filling", "custom_filter"}
        expected = {
            "Report.docx": all_roles - {"form_filling", "custom_filter"},
            "Sheet.XLSX": all_roles - {"reviewer", "form_filling"},
            "Slides.pptx": {"none", "view", "commenter", "edit"},
            "Form.pdf": {"none", "view", "edit", "form_filling"},
            "Notes.txt": {"none", "view", "edit"},
            "no_extension": {"none", "view", "edit"},
        }
        for filename, keys in expected.items():
            with self.subTest(filename=filename):
                self.assertEqual(set(roles(filename)), keys)

    def test_permission_panel_roles_extend_the_standard_ones_per_file_type(self):
        """documents.document._get_available_roles only adds the roles Documents itself has no counterpart for."""
        roles = self.env["documents.document"]._get_available_roles
        self.assertEqual(set(roles("a.docx")), {"commenter", "reviewer"})
        self.assertEqual(set(roles("a.xlsx")), {"commenter", "custom_filter"})
        self.assertEqual(set(roles("a.pptx")), {"commenter"})
        self.assertEqual(set(roles("a.pdf")), {"form_filling"})
        self.assertEqual(set(roles("a.zip")), {"view", "edit"})

    def test_access_defaults_and_cascade(self):
        document = self._document()
        access = self.env["onlyoffice.odoo.documents.access"].create({"document_id": document.id})
        self.assertEqual((access.internal_users, access.link_access), ("none", "view"))

        document.sudo().unlink()
        self.assertFalse(access.exists())

    def test_attachment_version_starts_at_one(self):
        self.assertEqual(self._document().attachment_id.oo_attachment_version, 1)


@tagged("post_install", "-at_install")
class TestAdvancedShare(DocumentsCase, TransactionCase):
    """onlyoffice.odoo.documents.advanced_share_save, the storage behind the custom roles of the share panel."""

    def setUp(self):
        super().setUp()
        self.document = self._document()
        self.share = self.env["onlyoffice.odoo.documents"].with_user(self.owner)

    def _user_roles(self):
        rows = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", self.document.id)])
        return {row.user_id: row.role for row in rows}

    def test_owner_sets_default_and_per_user_roles(self):
        partner = self.colleague.partner_id
        self.share.advanced_share_save(
            {
                "document_id": self.document.id,
                "internal_users": "commenter",
                "link_access": "view",
                "user_accesses": [{"user_id": partner.id, "role": "reviewer"}],
            }
        )
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", self.document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("commenter", "view"))
        self.assertEqual(self._user_roles(), {partner: "reviewer"})

    def test_saving_again_updates_roles_and_removes_users(self):
        partner = self.colleague.partner_id
        vals = {"document_id": self.document.id, "internal_users": "view", "link_access": "none"}
        self.share.advanced_share_save({**vals, "user_accesses": [{"user_id": partner.id, "role": "reviewer"}]})

        self.share.advanced_share_save({**vals, "user_accesses": [{"user_id": partner.id, "role": "edit"}]})
        self.assertEqual(self._user_roles(), {partner: "edit"})
        self.assertEqual(
            self.env["onlyoffice.odoo.documents.access"].search_count([("document_id", "=", self.document.id)]), 1
        )

        self.share.advanced_share_save({**vals, "users_to_remove": [partner.id]})
        self.assertEqual(self._user_roles(), {})

    def test_unknown_partners_and_empty_roles_are_skipped(self):
        self.share.advanced_share_save(
            {
                "document_id": self.document.id,
                "user_accesses": [
                    {"user_id": self.colleague.partner_id.id, "role": False},
                    {"user_id": 999_999_999, "role": "edit"},
                ],
            }
        )
        self.assertEqual(self._user_roles(), {})

    def test_only_the_owner_or_an_administrator_can_share(self):
        with self.assertRaises(AccessError):
            self.share.with_user(self.colleague).advanced_share_save({"document_id": self.document.id})

        self.share.with_user(self.env.ref("base.user_admin")).advanced_share_save(
            {"document_id": self.document.id, "internal_users": "view"}
        )

    def test_a_document_is_required(self):
        with self.assertRaises(AccessError):
            self.share.advanced_share_save({})


@tagged("post_install", "-at_install")
class TestDocumentAccessRights(DocumentsCase, TransactionCase):
    """documents.document overrides: custom roles in the standard share panel."""

    def test_custom_roles_are_stored_and_mapped_to_standard_rights(self):
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id

        document.action_update_access_rights(
            access_internal="commenter", access_via_link="custom_filter", partners={partner.id: ["reviewer", False]}
        )

        # Documents itself only knows view/edit: read-only custom roles become view, custom_filter becomes edit.
        self.assertEqual((document.access_internal, document.access_via_link), ("view", "edit"))
        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == partner).role, "view")
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("commenter", "custom_filter"))
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (partner, "reviewer"))

    def test_removing_a_partner_removes_the_custom_role(self):
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id
        document.action_update_access_rights(partners={partner.id: ["commenter", False]})

        document.action_update_access_rights(partners={partner.id: [False, False]})

        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))

    def test_permission_panel_shows_the_custom_roles(self):
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id
        document.action_update_access_rights(access_internal="commenter", partners={partner.id: ["reviewer", False]})

        data = document.permission_panel_data()

        self.assertEqual(data["record"]["access_internal"], "commenter")
        self.assertIn("commenter", dict(data["selections"]["access_internal"]))
        self.assertIn("reviewer", dict(data["selections"]["doc_access_roles"]))
        self.assertNotIn("form_filling", dict(data["selections"]["access_internal"]))  # docx has no form filling
        roles = {access["partner_id"]["id"]: access["role"] for access in data["record"]["access_ids"]}
        self.assertEqual(roles[partner.id], "reviewer")

    def test_pdf_documents_have_no_server_thumbnail(self):
        document = self._document("Form.pdf")
        self.assertFalse(document.thumbnail)
        self.assertFalse(document.thumbnail_status)


@tagged("post_install", "-at_install")
class TestSpreadsheetMetadata(DocumentsCase, TransactionCase):
    """ODOO_* metadata of an XLSX: restored from its hidden `_OdooMetadata` sheet, listed for the selector."""

    def _xlsx(self, content, name="Sales.xlsx"):
        return self._document(name, content=content, mimetype=XLSX_MIMETYPE)

    def test_extract_reads_the_json_split_over_column_a(self):
        self.assertEqual(_extract_odoo_metadata_from_xlsx(xlsx_with_metadata(METADATA)), METADATA)

    def test_extract_reads_inline_strings(self):
        xlsx = make_xlsx({"_OdooMetadata": [json.dumps(METADATA)]}, shared_strings=False)
        self.assertEqual(_extract_odoo_metadata_from_xlsx(xlsx), METADATA)

    def test_extract_without_the_hidden_sheet(self):
        self.assertIsNone(_extract_odoo_metadata_from_xlsx(make_xlsx({"Sheet1": ["a"]})))
        self.assertIsNone(_extract_odoo_metadata_from_xlsx(make_xlsx({"_OdooMetadata": []})))

    def test_reuploaded_xlsx_gets_its_metadata_back_once(self):
        document = self._xlsx(xlsx_with_metadata(METADATA))

        document._ensure_onlyoffice_spreadsheet_metadata()
        self.assertEqual(json.loads(document.onlyoffice_spreadsheet_metadata), METADATA)
        self.assertTrue(document.onlyoffice_spreadsheet_metadata_checked)

        document.onlyoffice_spreadsheet_metadata = False
        document._ensure_onlyoffice_spreadsheet_metadata()
        self.assertFalse(document.onlyoffice_spreadsheet_metadata, "the file is read only once")

    def test_plain_or_broken_xlsx_is_only_marked_as_checked(self):
        for content in (blank("xlsx"), make_xlsx({"_OdooMetadata": ["{not json"]})):
            with self.subTest(content=content[:8]):
                document = self._xlsx(content)
                document._ensure_onlyoffice_spreadsheet_metadata()
                self.assertTrue(document.onlyoffice_spreadsheet_metadata_checked)
                self.assertFalse(document.onlyoffice_spreadsheet_metadata)

    def test_other_files_are_not_read(self):
        document = self._document()
        document._ensure_onlyoffice_spreadsheet_metadata()
        self.assertFalse(document.onlyoffice_spreadsheet_metadata_checked)

    def test_read_only_user_does_not_fail(self):
        document = self._xlsx(xlsx_with_metadata(METADATA))
        document.action_update_access_rights(access_internal="view")
        document.with_user(self.colleague)._ensure_onlyoffice_spreadsheet_metadata()
        self.assertFalse(document.onlyoffice_spreadsheet_metadata_checked, "retried on the next open")

    def test_spreadsheet_selector_lists_xlsx_documents_only(self):
        xlsx = self._xlsx(blank("xlsx"), name="OO selector.xlsx")
        self._document("OO selector.docx")
        domain = [("name", "like", "OO selector")]
        Document = self.env["documents.document"].with_user(self.owner)

        self.assertEqual(Document.get_onlyoffice_spreadsheets_count(domain), 1)
        listed = Document.get_onlyoffice_spreadsheets_to_display(domain)
        self.assertEqual([(row["id"], row["name"]) for row in listed], [(xlsx.id, "OO selector.xlsx")])
