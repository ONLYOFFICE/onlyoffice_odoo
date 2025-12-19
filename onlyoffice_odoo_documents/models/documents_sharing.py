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

        standard_accesses = self.env["documents.access"].search([("document_id", "=", doc_id)])
        for std_access in standard_accesses:
            if std_access.partner_id not in original_user_roles:
                original_user_roles[std_access.partner_id] = std_access.role

        modified_custom_or_standard_access = self.share_access_ids.filtered(
            lambda a: not a.role.startswith(self.WRITE_VALUE_PREFIX)
            and not a.is_deleted
            and (self._is_custom_role(a.role) or a.role in ["view", "edit"])
            and original_user_roles.get(a.partner_id) != a.role
        )

        if modified_custom_or_standard_access:
            if "partners" not in res:
                res["partners"] = {}

            for access in modified_custom_or_standard_access:
                if access.partner_id not in res["partners"]:
                    res["partners"][access.partner_id] = (
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

        if not self._is_custom_role(self.invite_role):
            return super().action_invite_members()

        if not self.invite_partner_ids:
            params = {
                "title": _("No partners"),
                "message": "",
                "type": "warning",
            }
        elif self.invite_partner_ids.filtered(lambda p: not p.email):
            params = {
                "title": _("Some emails are missing"),
                "message": _("Please fill in the missing email addresses."),
                "type": "warning",
            }
        else:
            self.document_ids.action_update_access_rights(
                partners={partner: (self.invite_role, None) for partner in self.invite_partner_ids},
                no_propagation=not self.is_folder_only,
            )

            if self.invite_notify:
                share_template = self.env.ref("documents.mail_template_document_share", raise_if_not_found=False)
                if share_template:
                    share_template.with_context(
                        documents=self.document_ids, message=self.invite_notify_message or ""
                    ).send_mail_batch(self.invite_partner_ids.ids)

            params = {
                "title": _("Successfully Shared"),
                "message": (
                    _("%s members added.", len(self.invite_partner_ids))
                    if len(self.invite_partner_ids) > 1
                    else _("Member added.")
                ),
                "type": "success",
                "next": self.action_open(self.document_ids.ids),
            }

        return {"type": "ir.actions.client", "tag": "display_notification", "params": params}

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
    def action_open(self, document_ids):  # noqa: C901
        """Override to load custom ONLYOFFICE roles."""
        if not document_ids:
            raise ValueError("Expected one or more documents.")

        documents = (
            self.env["documents.document"]
            .browse(document_ids)
            .mapped(lambda d: d.shortcut_document_id if d.shortcut_document_id else d)
        )
        document0 = documents[0]

        is_single_doc = len(documents) == 1

        all_partners = self._filtered_relevant_access(documents).partner_id
        access_by_partner_by_doc = {
            doc: {access.partner_id: access.role for access in self._filtered_relevant_access(doc)}
            | ({doc.owner_id.partner_id: "edit"} if doc.owner_id else {})
            for doc in documents
        }

        # Load custom roles
        onlyoffice_access_by_partner = {}
        for doc in documents:
            onlyoffice_user_accesses = self.env["onlyoffice.odoo.documents.access.user"].search(
                [("document_id", "=", doc.id)]
            )
            for access in onlyoffice_user_accesses:
                if access.user_id:
                    if doc not in onlyoffice_access_by_partner:
                        onlyoffice_access_by_partner[doc] = {}
                    onlyoffice_access_by_partner[doc][access.user_id] = access.role
                    all_partners |= access.user_id

        # Combine standard and custom roles
        for doc, custom_accesses in onlyoffice_access_by_partner.items():
            if doc in access_by_partner_by_doc:
                for partner, role in custom_accesses.items():
                    access_by_partner_by_doc[doc][partner] = role
            else:
                access_by_partner_by_doc[doc] = custom_accesses

        if is_single_doc:
            expiration_per_partner = {
                access.partner_id: access.expiration_date for access in self._filtered_relevant_access(documents)
            }

        access_shares = []
        if any(d.owner_id != document0.owner_id for d in documents):
            all_partners |= documents.owner_id.partner_id

        for partner in all_partners:
            role0 = access_by_partner_by_doc.get(documents[0], {}).get(partner)
            is_mixed = any(role0 != access_by_partner_by_doc.get(doc, {}).get(partner) for doc in documents[1:])
            expiration_date = expiration_per_partner.get(partner) if is_single_doc else False
            access_shares.append(
                Command.create(
                    {
                        "expiration_date": expiration_date,
                        "original_expiration_date": expiration_date,
                        "partner_id": partner.id,
                        "role": "mixed" if is_mixed else role0,
                    }
                )
            )

        # Load roles from ONLYOFFICE module (priority over standard)
        values = {}
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

        if len(set(documents.mapped("is_access_via_link_hidden"))) != 1:
            values["access_via_link_mode"] = "mixed"
        elif document0.is_access_via_link_hidden:
            values["access_via_link_mode"] = "link_required"
        else:
            values["access_via_link_mode"] = "discoverable"

        wizard_values = {
            "document_ids": documents.ids,
            "share_access_ids": access_shares,
            **values,
        }

        doc_sharing = self.env["documents.sharing"].create([wizard_values])

        if len(documents) == 1:
            name = _("Share: %(documentName)s", documentName=documents.name)
        else:
            name = _("Share: %(numberOfDocuments)s files", numberOfDocuments=len(documents))

        return {
            "context": {
                "dialog_size": "medium",
            },
            "name": name,
            "res_id": doc_sharing.id,
            "res_model": "documents.sharing",
            "target": "new",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "views": [[False, "form"]],
        }


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
