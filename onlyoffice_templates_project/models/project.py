# Copyright 2024 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

from odoo import api, fields, models, _

class ProjectProject(models.Model):
    _inherit = "project.project"

    def action_create_doc_template(self):
        self.ensure_one()
        model_name = "project.project"
        return {
            'name': _('Create Attachment'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment.create_templ',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': model_name, 'default_res_id': self.id}
        }

class ProjectTask(models.Model):
    _inherit = "project.task"

    def action_create_doc_template(self):
        self.ensure_one()
        model_name = "project.task"
        return {
            'name': _('Create Attachment'),
            'type': 'ir.actions.act_window',
            'res_model': 'ir.attachment.create_templ',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_res_model': model_name, 'default_res_id': self.id}
        }
