# Copyright (C) 2026 Ascensio System SIA

from odoo import fields, models


class Attachment(models.Model):
    _inherit = "ir.attachment"
    oo_attachment_version = fields.Integer(default=1)
