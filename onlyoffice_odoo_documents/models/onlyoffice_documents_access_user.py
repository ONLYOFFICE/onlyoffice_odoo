from odoo import fields, models
from odoo.tools.translate import _lt


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.odoo.documents.access.user"
    _description = "ONLYOFFICE Documents Access Users"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.partner", required=True, string="User")
    role = fields.Selection(
        [
            ("none", _lt("None")),
            ("view", _lt("Viewer")),
            ("commenter", _lt("Commenter")),
            ("reviewer", _lt("Reviewer")),
            ("edit", _lt("Editor")),
            ("form_filling", _lt("Form Filling")),
            ("custom_filter", _lt("Custom Filter")),
        ],
        required=True,
        string="Access Level",
    )
