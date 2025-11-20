#
# (c) Copyright Ascensio System SIA 2024
#

import base64
import json
import logging
import os
import re
import string
import time
from mimetypes import guess_type
from urllib.request import urlopen

import markupsafe
import requests
from werkzeug.exceptions import Forbidden

from odoo import _, fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import request

from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501


def onlyoffice_urlopen(url, timeout=120, context=None):
    url = url_utils.replace_public_url_to_internal(request.env, url)
    cert_verify_disabled = config_utils.get_certificate_verify_disabled(request.env)

    if cert_verify_disabled and url.startswith("https://"):
        import ssl

        context = context or ssl._create_unverified_context()

    return urlopen(url, timeout=timeout, context=context)


def onlyoffice_request(url, method, opts=None):
    _logger.info("External request: %s %s", method.upper(), url)
    url = url_utils.replace_public_url_to_internal(request.env, url)
    cert_verify_disabled = config_utils.get_certificate_verify_disabled(request.env)
    if opts is None:
        opts = {}

    if url.startswith("https://") and cert_verify_disabled and "verify" not in opts:
        opts["verify"] = False

    if "timeout" not in opts and "timeout" not in url:
        opts["timeout"] = 120

    try:
        if method.lower() == "post":
            response = requests.post(url, **opts)
        else:
            response = requests.get(url, **opts)

        _logger.info("External request completed: %s %s - status: %s", method.upper(), url, response.status_code)
        response.raise_for_status()
        return response

    except requests.exceptions.RequestException as e:
        error_details = {
            "error_type": type(e).__name__,
            "url": url,
            "method": method.upper(),
            "request_options": opts,
            "original_error": str(e),
        }

        _logger.error("ONLYOFFICE request failed: %s", error_details)
        raise requests.exceptions.RequestException(
            f"ONLYOFFICE request failed to {method.upper()} {url}: {str(e)}"
        ) from e

    except Exception as e:
        error_details = {
            "error_type": type(e).__name__,
            "url": url,
            "method": method.upper(),
            "request_options": opts,
            "original_error": str(e),
        }

        _logger.error("Unexpected error in ONLYOFFICE request: %s", error_details)
        raise requests.exceptions.RequestException(
            f"Unexpected error in ONLYOFFICE request to {method.upper()} {url}: {str(e)}"
        ) from e


