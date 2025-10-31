from odoo import api, models


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

    def _is_custom_role(self, role):
        if not role:
            return False
        clean_role = role.replace("write_", "") if role.startswith("write_") else role
        return clean_role in ["commenter", "reviewer", "form_filling", "custom_filter"]

    def _convert_custom_role_to_standard(self, role):
        """Convert custom roles to 'view' for base documents model."""
        if not role:
            return role
        clean_role = role.replace("write_", "") if role.startswith("write_") else role
        if clean_role in ["commenter", "reviewer", "form_filling", "custom_filter"]:
            return "view"
        return role

    def action_update_access_rights(
        self,
        access_internal=None,
        access_via_link=None,
        is_access_via_link_hidden=None,
        partners=None,
        no_propagation=False,
    ):
        """Synchronize roles between documents and ONLYOFFICE modules."""
        original_access_internal = access_internal
        original_access_via_link = access_via_link
        original_partners = partners.copy() if partners else None

        if access_internal:
            access_internal = self._convert_custom_role_to_standard(access_internal)

        if access_via_link:
            access_via_link = self._convert_custom_role_to_standard(access_via_link)

        partners_with_standard_roles = {}
        if partners:
            for partner_id, role_data in partners.items():
                if isinstance(role_data, tuple):
                    role, expiration_date = role_data
                    converted_role = self._convert_custom_role_to_standard(role) if role else role
                    partners_with_standard_roles[partner_id] = (converted_role, expiration_date)
                else:
                    converted_role = self._convert_custom_role_to_standard(role_data) if role_data else role_data
                    partners_with_standard_roles[partner_id] = converted_role

        result = super().action_update_access_rights(
            access_internal,
            access_via_link,
            is_access_via_link_hidden,
            partners_with_standard_roles,
            no_propagation,
        )

        self._save_onlyoffice_roles(
            original_access_internal,
            original_access_via_link,
            original_partners,
        )

        return result

    def _save_onlyoffice_roles(self, access_internal, access_via_link, partners):
        for document in self:
            user_accesses = []
            users_to_remove = []

            if partners:
                for partner_id, role_data in partners.items():
                    partner = self.env["res.partner"].browse(int(partner_id))
                    if partner.exists():
                        if isinstance(role_data, tuple):
                            role, expiration_date = role_data
                        else:
                            role = role_data

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

            if access_internal is not None:
                internal_to_save = access_internal
            else:
                internal_to_save = access.internal_users if access else None

            if access_via_link is not None:
                link_to_save = access_via_link
            else:
                link_to_save = access.link_access if access else None

            if internal_to_save or link_to_save or user_accesses or users_to_remove:
                vals = {
                    "document_id": document.id,
                    "internal_users": internal_to_save or "none",
                    "link_access": link_to_save or "none",
                    "user_accesses": user_accesses,
                    "users_to_remove": users_to_remove,
                }
                self.env["onlyoffice.odoo.documents"].advanced_share_save(vals)
