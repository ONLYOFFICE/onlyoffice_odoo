# Copyright (C) 2026 Ascensio System SIA

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from odoo.addons.onlyoffice_odoo.utils import jwt_utils

# ONLYOFFICE roles that save the file: the editor gets a callback URL for them.
SAVING_ROLES = ("edit", "custom_filter", "commenter", "reviewer", "form_filling")
# Saving roles that only add comments, suggested changes or form data: they save with the right to read in Odoo.
COMMENTING_ROLES = ("commenter", "reviewer", "form_filling")
# Roles that Odoo does not have: only these are kept in the ONLYOFFICE rows, Odoo keeps none / view / edit itself.
ONLYOFFICE_ONLY_ROLES = ("commenter", "reviewer", "form_filling", "custom_filter")


def onlyoffice_role(role):
    """``role`` if it is one Odoo does not have, else False.

    Odoo keeps none / view / edit itself: such a value in an ONLYOFFICE row was written by an older version and would
    hide the current rights of Odoo.
    """
    return role if role in ONLYOFFICE_ONLY_ROLES else False


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

    @api.model
    def _get_user_role(self, document, user, can_write):
        """ONLYOFFICE role of an internal user on a document, "none" when ONLYOFFICE is turned off for them.

        ONLYOFFICE roles are added to the rights of Odoo. Edit and custom filter need the right to write in Odoo
        (``can_write``). Commenting roles save with the right to read, as their save is checked by the Document
        Server: only with JWT, which signs it. Otherwise the user views. Without an ONLYOFFICE role of their own and
        without one for internal users, the rights of Odoo decide. A frozen spreadsheet
        is only viewed.
        """
        role = self._get_role_within_odoo_rights(document, user, can_write)
        return "view" if document.onlyoffice_frozen and role != "none" else role

    @api.model
    def _get_role_within_odoo_rights(self, document, user, can_write):
        """The role of ``_get_user_role`` before the frozen rule."""
        commenting_saves = jwt_utils.is_jwt_enabled(self.env)

        def within_odoo_rights(role):
            if can_write or role not in SAVING_ROLES or (role in COMMENTING_ROLES and commenting_saves):
                return role
            return "view"

        if document.owner_id == user:
            return "edit" if can_write else "view"
        # A role of their own comes with a live invitation of Odoo: one expired, or removed (by the autovacuum of
        # expired ones, or from a folder), gives nothing in Odoo, nor its ONLYOFFICE role.
        if self._is_invited(document, user):
            access_user = (
                self.env["onlyoffice.odoo.documents.access.user"]
                .sudo()
                .search([("document_id", "=", document.id), ("user_id", "=", user.partner_id.id)], limit=1)
            )
            if onlyoffice_role(access_user.role):
                return within_odoo_rights(access_user.role)
            return "edit" if can_write else "view"
        access = (
            self.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if onlyoffice_role(access.internal_users):
            return within_odoo_rights(access.internal_users)
        return "edit" if can_write else "view"

    @api.model
    def _is_invited(self, document, user):
        """Whether ``user`` is a member of ``document`` in Odoo: a row of its access with a role, not expired."""
        odoo_access = document.sudo().access_ids.filtered(lambda a: a.partner_id == user.partner_id)[:1]
        expired = odoo_access.expiration_date and odoo_access.expiration_date < fields.Datetime.now()
        return bool(odoo_access.role) and not expired

    @api.model
    def _forget_former_members(self, documents):
        """Drops the ONLYOFFICE roles of the users who are no longer members of ``documents`` in Odoo.

        Odoo removes a member without the ORM at times (from a folder and everything in it): a role left behind would
        come back with a later invitation given another way (to the folder above, say). An expired invitation keeps
        its role, which a new expiration date gives back.
        """
        rows = self.env["onlyoffice.odoo.documents.access.user"].sudo().search([("document_id", "in", documents.ids)])
        if not rows:
            return
        members = {
            (access.document_id.id, access.partner_id.id)
            for access in self.env["documents.access"]
            .sudo()
            .search([("document_id", "in", rows.document_id.ids), ("role", "!=", False)])
        }
        rows.filtered(lambda row: (row.document_id.id, row.user_id.id) not in members).unlink()

    @api.model
    def _saves_with_read_access(self, document):
        """Whether the current user saves the document with only the right to read it: a commenting role.

        Checked again at save time, as the role may have changed since the editor was opened.
        """
        if not jwt_utils.is_jwt_enabled(self.env) or not document.has_access("read") or document.is_locked:
            return False
        return self._get_user_role(document, self.env.user, False) in COMMENTING_ROLES

    def _get_available_roles(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        roles = {
            "none": _("None"),
            "view": _("Viewer"),
            "commenter": _("Commenter"),
            "reviewer": _("Reviewer"),
            "edit": _("Editor"),
            "form_filling": _("Form Filling"),
            "custom_filter": _("Custom Filter"),
        }

        if ext == "docx":
            roles.pop("form_filling", None)
            roles.pop("custom_filter", None)
        elif ext == "xlsx":
            roles.pop("reviewer", None)
            roles.pop("form_filling", None)
        elif ext == "pptx":
            roles.pop("reviewer", None)
            roles.pop("form_filling", None)
            roles.pop("custom_filter", None)
        elif ext == "pdf":
            roles.pop("commenter", None)
            roles.pop("reviewer", None)
            roles.pop("custom_filter", None)
        else:
            roles = {
                "none": _("None"),
                "view": _("Viewer"),
                "edit": _("Editor"),
            }

        return roles

    @api.model
    def advanced_share_save(self, vals):
        document_id = vals.get("document_id")
        if not document_id:
            raise AccessError(_("No document selected for sharing."))

        # Same rule as Documents' own sharing: whoever can edit the document can share it.
        self.env["documents.document"].browse(document_id).check_access("write")

        if self.env["documents.document"].browse(document_id).onlyoffice_frozen:
            roles = [vals.get("internal_users"), vals.get("link_access")]
            roles += [user_access.get("role") for user_access in vals.get("user_accesses", [])]
            if any(role not in (False, None, "", "view", "none") for role in roles):
                raise UserError(_("The frozen spreadsheets are readonly."))

        # Roles are read-only for users: they are changed only here, after the check above.
        Access = self.env["onlyoffice.odoo.documents.access"].sudo()
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"].sudo()

        # Only the roles Odoo does not have are kept: Odoo keeps the others itself.
        roles = {
            "internal_users": onlyoffice_role(vals.get("internal_users")),
            "link_access": onlyoffice_role(vals.get("link_access")),
        }
        access = Access.search([("document_id", "=", document_id)], limit=1)
        if not access:
            access = Access.create({"document_id": document_id, **roles})
        else:
            access.write(roles)

        users_to_remove = vals.get("users_to_remove", [])
        if users_to_remove:
            AccessUser.search([("document_id", "=", document_id), ("user_id", "in", users_to_remove)]).unlink()

        user_accesses = vals.get("user_accesses", [])
        existing_accesses = AccessUser.search([("document_id", "=", document_id)]).mapped("user_id.id")

        for user_data in user_accesses:
            role = onlyoffice_role(user_data.get("role"))
            if not role:
                AccessUser.search([("document_id", "=", document_id), ("user_id", "=", user_data["user_id"])]).unlink()
                continue
            if user_data["user_id"] in existing_accesses:
                AccessUser.search([("document_id", "=", document_id), ("user_id", "=", user_data["user_id"])]).write(
                    {"role": role}
                )
            else:
                if self.env["res.partner"].search_count([("id", "=", user_data["user_id"])]):
                    AccessUser.create(
                        {
                            "document_id": document_id,
                            "user_id": user_data["user_id"],
                            "role": role,
                        }
                    )

        return True
