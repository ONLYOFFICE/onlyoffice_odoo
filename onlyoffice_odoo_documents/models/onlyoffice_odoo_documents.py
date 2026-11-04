# Copyright (C) 2026 Ascensio System SIA

from odoo import _, api, models
from odoo.exceptions import AccessError


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

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
                    "internal_users": vals.get("internal_users", "none"),
                    "link_access": vals.get("link_access", "none"),
                }
            )
        else:
            access.write(
                {
                    "internal_users": vals.get("internal_users"),
                    "link_access": vals.get("link_access"),
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
