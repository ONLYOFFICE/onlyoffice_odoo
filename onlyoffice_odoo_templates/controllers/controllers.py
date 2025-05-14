#
# (c) Copyright Ascensio System SIA 2024
#
import base64
import codecs
import io
import json
import logging
import re
import time
import zipfile
from datetime import datetime
from urllib.parse import quote

import requests

from odoo import http
from odoo.http import request
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, file_open, get_lang

from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

logger = logging.getLogger(__name__)


class Onlyoffice_Inherited_Connector(Onlyoffice_Connector):
    @http.route("/onlyoffice/template/preview", type="http", auth="user")
    def preview_template(self, template_path, **kwargs):
        unique = int(time.time() * 1000)
        file_url = f"/onlyoffice/template/pdf_content/{template_path.replace('/', '_')}"
        viewer_url = f"/web/static/lib/pdfjs/web/viewer.html?unique={unique}&file={file_url}"

        return request.redirect(viewer_url)

    @http.route("/onlyoffice/template/pdf_content/<string:template_path>", type="http", auth="user")
    def get_pdf_content(self, template_path, **kwargs):
        try:
            file_content = request.env["onlyoffice.odoo.demo.templates"].get_template_content(
                template_path.replace("_", "/")
            )

            return request.make_response(
                file_content,
                headers=[
                    ("Content-Type", "application/pdf"),
                    ("Content-Disposition", 'inline; filename="preview.pdf"'),
                ],
            )
        except Exception as e:
            return request.not_found(f"Error: {str(e)}")

    @http.route("/onlyoffice/template/editor", auth="user", methods=["POST"], type="json", csrf=False)
    def override_render_editor(self, attachment_id, access_token=None):
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return request.not_found()

        attachment.validate_access(access_token)

        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]
        filename = data["name"]

        can_read = attachment.has_access("read") and file_utils.can_view(filename)
        hasAccess = http.request.env.user.has_group("onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_admin")
        can_write = hasAccess and attachment.has_access("write") and file_utils.can_edit(filename)

        if not can_read:
            raise Exception("cant read")

        prepare_editor_values = self.prepare_editor_values(attachment, access_token, can_write)
        return prepare_editor_values


