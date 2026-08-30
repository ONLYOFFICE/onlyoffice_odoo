# Copyright 2024 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    def action_create_doc_template(self):
        self.ensure_one()
        model_name = 'res.partner'
        return {
            'name': _('Create Attachment'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment.create_templ',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': model_name, 'default_res_id': self.id}
        }
