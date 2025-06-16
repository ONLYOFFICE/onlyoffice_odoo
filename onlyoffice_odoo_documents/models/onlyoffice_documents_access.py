from odoo import _, fields, models


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.odoo.documents.access"
    _description = "ONLYOFFICE Documents Access"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    internal_users = fields.Selection(
        [
            ("deny_access", _("Deny access")),
            ("read_only", _("Read only")),
            ("comment", _("Comment")),
            ("reviewer", _("Reviewer")),
            ("full_access", _("Full access")),
            ("form_filling", _("Form Filling")),
        ],
        default="deny_access",
        string="Internal Users Access",
    )
    link_access = fields.Selection(
        [
            ("deny_access", _("Deny access")),
            ("read_only", _("Read only")),
            ("comment", _("Comment")),
            ("reviewer", _("Reviewer")),
            ("full_access", _("Full access")),
            ("form_filling", _("Form Filling")),
        ],
        default="read_only",
        string="Link Access",
    )