class Onlyoffice_Connector(http.Controller):
    @http.route("/onlyoffice/editor/get_config", auth="user", methods=["POST"], type="json", csrf=False)
    def get_config(self, document_id=None, attachment_id=None, access_token=None):
        _logger.info("POST /onlyoffice/editor/get_config - document: %s, attachment: %s", document_id, attachment_id)
        document = None
        if document_id:
            document = request.env["documents.document"].browse(int(document_id))
            attachment_id = document.attachment_id.id

        attachment = self.get_attachment(attachment_id)
        if not attachment:
            _logger.warning("POST /onlyoffice/editor/get_config - attachment not found: %s", attachment_id)
            return request.not_found()

        attachment.validate_access(access_token)

        if attachment.res_model == "documents.document" and not document:
            document = request.env["documents.document"].browse(int(attachment.res_id))

        if document:
            self._check_document_access(document)

        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]
        filename = data["name"]

        can_read = attachment.check_access_rights("read", raise_exception=False) and file_utils.can_view(filename)

        if not can_read:
            _logger.warning("POST /onlyoffice/editor/get_config - no read access: %s", attachment_id)
            raise Exception("cant read")

        can_write = attachment.check_access_rights("write", raise_exception=False) and file_utils.can_edit(filename)

        config = self.prepare_editor_values(attachment, access_token, can_write)
        _logger.info("POST /onlyoffice/editor/get_config - success: %s", attachment_id)
        return config

    @http.route("/onlyoffice/file/content/test.txt", auth="public")
    def get_test_file(self):
        _logger.info("GET /onlyoffice/file/content/test.txt")
        content = "test"
        headers = [
            ("Content-Length", len(content)),
            ("Content-Type", "text/plain"),
            ("Content-Disposition", "attachment; filename=test.txt"),
        ]
        response = request.make_response(content, headers)
        return response

    @http.route("/onlyoffice/file/content/<int:attachment_id>", auth="public")
    def get_file_content(self, attachment_id, oo_security_token=None, access_token=None):
        _logger.info("GET /onlyoffice/file/content/%s", attachment_id)
        attachment = self.get_attachment(attachment_id, self.get_user_from_token(oo_security_token))
        if not attachment:
            _logger.warning("GET /onlyoffice/file/content/%s - attachment not found", attachment_id)
            return request.not_found()

        attachment.validate_access(access_token)
        attachment.has_access("read")

        if jwt_utils.is_jwt_enabled(request.env):
            token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env))
            if token:
                token = token[len("Bearer ") :]

            if not token:
                _logger.warning("GET /onlyoffice/file/content/%s - JWT token missing", attachment_id)
                raise Exception("expected JWT")

            jwt_utils.decode_token(request.env, token)

        stream = request.env["ir.binary"]._get_stream_from(attachment, "datas", None, "name", None)

        send_file_kwargs = {"as_attachment": True, "max_age": None}

        _logger.info("GET /onlyoffice/file/content/%s - success", attachment_id)
        return stream.get_response(**send_file_kwargs)

    @http.route("/onlyoffice/editor/<int:attachment_id>", auth="public", type="http", website=True)
    def render_editor(self, attachment_id, access_token=None):
        _logger.info("GET /onlyoffice/editor/%s", attachment_id)
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            _logger.warning("GET /onlyoffice/editor/%s - attachment not found", attachment_id)
            return request.not_found()

        attachment.validate_access(access_token)

        if attachment.res_model == "documents.document":
            document = request.env["documents.document"].browse(int(attachment.res_id))
            self._check_document_access(document)

        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]
        filename = data["name"]

        can_read = attachment.has_access("read") and file_utils.can_view(filename)
        can_write = attachment.has_access("write") and file_utils.can_edit(filename)

        if not can_read:
            _logger.warning("GET /onlyoffice/editor/%s - no read access", attachment_id)
            raise Exception("cant read")

        _logger.info("GET /onlyoffice/editor/%s - success", attachment_id)
        return request.render(
            "onlyoffice_odoo.onlyoffice_editor", self.prepare_editor_values(attachment, access_token, can_write)
        )

    @http.route(
        "/onlyoffice/editor/callback/<int:attachment_id>", auth="public", methods=["POST"], type="http", csrf=False
    )
    def editor_callback(self, attachment_id, oo_security_token=None, access_token=None):
        _logger.info("POST /onlyoffice/editor/callback/%s", attachment_id)
        response_json = {"error": 0}

        try:
            body = request.get_json_data()
            user = self.get_user_from_token(oo_security_token)
            attachment = self.get_attachment(attachment_id, user)
            if not attachment:
                _logger.warning("POST /onlyoffice/editor/callback/%s - attachment not found", attachment_id)
                raise Exception("attachment not found")

            attachment.validate_access(access_token)
            attachment.has_access("write")

            if jwt_utils.is_jwt_enabled(request.env):
                token = body.get("token")

                if not token:
                    token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env))
                    if token:
                        token = token[len("Bearer ") :]

                if not token:
                    _logger.warning("POST /onlyoffice/editor/callback/%s - JWT token missing", attachment_id)
                    raise Exception("expected JWT")

                body = jwt_utils.decode_token(request.env, token)
                if body.get("payload"):
                    body = body["payload"]

            status = body["status"]
            _logger.info("POST /onlyoffice/editor/callback/%s - status: %s", attachment_id, status)

            if (status == 2) | (status == 3):  # mustsave, corrupted
                file_url = url_utils.replace_public_url_to_internal(request.env, body.get("url"))
                datas = onlyoffice_urlopen(file_url).read()
                if attachment.res_model == "documents.document":
                    datas = base64.encodebytes(datas)
                    document = request.env["documents.document"].browse(int(attachment.res_id))
                    document.with_user(user).write(
                        {
                            "name": attachment.name,
                            "datas": datas,
                            "mimetype": guess_type(file_url)[0],
                        }
                    )

                    attachment_version = attachment.oo_attachment_version
                    attachment.write({"oo_attachment_version": attachment_version + 1})
                    document.sudo().message_post(body=_("Document edited by %(user)s", user=user.name))

                    previous_attachments = (
                        request.env["ir.attachment"]
                        .sudo()
                        .search(
                            [
                                ("res_model", "=", "documents.document"),
                                ("res_id", "=", document.id),
                                ("oo_attachment_version", "=", attachment_version),
                            ],
                            limit=1,
                        )
                    )
                    name = attachment.name
                    filename, ext = os.path.splitext(attachment.name)
                    name = f"{filename} ({attachment_version}){ext}"
                    previous_attachments.sudo().write({"name": name})
                else:
                    attachment.write({"raw": datas, "mimetype": guess_type(file_url)[0]})

                _logger.info("POST /onlyoffice/editor/callback/%s - file saved successfully", attachment_id)

        except Exception as ex:
            _logger.error("POST /onlyoffice/editor/callback/%s - error: %s", attachment_id, str(ex))
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )

    def prepare_editor_values(self, attachment, access_token, can_write):
        _logger.info("prepare_editor_values - attachment: %s", attachment.id)
        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]
        key = str(data["id"]) + str(data["checksum"])
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        filename = self.filter_xss(data["name"])

        security_token = jwt_utils.encode_payload(
            request.env, {"id": request.env.user.id}, config_utils.get_internal_jwt_secret(request.env)
        )
        security_token = security_token.decode("utf-8") if isinstance(security_token, bytes) else security_token
        access_token = access_token.decode("utf-8") if isinstance(access_token, bytes) else access_token
        path_part = (
            str(data["id"])
            + "?oo_security_token="
            + security_token
            + ("&access_token=" + access_token if access_token else "")
            + "&shardkey="
            + key
        )

        document_type = file_utils.get_file_type(filename)

        is_mobile = bool(re.search(_mobile_regex, request.httprequest.headers.get("User-Agent"), re.IGNORECASE))

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "mobile" if is_mobile else "desktop",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": odoo_url + "onlyoffice/file/content/" + path_part,
                "fileType": file_utils.get_file_ext(filename),
                "key": key,
                "permissions": {},
            },
            "editorConfig": {
                "lang": request.env.user.lang,
                "user": {"id": str(request.env.user.id), "name": request.env.user.name},
                "customization": {},
            },
        }

        if can_write:
            root_config["editorConfig"]["callbackUrl"] = odoo_url + "onlyoffice/editor/callback/" + path_part

        if attachment.res_model != "documents.document":
            root_config["editorConfig"]["mode"] = "edit" if can_write else "view"
            root_config["document"]["permissions"]["edit"] = can_write
        elif attachment.res_model == "documents.document":
            root_config = self.get_documents_permissions(attachment, can_write, root_config)

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        _logger.info("prepare_editor_values - success: %s", attachment.id)
        return {
            "docTitle": filename,
            "docIcon": f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico",
            "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
            "editorConfig": markupsafe.Markup(json.dumps(root_config)),
        }

    def get_documents_permissions(self, attachment, can_write, root_config):  # noqa: C901
        _logger.info("get_documents_permissions - attachment: %s", attachment.id)
        role = None
        document = request.env["documents.document"].browse(int(attachment.res_id))

        now = fields.Datetime.now()
        document_access_id = document.access_ids.filtered(lambda a: a.partner_id == request.env.user.partner_id)
        expired_timer = False
        if document_access_id and document_access_id.exists():
            if document_access_id.expiration_date:
                expired_timer = document_access_id.expiration_date < now

        if document.attachment_id.id != attachment.id:  # history files
            root_config["editorConfig"]["mode"] = "view"
            root_config["document"]["permissions"]["edit"] = False
            return root_config

        if document.owner_id.id == request.env.user.id:  # owner
            if can_write:
                role = "edit"
            else:
                role = "view"
        else:
            access_user = request.env["onlyoffice.odoo.documents.access.user"].search(
                [("document_id", "=", document.id), ("user_id", "=", request.env.user.partner_id.id)], limit=1
            )
            if access_user and not expired_timer:
                if access_user.role == "none":
                    raise AccessError(_("User has no read access rights to open this document"))
                elif access_user.role == "edit" and can_write:
                    role = "edit"
                else:
                    role = access_user.role
            if not role:
                access = request.env["onlyoffice.odoo.documents.access"].search(
                    [("document_id", "=", document.id)], limit=1
                )
                if access:
                    if access.internal_users == "none":
                        raise AccessError(_("User has no read access rights to open this document"))
                    elif access.internal_users == "edit" and can_write:
                        role = "edit"
                    else:
                        role = access.internal_users
                else:
                    role = "view"  # default role for internal users

        if not role:
            raise AccessError(_("User has no read access rights to open this document"))
        elif role == "view":
            root_config["editorConfig"]["mode"] = "view"
            root_config["document"]["permissions"]["edit"] = False
        elif role == "commenter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["comment"] = True
        elif role == "reviewer":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["review"] = True
        elif role == "edit":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
        elif role == "form_filling":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["fillForms"] = True
        elif role == "custom_filter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
            root_config["document"]["permissions"]["modifyFilter"] = False

        _logger.info("get_documents_permissions - role: %s", role)
        return root_config

    def get_attachment(self, attachment_id, user=None):
        IrAttachment = request.env["ir.attachment"]
        if user:
            IrAttachment = IrAttachment.with_user(user)
        try:
            attachment = IrAttachment.browse([attachment_id]).exists().ensure_one()
            _logger.debug("get_attachment - found: %s", attachment_id)
            return attachment
        except Exception:
            _logger.debug("get_attachment - not found: %s", attachment_id)
            return None

    def get_user_from_token(self, token):
        _logger.info("get_user_from_token")
        if not token:
            raise Exception("missing security token")

        user_id = jwt_utils.decode_token(request.env, token, config_utils.get_internal_jwt_secret(request.env))["id"]
        user = request.env["res.users"].sudo().browse(user_id).exists().ensure_one()
        _logger.info("get_user_from_token - user: %s", user.name)
        return user

    def filter_xss(self, text):
        allowed_symbols = set(string.digits + " _-,.:@+")
        text = "".join(char for char in text if char.isalpha() or char in allowed_symbols)
        return text

    def _check_document_access(self, document):
        if document.is_locked and document.lock_uid.id != request.env.user.id:
            _logger.error("Document is locked by another user")
            raise Forbidden()
        try:
            document.check_access_rule("read")
        except AccessError as e:
            _logger.error("User has no read access rights to open this document")
            raise Forbidden() from e

    @http.route("/onlyoffice/preview", type="http", auth="user")
    def preview(self, url, title):
        _logger.info("GET /onlyoffice/preview - url: %s, title: %s", url, title)
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        if url and url.startswith("/onlyoffice/file/content/"):
            internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
            user_id = request.env.user.id
            security_token = jwt_utils.encode_payload(request.env, {"id": user_id}, internal_jwt_secret)
            security_token = security_token.decode("utf-8") if isinstance(security_token, bytes) else security_token
            url = url + "?oo_security_token=" + security_token

        if url and not url.startswith(("http://", "https://")):
            url = odoo_url.rstrip("/") + "/" + url.lstrip("/")

        document_type = file_utils.get_file_type(title)
        key = str(int(time.time() * 1000))

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "embedded",
            "documentType": document_type,
            "document": {
                "title": self.filter_xss(title),
                "url": url,
                "fileType": file_utils.get_file_ext(title),
                "key": key,
                "permissions": {"edit": False},
            },
            "editorConfig": {
                "mode": "view",
                "lang": request.env.user.lang,
                "user": {"id": str(request.env.user.id), "name": request.env.user.name},
                "customization": {},
            },
        }

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        _logger.info("GET /onlyoffice/preview - success")
        return request.render(
            "onlyoffice_odoo.onlyoffice_editor",
            {
                "docTitle": title,
                "docIcon": f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico",
                "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
                "editorConfig": markupsafe.Markup(json.dumps(root_config)),
            },
        )


