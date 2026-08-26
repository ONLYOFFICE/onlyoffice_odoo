# Copyright (C) 2026 Ascensio System SIA
# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

import base64
import json
import logging
import os

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, conversion_utils, file_utils, jwt_utils, url_utils
from odoo.addons.onlyoffice_odoo_templates.utils import keys_utils, pdf_utils

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
    hide_file_field = fields.Boolean(string="Hide File Field", default=False)  # pylint: disable=attribute-string-redundant
    attachment_id = fields.Many2one("ir.attachment", readonly=True)
    mimetype = fields.Char(default="application/pdf")
    # Cached PDF Form field keys for the template PDF, stored as a JSON list.
    # The keys depend only on the attachment contents (not on the records
    # being filled), so they are eagerly (re)computed and cached here whenever
    # the underlying PDF changes -- see IrAttachment.write/create overrides in
    # ir_attachment.py, which call ``_update_field_keys`` below. This avoids
    # an extra synchronous docbuilder round-trip on every fill.
    field_keys = fields.Text(string="Cached form field keys", readonly=True, copy=False)
    report_id = fields.Many2one("ir.actions.report", string="Related Report", copy=False)

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
                self.env.cr.commit()  # pylint: disable=invalid-commit
                converted_result = self._convert_to_form(self.attachment_id)
                if converted_result.get("error"):
                    self.attachment_id.write({"datas": old_datas})
                    self.env.cr.commit()  # pylint: disable=invalid-commit
                    raise UserError(converted_result.get("message"))
                if converted_result.get("fileUrl"):
                    try:
                        response = onlyoffice_request(
                            url=converted_result["fileUrl"],
                            method="get",
                            env=self.env,
                        )
                        new_datas = base64.b64encode(response.content)
                        self.attachment_id.write({"datas": new_datas})
                        self.env.cr.commit()  # pylint: disable=invalid-commit
                    except Exception as e:
                        logger.error("Failed to download and update PDF form: %s", str(e))
                        self.attachment_id.write({"datas": old_datas})
                        self.env.cr.commit()  # pylint: disable=invalid-commit
                        raise UserError(_("Failed to download converted PDF form")) from e

    @api.model
    def _create_demo_data(self):
        demo_templates = self.env["onlyoffice.odoo.demo.templates"]
        structure = demo_templates._get_template_structure()

        for model_name, model_data in structure.items():
            model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
            if not model:
                continue

            for file_info in model_data["files"]:
                name = os.path.splitext(file_info["name"])[0]

                try:
                    content = demo_templates.get_template_content(file_info["path"])
                except (ValueError, FileNotFoundError, OSError) as e:
                    logger.error("Failed to process template %s: %s", file_info["path"], str(e))
                    continue

                self.with_context(skip_field_keys_refresh=True).create(
                    {
                        "name": name,
                        "template_model_id": model.id,
                        "file": base64.encodebytes(content),
                    }
                )

    @api.model
    def create(self, vals):
        url = self._context.get("url", None)
        if isinstance(url, str) and url.startswith(("http://", "https://")) and url.endswith(".pdf"):
            try:
                response = onlyoffice_request(
                    url=url,
                    method="get",
                    env=self.env,
                )

                file_content = response.content
                vals["file"] = base64.b64encode(file_content)
            except Exception as e:
                raise UserError(_("Failed to download form")) from e

        is_pdf_form = None
        if vals.get("file"):
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
            self.env.cr.commit()  # pylint: disable=invalid-commit
            converted_result = self._convert_to_form(attachment)
            if converted_result.get("error"):
                attachment.unlink()
                record.unlink()
                super().unlink()
                self.env.cr.commit()  # pylint: disable=invalid-commit
                raise UserError(converted_result.get("message"))
            if converted_result.get("fileUrl"):
                try:
                    response = onlyoffice_request(
                        url=converted_result["fileUrl"],
                        method="get",
                        env=self.env,
                    )
                    new_datas = base64.b64encode(response.content)
                    attachment.write({"datas": new_datas, "mimetype": vals.get("mimetype")})
                    self.env.cr.commit()  # pylint: disable=invalid-commit
                except Exception as e:
                    logger.error("Failed to download and update PDF form: %s", str(e))
                    attachment.unlink()
                    record.unlink()
                    super().unlink()
                    self.env.cr.commit()  # pylint: disable=invalid-commit
                    raise UserError(_("Failed to download converted PDF form")) from e
        return record

    @api.model
    def _convert_to_form(self, attachment):
        jwt_header = config_utils.get_jwt_header(self.env)
        jwt_secret = config_utils.get_jwt_secret(self.env)
        docserver_url = config_utils.get_doc_server_public_url(self.env)
        docserver_url = url_utils.replace_public_url_to_internal(self.env, docserver_url)

        odoo_url = config_utils.get_base_or_odoo_url(self.env)
        internal_jwt_secret = config_utils.get_internal_jwt_secret(self.env)

        oo_security_token = jwt_utils.encode_payload(self.env, {"id": self.env.user.id}, internal_jwt_secret)
        oo_security_token = (
            oo_security_token.decode("utf-8") if isinstance(oo_security_token, bytes) else oo_security_token
        )

        source_url = f"{odoo_url}onlyoffice/template/download/{attachment.id}?oo_security_token={oo_security_token}"
        body_json = conversion_utils.build_conversion_body(
            source_url, "pdf", "pdf", extra_options={"pdf": {"form": True}}
        )
        conversion_url = os.path.join(docserver_url, "converter", f"?shardkey={body_json['key']}")
        body_json, headers = conversion_utils.sign_conversion_request(self.env, body_json, jwt_secret, jwt_header)

        try:
            response = onlyoffice_request(
                url=conversion_url,
                method="post",
                opts={
                    "data": json.dumps(body_json),
                    "headers": headers,
                },
                env=self.env,
            )
        except Exception:
            return {
                "error": 1,
                "message": "Document conversion service cannot be reached",
            }

        return conversion_utils.parse_conversion_response(response)

    def _update_field_keys(self, attachment=None):
        """Refresh the cached OFORM field keys for this template.

        Called by ``IrAttachment.create``/``write`` (see ir_attachment.py)
        whenever the template's PDF attachment is created or its content
        changes -- covers new uploads, re-uploads, form conversion, and
        ONLYOFFICE editor saves. Only PDF forms have fillable fields, so a
        non-form PDF simply clears the cache instead of querying docbuilder.
        """
        self.ensure_one()
        attachment = attachment or self.attachment_id
        if not attachment or not attachment.datas:
            self.sudo().write({"field_keys": False})
            return

        try:
            content = base64.b64decode(attachment.datas)
        except Exception as e:
            logger.warning("_update_field_keys - invalid attachment data for template %s: %s", self.id, str(e))
            self.sudo().write({"field_keys": False})
            return

        if not pdf_utils.is_pdf_form(content):
            self.sudo().write({"field_keys": False})
            return

        try:
            keys = self._fetch_field_keys(attachment.id)
            self.sudo().write({"field_keys": json.dumps(keys)})
            logger.info("_update_field_keys - cached %s keys for template %s", len(keys), self.id)
        except Exception as e:
            logger.warning("_update_field_keys - failed to fetch keys for template %s: %s", self.id, str(e))

    def _fetch_field_keys(self, attachment_id):
        internal_jwt_secret = config_utils.get_internal_jwt_secret(self.env)
        oo_security_token = jwt_utils.encode_payload(self.env, {"id": self.env.user.id}, internal_jwt_secret)
        oo_security_token = (
            oo_security_token.decode("utf-8") if isinstance(oo_security_token, bytes) else oo_security_token
        )
        return keys_utils.fetch_field_keys(self.env, attachment_id, oo_security_token)

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

    def open_template_editor(self):
        """
        Open ONLYOFFICE template editor for this record
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "onlyoffice_template_editor",
            "target": "current",
            "params": {
                "attachment_id": self.attachment_id.id,
                "id": self.id,
                "template_model_model": self.template_model_model,
            },
        }

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

    def create_action(self):
        """Create associated report action for this template"""
        for template in self:
            if not template.report_id:
                report = self.env["ir.actions.report"].create(
                    {
                        "name": f"{template.name} Print (ONLYOFFICE)",
                        "report_type": "onlyoffice-pdf",
                        "report_name": template.name,
                        "onlyoffice_template_id": template.id,
                        "model": template.template_model_id.model,
                        "binding_model_id": template.template_model_id.id,
                    }
                )
                template.report_id = report.id

    def unlink_action(self):
        """Remove associated report action"""
        for template in self:
            if template.report_id:
                template.report_id.unlink()

    def associated_report(self):
        """Open associated report form"""
        self.ensure_one()
        if self.report_id:
            return {
                "name": "Associated Report",
                "type": "ir.actions.act_window",
                "res_model": "ir.actions.report",
                "res_id": self.report_id.id,
                "view_mode": "form",
            }
        else:
            return {
                "type": "ir.actions.act_window_close",
            }
