from odoo import _, fields, models


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.odoo.documents.access"
    _description = "ONLYOFFICE Documents Access"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    internal_users = fields.Selection(
        [
            ("none", _("None")),
            ("view", _("Viewer")),
            ("commenter", _("Commenter")),
            ("reviewer", _("Reviewer")),
            ("edit", _("Editor")),
            ("form_filling", _("Form Filling")),
            ("custom_filter", _("Custom Filter")),
        ],
        default="none",
        string="Internal Users Access",
    )
    link_access = fields.Selection(
        [
            ("none", _("None")),
            ("view", _("Viewer")),
            ("commenter", _("Commenter")),
            ("reviewer", _("Reviewer")),
            ("edit", _("Editor")),
            ("form_filling", _("Form Filling")),
            ("custom_filter", _("Custom Filter")),
        ],
        default="view",
        string="Link Access",
    )
