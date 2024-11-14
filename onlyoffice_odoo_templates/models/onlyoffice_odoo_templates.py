import base64
import json
import os

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.modules import get_module_path

from odoo.addons.onlyoffice_odoo.utils import file_utils
from odoo.addons.onlyoffice_odoo_templates.utils import pdf_utils


class OnlyOfficeTemplate(models.Model):
    _name = "onlyoffice.odoo.templates"
    _description = "ONLYOFFICE Templates"

    name = fields.Char(required=True, string="Template Name")
    template_model_id = fields.Many2one("ir.model", string="Select Model")
    template_model_name = fields.Char("Model Description", related="template_model_id.name")
    template_model_model = fields.Char("Model", related="template_model_id.model")
    file = fields.Binary(string="Upload an existing template")
    attachment_id = fields.Many2one("ir.attachment", readonly=True)
    mimetype = fields.Char(default="application/pdf")

    @api.onchange("name")
    def _onchange_name(self):
        if self.attachment_id:
            self.attachment_id.name = self.name + ".pdf"
            self.attachment_id.display_name = self.name

    @api.onchange("file")
    def _onchange_file(self):
        if self.file and self.create_date:  # if file exist
            decode_file = base64.b64decode(self.file)
            is_pdf_form = pdf_utils.is_pdf_form(decode_file)
            if not is_pdf_form:
                self.file = False
                raise UserError(_("Only PDF Form can be uploaded."))
            self.attachment_id.datas = self.file
            self.file = False

    @api.model
    def _create_demo_data(self):
        module_path = get_module_path(self._module)
        templates_dir = os.path.join(module_path, "data", "templates")
        if not os.path.exists(templates_dir):
            return

        model_folders = [name for name in os.listdir(templates_dir) if os.path.isdir(os.path.join(templates_dir, name))]

        installed_models = self.env["ir.model"].search([])
        installed_models_list = [(model.model, model.name) for model in installed_models]

        for model_name in model_folders:
            if any(model_name == model[0] for model in installed_models_list):
                templates_path = os.path.join(templates_dir, model_name)
                templates_name = [
                    name
                    for name in os.listdir(templates_path)
                    if os.path.isfile(os.path.join(templates_path, name)) and name.lower().endswith(".pdf")
                ]
                for template_name in templates_name:
                    template_path = os.path.join(templates_path, template_name)
                    template = open(template_path, "rb")
                    try:
                        template_data = template.read()
                        template_data = base64.encodebytes(template_data)
                        model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
                        name = template_name.rstrip(".pdf")
                        self.create(
                            {
                                "name": name,
                                "template_model_id": model.id,
                                "file": template_data,
                            }
                        )
                    finally:
                        template.close()
        return

    @api.model
    def create(self, vals):
        if vals.get("file"):
            decode_file = base64.b64decode(vals.get("file"))
            is_pdf_form = pdf_utils.is_pdf_form(decode_file)
            if not is_pdf_form:
                raise UserError(_("Only PDF Form can be uploaded."))

        file = vals.get("file") or base64.encodebytes(file_utils.get_default_file_template(self.env.user.lang, "pdf"))
        mimetype = file_utils.get_mime_by_ext("pdf")

        vals["file"] = file
        vals["mimetype"] = mimetype

        datas = vals.pop("file", None)
        record = super().create(vals)
        if datas:
            attachment = self.env["ir.attachment"].create(
                {
                    "name": vals.get("name", record.name) + ".pdf",
                    "display_name": vals.get("name", record.name),
                    "mimetype": vals.get("mimetype", ""),
                    "datas": datas,
                    "res_model": self._name,
                    "res_id": record.id,
                }
            )
            record.attachment_id = attachment.id
        return record

    @api.model
    def get_fields_for_model(self, model_name):
        processed_models = set()
        cached_models = {}

        def process_model(model_name):
            if model_name in processed_models:
                return {}

            processed_models.add(model_name)

            model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
            if not model:
                processed_models.discard(model_name)
                return {}
            description = model.name

            fields = self.env[model_name].fields_get([], attributes=("name", "type", "string", "relation"))

            form_fields = self.env[model_name].get_view()["models"]
            form_fields = form_fields[model_name]

            field_list = []
            for field_name, field_props in fields.items():
                field_type = field_props["type"]

                if field_type in ["one2many", "many2many", "many2one"] and field_name not in form_fields:
                    continue

                if field_type in ["html", "json"]:
                    continue  # TODO:

                field_dict = {
                    "name": field_name,
                    "string": field_props.get("string", ""),
                    "type": field_props["type"],
                }

                if field_type in ["one2many", "many2many", "many2one"]:
                    related_model = field_props["relation"]
                    if cached_models.get(related_model):
                        field_dict["related_model"] = {
                            "name": field_name,
                            "description": cached_models[related_model]["description"],
                            "fields": cached_models[related_model]["fields"],
                        }
                    else:
                        if field_type == "many2one":
                            related_description = self.env["ir.model"].search([("model", "=", related_model)], limit=1)
                            related_description = related_description.name
                            related_fields = self.env[related_model].fields_get(
                                [], attributes=("name", "type", "string")
                            )
                            related_form_fields = self.env[related_model].get_view()["models"]
                            related_form_fields = related_form_fields[related_model]
                            related_field_list = []
                            for related_field_name, related_field_props in related_fields.items():
                                if related_field_props["type"] in ["html", "json"]:
                                    continue  # TODO:
                                if related_field_name not in related_form_fields:
                                    continue
                                related_field_dict = {
                                    "name": related_field_name,
                                    "string": related_field_props.get("string", ""),
                                    "type": related_field_props["type"],
                                }
                                related_field_list.append(related_field_dict)
                            related_model_info = {
                                "name": field_name,
                                "description": related_description,
                                "fields": related_field_list,
                            }
                            if related_field_list:
                                field_dict["related_model"] = related_model_info
                            cached_models[related_model] = related_model_info
                        else:
                            processed_model = process_model(related_model)
                            if processed_model:
                                field_dict["related_model"] = processed_model
                                cached_models[related_model] = processed_model

                field_list.append(field_dict)

            model_info = {
                "name": model_name,
                "description": description,
                "fields": field_list,
            }

            processed_models.discard(model_name)
            return model_info

        models_info = process_model(model_name)
        data = json.dumps(models_info, ensure_ascii=False)
        return data
