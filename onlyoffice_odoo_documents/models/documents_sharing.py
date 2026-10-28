# Copyright (C) 2026 Ascensio System SIA

from odoo import Command, _, api, fields, models
from odoo.exceptions import ValidationError


class DocumentsSharing(models.TransientModel):
    _inherit = "documents.sharing"

    oo_file_extension = fields.Char(string="File Extension", compute="_compute_oo_file_extension", store=False)

    invite_role = fields.Selection(
        selection="_get_invite_role_options",
        string="Role",
        default="view",
        required=True,
    )

    @api.depends("document_ids")
    def _compute_oo_file_extension(self):
        """Return file extension if all files are same type, else empty string."""
        for record in self:
            file_extension = None
            if record.document_ids:
                extensions = set()
                for document in record.document_ids:
                    if document.type == "binary" and document.name and "." in document.name:
                        ext = document.name.split(".")[-1].lower()
                        extensions.add(ext)

                if len(extensions) == 1:
                    file_extension = extensions.pop()

            record.oo_file_extension = file_extension or ""

    CUSTOM_ROLES = [
        ("commenter", "Commenter"),
        ("reviewer", "Reviewer"),
        ("form_filling", "Form Filling"),
        ("custom_filter", "Custom Filter"),
    ]

    ROLES_BY_EXTENSION = {
        "docx": ["commenter", "reviewer"],
        "xlsx": ["commenter", "custom_filter"],
        "pptx": ["commenter"],
        "pdf": ["commenter", "form_filling"],
    }

    def _get_update_rights_params(self):
        """Override to handle custom role changes. Add only actually changed roles."""
        res = super()._get_update_rights_params()

        if not self.document_ids or len(self.document_ids) != 1:
            return res

        doc_id = self.document_ids[0].id
        original_user_roles = {}
        for access_user in self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", doc_id)]):
            original_user_roles[access_user.user_id] = access_user.role
        original_group_roles = {}
        for access_group in self.env["onlyoffice.odoo.documents.access.group"].search([("document_id", "=", doc_id)]):
            original_group_roles[access_group.group_id] = access_group.role

        standard_accesses = self.env["documents.access"].search([("document_id", "=", doc_id)])
        for std_access in standard_accesses:
            if std_access.partner_id and std_access.partner_id not in original_user_roles:
                original_user_roles[std_access.partner_id] = std_access.role
            if std_access.group_id and std_access.group_id not in original_group_roles:
                original_group_roles[std_access.group_id] = std_access.role

        def original_role(access):
            if access.group_id:
                return original_group_roles.get(access.group_id)
            return original_user_roles.get(access.partner_id)

        modified_custom_or_standard_access = self.share_access_ids.filtered(
            lambda a: (
                not a.role.startswith(self.WRITE_VALUE_PREFIX)
                and not a.is_deleted
                and (self._is_custom_role(a.role) or a.role in ["view", "edit"])
                and original_role(a) != a.role
            )
        )

        for access in modified_custom_or_standard_access:
            key, member = ("groups", access.group_id) if access.group_id else ("partners", access.partner_id)
            res.setdefault(key, {})
            if member not in res[key]:
                res[key][member] = (
                    access.role,
                    access.expiration_date if self.is_single else None,
                )

        return res

    @api.model
    def _get_role_options(self):
        """Add custom roles. Filtering by document format count happens in client."""
        base_options = super()._get_role_options()

        custom_options = []
        for code, label in self.CUSTOM_ROLES:
            translated_label = _(label)
            custom_options.append((code, translated_label))
            custom_options.append((f"{self.WRITE_VALUE_PREFIX}{code}", translated_label))

        result = []
        inserted = False
        for option in base_options:
            if option[0] in ("none", "write_none", "mixed", "write_mixed") and not inserted:
                result.extend(custom_options)
                inserted = True
            result.append(option)

        return result

    @api.model
    def _get_invite_role_options(self):
        base_options = [
            ("view", _("Viewer")),
            ("edit", _("Editor")),
        ]
        custom_roles = [(code, _(label)) for code, label in self.CUSTOM_ROLES]
        return base_options + custom_roles

    def action_invite_members(self):
        """Override to support custom roles in invite_role."""
        self.ensure_one()

        # Odoo ranks the current members by their standard roles to decide whom to notify
        for access in self.share_access_ids.filtered(lambda a: self._is_custom_role(a.role)):
            access.role = self.document_ids._convert_custom_role_to_standard(access.role)

        if not self._is_custom_role(self.invite_role):
            return super().action_invite_members()

        # Odoo gets the standard equivalent of the custom role, action_update_access_rights keeps the custom one
        custom_role = self.invite_role
        self.invite_role = self.document_ids._convert_custom_role_to_standard(custom_role)
        return super(DocumentsSharing, self.with_context(onlyoffice_invite_role=custom_role)).action_invite_members()

    def _get_allowed_roles_for_extension(self, ext):
        return self.ROLES_BY_EXTENSION.get(ext.lower() if ext else "", [])

    def _is_custom_role(self, role):
        if not role:
            return False
        clean_role = role.replace(self.WRITE_VALUE_PREFIX, "") if role.startswith(self.WRITE_VALUE_PREFIX) else role
        return clean_role in [code for code, _ in self.CUSTOM_ROLES]

    def _validate_custom_role_for_documents(self, role, documents):
        if not role or not self._is_custom_role(role):
            return True

        clean_role = role.replace(self.WRITE_VALUE_PREFIX, "") if role.startswith(self.WRITE_VALUE_PREFIX) else role

        for doc in documents:
            if doc.type == "binary" and doc.name:
                ext = doc.name.split(".")[-1].lower() if "." in doc.name else ""
                allowed_roles = self._get_allowed_roles_for_extension(ext)
                if clean_role not in allowed_roles:
                    raise ValidationError(
                        _(
                            "Role '%(role)s' is not available for %(ext)s files. Allowed roles: %(allowed)s",
                            role=clean_role,
                            ext=ext.upper(),
                            allowed=", ".join(allowed_roles) if allowed_roles else "view, edit",
                        )
                    )
        return True

    @api.constrains("access_internal", "access_via_link", "share_access_ids", "document_ids")
    def _check_custom_roles(self):
        for record in self:
            if not record.document_ids or len(record.document_ids) != 1:
                continue

            if record.access_internal:
                record._validate_custom_role_for_documents(record.access_internal, record.document_ids)

            if record.access_via_link:
                record._validate_custom_role_for_documents(record.access_via_link, record.document_ids)

            for access in record.share_access_ids:
                if access.role and not access.is_deleted:
                    record._validate_custom_role_for_documents(access.role, record.document_ids)

    @api.model
    def action_open(self, document_ids):
        """Override to show the custom ONLYOFFICE roles instead of their standard equivalents."""
        action = super().action_open(document_ids)
        self.browse(action["res_id"])._load_onlyoffice_roles()
        return action

    def _load_onlyoffice_roles(self):
        self.ensure_one()
        documents = self.document_ids

        user_roles = {doc: {} for doc in documents}
        for access in self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "in", documents.ids)]):
            if access.user_id and access.user_id != access.document_id.owner_id.partner_id:
                user_roles[access.document_id][access.user_id] = access.role
        group_roles = {doc: {} for doc in documents}
        for access in self.env["onlyoffice.odoo.documents.access.group"].search([("document_id", "in", documents.ids)]):
            group_roles[access.document_id][access.group_id] = access.role

        def member_role(member, custom_roles):
            """ONLYOFFICE role of a partner/group on the documents, its standard role where it has none."""
            roles = set()
            for doc in documents:
                role = custom_roles[doc].get(member)
                if not role:
                    access = self._filtered_relevant_access(doc).filtered(
                        lambda a, member=member: (a.group_id or a.partner_id) == member
                    )
                    role = access[:1].role or ("edit" if member == doc.owner_id.partner_id else False)
                roles.add(role)
            return roles.pop() if len(roles) == 1 else "mixed"

        for row in self.share_access_ids:
            member, custom_roles = (row.group_id, group_roles) if row.group_id else (row.partner_id, user_roles)
            if any(member in custom_roles[doc] for doc in documents):
                row.role = member_role(member, custom_roles)

        # Members with an ONLYOFFICE role but without a standard access
        access_shares = [
            Command.create({"partner_id": partner.id, "role": member_role(partner, user_roles)})
            for partner in {partner for roles in user_roles.values() for partner in roles}
            if partner not in self.share_access_ids.partner_id
        ] + [
            Command.create({"group_id": group.id, "role": member_role(group, group_roles)})
            for group in {group for roles in group_roles.values() for group in roles}
            if group not in self.share_access_ids.group_id
        ]

        # Load roles from ONLYOFFICE module (priority over standard)
        values = {"share_access_ids": access_shares} if access_shares else {}
        for field in ("access_internal", "access_via_link"):
            custom_field = "internal_users" if field == "access_internal" else "link_access"

            # Collect values from ONLYOFFICE module for all documents
            onlyoffice_values = []
            for doc in documents:
                onlyoffice_access = self.env["onlyoffice.odoo.documents.access"].search(
                    [("document_id", "=", doc.id)], limit=1
                )
                if onlyoffice_access and onlyoffice_access[custom_field]:
                    onlyoffice_values.append(onlyoffice_access[custom_field])
                else:
                    # If no record - use standard value from documents
                    onlyoffice_values.append(doc[field])

            # Check if all values are the same
            unique_values = set(onlyoffice_values)
            if len(unique_values) == 1:
                values[field] = onlyoffice_values[0]
            else:
                values[field] = "mixed"

        self.write(values)


class DocumentsShareAccess(models.TransientModel):
    _inherit = "documents.sharing.access"

    oo_file_extension = fields.Char(string="File Extension", compute="_compute_oo_file_extension", store=False)

    @api.depends("documents_sharing_id.oo_file_extension")
    def _compute_oo_file_extension(self):
        for record in self:
            record.oo_file_extension = (
                record.documents_sharing_id.oo_file_extension if record.documents_sharing_id else ""
            )

    @api.model
    def _get_role_options(self):
        """Override to support custom roles in access list."""
        return self.env["documents.sharing"]._get_role_options()
