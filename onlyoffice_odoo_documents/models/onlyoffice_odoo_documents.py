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

        is_admin = self.env.user.has_group("base.group_system")
        document = self.env["documents.document"].browse(document_id)
        if not is_admin and document.create_uid != self.env.user:
            raise AccessError(_("Only the owner or administrator can share documents."))

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document_id)], limit=1)
        if not access:
            access = self.env["onlyoffice.odoo.documents.access"].create(
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
            self.env["onlyoffice.odoo.documents.access.user"].search(
                [("document_id", "=", document_id), ("user_id", "in", users_to_remove)]
            ).unlink()

        user_accesses = vals.get("user_accesses", [])
        existing_accesses = (
            self.env["onlyoffice.odoo.documents.access.user"]
            .search([("document_id", "=", document_id)])
            .mapped("user_id.id")
        )

        for user_data in user_accesses:
            if user_data["user_id"] in existing_accesses:
                self.env["onlyoffice.odoo.documents.access.user"].search(
                    [("document_id", "=", document_id), ("user_id", "=", user_data["user_id"])]
                ).write({"role": user_data["role"]})
            else:
                if self.env["res.partner"].search_count([("id", "=", user_data["user_id"])]):
                    self.env["onlyoffice.odoo.documents.access.user"].create(
                        {
                            "document_id": document_id,
                            "user_id": user_data["user_id"],
                            "role": user_data["role"],
                        }
                    )

        return True
