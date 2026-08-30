# Copyright 2024 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

from odoo import api, fields, models, _

class SaleOrder(models.Model):
    _inherit = "sale.order"

    def action_create_doc_template(self):
        self.ensure_one()
        model_name = "sale.order"
        return {
            'name': _('Create Attachment'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment.create_templ',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': model_name, 'default_res_id': self.id}
        }

class Lead(models.Model):
    _inherit = "crm.lead"

    def action_create_doc_template(self):
        self.ensure_one()
        model_name = "crm.lead"
        return {
            'name': _('Create Attachment'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment.create_templ',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': model_name, 'default_res_id': self.id}
        }