class OnlyofficeTemplate_Connector(http.Controller):
    @http.route("/onlyoffice/template/fill", auth="user", type="http")
    def main(self, template_id, record_ids):
        internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
        oo_security_token = jwt_utils.encode_payload(request.env, {"id": request.env.user.id}, internal_jwt_secret)

        try:
            templates = self.fill_template(oo_security_token, record_ids, template_id)
            if len(templates) == 1:
                url = next(iter(templates.values()))
                filename = next(iter(templates))
                filename = filename.encode("ascii", "ignore").decode("ascii")
                if not filename:
                    filename = "document.pdf"
                response = requests.get(quote(url, safe="/:?=&"), timeout=120)
                if response.status_code == 200:
                    headers = [
                        ("Content-Type", "application/pdf"),
                        ("X-Content-Type-Options", "nosniff"),
                        ("Content-Length", str(len(response.content))),
                        ("Content-Disposition", f'attachment; filename="{filename}"'),
                    ]
                    return request.make_response(response.content, headers)
                else:
                    e = f"error while downloading the document file, status = {response.status_code}"
                    logger.warning(e)
                    return request.not_found()
            elif len(templates) > 1:
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                    for filename, url in templates.items():
                        response = requests.get(url, timeout=120)
                        if response.status_code == 200:
                            archive.writestr(filename, response.content)
                        else:
                            e = f"error while downloading the document file to be generated zip, status = {response.status_code}"  # noqa: E501
                            logger.warning(e)
                            return request.not_found()
                stream.seek(0)
                content = stream.read()
                stream.flush()

                filename = f"onlyoffice-templates-{datetime.now().strftime('%Y_%m_%d_%H_%M')}.zip"
                headers = [
                    ("Content-Type", "application/zip"),
                    ("X-Content-Type-Options", "nosniff"),
                    ("Content-Length", str(len(response.content))),
                    ("Content-Disposition", f'attachment; filename="{filename}"'),
                ]
                return request.make_response(content, headers)
            else:
                logger.warning("no templates found")
                logger.debug(templates)
                return request.not_found()
        except Exception as e:
            logger.warning(e)
            return request.not_found()

        logger.warning("unknown error")
        return request.not_found()

    def fill_template(self, oo_security_token, record_ids, template_id):
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docbuilder_url = f"{docserver_url}docbuilder"
        jwt_header = config_utils.get_jwt_header(request.env)
        jwt_secret = config_utils.get_jwt_secret(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        docbuilder_callback_url = f"{odoo_url}onlyoffice/template/callback/docbuilder/fill_template?oo_security_token={oo_security_token}&record_ids={record_ids}&template_id={template_id}"  # noqa: E501
        docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

        if jwt_secret:
            docbuilder_payload["token"] = jwt_utils.encode_payload(request.env, docbuilder_payload, jwt_secret)
            docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                request.env, {"payload": docbuilder_payload}, jwt_secret
            )

        try:
            if jwt_secret:
                docbuilder_response = requests.post(
                    docbuilder_url, json=docbuilder_payload, headers=docbuilder_headers, timeout=120
                )
            else:
                docbuilder_response = requests.post(docbuilder_url, json=docbuilder_payload, timeout=120)
            docbuilder_response.raise_for_status()
            docbuilder_json = docbuilder_response.json()
            if docbuilder_json.get("error"):
                e = self.get_docbuilder_error(docbuilder_json.get("error"))
                raise Exception(e)

            urls = docbuilder_json.get("urls")
            return urls
        except:
            raise

    @http.route("/onlyoffice/template/callback/docbuilder/fill_template", auth="public")
    def docbuilder_fill_template(self, oo_security_token, record_ids, template_id):
        if not oo_security_token or not record_ids or not template_id:
            logger.warning("oo_security_token or record_ids or template_id not found")
            return request.not_found()

        user = self.get_user_from_token(oo_security_token)
        if not user:
            logger.warning("user not found")
            return request.not_found()

        template = self.get_record("onlyoffice.odoo.templates", template_id, user)
        if not template:
            logger.warning("template not found")
            return request.not_found()

        attachment_id = template.attachment_id.id
        if not attachment_id:
            logger.warning("attachment_id of the template was not found")
            return request.not_found()

        model = template.template_model_model
        if not model:
            logger.warning("model of the template was not found")
            return request.not_found()

        try:
            record_ids = [int(x) for x in record_ids.split(",")]
            url = f"{config_utils.get_base_or_odoo_url(http.request.env)}onlyoffice/template/download/{attachment_id}?oo_security_token={oo_security_token}"  # noqa: E501

            docbuilder_content = ""
            docbuilder_script_content = ""
            with file_open("onlyoffice_odoo_templates/controllers/fill_template.docbuilder", "r") as f:
                docbuilder_script_content = f.read()

            keys = self.get_keys(attachment_id, oo_security_token)
            for record_id in record_ids:
                fields = self.get_fields(keys, model, record_id, user)
                fields = json.dumps(fields, ensure_ascii=False)

                docbuilder_content += f"""
                    builder.OpenFile("{url}");
                    var fields = {fields};
                """
                docbuilder_content += docbuilder_script_content

                record = self.get_record(model, record_id, user)
                record_name = getattr(record, "display_name", getattr(record, "name", str(record_id)))
                template_name = getattr(template, "display_name", getattr(template, "name", "Filled Template"))
                filename = re.sub(r"[<>:'/\\|?*\x00-\x1f]", " ", f"{template_name} - {record_name}")

                docbuilder_content += f"""
                    builder.SaveFile("pdf", "{filename}.pdf");
                    builder.CloseFile();
                """

            headers = {
                "Content-Disposition": "attachment; filename='fill_template.docbuilder'",
                "Content-Type": "text/plain",
            }

            return request.make_response(docbuilder_content, headers)

        except Exception as e:
            logger.warning(e)
            return request.not_found()

    def get_keys(self, attachment_id, oo_security_token):
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docbuilder_url = f"{docserver_url}docbuilder"
        jwt_header = config_utils.get_jwt_header(request.env)
        jwt_secret = config_utils.get_jwt_secret(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        docbuilder_callback_url = f"{odoo_url}onlyoffice/template/callback/docbuilder/get_keys?attachment_id={attachment_id}&oo_security_token={oo_security_token}"  # noqa: E501
        docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

        if jwt_secret:
            docbuilder_payload["token"] = jwt_utils.encode_payload(request.env, docbuilder_payload, jwt_secret)
            docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                request.env, {"payload": docbuilder_payload}, jwt_secret
            )

        try:
            if jwt_secret:
                docbuilder_response = requests.post(
                    docbuilder_url, json=docbuilder_payload, headers=docbuilder_headers, timeout=120
                )
            else:
                docbuilder_response = requests.post(docbuilder_url, json=docbuilder_payload, timeout=120)
            docbuilder_response.raise_for_status()
            docbuilder_json = docbuilder_response.json()
            if docbuilder_json.get("error"):
                e = self.get_docbuilder_error(docbuilder_json.get("error"))
                raise Exception(e)

            urls = docbuilder_json.get("urls")
            keys_url = urls.get("keys.txt")
            keys_response = requests.get(keys_url, timeout=120)
            keys_response.raise_for_status()
            response_content = codecs.decode(keys_response.content, "utf-8-sig")

            return json.loads(response_content)
        except:
            raise

    @http.route("/onlyoffice/template/callback/docbuilder/get_keys", auth="public")
    def docbuilder_get_keys(self, attachment_id, oo_security_token):
        if not attachment_id or not oo_security_token:
            logger.warning("attachment_id or oo_security_token not found")
            return request.not_found()

        url = f"{config_utils.get_base_or_odoo_url(http.request.env)}onlyoffice/template/download/{attachment_id}?oo_security_token={oo_security_token}"  # noqa: E501
        docbuilder_content = f"""
            builder.OpenFile("{url}");
        """

        with file_open("onlyoffice_odoo_templates/controllers/get_keys.docbuilder", "r") as f:
            docbuilder_content = docbuilder_content + f.read()

        headers = {
            "Content-Disposition": "attachment; filename='get_keys.docbuilder'",
            "Content-Type": "text/plain",
        }

        return request.make_response(docbuilder_content, headers)

    @http.route("/onlyoffice/template/download/<int:attachment_id>", auth="public")
    def download(self, attachment_id, oo_security_token):
        if not attachment_id or not oo_security_token:
            logger.warning("attachment_id or oo_security_token not found")
            return request.not_found()

        attachment = self.get_record("ir.attachment", attachment_id, self.get_user_from_token(oo_security_token))
        if attachment:
            content = base64.b64decode(attachment.datas)
            headers = {
                "Content-Type": "application/pdf",
                "Content-Disposition": "attachment; filename=template.pdf",
            }
            return request.make_response(content, headers)
        else:
            logger.warning("attachment not found")
            return request.not_found()

    def get_fields(self, keys, model, record_id, user):  # noqa: C901
        def convert_keys(input_list):
            output_dict = {}
            for item in input_list:
                if " " in item:
                    keys = item.split(" ")
                    current_dict = output_dict
                    for key in keys[:-1]:
                        current_dict = current_dict.setdefault(key, {})
                    current_dict[keys[-1]] = None
                else:
                    output_dict[item] = None

            def dict_to_list(input_dict):
                output_list = []
                for key, value in input_dict.items():
                    if isinstance(value, dict):
                        output_list.append({key: dict_to_list(value)})
                    else:
                        output_list.append(key)
                return output_list

            return dict_to_list(output_dict)

        def get_related_field(keys, model, record_id):  # noqa: C901
            result = {}
            record = self.get_record(model, record_id, user)
            if not record:
                logger.warning("Record not found")
                return
            for field in keys:
                try:
                    if isinstance(field, dict):
                        related_field = list(field.keys())[0]
                        if related_field not in record._fields:
                            continue
                        field_type = record._fields[related_field].type
                        related_keys = field[related_field]
                        if field_type in ["one2many", "many2many", "many2one"]:
                            related_model = record._fields[related_field].comodel_name
                            related_record_ids = record.read([related_field])[0][related_field]
                            if not related_record_ids:
                                continue
                            if field_type == "many2one" and isinstance(related_record_ids, tuple):
                                related_data = get_related_field(related_keys, related_model, related_record_ids[0])
                            else:
                                related_data = []
                                for record_id in related_record_ids:
                                    related_data_temp = get_related_field(related_keys, related_model, record_id)
                                    if related_data_temp:
                                        related_data.append(related_data_temp)
                            if related_data:
                                result[related_field] = related_data
                    else:
                        if field not in record._fields:
                            continue
                        field_type = record._fields[field].type
                        data = record.read([field])[0][field]
                        if field_type in ["html", "json"]:
                            continue  # TODO
                        elif field_type == "boolean":
                            result[field] = str(data).lower()
                        elif isinstance(data, tuple):
                            result[field] = str(data[1])
                        elif field_type == "binary" and isinstance(data, bytes):
                            img = re.search(r"'(.*?)'", str(data))
                            if img:
                                result[field] = img.group(1)
                        elif data:
                            if field_type in ["float", "integer", "char", "text"]:
                                result[field] = str(data)
                            elif field_type == "monetary":
                                data = f"{float(data):,.2f}"
                                currency_field_name = record._fields[field].currency_field
                                if currency_field_name:
                                    currency = getattr(record, currency_field_name).name
                                    result[field] = f"{data} {currency}" if currency else str(data)
                                else:
                                    result[field] = str(data)
                            elif field_type == "date":
                                date_format = None
                                lang = request.env["res.lang"].search([("code", "=", user.lang)], limit=1)
                                user_date_format = lang.date_format
                                if user_date_format:
                                    date_format = user_date_format
                                else:
                                    date_format = get_lang(request.env).date_format
                                format_to_use = date_format or DEFAULT_SERVER_DATE_FORMAT
                                result[field] = str(data.strftime(format_to_use))
                            elif field_type == "datetime":
                                date_format = None
                                time_format = None
                                lang = request.env["res.lang"].search([("code", "=", user.lang)], limit=1)
                                user_date_format = lang.date_format
                                user_time_format = lang.time_format
                                if user_date_format and user_time_format:
                                    date_format = user_date_format
                                    time_format = user_time_format
                                else:
                                    date_format = get_lang(request.env).date_format
                                    time_format = get_lang(request.env).time_format
                                if date_format and time_format:
                                    format_to_use = f"{date_format} {time_format}"
                                else:
                                    format_to_use = DEFAULT_SERVER_DATETIME_FORMAT
                                result[field] = str(data.strftime(format_to_use))
                            elif field_type == "selection":
                                selection = record._fields[field].selection
                                if isinstance(selection, list):
                                    result[field] = str(dict(selection).get(data))
                                else:
                                    result[field] = str(data)
                except Exception as e:
                    logger.warning(e)
                    continue
            return result

        keys = convert_keys(keys)
        return get_related_field(keys, model, record_id)

    def get_record(self, model, record_id, user=None):
        if not isinstance(record_id, list):
            record_id = [int(record_id)]
        model = request.env[model].sudo()
        context = {"lang": request.env.context.get("lang", "en_US")}
        if user:
            model = model.with_user(user)
            context["lang"] = user.lang
            context["uid"] = user.id
        try:
            return model.with_context(**context).browse(record_id).exists()  # TODO: Add .sudo()
        except Exception as e:
            logger.warning(e)
            raise

    def get_user_from_token(self, token):
        if not token:
            raise Exception("missing security token")
        user_id = jwt_utils.decode_token(request.env, token, config_utils.get_internal_jwt_secret(request.env))["id"]
        user = request.env["res.users"].sudo().browse(user_id).exists().ensure_one()
        return user

    def get_docbuilder_error(self, error_code):
        docbuilder_messages = {
            -1: "Unknown error.",
            -2: "Generation timeout error.",
            -3: "Document generation error.",
            -4: "Error while downloading the document file to be generated.",
            -6: "Error while accessing the document generation result database.",
            -8: "Invalid token.",
        }
        return docbuilder_messages.get(error_code, "Error code not recognized.")
