from odoo import api, fields, models
from odoo.exceptions import AccessError


class OnlyofficeDocuments(models.Model):
    _name = "onlyoffice.odoo.documents"
    _description = "ONLYOFFICE Documents"

    folder_id = fields.Many2one("documents.folder", string="Workspace", required=True, ondelete="cascade")
    type = fields.Selection([("ids", "Document list"), ("domain", "Domain")], default="ids", string="Share type")
    document_ids = fields.Many2many("documents.document", string="Shared Documents")
    domain = fields.Char()
    tag_ids = fields.Many2many("documents.tag", string="Shared Tags")
    user_ids = fields.Many2many(
        "res.users",
        string="Users",
        relation="document_share_access_users_rel",
        column1="document_id",
        column2="user_id",
    )
    user_access = fields.Selection(
        [
            ("none", "None"),
            ("viewer", "Viewer"),
            ("comment", "Comment"),
            ("reviewer", "Reviewer"),
            ("editor", "Editor"),
            ("form filling", "Form Filling"),
        ],
        string="User Access",
        default="viewer",
    )
    users_rules = fields.Html(compute="_compute_users_rules", string="People with access")

    internal_access = fields.Selection(
        selection=[
            ("none", "None"),
            ("viewer", "Viewer"),
            ("comment", "Comment"),
            ("reviewer", "Reviewer"),
            ("editor", "Editor"),
            ("form filling", "Form Filling"),
            ("mixed", "Mixed"),
        ],
        default="viewer",
        string="Internal Access",
    )
    default_internal_access = fields.Char()

    link_access = fields.Selection(
        selection=[
            ("none", "None"),
            ("viewer", "Viewer"),
            ("comment", "Comment"),
            ("reviewer", "Reviewer"),
            ("editor", "Editor"),
            ("form filling", "Form Filling"),
            ("mixed", "Mixed"),
        ],
        default="viewer",
        string="Link Access",
    )
    default_link_access = fields.Char()

    users_rules_ids = fields.One2many(
        "onlyoffice.documents.access.user",
        "document_id",
        string="People with access",
        compute="_compute_users_rules_ids",
    )

    extension = fields.Char(
        string="Extension",
        compute="_compute_extension",
        store=True,
    )

    @api.depends("document_ids")
    def _compute_extension(self):
        for record in self:
            if not record.document_ids:
                record.extension = False
                continue

            extensions = set()
            for doc in record.document_ids:
                attachment = doc.attachment_id or self.env["ir.attachment"].search(
                    [("res_model", "=", "documents.document"), ("res_id", "=", doc.id)], limit=1
                )

                if attachment:
                    file_name = attachment.name
                    if "." in file_name:
                        ext = file_name.split(".")[-1].lower().strip()
                        extensions.add(ext)
                    else:
                        extensions.add("unknown")
                else:
                    extensions.add("unknown")

            if len(extensions) == 1:
                record.extension = extensions.pop()
            else:
                record.extension = "mixed"

    @api.depends("document_ids")
    def _compute_users_rules_ids(self):
        for rec in self:
            if rec.document_ids:
                rec.users_rules_ids = self.env["onlyoffice.documents.access.user"].search(
                    [("document_id", "in", rec.document_ids.ids)]
                )
            else:
                rec.users_rules_ids = False

    @api.depends("document_ids", "folder_id", "users_rules_ids")
    def _compute_users_rules(self):
        for rec in self:
            rec.users_rules = False

            if rec.document_ids:
                target_field = "document_id"
                target_ids = rec.document_ids.ids
                total_targets = len(target_ids)
            elif rec.folder_id:
                target_field = "folder_id"
                target_ids = [rec.folder_id.id]
                total_targets = 1
            else:
                continue

            existing_access = self.env["onlyoffice.documents.access.user"].search([(target_field, "in", target_ids)])

            if not existing_access:
                continue

            user_info = {}
            for access in existing_access:
                user_id = access.user_id.id
                if user_id not in user_info:
                    user_info[user_id] = {
                        "name": access.user_id.name,
                        "roles": set(),
                        "targets_with_access": set(),
                    }
                user_info[user_id]["roles"].add(access.role)
                user_info[user_id]["targets_with_access"].add(access[target_field].id)

            rows = []
            for user_id, data in user_info.items():  # noqa: B007
                if data["targets_with_access"]:
                    if len(data["roles"]) > 1 or len(data["targets_with_access"]) < total_targets:
                        role_display = "Mixed"
                    else:
                        role_display = list(data["roles"])[0]

                    rows.append(f"""
                        <tr>
                            <td>{data["name"]}</td>
                            <td>{role_display}</td>
                        </tr>
                    """)

            if rows:
                rec.users_rules = f"""
                    <table class="table table-bordered">
                        <thead>
                            <tr>
                                <th>User</th>
                                <th>Role</th>
                            </tr>
                        </thead>
                        <tbody>
                            {"".join(rows)}
                        </tbody>
                    </table>
                """

    @api.model
    def open_advanced_share_popup(self, vals):
        is_admin = self.env.user.has_group("base.group_system")
        if is_admin:
            pass
        else:
            document_ids = vals.get("document_ids")
            documents = self.env["documents.document"].browse(document_ids[0][2])
            if any(doc.create_uid != self.env.user for doc in documents):
                raise AccessError("Only the owner or administrator can share documents.")

        vals["internal_access"] = "viewer"
        vals["link_access"] = "viewer"

        target_field = None
        target_ids = None

        document_ids = vals.get("document_ids", None)
        folder_id = vals.get("folder_id", None)
        if document_ids:
            target_field = "document_id"
            target_ids = document_ids[0][2]
        elif folder_id:
            target_field = "folder_id"
            target_ids = [folder_id]

        if target_field and target_ids:
            access = self.env["onlyoffice.documents.access"].search([(target_field, "in", target_ids)])

            if access:
                if len(target_ids) == 1:
                    vals["internal_access"] = access.internal_access
                else:
                    all_internal = []
                    for target_id in target_ids:
                        acc = access.filtered(lambda x: x[target_field].id == target_id)  # noqa: B023
                        if acc:
                            all_internal.append(acc.internal_access)
                        else:
                            all_internal.append("viewer")

                    if len(set(all_internal)) > 1:
                        vals["internal_access"] = "mixed"
                    else:
                        vals["internal_access"] = all_internal[0]

                if len(target_ids) == 1:
                    vals["link_access"] = access.link_access
                else:
                    all_link = []
                    for target_id in target_ids:
                        acc = access.filtered(lambda x: x[target_field].id == target_id)  # noqa: B023
                        if acc:
                            all_link.append(acc.link_access)
                        else:
                            all_link.append("viewer")

                    if len(set(all_link)) > 1:
                        vals["link_access"] = "mixed"
                    else:
                        vals["link_access"] = all_link[0]

        vals["default_internal_access"] = vals["internal_access"]
        vals["default_link_access"] = vals["link_access"]

        context = dict(self.env.context)
        context.update(
            {
                "default_owner_id": self.env.uid,
                "default_folder_id": vals.get("folder_id"),
                "default_tag_ids": vals.get("tag_ids"),
                "default_type": vals.get("type", "domain"),
                "default_domain": vals.get("domain") if vals.get("type", "domain") == "domain" else False,
                "default_document_ids": vals.get("document_ids", False),
                "default_internal_access": vals.get("internal_access"),
                "default_link_access": vals.get("link_access"),
            }
        )
        record = self.with_context(**context).create(vals)
        return record._get_advanced_share_popup(context, vals)

    def _get_advanced_share_popup(self, context, vals):
        form = self.env.ref("onlyoffice_odoo_documents.onlyoffice_odoo_documents_advanced_access")
        return {
            "context": context,
            "res_model": "onlyoffice.odoo.documents",
            "target": "new",
            "name": "Advanced Share",
            "res_id": self.id if self else False,
            "type": "ir.actions.act_window",
            "views": [[form.id, "form"]],
        }

    def save(self):
        access = self.env["onlyoffice.documents.access"]
        access_user = self.env["onlyoffice.documents.access.user"]

        if self.document_ids:
            target_field = "document_id"
            targets = self.document_ids
            target_ids = targets.ids
        elif self.folder_id:
            target_field = "folder_id"
            targets = self.folder_id
            target_ids = [targets.id]
        else:
            return {"type": "ir.actions.act_window_close"}

        existing_access = access.search([(target_field, "in", target_ids)])
        existing_access_user = access_user.search(
            [(target_field, "in", target_ids), ("user_id", "in", self.user_ids.ids)]
        )

        old_access_map = {acc[target_field].id: acc for acc in existing_access}

        existing_access_user.unlink()

        for target in targets:
            target_id = target.id
            old_access = old_access_map.get(target_id)

            vals = {target_field: target_id}

            if self.internal_access == "mixed":
                if old_access:
                    vals["internal_access"] = old_access.internal_access
                else:
                    vals["internal_access"] = (
                        "viewer" if not self.default_internal_access else self.default_internal_access
                    )
            else:
                vals["internal_access"] = self.internal_access

            if self.link_access == "mixed":
                if old_access:
                    vals["link_access"] = old_access.link_access
                else:
                    vals["link_access"] = "viewer" if not self.default_link_access else self.default_link_access
            else:
                vals["link_access"] = self.link_access

            if vals.get("internal_access") == "mixed":
                vals["internal_access"] = "viewer"
            if vals.get("link_access") == "mixed":
                vals["link_access"] = "viewer"

            if old_access:
                old_access.write(vals)
            else:
                access.create(vals)

        for user in self.user_ids:
            access_user_vals = {
                "user_id": user.id,
                "role": self.user_access,
            }
            if target_field == "document_id":
                for target in targets:
                    access_user_vals["document_id"] = target.id
                    access_user.create(access_user_vals)
            else:
                access_user_vals["folder_id"] = targets.id
                access_user.create(access_user_vals)

        return {"type": "ir.actions.act_window_close"}
