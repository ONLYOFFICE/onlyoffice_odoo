# Copyright (C) 2026 Ascensio System SIA
# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import base64
import json
import logging
import os
import time

from odoo import api, fields, models
from odoo.exceptions import UserError

from odoo.addons.onlyoffice_odoo.controllers.controllers import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils
from odoo.addons.onlyoffice_odoo_templates.utils import pdf_utils

_logger = logging.getLogger(__name__)


class OnlyOfficeTemplate(models.Model):
  _name = 'onlyoffice.odoo.templates'
  _description = 'ONLYOFFICE Templates'

  name = fields.Char(
    required=True,
    string='Template Name',
  )
  template_model_id = fields.Many2one(
    comodel_name='ir.model',
    string='Select Model',
  )
  template_model_name = fields.Char(
    string='Model Description',
    compute='_compute_template_model_fields',
    store=True,
  )
  template_model_related_name = fields.Char(
    string='Model Description',
    related='template_model_id.name',
  )
  template_model_model = fields.Char(
    string=' ',
    compute='_compute_template_model_fields',
    store=True,
  )
  file = fields.Binary(
    string='Upload an existing template',
  )
  hide_file_field = fields.Boolean(
    string='Hide File Field',
    default=False,
  )
  attachment_id = fields.Many2one(
    comodel_name='ir.attachment',
    readonly=True,
  )
  mimetype = fields.Char(
    default='application/pdf',
  )
  report_id = fields.Many2one(
    comodel_name='ir.actions.report',
    string='Related Report',
    copy=False,
  )

  @api.onchange('name')
  def _onchange_name(self):
    if self.attachment_id:
      self.attachment_id.name = f'{self.name}.pdf'
      self.attachment_id.display_name = self.name

  @api.depends('template_model_id')
  def _compute_template_model_fields(self):
    for record in self:
      if record.template_model_id:
        record.template_model_name = record.template_model_id.name
        record.template_model_model = record.template_model_id.model
      else:
        record.template_model_name = False
        record.template_model_model = False

  @api.onchange('file')
  def _onchange_file(self):
    if self.file and self.create_date:
      decode_file = base64.b64decode(self.file)
      is_pdf_form = pdf_utils.is_pdf_form(decode_file)
      old_datas = self.attachment_id.datas
      self.attachment_id.write({'datas': self.file})
      self.file = False
      if not is_pdf_form:
        converted_result = self._convert_to_form(self.attachment_id)
        if converted_result.get('error'):
          self.attachment_id.write({'datas': old_datas})
          raise UserError(converted_result.get('message'))
        if converted_result.get('fileUrl'):
          try:
            response = onlyoffice_request(
              url=converted_result['fileUrl'],
              method='get',
            )
            new_datas = base64.b64encode(response.content)
            self.attachment_id.write({'datas': new_datas})
          except Exception as e:
            _logger.error('Failed to download and update PDF form: %s', str(e))
            self.attachment_id.write({'datas': old_datas})
            raise UserError(self.env._('Failed to download converted PDF form')) from e

  @api.model
  def _create_demo_data(self):
    demo_templates = self.env['onlyoffice.odoo.demo.templates']
    structure = demo_templates._get_template_structure()
    vals_list = []
    for model_name, model_data in structure.items():
      model = self.env['ir.model'].search([('model', '=', model_name)], limit=1)
      if not model:
        continue
      for file_info in model_data['files']:
        name = os.path.splitext(file_info['name'])[0]
        try:
          content = demo_templates.get_template_content(file_info['path'])
          vals_list.append({
            'name': name,
            'template_model_id': model.id,
            'file': base64.b64encode(content),
          })
        except (ValueError, FileNotFoundError, OSError) as e:
          _logger.error('Failed to process template %s: %s', file_info['path'], str(e))
          continue
    if vals_list:
      self.create(vals_list)

  @api.model_create_multi
  def create(self, vals_list):
    create_vals = []
    extra_data = []
    for vals in vals_list:
      url = self.env.context.get('url')
      if isinstance(url, str) and url.startswith(('http://', 'https://')) and url.endswith('.pdf'):
        try:
          response = onlyoffice_request(url=url, method='get')
          vals['file'] = base64.b64encode(response.content)
        except Exception as e:
          raise UserError(self.env._('Failed to download form')) from e
      is_pdf_form = None
      if vals.get('file'):
        try:
          decode_file = base64.b64decode(vals['file'])
          is_pdf_form = pdf_utils.is_pdf_form(decode_file)
        except Exception as e:
          raise UserError(self.env._('Invalid file format.')) from e
      else:
        default_file = file_utils.get_default_file_template(self.env.user.lang, 'pdf')
        vals['file'] = base64.b64encode(default_file)
        is_pdf_form = True

      if vals.get('template_model_id'):
        model = self.env['ir.model'].browse(vals['template_model_id'])
        vals['template_model_name'] = model.name if model.exists() else ''
        vals['template_model_model'] = model.model if model.exists() else ''
      vals['mimetype'] = file_utils.get_mime_by_ext('pdf')
      datas = vals.pop('file', None)
      vals.pop('hide_file_field', None)
      vals.pop('datas', None)
      vals['name'] = vals.get('name', 'New Template')
      create_vals.append(vals)
      extra_data.append({
        'datas': datas,
        'is_pdf_form': is_pdf_form,
        'original_vals': vals.copy()
      })
    records = super().create(create_vals)
    for record, extra in zip(records, extra_data):
      orig_vals = extra['original_vals']
      display_name = orig_vals.get('name', record.name)
      attachment = self.env['ir.attachment'].create({
        'name': f'{display_name}.pdf',
        'display_name': display_name,
        'mimetype': orig_vals.get('mimetype', 'application/pdf'),
        'datas': extra['datas'],
        'res_model': self._name,
        'res_id': record.id,
      })
      record.attachment_id = attachment.id
      if not extra['is_pdf_form']:
        converted_result = self._convert_to_form(attachment)
        if converted_result.get('error'):
          attachment.unlink()
          record.unlink()
          raise UserError(converted_result.get('message'))
        if converted_result.get('fileUrl'):
          try:
            response = onlyoffice_request(
              url=converted_result['fileUrl'],
              method='get',
            )
            new_datas = base64.b64encode(response.content)
            attachment.write({'datas': new_datas, 'mimetype': orig_vals.get('mimetype')})
          except Exception as e:
            _logger.error('Failed to download and update PDF form: %s', str(e))
            attachment.unlink()
            record.unlink()
            raise UserError(self.env._('Failed to download converted PDF form')) from e
    return records

  @api.model
  def _convert_to_form(self, attachment):
    jwt_header = config_utils.get_jwt_header(self.env)
    jwt_secret = config_utils.get_jwt_secret(self.env)
    docserver_url = config_utils.get_doc_server_public_url(self.env)
    docserver_url = url_utils.replace_public_url_to_internal(self.env, docserver_url)
    odoo_url = config_utils.get_base_or_odoo_url(self.env)
    internal_jwt_secret = config_utils.get_internal_jwt_secret(self.env)
    oo_security_token = jwt_utils.encode_payload(self.env, {'id': self.env.user.id}, internal_jwt_secret)
    if isinstance(oo_security_token, bytes):
      oo_security_token = oo_security_token.decode('utf-8')
    key = int(time.time())
    conversion_url = os.path.join(docserver_url, 'converter', f'?shardkey={key}')
    payload = {
      'url': f'{odoo_url}onlyoffice/template/download/{attachment.id}?oo_security_token={oo_security_token}',
      'key': key,
      'filetype': 'pdf',
      'outputtype': 'pdf',
      'pdf': {
        'form': True,
      },
    }
    headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    }
    if jwt_secret:
      payload = {'payload': payload}
      token = jwt_utils.encode_payload(self.env, payload, jwt_secret)
      headers[jwt_header] = f'Bearer {token}'
      payload['token'] = token
    try:
      response = onlyoffice_request(
        url=conversion_url,
        method='post',
        opts={
          'data': json.dumps(payload),
          'headers': headers,
        },
      )
      if response.status_code == 200:
        response_json = response.json()
        if 'error' in response_json:
          return {
            'error': response_json.get('error'),
            'message': self._get_conversion_error_message(response_json.get('error')),
          }
        return response_json
      return {
        'error': response.status_code,
        'message': f'Document conversion service returned status {response.status_code}',
      }
    except Exception:
      return {
        'error': 1,
        'message': 'Document conversion service cannot be reached',
      }

  def _get_conversion_error_message(self, error_code):
    error_dictionary = {
      -1: 'Unknown error',
      -2: 'Conversion timeout error',
      -3: 'Conversion error',
      -4: 'Error while downloading the document file to be converted',
      -5: 'Incorrect password',
      -6: 'Error while accessing the conversion result database',
      -7: 'Input error',
      -8: 'Invalid token',
    }
    return error_dictionary.get(error_code, 'Undefined error code')

  @api.model
  def get_fields_for_model(self, model, prefix='', parent_name='', exclude=None):
    try:
      m = self.env[model]
      fields_dict = m.fields_get()
    except Exception:
      return []
    fields_items = sorted(fields_dict.items(), key=lambda field: str(field[1].get('string', '')).lower())
    records = []
    for field_name, field in fields_items:
      if exclude and field_name in exclude:
        continue
      if field.get('type') in ('properties', 'properties_definition', 'html', 'json'):
        continue
      if not field.get('exportable', True):
        continue
      ident = f'{prefix}/{field_name}' if prefix else field_name
      name = f"{parent_name}/{field['string']}" if parent_name else field['string']
      record = {
        'id': ident,
        'string': name,
        'value': ident,
        'children': False,
        'field_type': field.get('type'),
        'required': field.get('required'),
        'relation_field': field.get('relation_field'),
      }
      records.append(record)
      if len(ident.split('/')) < 4 and 'relation' in field:
        ref = field.pop('relation')
        record['value'] += '/id'
        record['params'] = {'model': ref, 'prefix': ident, 'name': name}
        record['children'] = True
    return records

  def open_template_editor(self):
    self.ensure_one()
    return {
      'type': 'ir.actions.client',
      'tag': 'onlyoffice_template_editor',
      'target': 'current',
      'params': {
        'attachment_id': self.attachment_id.id,
        'id': self.id,
        'template_model_model': self.template_model_model,
      },
    }

  @api.model
  def update_relationship(self, template_model_id, model):
    if not template_model_id or not model:
      return
    model_record = self.env['ir.model'].sudo().search([('model', '=', model)], limit=1)
    if not model_record:
      return
    record = self.env['onlyoffice.odoo.templates'].sudo().browse(template_model_id)
    if record.exists() and record.template_model_id.id != model_record.id:
      record.template_model_id = model_record.id

  def create_action(self):
    reports_vals = []
    for template in self:
      if not template.report_id:
        reports_vals.append({
          'name': f'{template.name} Print (ONLYOFFICE)',
          'report_type': 'onlyoffice-pdf',
          'report_name': template.name,
          'onlyoffice_template_id': template.id,
          'model': template.template_model_id.model,
          'binding_model_id': template.template_model_id.id,
        })
    if reports_vals:
      reports = self.env['ir.actions.report'].create(reports_vals)
      templates_without_report = self.filtered(lambda t: not t.report_id)
      for template, report in zip(templates_without_report, reports):
        template.report_id = report.id

  def unlink_action(self):
    self.mapped('report_id').unlink()

  def associated_report(self):
    self.ensure_one()
    if self.report_id:
      return {
        'name': 'Associated Report',
        'type': 'ir.actions.act_window',
        'res_model': 'ir.actions.report',
        'res_id': self.report_id.id,
        'view_mode': 'form',
      }
    return {'type': 'ir.actions.act_window_close'}
