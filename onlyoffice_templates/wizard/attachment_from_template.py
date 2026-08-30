#   -*- coding: utf-8 -*-
#   Copyright Open2Bizz 2024

import time

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AttachmentFromtemplate(models.TransientModel):
    _name = "ir.attachment.create_templ"
    _description = "Create from template"

    template_id = fields.Many2one('ir.attachment', string="Template")
    res_model = fields.Char('Resource Model', readonly=True)
    res_id = fields.Many2oneReference(
        'Resource ID',
        model_field='res_model',
        readonly=True
    )
    icon_image = fields.Binary(string="Preview", related="template_id.icon_image")

    def create_from_template(self):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id)
        if not record:
            raise UserError(_("No record selected to add the document!"))
        name = "(" + str(self.res_id) + ") " + self.template_id.name
        copy = self.template_id.copy()
        copy.write({'res_model': self.res_model,'res_id': record.id,'name': name,'template_id':self.template_id.id})
        record.message_post(body=name,attachment_ids=[copy.id])