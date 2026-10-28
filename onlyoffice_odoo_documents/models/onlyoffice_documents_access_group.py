# Copyright (C) 2026 Ascensio System SIA

from odoo import fields, models


class OnlyofficeDocumentsAccessGroup(models.Model):
    _name = "onlyoffice.odoo.documents.access.group"
    _description = "ONLYOFFICE Documents Access Groups"

    document_id = fields.Many2one("documents.document", required=True, ondelete="cascade")
    group_id = fields.Many2one("res.group.functional", required=True, ondelete="cascade")
    role = fields.Selection(
        [
            ("none", "None"),
            ("view", "Viewer"),
            ("commenter", "Commenter"),
            ("reviewer", "Reviewer"),
            ("edit", "Editor"),
            ("form_filling", "Form Filling"),
            ("custom_filter", "Custom Filter"),
        ],
        required=True,
        string="Access Level",
    )
