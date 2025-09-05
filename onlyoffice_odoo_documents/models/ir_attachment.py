from odoo import fields, models


class Attachment(models.Model):
    _inherit = "ir.attachment"

    oo_attachment_version = fields.Integer(default=1)
