import base64
import json
import logging
import os
import time

import requests

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError
from odoo.modules import get_module_path

from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_templates.utils import pdf_utils

logger = logging.getLogger(__name__)


class OnlyOfficeTemplate(models.Model):
    _name = "onlyoffice.odoo.templates"
    _description = "ONLYOFFICE Templates"

    name = fields.Char(required=True, string="Template Name")
    template_model_id = fields.Many2one("ir.model", string="Select Model")
    template_model_name = fields.Char(string="Model Description", compute="_compute_template_model_fields", store=True)
    template_model_related_name = fields.Char("Model Description", related="template_model_id.name")
    template_model_model = fields.Char(string=" ", compute="_compute_template_model_fields", store=True)
    file = fields.Binary(string="Upload an existing template")
    hide_file_field = fields.Boolean(string="Hide File Field", default=False)
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
            old_datas = self.attachment_id.datas
            self.attachment_id.write({"datas": self.file})
            self.file = False

            if not is_pdf_form:
                self.env.cr.commit()
                converted_result = self._convert_to_form(self.attachment_id)
                if converted_result.get("error"):
                    self.attachment_id.write({"datas": old_datas})
                    self.env.cr.commit()
                    raise UserError(converted_result.get("message"))
                if converted_result.get("fileUrl"):
                    try:
                        response = requests.get(converted_result["fileUrl"], timeout=60)
                        response.raise_for_status()
                        new_datas = base64.b64encode(response.content)
                        self.attachment_id.write({"datas": new_datas})
                        self.env.cr.commit()
                    except Exception as e:
                        logger.error("Failed to download and update PDF form: %s", str(e))
                        self.attachment_id.write({"datas": old_datas})
                        self.env.cr.commit()
                        raise UserError("Failed to download converted PDF form") from e

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
        url = self._context.get("url", None)
        if isinstance(url, str) and url.startswith(("http://", "https://")) and url.endswith(".pdf"):
            try:
                response = requests.get(url)
                response.raise_for_status()

                file_content = response.content
                vals["file"] = base64.b64encode(file_content)
            except Exception as e:
                raise UserError(_("Failed to download form")) from e

        is_pdf_form = None
        if "file" in vals and vals["file"]:
            try:
                decode_file = base64.b64decode(vals["file"])
                is_pdf_form = pdf_utils.is_pdf_form(decode_file)
            except Exception as e:
                raise UserError(_("Invalid file format.")) from e
        else:
            vals["file"] = base64.encodebytes(file_utils.get_default_file_template(self.env.user.lang, "pdf"))
            is_pdf_form = True

        model = self.env["ir.model"].search([("id", "=", vals["template_model_id"])], limit=1)
        vals["template_model_name"] = model.name
        vals["template_model_model"] = model.model
        vals["mimetype"] = file_utils.get_mime_by_ext("pdf")

        datas = vals.pop("file")
        vals.pop("hide_file_field", None)
        vals.pop("datas", None)

        record = super().create(
            {
                "name": vals.get("name", "New Template"),
                "template_model_id": vals.get("template_model_id"),
                "mimetype": vals.get("mimetype", "application/pdf"),
                "template_model_name": vals.get("template_model_name", ""),
                "template_model_model": vals.get("template_model_model", ""),
            }
        )

        attachment = self.env["ir.attachment"].create(
            {
                "name": vals.get("name", record.name) + ".pdf",
                "display_name": vals.get("name", record.name),
                "mimetype": vals.get("mimetype"),
                "datas": datas,
                "res_model": self._name,
                "res_id": record.id,
            }
        )
        record.attachment_id = attachment.id

        if not is_pdf_form:
            self.env.cr.commit()
            converted_result = self._convert_to_form(attachment)
            if converted_result.get("error"):
                attachment.unlink()
                record.unlink()
                super().unlink()
                self.env.cr.commit()
                raise UserError(converted_result.get("message"))
            if converted_result.get("fileUrl"):
                try:
                    response = requests.get(converted_result["fileUrl"], timeout=60)
                    response.raise_for_status()
                    new_datas = base64.b64encode(response.content)
                    attachment.write({"datas": new_datas, "mimetype": vals.get("mimetype")})
                    self.env.cr.commit()
                except Exception as e:
                    logger.error("Failed to download and update PDF form: %s", str(e))
                    attachment.unlink()
                    record.unlink()
                    super().unlink()
                    self.env.cr.commit()
                    raise UserError("Failed to download converted PDF form") from e
        return record

    @api.model
    def _convert_to_form(self, attachment):
        jwt_header = config_utils.get_jwt_header(self.env)
        jwt_secret = config_utils.get_jwt_secret(self.env)
        public_url = config_utils.get_doc_server_public_url(self.env)
        odoo_url = config_utils.get_base_or_odoo_url(self.env)
        internal_jwt_secret = config_utils.get_internal_jwt_secret(self.env)

        oo_security_token = jwt_utils.encode_payload(self.env, {"id": self.env.user.id}, internal_jwt_secret)
        oo_security_token = (
            oo_security_token.decode("utf-8") if isinstance(oo_security_token, bytes) else oo_security_token
        )

        conversion_url = os.path.join(public_url, "ConvertService.ashx")

        payload = {
            "url": f"{odoo_url}onlyoffice/template/download/{attachment.id}?oo_security_token={oo_security_token}",
            "key": int(time.time()),
            "filetype": "pdf",
            "outputtype": "pdf",
            "pdf": {
                "form": True,
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if bool(jwt_secret):
            payload = {"payload": payload}
            token = jwt_utils.encode_payload(self.env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + token
            payload["token"] = token

        try:
            response = requests.post(conversion_url, data=json.dumps(payload), headers=headers, timeout=60)

            if response.status_code == 200:
                response_json = response.json()
                if "error" in response_json:
                    return {
                        "error": response_json.get("error"),
                        "message": self._get_conversion_error_message(response_json.get("error")),
                    }
                else:
                    return response_json
            else:
                return {
                    "error": response.status_code,
                    "message": f"Document conversion service returned status {response.status_code}",
                }
        except Exception:
            return {
                "error": 1,
                "message": "Document conversion service cannot be reached",
            }

    def _get_conversion_error_message(self, error_code):
        error_dictionary = {
            -1: "Unknown error",
            -2: "Conversion timeout error",
            -3: "Conversion error",
            -4: "Error while downloading the document file to be converted",
            -5: "Incorrect password",
            -6: "Error while accessing the conversion result database",
            -7: "Input error",
            -8: "Invalid token",
        }
        try:
            return error_dictionary[error_code]
        except Exception:
            return "Undefined error code"

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
