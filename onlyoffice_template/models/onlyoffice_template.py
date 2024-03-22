from odoo import api, models, fields
from odoo.http import request
from odoo.exceptions import UserError
import json
import re

class OnlyofficeTemplate(models.Model):
    _name = 'onlyoffice.template'
    _description = 'ONLYOFFICE Template'

    name = fields.Char(required=True, string="Template Name")
    file = fields.Binary(string="Document")
    create_uid = fields.Many2one('res.users', string="Created By", readonly=True)
    create_date = fields.Datetime("Template Create Date", readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string="Document Attachment", readonly=True)
    mimetype = fields.Char(string="Template Mimetype")


    def get_field_info(self, model_name, record_id, depth=0):
        if depth > 2:
            return 'Maximum recursion depth exceeded.'

        result = []

        if model_name not in self.env:
            return f'Model {model_name} does not exist.'

        record = self.env[model_name].browse(record_id)
        if not record.exists():
            return f'Record with ID {record_id} not found in model {model_name}.'

        for field_name, field in self.env[model_name]._fields.items():
            field_data = {
                'model': model_name,
                'name': field_name,
                'string': field.string or "",
                'type': field.type,
            }

            if field.type in ['many2one', 'one2many', 'many2many'] and field.comodel_name:
                related_records = record.mapped(field_name)
                field_data['value'] = [self.get_field_info(field.comodel_name, rec.id, depth + 1) for rec in related_records]
            elif field.type not in ['many2one', 'one2many', 'many2many']:
                field_data['value'] = record[field_name]

            result.append(field_data)

        return result

    @api.model
    def create(self, vals):
        #model_obj = self.get_field_info('sale.order', 1, 0) 

        record = super(OnlyofficeTemplate, self).create(vals)
        if vals.get('file'):
            attachment = self.env['ir.attachment'].create({
                'name': record.name,
                'mimetype': vals['mimetype'],
                'datas': vals['file'],
                'res_model': self._name,
                'res_id': record.id,
            })
            record.attachment_id = attachment.id
        return record

    def unlink(self):
        for record in self:
            if record.attachment_id:
                record.attachment_id.unlink()
        return super(OnlyofficeTemplate, self).unlink()

    @api.model
    def get_fields(self):
        '''
        all_models = self.env['ir.model'].search([])
        models_fields_info = {}
        for model in all_models:
            fields = self.env[model.model].fields_get()
            models_fields_info[model.model] = {
                field: {
                    'name': clean_text(field),
                    'string': clean_text(fields[field]['string']),
                    'type': clean_text(fields[field]['type'])
                } for field in fields
            }
        '''
        models_fields_info = {}
        fields = self.env["sale.order"].fields_get()
        models_fields_info["sale.order"] = {
            field: {
                'name': field,
                'string': clean_text(fields[field]['string']),
                'type': fields[field]['type']
            } for field in fields
        }
        result = json.dumps(models_fields_info, ensure_ascii=False)
        return result

    def action_delete_attachment(self):
        self.ensure_one()
        if self.attachment_id:
            self.attachment_id.unlink()
            self.attachment_id = False
            self.file = False 
            self.sudo().unlink()
            return
        else:
            raise UserError("No document attached to delete.")
    
def clean_text(text):
    return re.sub(r'[^a-zA-Z0-9]', ' ', text)