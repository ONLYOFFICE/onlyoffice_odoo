# Copyright (C) 2026 Ascensio System SIA

from odoo import _, fields, models


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.odoo.documents.access.user"
    _description = "ONLYOFFICE Documents Access Users"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    user_id = fields.Many2one("res.users", required=True, string="User")
    role = fields.Selection(
        [
            ("none", _("None")),
            ("viewer", _("Viewer")),
            ("commenter", _("Commenter")),
            ("reviewer", _("Reviewer")),
            ("editor", _("Editor")),
            ("form_filling", _("Form Filling")),
            ("custom_filter", _("Custom Filter")),
        ],
        required=True,
        string="Access Level",
    )
