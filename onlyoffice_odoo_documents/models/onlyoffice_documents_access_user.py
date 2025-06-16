from odoo import _, fields, models


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.odoo.documents.access.user"
    _description = "ONLYOFFICE Documents Access Users"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, string="User")
    role = fields.Selection(
        [
            ("deny_access", _("Deny access")),
            ("read_only", _("Read only")),
            ("comment", _("Comment")),
            ("reviewer", _("Reviewer")),
            ("full_access", _("Full access")),
            ("form_filling", _("Form Filling")),
        ],
        required=True,
        string="Access Level",
    )
