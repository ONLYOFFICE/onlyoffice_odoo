# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_documents.models.documents import _extract_odoo_metadata_from_xlsx

from .common import XLSX_MIMETYPE, DocumentsCase, blank, make_xlsx, xlsx_with_metadata

METADATA = {"lists": {"1": {"model": "res.partner", "columns": ["name"]}}, "globalFilters": []}


@tagged("post_install", "-at_install")
class TestAccessRoles(DocumentsCase, TransactionCase):
    """The ONLYOFFICE roles stored next to the standard Documents access rights."""

    def test_custom_roles_depend_on_the_file_type(self):
        """The share dialog offers only the roles Documents itself has no counterpart for, per file type."""
        roles = self.env["documents.sharing"]._get_allowed_roles_for_extension
        self.assertEqual(roles("docx"), ["commenter", "reviewer"])
        self.assertEqual(roles("XLSX"), ["commenter", "custom_filter"])
        self.assertEqual(roles("pptx"), ["commenter"])
        self.assertEqual(roles("pdf"), ["commenter", "form_filling"])
        self.assertEqual(roles("zip"), [])
        self.assertEqual(roles(""), [])

    def test_share_dialog_offers_the_custom_roles(self):
        sharing = self.env["documents.sharing"]
        options = dict(sharing._get_role_options())
        for role in ("commenter", "reviewer", "form_filling", "custom_filter"):
            with self.subTest(role=role):
                self.assertIn(role, options)
                self.assertIn(f"{sharing.WRITE_VALUE_PREFIX}{role}", options)

    def test_custom_role_must_fit_the_file_type(self):
        sharing = self.env["documents.sharing"]
        docx = self._document()
        for role in ("view", "edit", "reviewer", f"{sharing.WRITE_VALUE_PREFIX}commenter"):
            with self.subTest(role=role):
                self.assertTrue(sharing._validate_custom_role_for_documents(role, docx))
        with self.assertRaises(ValidationError):
            sharing._validate_custom_role_for_documents("form_filling", docx)

    def test_access_defaults_and_cascade(self):
        document = self._document()
        access = self.env["onlyoffice.odoo.documents.access"].create({"document_id": document.id})
        self.assertEqual((access.internal_users, access.link_access), ("none", "view"))

        document.sudo().unlink()
        self.assertFalse(access.exists())

    def test_users_read_the_roles_but_cannot_change_them_directly(self):
        """Roles are changed only through advanced_share_save, which checks the right to share first."""
        document = self._document(access_internal="view")
        self._roles(document, internal_users="view", owner="edit")
        Access = self.env["onlyoffice.odoo.documents.access"].with_user(self.colleague)
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"].with_user(self.colleague)
        own_role = {"document_id": document.id, "user_id": self.colleague.partner_id.id, "role": "edit"}
        attempts = {
            "create a role": lambda: AccessUser.create(own_role),
            "raise the internal role": lambda: Access.search([("document_id", "=", document.id)]).write(
                {"internal_users": "edit"}
            ),
            "remove a role": lambda: AccessUser.search([("document_id", "=", document.id)]).unlink(),
        }
        for attempt, action in attempts.items():
            with self.subTest(attempt=attempt), self.assertRaises(AccessError):
                action()
        self.assertEqual(AccessUser.search([("document_id", "=", document.id)]).role, "edit")

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

    def test_whoever_can_edit_the_document_can_share_it(self):
        """The rule of Documents itself: the right to edit the document, not being its owner."""
        document = self._document(access_internal="view")
        vals = {"document_id": document.id, "internal_users": "commenter"}
        with self.assertRaises(AccessError):
            self.share.with_user(self.colleague).advanced_share_save(vals)

        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("edit", None)}
        )
        self.share.with_user(self.colleague).advanced_share_save(vals)
        self.share.with_user(self.env.ref("base.user_admin")).advanced_share_save(vals)
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual(access.internal_users, "commenter")

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
            access_internal="commenter", access_via_link="custom_filter", partners={partner.id: ("reviewer", None)}
        )

        # Documents itself only knows view/edit: read-only custom roles become view, custom_filter becomes edit.
        self.assertEqual((document.access_internal, document.access_via_link), ("view", "edit"))
        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == partner).role, "view")
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("commenter", "custom_filter"))
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (partner, "reviewer"))

    def test_changing_the_link_keeps_the_right_of_internal_users(self):
        document = self._document().with_user(self.owner)
        document.sudo().access_internal = "edit"

        document.action_update_access_rights(access_via_link="commenter")

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), (False, "commenter"))
        self.assertEqual(document.access_internal, "edit")

    def test_roles_are_read_only_with_their_document(self):
        private = self._document("Salaries.docx", access_internal="none")
        shared = self._document()
        for document in (private, shared):
            self._roles(document, internal_users="commenter", colleague="reviewer")

        for model in ("onlyoffice.odoo.documents.access", "onlyoffice.odoo.documents.access.user"):
            with self.subTest(model=model):
                rows = self.env[model].with_user(self.colleague)
                self.assertEqual(rows.search([("document_id", "in", (private | shared).ids)]).document_id, shared)
                hidden = self.env[model].search([("document_id", "=", private.id)])
                with self.assertRaises(AccessError):
                    hidden.with_user(self.colleague).read(["document_id"])

    def test_an_editor_invites_a_contact_with_a_custom_role(self):
        document = self._document(access_internal="view")
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("edit", None)}
        )
        contact = self.env["res.partner"].create({"name": "OO Contact", "email": "oo.contact@example.com"})

        document.with_user(self.colleague).action_update_access_rights(partners={contact.id: ("commenter", None)})

        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == contact).role, "view")
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search(
            [("document_id", "=", document.id), ("user_id", "=", contact.id)]
        )
        self.assertEqual(user_access.role, "commenter")

    def test_standard_roles_are_left_to_odoo(self):
        """Only roles Odoo has no counterpart for are kept: the panel then shows what Odoo has, kept current."""
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id
        document.action_update_access_rights(access_internal="commenter", partners={partner.id: ("reviewer", None)})

        document.action_update_access_rights(
            access_internal="edit", access_via_link="view", partners={partner.id: ("edit", None)}
        )

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), (False, False))
        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))
        self.assertEqual((document.access_internal, document.access_via_link), ("edit", "view"))

        document.sudo().access_internal = "view"
        Sharing = self.env["documents.sharing"].with_user(self.owner)
        wizard = Sharing.browse(Sharing.action_open(document.ids)["res_id"])
        self.assertEqual((wizard.access_internal, wizard.access_via_link), ("view", "view"))
        self.assertEqual(wizard.share_access_ids.filtered(lambda a: a.partner_id == partner).role, "edit")

    def test_removing_a_partner_removes_the_custom_role(self):
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id
        document.action_update_access_rights(partners={partner.id: ("commenter", None)})

        document.action_update_access_rights(partners={partner.id: (False, None)})

        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))

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
