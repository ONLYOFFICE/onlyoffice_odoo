#
# (c) Copyright Ascensio System SIA 2024
#
import base64
import codecs
import json
import logging
import re

import requests

from odoo import http
from odoo.http import request
from odoo.tools import (
    DEFAULT_SERVER_DATE_FORMAT,
    DEFAULT_SERVER_DATETIME_FORMAT,
    file_open,
    get_lang,
)

from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

_logger = logging.getLogger(__name__)


class Onlyoffice_Inherited_Connector(Onlyoffice_Connector):
    @http.route("/onlyoffice/template/editor", auth="user", methods=["POST"], type="json", csrf=False)
    def override_render_editor(self, attachment_id, access_token=None):
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return request.not_found()

        attachment.validate_access(access_token)

        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]
        filename = data["name"]

        can_read = attachment.check_access_rights("read", raise_exception=False) and file_utils.can_view(filename)
        hasAccess = http.request.env.user.has_group("onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_admin")
        can_write = (
            hasAccess
            and attachment.check_access_rights("write", raise_exception=False)
            and file_utils.can_edit(filename)
        )

        if not can_read:
            raise Exception("cant read")

        prepare_editor_values = self.prepare_editor_values(attachment, access_token, can_write)
        return prepare_editor_values


class OnlyofficeTemplate_Connector(http.Controller):
    @http.route("/onlyoffice/template/get_filled_template", auth="user", methods=["POST"], type="json")
    def get_filled_template(self, template_id, record_id, model_name):
        jwt_secret = config_utils.get_jwt_secret(request.env)
        jwt_header = config_utils.get_jwt_header(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docbuilder_url = f"{docserver_url}docbuilder"
        internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
        oo_security_token = jwt_utils.encode_payload(request.env, {"id": request.env.user.id}, internal_jwt_secret)

        template_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        template_callback_url = f"{odoo_url}onlyoffice/template/callback/fill_template?template_id={template_id}&record_id={record_id}&model_name={model_name}&oo_security_token={oo_security_token}"  # noqa: E501
        template_payload = {"async": False, "url": template_callback_url}

        if jwt_secret:
            template_payload["token"] = jwt_utils.encode_payload(request.env, template_payload, jwt_secret)
            template_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                request.env, {"payload": template_payload}, jwt_secret
            )

        try:
            response = requests.post(docbuilder_url, json=template_payload, headers=template_headers, timeout=10)
            response.raise_for_status()
            response_json = response.json()

            if response_json.get("error"):
                return {"error": self.get_docbuilder_error(response_json.get("error"))}

            urls = response_json.get("urls")
            if urls:
                first_url = next(iter(urls.values()), None)
                if first_url:
                    return {"href": first_url}

        except requests.RequestException as e:
            return {"error": e}

        return {"error": "Unknown error"}

    @http.route("/onlyoffice/template/callback/fill_template", auth="public")
    def fill_template(self, template_id, record_id, model_name, oo_security_token):
        user = self.get_user_from_token(oo_security_token)
        if not user:
            return

        template_record = self.get_record(
            template_id, "onlyoffice.odoo.templates", self.get_user_from_token(oo_security_token)
        )
        if not template_record:
            _logger("Template not found")
            return
        attachment_id = template_record.attachment_id.id

        jwt_secret = config_utils.get_jwt_secret(request.env)
        jwt_header = config_utils.get_jwt_header(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docbuilder_url = f"{docserver_url}docbuilder"

        keys_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        keys_callback_url = f"{odoo_url}onlyoffice/template/callback/get_keys?attachment_id={attachment_id}&oo_security_token={oo_security_token}"  # noqa: E501
        keys_payload = {"async": False, "url": keys_callback_url}

        if jwt_secret:
            keys_payload["token"] = jwt_utils.encode_payload(request.env, keys_payload, jwt_secret)
            keys_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                request.env, {"payload": keys_payload}, jwt_secret
            )

        try:
            response = requests.post(docbuilder_url, json=keys_payload, headers=keys_headers, timeout=10)
            response.raise_for_status()
            response_json = response.json()

            if response_json.get("error"):
                _logger(response_json.get("error"))
                return

            urls = response_json.get("urls")
            if urls:
                first_url = next(iter(urls.values()), None)
                if first_url:
                    response = requests.get(first_url, timeout=10)
                    response.raise_for_status()

                    response_content = codecs.decode(response.content, "utf-8-sig")
                    keys = sorted(json.loads(response_content))

        except requests.RequestException as e:
            _logger(e)  # TODO
            return

        try:
            fields = self.get_fields(model_name, record_id, keys, user)
            fields_json = json.dumps(fields, ensure_ascii=False)
        except Exception as e:
            _logger(e)  # TODO
            fields_json = ""

        url = f"{config_utils.get_base_or_odoo_url(http.request.env)}onlyoffice/template/download/{attachment_id}?oo_security_token={oo_security_token}"  # noqa: E501
        docbuilder_content = f"""
            builder.OpenFile("{url}");
            var fields = {fields_json};
        """

        with file_open("onlyoffice_odoo_templates/controllers/fill_template.docbuilder", "r") as f:
            docbuilder_content = docbuilder_content + f.read()

        record = self.get_record(record_id, model_name, user)
        record_name = getattr(record, "display_name", getattr(record, "name", str(record_id)))
        template_name = getattr(template_record, "display_name", getattr(template_record, "name", "Filled Template"))
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

    @http.route("/onlyoffice/template/callback/get_keys", auth="public")
    def get_keys(self, attachment_id, oo_security_token):
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
    def download_template(self, attachment_id, oo_security_token=None):
        if request.env.user and request.env.user.id and not oo_security_token:
            internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
            oo_security_token = jwt_utils.encode_payload(request.env, {"id": request.env.user.id}, internal_jwt_secret)

        attachment = self.get_record(attachment_id, "ir.attachment", self.get_user_from_token(oo_security_token))

        attachment_name = getattr(
            attachment, "display_name", getattr(attachment, "name", f"Template - {attachment_id}.pdf")
        )

        if attachment:
            template_content = base64.b64decode(attachment.datas)
            headers = {
                "Content-Type": file_utils.get_mime_by_ext("pdf"),
                "Content-Disposition": f"attachment; filename={attachment_name}",
            }
            return request.make_response(template_content, headers)
        else:
            return request.not_found()

    def get_fields(self, model_name, record_id, keys, user):  # noqa: C901
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

        def get_related_field(model_name, record_id, keys):  # noqa: C901
            result = {}
            record = self.get_record(record_id, model_name, user)
            if not record:
                _logger("Record not found")
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
                                related_data = get_related_field(related_model, related_record_ids[0], related_keys)
                            else:
                                related_data = []
                                for record_id in related_record_ids:
                                    related_data_temp = get_related_field(related_model, record_id, related_keys)
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
                                date_format = get_lang(request.env).date_format
                                format_to_use = date_format or DEFAULT_SERVER_DATE_FORMAT
                                result[field] = str(data.strftime(format_to_use))
                            elif field_type == "datetime":
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
                    _logger(e)  # TODO
                    continue
            return result

        keys = convert_keys(keys)
        return get_related_field(model_name, record_id, keys)

    def get_record(self, record_id, model_name, user=None):
        if not isinstance(record_id, list):
            record_id = [int(record_id)]
        model_name = request.env[model_name].sudo()
        context = {"lang": request.env.context.get("lang", "en_US")}
        if user:
            model_name = model_name.with_user(user)
            context["lang"] = user.lang
            context["uid"] = user.id
        try:
            return model_name.with_context(**context).browse(record_id).exists()  # TODO: Add .sudo()
        except Exception as e:
            _logger(e)
            return None

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
