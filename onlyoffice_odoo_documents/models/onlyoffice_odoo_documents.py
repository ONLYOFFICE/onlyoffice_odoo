# Copyright (C) 2026 Ascensio System SIA

from odoo import _, api, models
from odoo.exceptions import AccessError

# ONLYOFFICE roles that save the file (edits, comments, review, filled forms); they need the right to write in Odoo.
SAVING_ROLES = ("editor", "custom_filter", "commenter", "reviewer", "form_filling")


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

    @api.model
    def _get_user_role(self, document, user, can_write):
        """ONLYOFFICE role of an internal user on a document, "none" when ONLYOFFICE is turned off for them.

        ONLYOFFICE roles are added to the rights of Odoo: a role that saves the file works only with the right to
        write in Odoo (``can_write``), otherwise the user views. Without a role of their own and without a role for
        internal users, the rights of Odoo decide.
        """

        def within_odoo_rights(role):
            return "viewer" if role in SAVING_ROLES and not can_write else role

        if document.owner_id == user:
            return "editor" if can_write else "viewer"
        access_user = (
            self.env["onlyoffice.odoo.documents.access.user"]
            .sudo()
            .search([("document_id", "=", document.id), ("user_id", "=", user.id)], limit=1)
        )
        if access_user.role:
            return within_odoo_rights(access_user.role)
        access = (
            self.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if access.internal_users:
            return within_odoo_rights(access.internal_users)
        return "editor" if can_write else "viewer"

    @api.model
    def advanced_share_data(self, vals):
        document_id = vals.get("document_id")
        if not document_id:
            raise AccessError(_("No document selected for sharing."))

        if len(document_id) > 1:
            raise AccessError(_("Please select only one document for advanced sharing."))

        is_admin = self.env.user.has_group("base.group_system")
        document = self.env["documents.document"].browse(document_id)
        if not is_admin and document.owner_id != self.env.user:
            raise AccessError(_("Only the owner or administrator can share documents."))

        ext = document.name.split(".")[-1].lower() if "." in document.name else ""

        if ext not in ["docx", "xlsx", "pptx", "pdf"]:
            raise AccessError(_("Incorrect file type for advanced sharing. Please select a different document."))

        roles = self._get_available_roles(document.name)

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document_id)], limit=1)

        users_access = []
        for user_access in self.env["onlyoffice.odoo.documents.access.user"].search(
            [("document_id", "=", document_id)]
        ):
            users_access.append(
                {
                    "user": {
                        "id": user_access.user_id.id,
                        "name": user_access.user_id.name,
                        "email": user_access.user_id.email,
                    },
                    "role": {
                        "id": user_access.id,
                        "role": user_access.role,
                    },
                }
            )

        return {
            "document": {
                "id": document.id,
                "text": document.name,
            },
            "internal_users": access.internal_users or False,
            "internal_users_roles": roles,
            "link_access": access.link_access or False,
            "link_access_roles": roles,
            "users_access": users_access,
            "users_access_roles": roles,
        }

    def _get_available_roles(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        roles = {
            "none": _("None"),
            "viewer": _("Viewer"),
            "commenter": _("Commenter"),
            "reviewer": _("Reviewer"),
            "editor": _("Editor"),
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
                "viewer": _("Viewer"),
                "editor": _("Editor"),
            }

        return roles

    @api.model
    def advanced_share_save(self, vals):
        document_id = vals.get("document_id")
        if not document_id:
            raise AccessError(_("No document selected for sharing."))

        if len(document_id) > 1:
            raise AccessError(_("Please select only one document for advanced sharing."))

        is_admin = self.env.user.has_group("base.group_system")
        document = self.env["documents.document"].browse(document_id)
        if not is_admin and document.owner_id != self.env.user:
            raise AccessError(_("Only the owner or administrator can share documents."))

        # Roles are read-only for users: they are changed only here, after the check above.
        Access = self.env["onlyoffice.odoo.documents.access"].sudo()
        AccessUser = self.env["onlyoffice.odoo.documents.access.user"].sudo()

        access = Access.search([("document_id", "=", document_id)], limit=1)
        if not access:
            access = Access.create(
                {
                    "document_id": document_id[0],
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

        user_accesses = vals.get("user_accesses", [])
        current_accesses = AccessUser.search([("document_id", "=", document_id)])

        existing_accesses = {acc.user_id.id: acc for acc in current_accesses}
        new_user_ids = {ua["user_id"] for ua in user_accesses}

        for user_data in user_accesses:
            user_id = user_data["user_id"]
            if user_id in existing_accesses:
                existing_accesses[user_id].write({"role": user_data["role"]})
            else:
                AccessUser.create(
                    {
                        "document_id": document_id[0],
                        "user_id": user_id,
                        "role": user_data["role"],
                    }
                )

        to_remove = set(existing_accesses.keys()) - new_user_ids
        if to_remove:
            current_accesses.filtered(lambda a: a.user_id.id in to_remove).unlink()

        return True
