# Copyright (C) 2026 Ascensio System SIA
import base64
import codecs
import io
import json
import logging
import re
import zipfile
from datetime import datetime
from urllib.parse import quote

from odoo import http
from odoo.http import request
from odoo.tools import (
    file_open,
    misc,
)

from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector, onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils
from odoo.addons.onlyoffice_odoo_templates.utils import config_utils as templates_config_utils

logger = logging.getLogger(__name__)


class Onlyoffice_Inherited_Connector(Onlyoffice_Connector):
    @http.route("/onlyoffice/template/template_content/<string:path>", auth="public")
    def get_template_content(self, path):
        try:
            file_content = request.env["onlyoffice.odoo.demo.templates"].get_template_content(path.replace("_", "/"))

            return request.make_response(
                file_content,
                headers=[
                    ("Content-Type", "application/pdf"),
                    ("Content-Disposition", 'inline; filename="preview.pdf"'),
                ],
            )
        except Exception as e:
            return request.not_found(f"Error: {str(e)}")

    @http.route("/onlyoffice/template/editor", auth="user", methods=["POST"], type="jsonrpc", csrf=False)
    def override_render_editor(self, attachment_id, access_token=None):
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return request.not_found()

        attachment._can_return_content(access_token=access_token)

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
        logger.info("GET /onlyoffice/template/fill - template: %s, records: %s", template_id, record_ids)
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
                response = onlyoffice_request(url=quote(url, safe="/:?=&"), method="get")
                if response.status_code == 200:
                    headers = [
                        ("Content-Type", "application/pdf"),
                        ("X-Content-Type-Options", "nosniff"),
                        ("Content-Length", str(len(response.content))),
                        ("Content-Disposition", f'attachment; filename="{filename}"'),
                    ]
                    logger.info("GET /onlyoffice/template/fill - returning single PDF: %s", filename)
                    return request.make_response(response.content, headers)
                else:
                    e = f"error while downloading the document file, status = {response.status_code}"
                    logger.warning(e)
                    return request.not_found()
            elif len(templates) > 1:
                logger.info("GET /onlyoffice/template/fill - creating ZIP with %s files", len(templates))
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                    for filename, url in templates.items():
                        response = onlyoffice_request(url=url, method="get")
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
                logger.info("GET /onlyoffice/template/fill - returning ZIP: %s", filename)
                return request.make_response(content, headers)
            else:
                logger.warning("no templates found")
                logger.debug(templates)
                return request.not_found()
        except Exception as e:
            logger.warning(e)
            return request.not_found()

        return request.not_found()

    def fill_template(self, oo_security_token, record_ids, template_id):
        logger.info("fill_template - template: %s, records: %s", template_id, record_ids)
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docserver_url = url_utils.replace_public_url_to_internal(request.env, docserver_url)
        docbuilder_url = f"{docserver_url}docbuilder"
        jwt_header = config_utils.get_jwt_header(request.env)
        jwt_secret = config_utils.get_jwt_secret(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        docbuilder_callback_url = f"{odoo_url}onlyoffice/template/callback/docbuilder/fill_template?oo_security_token={oo_security_token}&record_ids={record_ids}&template_id={template_id}"  # noqa: E501
        docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

        logger.info("fill_template - docserver_url: %s", docserver_url)
        logger.info("fill_template - jwt_enabled: %s", bool(jwt_secret))

        if jwt_secret:
            docbuilder_payload["token"] = jwt_utils.encode_payload(request.env, docbuilder_payload, jwt_secret)
            docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                request.env, {"payload": docbuilder_payload}, jwt_secret
            )

        try:
            if jwt_secret:
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                        "headers": docbuilder_headers,
                    },
                )
            else:
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                    },
                )
            docbuilder_json = docbuilder_response.json()
            if docbuilder_json.get("error"):
                e = self.get_docbuilder_error(docbuilder_json.get("error"))
                logger.warning("fill_template - docbuilder error: %s", e)
                raise Exception(e)

            urls = docbuilder_json.get("urls")
            logger.info("fill_template - success, got %s URLs", len(urls) if urls else 0)
            return urls
        except Exception as e:
            logger.warning("fill_template - error: %s", str(e))
            raise

    @http.route("/onlyoffice/template/callback/docbuilder/fill_template", auth="public")
    def docbuilder_fill_template(self, oo_security_token, record_ids, template_id):
        logger.info(
            "GET /onlyoffice/template/callback/docbuilder/fill_template - template: %s, records: %s",
            template_id,
            record_ids,
        )
        if not oo_security_token or not record_ids or not template_id:
            logger.warning("oo_security_token or record_ids or template_id not found")
            return request.not_found()

        user = self.get_user_from_token(oo_security_token)
        if not user:
            logger.warning("user not found")
            return request.not_found()

        template = self.get_record("onlyoffice.odoo.templates", template_id, user)
        if not template:
            logger.warning("template not found: %s", template_id)
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
            logger.info(
                "GET /onlyoffice/template/callback/docbuilder/fill_template - processing %s records", len(record_ids)
            )
            url = f"{config_utils.get_base_or_odoo_url(http.request.env)}onlyoffice/template/download/{attachment_id}?oo_security_token={oo_security_token}"  # noqa: E501

            docbuilder_content = ""
            docbuilder_script_content = ""
            with file_open("onlyoffice_odoo_templates/controllers/fill_template.docbuilder", "r") as f:
                docbuilder_script_content = f.read()

            keys = self.get_keys(attachment_id, oo_security_token)
            logger.info(
                "GET /onlyoffice/template/callback/docbuilder/fill_template - got %s keys", len(keys) if keys else 0
            )
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

                editable_form_fields = templates_config_utils.get_editable_form_fields(http.request.env)
                if editable_form_fields:
                    docbuilder_content += f"""
                        builder.SaveFile("pdf",  "{filename}.pdf", "<m_sJsonParams>{{&quot;isPrint&quot;:true}}</m_sJsonParams>")
                        builder.CloseFile();
                    """  # noqa: E501
                else:
                    docbuilder_content += f"""
                        builder.SaveFile("pdf", "{filename}.pdf");
                        builder.CloseFile();
                    """

            headers = {
                "Content-Disposition": "attachment; filename='fill_template.docbuilder'",
                "Content-Type": "text/plain",
            }

            logger.info("GET /onlyoffice/template/callback/docbuilder/fill_template - success")
            return request.make_response(docbuilder_content, headers)

        except Exception as e:
            logger.warning(e)
            return request.not_found()

    def get_keys(self, attachment_id, oo_security_token):
        logger.info("get_keys - attachment: %s", attachment_id)
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docserver_url = url_utils.replace_public_url_to_internal(request.env, docserver_url)
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
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                        "headers": docbuilder_headers,
                    },
                )
            else:
                docbuilder_response = onlyoffice_request(
                    url=docbuilder_url,
                    method="post",
                    opts={
                        "json": docbuilder_payload,
                    },
                )
            docbuilder_json = docbuilder_response.json()
            if docbuilder_json.get("error"):
                e = self.get_docbuilder_error(docbuilder_json.get("error"))
                raise Exception(e)

            urls = docbuilder_json.get("urls")
            keys_url = urls.get("keys.txt")
            keys_response = onlyoffice_request(
                url=keys_url,
                method="get",
            )
            response_content = codecs.decode(keys_response.content, "utf-8-sig")

            logger.info("get_keys - success")
            return json.loads(response_content)
        except Exception as e:
            logger.warning("get_keys - error: %s", str(e))
            raise

    @http.route("/onlyoffice/template/callback/docbuilder/get_keys", auth="public")
    def docbuilder_get_keys(self, attachment_id, oo_security_token):
        logger.info("GET /onlyoffice/template/callback/docbuilder/get_keys - attachment: %s", attachment_id)
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

        logger.info("GET /onlyoffice/template/callback/docbuilder/get_keys - success")
        return request.make_response(docbuilder_content, headers)

    @http.route("/onlyoffice/template/download/<int:attachment_id>", auth="public")
    def download(self, attachment_id, oo_security_token):
        logger.info("GET /onlyoffice/template/download - attachment: %s", attachment_id)
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
            logger.info("GET /onlyoffice/template/download - success")
            return request.make_response(content, headers)
        else:
            logger.warning("attachment not found: %s", attachment_id)
            return request.not_found()

    def get_fields(self, keys, model, record_id, user):  # noqa: C901
        logger.info("get_fields - model: %s, record: %s", model, record_id)

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
                        elif data or field_type in ["integer", "float", "monetary"]:
                            if field_type in ["char", "text"]:
                                result[field] = str(data)
                            elif field_type == "float":
                                lang = request.env["res.lang"].sudo().search([("code", "=", user.lang)], limit=1)
                                digits = record._fields[field].get_digits(request.env)
                                precision = digits[1] if digits else 2
                                result[field] = lang.format(percent=f"%.{precision}f", value=data)
                            elif field_type == "integer":
                                lang = request.env["res.lang"].sudo().search([("code", "=", user.lang)], limit=1)
                                result[field] = lang.format(percent="%d", value=data)
                            elif field_type == "monetary":
                                currency = None
                                currency_field_name = record._fields[field].currency_field or "currency_id"
                                if currency_field_name:
                                    currency = getattr(record, currency_field_name)
                                result[field] = misc.format_amount(
                                    env=request.env, amount=data, currency=currency, lang_code=user.lang
                                )
                            elif field_type == "date":
                                result[field] = misc.format_date(request.env, data, user.lang)
                            elif field_type == "datetime":
                                result[field] = misc.format_datetime(
                                    env=request.env, value=data, tz=user.tz or "GMT", lang_code=user.lang
                                )
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
        logger.info("get_record - model: %s, record: %s", model, record_id)
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
        logger.info("get_user_from_token - user: %s", user.name)
        return user

    @http.route("/onlyoffice/template/documents/check", auth="user", type="json")
    def check_documents_module(self):
        """Check if the documents module is installed."""
        return bool(
            request.env["ir.module.module"].sudo().search([("name", "=", "documents"), ("state", "=", "installed")])
        )

    @http.route("/onlyoffice/template/documents/folders", auth="user", type="json")
    def get_documents_folders(self):
        """Get folders available to the current user from the Documents module."""
        try:
            Document = request.env["documents.document"]
        except KeyError:
            return []

        folders = Document.search([("type", "=", "folder")])
        result = []
        for folder in folders:
            if folder.access_internal != "edit":
                continue

            parts = []
            current = folder
            while current and current.type == "folder":
                parts.append(current.name)
                current = current.folder_id
            full_path = "/".join(reversed(parts))
            result.append({"id": folder.id, "display_name": full_path})

        result.sort(key=lambda f: f["display_name"])
        return result

    @http.route("/onlyoffice/template/documents/save", auth="user", type="json")
    def save_to_documents(self, template_id, record_ids, folder_id):
        """Fill template and save the result to the specified Documents folder."""
        logger.info(
            "save_to_documents - template: %s, records: %s, folder: %s",
            template_id,
            record_ids,
            folder_id,
        )
        try:
            folder = request.env["documents.document"].browse(int(folder_id))
            if not folder.exists() or folder.type != "folder":
                raise Exception("Access denied to the selected folder")
        except KeyError:
            raise Exception("Documents module is not installed")  # noqa: B904

        internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
        oo_security_token = jwt_utils.encode_payload(request.env, {"id": request.env.user.id}, internal_jwt_secret)

        if isinstance(record_ids, list):
            record_ids = ",".join(str(r) for r in record_ids)
        else:
            record_ids = str(record_ids)

        templates = self.fill_template(oo_security_token, record_ids, template_id)
        saved_documents = []

        for filename, url in templates.items():
            response = onlyoffice_request(url=quote(url, safe="/:?=&"), method="get")
            if response.status_code == 200:
                attachment = request.env["ir.attachment"].create(
                    {
                        "name": filename,
                        "datas": base64.b64encode(response.content),
                        "mimetype": "application/pdf",
                    }
                )
                document = request.env["documents.document"].create(
                    {
                        "name": filename,
                        "folder_id": int(folder_id),
                        "attachment_id": attachment.id,
                    }
                )
                saved_documents.append(document.id)
                logger.info("save_to_documents - saved document %s to folder %s", document.id, folder_id)
            else:
                logger.warning("save_to_documents - failed to download file: %s", response.status_code)
                raise Exception(f"Failed to download generated file, status={response.status_code}")

        return {"success": True, "document_ids": saved_documents}

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
