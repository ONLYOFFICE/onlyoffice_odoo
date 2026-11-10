# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import importlib.util
import json

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.misc import file_path

from odoo.addons.onlyoffice_odoo.utils import config_utils
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

    def test_users_read_the_roles_but_cannot_change_them_directly(self):
        """Roles are changed only through advanced_share_save, which checks the right to share first."""
        document = self._document(access_internal="view")
        self._roles(document, internal_users="commenter", colleague="reviewer")
        Access = self.env["onlyoffice.odoo.documents.access"].with_user(self.colleague)
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"].with_user(self.colleague)
        own_role = {"document_id": document.id, "user_id": self.owner.partner_id.id, "role": "commenter"}
        attempts = {
            "create a role": lambda: AccessUser.create(own_role),
            "raise the internal role": lambda: Access.search([("document_id", "=", document.id)]).write(
                {"internal_users": "custom_filter"}
            ),
            "remove a role": lambda: AccessUser.search([("document_id", "=", document.id)]).unlink(),
        }
        for attempt, action in attempts.items():
            with self.subTest(attempt=attempt), self.assertRaises(AccessError):
                action()
        self.assertEqual(AccessUser.search([("document_id", "=", document.id)]).role, "reviewer")

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
                "link_access": "form_filling",
                "user_accesses": [{"user_id": partner.id, "role": "reviewer"}],
            }
        )
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", self.document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("commenter", "form_filling"))
        self.assertEqual(self._user_roles(), {partner: "reviewer"})

    def test_roles_of_odoo_are_left_to_odoo(self):
        # It is called by RPC too: none / view / edit are never stored, a user given one loses the stored role.
        partner = self.colleague.partner_id
        vals = {"document_id": self.document.id, "user_accesses": [{"user_id": partner.id, "role": "reviewer"}]}
        self.share.advanced_share_save(vals)
        self.share.advanced_share_save(
            {
                "document_id": self.document.id,
                "internal_users": "none",
                "link_access": "edit",
                "user_accesses": [{"user_id": partner.id, "role": "view"}],
            }
        )
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", self.document.id)])
        self.assertEqual((access.internal_users, access.link_access), (False, False))
        self.assertEqual(self._user_roles(), {})

    def test_saving_again_updates_roles_and_removes_users(self):
        partner = self.colleague.partner_id
        vals = {"document_id": self.document.id, "internal_users": "commenter"}
        self.share.advanced_share_save({**vals, "user_accesses": [{"user_id": partner.id, "role": "reviewer"}]})

        self.share.advanced_share_save({**vals, "user_accesses": [{"user_id": partner.id, "role": "commenter"}]})
        self.assertEqual(self._user_roles(), {partner: "commenter"})
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
                    {"user_id": 999_999_999, "role": "commenter"},
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
            partners={self.colleague.partner_id.id: ["edit", False]}
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
            access_internal="commenter", access_via_link="custom_filter", partners={partner.id: ["reviewer", False]}
        )

        # Documents itself only knows view/edit: read-only custom roles become view, custom_filter becomes edit.
        self.assertEqual((document.access_internal, document.access_via_link), ("view", "edit"))
        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == partner).role, "view")
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("commenter", "custom_filter"))
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (partner, "reviewer"))

    def test_roles_are_read_only_with_their_document(self):
        private = self._document("Salaries.docx", access_internal="none")
        shared = self._document()
        for document in (private, shared):
            # The rows alone: an invitation would open the private document.
            self.env["onlyoffice.odoo.documents.access"].create(
                {"document_id": document.id, "internal_users": "commenter"}
            )
            self.env["onlyoffice.odoo.documents.access.user"].create(
                {"document_id": document.id, "user_id": self.colleague.partner_id.id, "role": "reviewer"}
            )

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
            partners={self.colleague.partner_id.id: ["edit", False]}
        )
        contact = self.env["res.partner"].create({"name": "OO Contact", "email": "oo.contact@example.com"})

        document.with_user(self.colleague).action_update_access_rights(partners={contact.id: ["commenter", False]})

        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == contact).role, "view")
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search(
            [("document_id", "=", document.id), ("user_id", "=", contact.id)]
        )
        self.assertEqual(user_access.role, "commenter")

    def test_standard_roles_are_left_to_odoo(self):
        """Only roles Odoo has no counterpart for are kept: the panel then shows what Odoo has, kept current."""
        document = self._document().with_user(self.owner)
        partner = self.colleague.partner_id
        document.action_update_access_rights(access_internal="commenter", partners={partner.id: ["reviewer", False]})

        document.action_update_access_rights(
            access_internal="edit", access_via_link="view", partners={partner.id: ["edit", False]}
        )

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), (False, False))
        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))
        self.assertEqual((document.access_internal, document.access_via_link), ("edit", "view"))

        document.sudo().access_internal = "view"
        data = document.permission_panel_data()
        self.assertEqual((data["record"]["access_internal"], data["record"]["access_via_link"]), ("view", "view"))
        roles = {access["partner_id"]["id"]: access["role"] for access in data["record"]["access_ids"]}
        self.assertEqual(roles[partner.id], "edit")

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
class TestRolesOfMembers(DocumentsCase, TransactionCase):
    """A role of a user comes with their membership in Odoo; the roles of Odoo left in the rows by older versions."""

    def setUp(self):
        super().setUp()
        config_utils.set_jwt_secret(self.env, "ds-secret")  # a commenting role saves with the right to read
        self.Roles = self.env["onlyoffice.odoo.documents"]

    def _role(self, document, user=None):
        user = user or self.colleague
        return self.Roles._get_user_role(document, user, document.with_user(user).has_access("write"))

    def _invite(self, document, role, expiration_date=False):
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: [role, False]}
        )
        if expiration_date:
            self._invitation(document).expiration_date = expiration_date

    def _invitation(self, document):
        return document.access_ids.filtered(lambda a: a.partner_id == self.colleague.partner_id)

    def _own_rows(self, document):
        return self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])

    def test_an_invitation_removed_by_the_autovacuum_gives_no_role(self):
        document = self._document(access_internal="view")
        self._invite(document, "commenter", "2020-01-01 00:00:00")
        self.assertEqual(self._role(document), "view", "expired")

        self.env["documents.access"]._gc_expired()

        self.assertFalse(self._invitation(document))
        self.assertEqual(self._role(document), "view")
        self.assertFalse(self._own_rows(document), "the role goes with the invitation")

    def test_an_expired_invitation_given_a_new_date_gets_its_role_back(self):
        document = self._document(access_internal="view")
        self._invite(document, "commenter", "2020-01-01 00:00:00")
        self._invitation(document).expiration_date = "2999-01-01 00:00:00"
        self.assertEqual(self._role(document), "commenter")

    def test_a_member_removed_from_the_folder_loses_the_roles_in_it(self):
        folder = self.env["documents.document"].create(
            {"name": "OO Team", "type": "folder", "access_internal": "none", "owner_id": self.owner.id}
        )
        document = self._document(folder_id=folder.id, access_internal="none")
        self._invite(document, "commenter")
        self.assertEqual(self._role(document), "commenter")

        # Odoo removes the member from the folder and everything in it, without the ORM.
        folder.action_update_access_rights(partners={self.colleague.partner_id.id: [False, False]})
        self.assertFalse(self._own_rows(document))
        # Invited to the folder again, with a role of Odoo: the former role does not come back.
        folder.action_update_access_rights(partners={self.colleague.partner_id.id: ["view", False]})
        self.assertEqual(self._role(document), "view")

    def test_a_new_role_on_the_folder_replaces_the_roles_in_it(self):
        # Odoo gives the member the role of the folder in everything in it: an ONLYOFFICE role set before on a file
        # in there gives way, in the trash too.
        folder = self.env["documents.document"].create(
            {"name": "OO Team", "type": "folder", "access_internal": "none", "owner_id": self.owner.id}
        )
        document = self._document(folder_id=folder.id, access_internal="none")
        trashed = self._document(folder_id=folder.id, access_internal="none")
        for file in (document, trashed):
            self._invite(file, "commenter")
        trashed.action_archive()

        folder.action_update_access_rights(partners={self.colleague.partner_id.id: ["edit", False]})

        self.assertEqual(self._role(document), "edit")
        self.assertFalse(self._own_rows(document) | self._own_rows(trashed))

    def test_a_role_without_a_membership_gives_nothing(self):
        document = self._document(access_internal="view")
        self.env["onlyoffice.odoo.documents.access.user"].create(
            {"document_id": document.id, "user_id": self.colleague.partner_id.id, "role": "commenter"}
        )
        self.assertEqual(self._role(document), "view")

    def test_roles_of_odoo_left_in_the_rows_are_not_used(self):
        # Older versions copied the roles of Odoo into the rows ("none" on every share): Odoo decides.
        document = self._document(access_internal="edit", access_via_link="view")
        self._invite(document, "edit")
        self.env["onlyoffice.odoo.documents.access"].create(
            {"document_id": document.id, "internal_users": "none", "link_access": "edit"}
        )
        self.env["onlyoffice.odoo.documents.access.user"].create(
            {"document_id": document.id, "user_id": self.colleague.partner_id.id, "role": "view"}
        )
        self.assertEqual(self._role(document), "edit")
        data = document.with_user(self.owner).permission_panel_data()
        self.assertEqual((data["record"]["access_internal"], data["record"]["access_via_link"]), ("edit", "view"))
        roles = {access["partner_id"]["id"]: access["role"] for access in data["record"]["access_ids"]}
        self.assertEqual(roles[self.colleague.partner_id.id], "edit")

    def test_update_clears_the_roles_of_odoo_from_the_rows(self):
        document = self._document()
        Access = self.env["onlyoffice.odoo.documents.access"]
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"]
        defaults = Access.create({"document_id": document.id, "internal_users": "none", "link_access": "view"})
        kept = Access.create({"document_id": self._document().id, "internal_users": "commenter", "link_access": "edit"})
        partner = self.colleague.partner_id.id
        stale = AccessUser.create({"document_id": document.id, "user_id": partner, "role": "edit"})
        own = AccessUser.create({"document_id": document.id, "user_id": self.owner.partner_id.id, "role": "reviewer"})
        migration = importlib.util.spec_from_file_location(
            "post_migrate", file_path("onlyoffice_odoo_documents/migrations/0.0.0/post-migrate.py")
        )
        script = importlib.util.module_from_spec(migration)
        migration.loader.exec_module(script)

        for _run in range(2):
            script.migrate(self.env.cr, "18.0.5.3.0")
            self.env.invalidate_all()
            self.assertEqual((defaults.internal_users, defaults.link_access), (False, False))
            self.assertEqual((kept.internal_users, kept.link_access), ("commenter", False))
            self.assertEqual((stale.exists(), own.exists()), (AccessUser, own))


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
