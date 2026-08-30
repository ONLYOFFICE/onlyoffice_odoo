# Copyright 2013-2020 Open2Bizz <info@open2bizz.nl>
# License LGPL-3
import base64
import odoo

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from odoo.modules import get_module_path

class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    is_template = fields.Boolean("Is a template", default=False, copy=False)
    template_id = fields.Many2one("ir.attachment",string="Template")
    template_model_id = fields.Many2one("ir.model",string="Template for Model")
    template_model = fields.Char("Templ Model Name", related="template_model_id.model")
    icon_image = fields.Binary(string='Preview')

    # TODO: add static preview image on form just like:
    # https://github.com/odoo/odoo/blob/b95edd874ce904ef231c295790a003992db002e3/addons/web/static/src/scss/mimetypes.scss#L32

    def set_icon_image(self):
        self.ensure_one()
        if not self.icon_image:
            mimetype = self.mimetype
            mod_path = get_module_path("onlyoffice_templates")
            base_path = mod_path + "/static/img/"
            if 'wordprocess' in mimetype:
                path = base_path + 'document.svg'
            elif 'spreadsheet' in mimetype:
                path = base_path + 'spreadsheet.svg'
            elif 'presentation' in mimetype:
                path = base_path + 'presentation.svg'
            else:
                path = base_path + 'unknown.svg'
            with tools.file_open(path, 'rb') as image_file:
                icon_image = base64.b64encode(image_file.read())
            if icon_image:
                self.write({'icon_image': icon_image})

    @api.model_create_multi
    def create(self, vals_list):
        attachment = super(IrAttachment, self).create(vals_list)
        if attachment.is_template and not attachment.icon_image:
            attachment.set_icon_image()
            attachment.type = 'binary'
        return attachment