class OnlyOfficeOFormsDocumentsController(http.Controller):
    CMSOFORMS_URL = "https://cmsoforms.onlyoffice.com/api"
    OFORMS_URL = "https://oforms.onlyoffice.com/dashboard/api"
    TIMEOUT = 20  # seconds

    def _make_api_request(self, url, endpoint, params=None, method="GET", data=None, files=None):
        url = f"{url}/{endpoint}"
        try:
            if method == "GET":
                response = requests.get(url, params=params, timeout=self.TIMEOUT)
            elif method == "POST":
                response = requests.post(url, data=data, files=files, timeout=self.TIMEOUT)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            _logger.error(f"API request failed to {url}: {str(e)}")
            raise UserError(f"Failed to connect to Forms API: {str(e)}") from e

    @http.route("/onlyoffice/oforms/locales", type="json", auth="user")
    def get_oform_locales(self):
        url = self.OFORMS_URL
        endpoint = "i18n/locales"
        response = self._make_api_request(url, endpoint)
        locales = response if isinstance(response, list) else []
        return {
            "data": [
                {
                    "code": locale.get("code"),
                    "name": locale.get("name", locale.get("code")),
                }
                for locale in locales
            ]
        }

    @http.route("/onlyoffice/oforms/category-types", type="json", auth="user")
    def get_category_types(self, locale="en"):
        url = self.OFORMS_URL
        endpoint = "menu-translations"
        params = {"populate": "*", "locale": locale}
        response = self._make_api_request(url, endpoint, params=params)

        categories = []
        for item in response.get("data", []):
            attrs = item.get("attributes", {})
            localized_name = next(
                (
                    loc["attributes"]["name"]
                    for loc in attrs.get("localizations", {}).get("data", [])
                    if loc["attributes"]["locale"] == locale
                ),
                None,
            ) or attrs.get("name", "")

            categories.append(
                {
                    "id": item["id"],
                    "categoryId": attrs.get("categoryId"),
                    "name": localized_name,
                    "type": attrs.get("categoryTitle"),
                }
            )

        return {"data": categories}

    @http.route("/onlyoffice/oforms/subcategories", type="json", auth="user")
    def get_subcategories(self, category_type, locale="en"):
        url = self.OFORMS_URL
        endpoint_map = {"categorie": "categories", "type": "types", "compilation": "compilations"}

        if category_type not in endpoint_map:
            return {"data": []}

        endpoint = f"{endpoint_map[category_type]}"
        params = {"populate": "*", "locale": locale}
        response = self._make_api_request(url, endpoint, params=params)

        subcategories = []
        for item in response.get("data", []):
            attrs = item.get("attributes", {})
            localized_name = next(
                (
                    loc["attributes"][category_type]
                    for loc in attrs.get("localizations", {}).get("data", [])
                    if loc["attributes"]["locale"] == locale
                ),
                None,
            ) or attrs.get(category_type, "")

            subcategories.append(
                {
                    "id": item["id"],
                    "name": localized_name,
                    "category_type": endpoint_map[category_type],
                }
            )

        return {"data": subcategories}

    @http.route("/onlyoffice/oforms", type="json", auth="user")
    def get_oforms(self, params=None, **kwargs):
        url = self.CMSOFORMS_URL
        if params is None:
            params = {}

        api_params = {
            "fields[0]": "name_form",
            "fields[1]": "updatedAt",
            "fields[2]": "description_card",
            "fields[3]": "template_desc",
            "filters[form_exts][ext][$eq]": params.get("type", "pdf"),
            "locale": params.get("locale", "en"),
            "pagination[page]": params.get("pagination[page]", 1),
            "pagination[pageSize]": params.get("pagination[pageSize]", 12),
            "populate[card_prewiew][fields][0]": "url",
            "populate[template_image][fields][0]": "formats",
            "populate[file_oform][fields][0]": "url",
            "populate[file_oform][fields][1]": "name",
            "populate[file_oform][fields][2]": "ext",
            "populate[file_oform][filters][url][$endsWith]": "." + params.get("type", "pdf"),
        }

        if "filters[name_form][$containsi]" in params:
            api_params["filters[name_form][$containsi]"] = params["filters[name_form][$containsi]"]

        if "filters[categories][$eq]" in params:
            api_params["filters[categories][id][$eq]"] = params["filters[categories][$eq]"]
        elif "filters[types][$eq]" in params:
            api_params["filters[types][id][$eq]"] = params["filters[types][$eq]"]
        elif "filters[compilations][$eq]" in params:
            api_params["filters[compilations][id][$eq]"] = params["filters[compilations][$eq]"]

        response = self._make_api_request(url, "oforms", params=api_params)
        return response
