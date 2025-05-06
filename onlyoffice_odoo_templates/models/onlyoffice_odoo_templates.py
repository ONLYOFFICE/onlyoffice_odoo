import base64
import os

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.modules import get_module_path

from odoo.addons.onlyoffice_odoo.utils import file_utils
from odoo.addons.onlyoffice_odoo_templates.utils import pdf_utils


class OnlyOfficeTemplate(models.Model):
    _name = "onlyoffice.odoo.templates"
    _description = "ONLYOFFICE Templates"

    name = fields.Char(required=True, string="Template Name")
    template_model_id = fields.Many2one("ir.model", string="Select Model")
    template_model_name = fields.Char(string="Model Description", compute="_compute_template_model_fields", store=True)
    template_model_related_name = fields.Char("Model Description", related="template_model_id.name")
    template_model_model = fields.Char(string=" ", compute="_compute_template_model_fields", store=True)
    file = fields.Binary(string="Upload an existing template")
    attachment_id = fields.Many2one("ir.attachment", readonly=True)
    mimetype = fields.Char(default="application/pdf")

    @api.onchange("name")
    def _onchange_name(self):
        if self.attachment_id:
            self.attachment_id.name = self.name + ".pdf"
            self.attachment_id.display_name = self.name

    @api.depends("template_model_id")
    def _compute_template_model_fields(self):
        for record in self:
            if record.template_model_id:
                record.template_model_name = record.template_model_id.name
                record.template_model_model = record.template_model_id.model
            else:
                record.template_model_name = False
                record.template_model_model = False

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
        model = self.env["ir.model"].search([("id", "=", vals["template_model_id"])], limit=1)
        vals["template_model_name"] = model.name
        vals["template_model_model"] = model.model
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
    def get_fields_for_model(self, model, prefix="", parent_name="", exclude=None):
        try:
            m = self.env[model]
            fields = m.fields_get()
        except Exception:
            return []

        fields = sorted(fields.items(), key=lambda field: tools.ustr(field[1].get("string", "").lower()))
        records = []
        for field_name, field in fields:
            if exclude and field_name in exclude:
                continue
            if field.get("type") in ("properties", "properties_definition", "html", "json"):
                continue
            if not field.get("exportable", True):
                continue

            ident = prefix + ("/" if prefix else "") + field_name
            val = ident
            name = parent_name + (parent_name and "/" or "") + field["string"]
            record = {
                "id": ident,
                "string": name,
                "value": val,
                "children": False,
                "field_type": field.get("type"),
                "required": field.get("required"),
                "relation_field": field.get("relation_field"),
            }
            records.append(record)

            if len(ident.split("/")) < 4 and "relation" in field:
                ref = field.pop("relation")
                record["value"] += "/id"
                record["params"] = {"model": ref, "prefix": ident, "name": name}
                record["children"] = True

        return records

    @api.model
    def update_relationship(self, template_model_id, model):
        """
        If the module was uninstalled and reinstalled, its model id may have changed.
        Update the model id in the template record
        """
        if not template_model_id or not model:
            return

        model_id = self.sudo().env["ir.model"].search([("model", "=", model)]).id
        if not model_id:
            return

        record = self.sudo().env["onlyoffice.odoo.templates"].browse(template_model_id)
        if not record:
            return

        if record.template_model_id != model_id:
            record.template_model_id = model_id
        return
