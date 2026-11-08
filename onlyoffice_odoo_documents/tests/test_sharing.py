# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import DocumentsCase


@tagged("post_install", "-at_install")
class TestSharingWizard(DocumentsCase, TransactionCase):
    """documents.sharing, the Share dialog of Odoo 19: the ONLYOFFICE roles next to the standard ones."""

    def _open(self, *documents, user=None):
        Sharing = self.env["documents.sharing"].with_user(user or self.owner)
        return Sharing.browse(Sharing.action_open([d.id for d in documents])["res_id"])

    def _role_of(self, wizard, user):
        return wizard.share_access_ids.filtered(lambda a: a.partner_id == user.partner_id).role

    def test_dialog_shows_the_custom_roles(self):
        document = self._document()
        document.with_user(self.owner).action_update_access_rights(
            access_internal="commenter",
            access_via_link="view",
            partners={self.colleague.partner_id.id: ("reviewer", None)},
        )

        wizard = self._open(document)

        self.assertEqual((wizard.access_internal, wizard.access_via_link), ("commenter", "view"))
        self.assertEqual(self._role_of(wizard, self.colleague), "reviewer")
        self.assertEqual(wizard.oo_file_extension, "docx")
        self.assertEqual(set(wizard.share_access_ids.mapped("oo_file_extension")), {"docx"})

    def test_dialog_hides_an_expired_invitation_with_a_custom_role(self):
        document = self._document()
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("reviewer", None)}
        )
        invitation = document.access_ids.filtered(lambda a: a.partner_id == self.colleague.partner_id)
        invitation.sudo().expiration_date = "2020-01-01 00:00:00"

        wizard = self._open(document)

        self.assertNotIn(self.colleague.partner_id, wizard.share_access_ids.partner_id)

    def test_dialog_hides_an_expired_group_with_a_custom_role(self):
        group = self.env["res.group.functional"].create({"name": "OO Group", "user_ids": [(6, 0, self.colleague.ids)]})
        document = self._document()
        document.with_user(self.owner).action_update_access_rights(groups={group.id: ("commenter", None)})
        document.access_ids.filtered(lambda a: a.group_id == group).sudo().expiration_date = "2020-01-01 00:00:00"

        wizard = self._open(document)

        self.assertNotIn(group, wizard.share_access_ids.group_id)

    def test_dialog_of_several_documents(self):
        report = self._document()
        sheet = self._document("Sheet.xlsx")
        self._roles(report, internal_users="commenter", link_access="none")
        self._roles(sheet, internal_users="custom_filter", link_access="none", colleague="commenter")

        wizard = self._open(report, sheet)

        self.assertEqual(wizard.access_internal, "mixed")
        self.assertEqual(self._role_of(wizard, self.colleague), "mixed")
        self.assertEqual(wizard.oo_file_extension, "")

    def test_saving_the_dialog_stores_a_changed_custom_role(self):
        document = self._document()
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("view", None)}
        )
        wizard = self._open(document)

        wizard.share_access_ids.filtered(lambda a: a.partner_id == self.colleague.partner_id).role = "commenter"
        wizard.action_update_rights()

        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (self.colleague.partner_id, "commenter"))
        # Documents itself keeps the standard counterpart of the custom role.
        self.assertEqual(document.access_ids.filtered(lambda a: a.partner_id == self.colleague.partner_id).role, "view")

    def test_invite_with_a_custom_role(self):
        document = self._document()
        wizard = self._open(document)
        wizard.write(
            {
                "invite_partner_ids": [(6, 0, self.colleague.partner_id.ids)],
                "invite_role": "reviewer",
                "invite_notify": False,
            }
        )

        result = wizard.action_invite_members()

        self.assertEqual(result["params"]["type"], "success")
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (self.colleague.partner_id, "reviewer"))

    def test_an_editor_invites_a_contact_with_a_custom_role(self):
        """Whoever can edit the document may share it, as in Documents itself, not only its owner."""
        document = self._document(access_internal="view")
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("edit", None)}
        )
        contact = self.env["res.partner"].create({"name": "OO Contact", "email": "oo.contact@example.com"})
        wizard = self._open(document, user=self.colleague)
        wizard.write({"invite_partner_ids": [(6, 0, contact.ids)], "invite_role": "commenter", "invite_notify": False})

        result = wizard.action_invite_members()

        self.assertEqual(result["params"]["type"], "success")
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search(
            [("document_id", "=", document.id), ("user_id", "=", contact.id)]
        )
        self.assertEqual(user_access.role, "commenter")

    def test_invite_needs_partners_with_an_email(self):
        document = self._document()
        nobody = self._open(document)
        nobody.invite_role = "commenter"
        self.assertEqual(nobody.action_invite_members()["params"]["type"], "warning")

        no_email = self.env["res.partner"].create({"name": "OO Without Email"})
        wizard = self._open(document)
        wizard.write({"invite_partner_ids": [(6, 0, no_email.ids)], "invite_role": "commenter"})
        self.assertEqual(wizard.action_invite_members()["params"]["type"], "warning")
        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))

    def test_custom_role_must_fit_the_file_type(self):
        document = self._document()
        wizard = self._open(document)
        with self.assertRaises(ValidationError):
            wizard.access_internal = "form_filling"
