from odoo import api, models, fields
from odoo.exceptions import UserError
import json
import re

class OnlyofficeTemplate(models.Model):
    _name = 'onlyoffice.template'
    _description = 'ONLYOFFICE Template'

    name = fields.Char(required=True, string="Template Name")
    file = fields.Binary(string="Document")
    create_date = fields.Datetime("Template Create Date", readonly=True)
    user_id = fields.Many2one('res.users', string="Created By", readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string="Document Attachment", readonly=True)
    mimetype = fields.Char(string="Template Mimetype")

    @api.model
    def create(self, vals):
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

    def write(self, vals):
        if 'file' in vals:
            for record in self:
                if record.attachment_id:
                    record.attachment_id.unlink()
                attachment = self.env['ir.attachment'].create({
                    'name': vals.get('name', record.name),
                    'datas': vals['file'],
                    'res_model': self._name,
                    'res_id': record.id,
                })
                vals['attachment_id'] = attachment.id
        return super(OnlyofficeTemplate, self).write(vals)

    def unlink(self):
        for record in self:
            if record.attachment_id:
                record.attachment_id.unlink()
        return super(OnlyofficeTemplate, self).unlink()

    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError("No document attached to download.")
        url = '/web/content/%s?download=true' % (self.attachment_id.id)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }

    @api.model
    def get_parameter(self):
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
        fields = self.env["ir.attachment"].fields_get()
        models_fields_info["ir.attachment"] = {
            field: {
                'name': clean_text(field),
                'string': clean_text(fields[field]['string']),
                'type': clean_text(fields[field]['type'])
            } for field in fields
        }
        result = json.dumps(models_fields_info, ensure_ascii=False)
        return result
    
    '''
    @api.model
    def action_download(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError("No document attached to download.")
        url = '/web/content/%s?download=true' % (self.attachment_id.id)
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'self',
        }
    '''

    def action_delete_attachment(self):
        self.ensure_one()
        if self.attachment_id:
            self.attachment_id.unlink()
            self.attachment_id = False
            self.file = False 
            self.sudo().unlink()
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        else:
            raise UserError("No document attached to delete.")
    
def clean_text(text):
    # Заменяем все неалфавитно-цифровые символы на пустую строку
    return re.sub(r'[^a-zA-Z0-9]', '', text)