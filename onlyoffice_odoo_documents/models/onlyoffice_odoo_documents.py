# Copyright (C) 2026 Ascensio System SIA

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.onlyoffice_odoo.utils import jwt_utils

# ONLYOFFICE roles that save the file: the editor gets a callback URL for them.
SAVING_ROLES = ("edit", "custom_filter", "commenter", "reviewer", "form_filling")
# Saving roles that only add comments, suggested changes or form data: they save with the right to read in Odoo.
COMMENTING_ROLES = ("commenter", "reviewer", "form_filling")
# Roles that Odoo does not have: only these are kept in the ONLYOFFICE rows, Odoo keeps none / view / edit itself.
ONLYOFFICE_ONLY_ROLES = ("commenter", "reviewer", "form_filling", "custom_filter")
# From the narrowest to the widest role: of several groups the widest counts.
ROLE_RANK = {
    role: rank
    for rank, role in enumerate(("none", "view", "form_filling", "commenter", "reviewer", "custom_filter", "edit"))
}


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

    @api.model
    def _get_user_role(self, document, user, can_write):
        """ONLYOFFICE role of an internal user on a document, "none" when ONLYOFFICE is turned off for them.

        The role of the user comes first, then the widest of their groups, then that of internal users.
        ONLYOFFICE roles are added to the rights of Odoo. Edit and custom filter need the right to write in Odoo
        (``can_write``). Commenting roles save with the right to read, as their save is checked by the Document
        Server: only with JWT, which signs it. Otherwise the user views. Without an ONLYOFFICE role of their own and
        without one for internal users, the rights of Odoo decide.
        """
        commenting_saves = jwt_utils.is_jwt_enabled(self.env)

        def within_odoo_rights(role):
            if can_write or role not in SAVING_ROLES or (role in COMMENTING_ROLES and commenting_saves):
                return role
            return "view"

        if document.owner_id == user:
            return "edit" if can_write else "view"
        odoo_access = document.sudo().access_ids.filtered(lambda a: a.partner_id == user.partner_id)[:1]
        # An expired invitation gives nothing in Odoo, nor its ONLYOFFICE role.
        if not (odoo_access.expiration_date and odoo_access.expiration_date < fields.Datetime.now()):
            access_user = (
                self.env["onlyoffice.odoo.documents.access.user"]
                .sudo()
                .search([("document_id", "=", document.id), ("user_id", "=", user.partner_id.id)], limit=1)
            )
            if access_user.role:
                return within_odoo_rights(access_user.role)
            if odoo_access.role:
                return "edit" if can_write else "view"
        group_role = self._get_group_role(document, user)
        if group_role:
            return within_odoo_rights(group_role)
        access = (
            self.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if access.internal_users:
            return within_odoo_rights(access.internal_users)
        return "edit" if can_write else "view"

    @api.model
    def _get_group_role(self, document, user):
        """The widest role ``user`` gets through the groups the document is shared with, None without one.

        A group gives its ONLYOFFICE role when it has one, its role in Odoo otherwise; an expired access gives nothing.
        """
        now = fields.Datetime.now()
        group_accesses = document.sudo().access_ids.filtered(
            lambda a: (
                a.group_id
                and a.role
                and user in a.group_id.user_ids
                and not (a.expiration_date and a.expiration_date < now)
            )
        )
        if not group_accesses:
            return None
        onlyoffice_roles = {
            access.group_id: access.role
            for access in self.env["onlyoffice.odoo.documents.access.group"]
            .sudo()
            .search([("document_id", "=", document.id), ("group_id", "in", group_accesses.group_id.ids)])
            if access.role
        }
        roles = [onlyoffice_roles.get(access.group_id, access.role) for access in group_accesses]
        return max(roles, key=lambda r: ROLE_RANK.get(r, 0))

    @api.model
    def _saves_with_read_access(self, document):
        """Whether the current user saves the document with only the right to read it: a commenting role.

        Checked again at save time, as the role may have changed since the editor was opened.
        """
        if not jwt_utils.is_jwt_enabled(self.env) or not document.has_access("read"):
            return False
        if document.lock_uid and document.lock_uid != self.env.user:
            return False
        return self._get_user_role(document, self.env.user, False) in COMMENTING_ROLES

    @api.model
    def advanced_share_save(self, vals):
        document_id = vals.get("document_id")
        if not document_id:
            raise AccessError(_("No document selected for sharing."))

        # Same rule as Documents' own sharing: whoever can edit the document can share it.
        self.env["documents.document"].browse(document_id).check_access("write")

        # Roles are read-only for users: they are changed only here, after the check above.
        Access = self.env["onlyoffice.odoo.documents.access"].sudo()
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"].sudo()
        AccessGroup = self.env["onlyoffice.odoo.documents.access.group"].sudo()

        access = Access.search([("document_id", "=", document_id)], limit=1)
        if not access:
            access = Access.create(
                {
                    "document_id": document_id,
                    "internal_users": vals.get("internal_users") or False,
                    "link_access": vals.get("link_access") or False,
                }
            )
        else:
            access.write(
                {
                    "internal_users": vals.get("internal_users") or False,
                    "link_access": vals.get("link_access") or False,
                }
            )

        users_to_remove = vals.get("users_to_remove", [])
        if users_to_remove:
            AccessUser.search([("document_id", "=", document_id), ("user_id", "in", users_to_remove)]).unlink()

        user_accesses = vals.get("user_accesses", [])
        existing_accesses = AccessUser.search([("document_id", "=", document_id)]).mapped("user_id.id")

        for user_data in user_accesses:
            role = user_data.get("role")
            if not role:
                continue
            if user_data["user_id"] in existing_accesses:
                AccessUser.search([("document_id", "=", document_id), ("user_id", "=", user_data["user_id"])]).write(
                    {"role": user_data["role"]}
                )
            else:
                if self.env["res.partner"].search_count([("id", "=", user_data["user_id"])]):
                    AccessUser.create(
                        {
                            "document_id": document_id,
                            "user_id": user_data["user_id"],
                            "role": user_data["role"],
                        }
                    )

        groups_to_remove = vals.get("groups_to_remove", [])
        if groups_to_remove:
            AccessGroup.search([("document_id", "=", document_id), ("group_id", "in", groups_to_remove)]).unlink()

        for group_data in vals.get("group_accesses", []):
            if not group_data.get("role"):
                continue
            group_access = AccessGroup.search(
                [("document_id", "=", document_id), ("group_id", "=", group_data["group_id"])]
            )
            if group_access:
                group_access.write({"role": group_data["role"]})
            else:
                AccessGroup.create(
                    {
                        "document_id": document_id,
                        "group_id": group_data["group_id"],
                        "role": group_data["role"],
                    }
                )

        return True
