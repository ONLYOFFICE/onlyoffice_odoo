from odoo import _, api, models
from odoo.exceptions import AccessError


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

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
            "internal_users": access.internal_users if access else "none",
            "internal_users_roles": roles,
            "link_access": access.link_access if access else "viewer",
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
        if not is_admin and document.create_uid != self.env.user:
            raise AccessError(_("Only the owner or administrator can share documents."))

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document_id)], limit=1)
        if not access:
            access = self.env["onlyoffice.odoo.documents.access"].create(
                {
                    "document_id": document_id[0],
                    "internal_users": vals.get("internal_users", "none"),
                    "link_access": "viewer",
                }
            )
        else:
            access.write({"internal_users": vals.get("internal_users")})

        user_accesses = vals.get("user_accesses", [])
        current_accesses = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document_id)])

        existing_accesses = {acc.user_id.id: acc for acc in current_accesses}
        new_user_ids = {ua["user_id"] for ua in user_accesses}

        for user_data in user_accesses:
            user_id = user_data["user_id"]
            if user_id in existing_accesses:
                existing_accesses[user_id].write({"role": user_data["role"]})
            else:
                self.env["onlyoffice.odoo.documents.access.user"].create(
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
