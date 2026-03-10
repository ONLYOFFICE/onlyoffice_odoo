from odoo import _, api, models


class Document(models.Model):
    _inherit = "documents.document"

    @api.depends("checksum")
    def _compute_thumbnail(self):
        super()._compute_thumbnail()

        for record in self:
            if record.mimetype == "application/pdf":
                record.thumbnail = False
                record.thumbnail_status = False
        return

    @api.readonly
    def permission_panel_data(self):
        result = super().permission_panel_data()

        if result["record"]["type"] == "binary":
            roles = list(self._get_available_roles(self.name).items())

            for key in ["access_via_link", "access_internal", "doc_access_roles"]:
                if key in result["selections"]:
                    result["selections"][key] = roles + result["selections"][key]

        document_id = result["record"]["id"]

        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document_id)])
        if access and access.exists():
            result["record"]["access_internal"] = access.internal_users
            result["record"]["access_via_link"] = access.link_access

        access_user = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document_id)])
        if access_user and access_user.exists():
            user_roles = {access.user_id.id: access.role for access in access_user if access.user_id}
            for access_id in result["record"].get("access_ids", []):
                partner_id = access_id["partner_id"]["id"]
                if partner_id in user_roles:
                    access_id["role"] = user_roles[partner_id]

        return result

    def _get_available_roles(self, filename):
        ext = filename.split(".")[-1].lower() if "." in filename else ""

        roles = {
            "commenter": _("Commenter"),
            "reviewer": _("Reviewer"),
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
                "view": _("Viewer"),
                "edit": _("Editor"),
            }

        return roles

    def action_update_access_rights(
        self,
        access_internal=None,
        access_via_link=None,
        is_access_via_link_hidden=None,
        partners=None,
        notify=False,
        message="",
    ):
        def convert_custom_role(role):
            if role in ["commenter", "reviewer", "form_filling"]:
                return "view"
            elif role == "custom_filter":
                return "edit"
            return role

        if partners:
            partners_with_standard_roles = {}
            for partner_id, role_data in partners.items():
                if isinstance(role_data, (list, tuple)):  # noqa: UP038
                    role = role_data[0]
                    expiration_date = role_data[1]
                    partners_with_standard_roles[partner_id] = [convert_custom_role(role), expiration_date]
                else:
                    partners_with_standard_roles[partner_id] = convert_custom_role(role_data)
        else:
            partners_with_standard_roles = partners

        result = super().action_update_access_rights(
            convert_custom_role(access_internal),
            convert_custom_role(access_via_link),
            is_access_via_link_hidden,
            partners_with_standard_roles,
            notify,
            message,
        )

        for document in self:
            if document.type != "binary":
                continue

            user_accesses = []
            users_to_remove = []

            if partners:
                for partner_key, role_data in partners.items():
                    if isinstance(partner_key, int):
                        partner = self.env["res.partner"].browse(partner_key)
                    elif isinstance(partner_key, str):
                        partner = self.env["res.partner"].browse(int(partner_key))
                    else:
                        partner = partner_key

                    if partner.exists():
                        role = role_data[0] if isinstance(role_data, (list, tuple)) else role_data  # noqa: UP038

                        if role is False:
                            users_to_remove.append(partner.id)
                        else:
                            user_accesses.append(
                                {
                                    "user_id": partner.id,
                                    "role": role,
                                }
                            )

            access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])

            if access_internal:
                internal_users = access_internal
            elif access and access.exists():
                internal_users = access.internal_users
            else:
                internal_users = document.access_internal

            if access_via_link:
                link_access = access_via_link
            elif access and access.exists():
                link_access = access.link_access
            else:
                link_access = document.access_via_link

            vals = {
                "document_id": document.id,
                "internal_users": internal_users,
                "link_access": link_access,
                "user_accesses": user_accesses,
                "users_to_remove": users_to_remove,
            }

            self.env["onlyoffice.odoo.documents"].advanced_share_save(vals)

        return result
