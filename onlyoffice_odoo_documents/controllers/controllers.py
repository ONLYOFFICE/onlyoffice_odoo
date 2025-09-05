#
# (c) Copyright Ascensio System SIA 2024
#
import base64
import json
import logging
import re
from mimetypes import guess_type
from urllib.request import urlopen

import markupsafe
import requests
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.documents.controllers.documents import ShareRoute
from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501


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

    @http.route("/onlyoffice/documents/oforms/locales", type="json", auth="user")
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

    @http.route("/onlyoffice/documents/oforms/category-types", type="json", auth="user")
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

    @http.route("/onlyoffice/documents/oforms/subcategories", type="json", auth="user")
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

    @http.route("/onlyoffice/documents/oforms", type="json", auth="user")
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


class OnlyofficeDocuments_Connector(http.Controller):
    @http.route("/onlyoffice/documents/file/create", auth="user", methods=["POST"], type="json")
    def post_file_create(self, folder_id, supported_format, title, url=None):
        result = {"error": None, "file_id": None, "document_id": None}

        try:
            _logger.info(f"Getting new file template {request.env.user.lang} {supported_format}")

            if url:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                file_data = response.content
            else:
                file_data = file_utils.get_default_file_template(request.env.user.lang, supported_format)

            data = {
                "name": title + "." + supported_format,
                "mimetype": file_utils.get_mime_by_ext(supported_format),
                "raw": file_data,
                "folder_id": int(folder_id),
            }

            document = request.env["documents.document"].create(data)
            request.env["onlyoffice.odoo.documents.access"].create(
                {
                    "document_id": document.id,
                    "internal_users": "none",
                    "link_access": "viewer",
                }
            )
            request.env["onlyoffice.odoo.documents.access.user"].create(
                {
                    "document_id": document.id,
                    "user_id": request.env.user.id,
                    "role": "editor",
                }
            )
            result["file_id"] = document.attachment_id.id
            result["document_id"] = document.id

        except Exception as ex:
            _logger.exception(f"Failed to create document {str(ex)}")
            result["error"] = _("Failed to create document")

        return json.dumps(result)


class OnlyofficeDocuments_Inherited_Connector(Onlyoffice_Connector):
    @http.route(
        ["/onlyoffice/documents/share/<int:share_id>/<access_token>/<int:document_id>"], type="http", auth="public"
    )
    def render_shared_document_editor(self, document_id=None, access_token=None, share_id=None):
        try:
            document = None
            if share_id:
                share = request.env["documents.share"].sudo().browse(int(share_id))
                document = share._get_documents_and_check_access(access_token, [int(document_id)], operation="read")
            if not document or not document.exists():
                raise request.not_found()

            return request.render(
                "onlyoffice_odoo.onlyoffice_editor", self.prepare_share_editor(document, access_token, share_id)
            )

        except Exception:
            _logger.error("Ffailed to open shared document")

        return request.not_found()

    @http.route("/onlyoffice/editor/document/<int:document_id>", auth="public", type="http", website=True)
    def render_document_editor(self, document_id, access_token=None):
        return request.render(
            "onlyoffice_odoo.onlyoffice_editor", self.prepare_document_editor(document_id, access_token)
        )

    def prepare_document_editor(self, document_id, access_token):
        document = request.env["documents.document"].browse(int(document_id))
        if document.is_locked and document.lock_uid.id != request.env.user.id:
            _logger.error("Document is locked by another user")
            raise Forbidden()
        try:
            document.check_access_rule("read")
        except AccessError:
            _logger.error("User has no read access rights to open this document")
            raise Forbidden()  # noqa: B904

        attachment = self.get_attachment(document.attachment_id.id)
        if not attachment:
            _logger.error("Current document has no attachments")
            raise Forbidden()  # noqa: B904

        try:
            document.check_access_rule("write")
            return self.prepare_editor_values(attachment, access_token, True)
        except AccessError:
            _logger.debug("Current user has no write access")
            return self.prepare_editor_values(attachment, access_token, False)

    def prepare_share_editor(self, document, access_token, share_id):
        role = None
        access = (
            request.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if access:
            if access.link_access == "none":
                raise AccessError(_("User has no read access rights to open this document"))
            else:
                role = access.link_access

        attachment = self.get_attachment(document.attachment_id.id)
        data = attachment.sudo().read(["id", "checksum", "public", "name", "access_token"])[0]
        key = str(data["id"]) + str(data["checksum"])
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        filename = self.filter_xss(data["name"])
        access_token = access_token.decode("utf-8") if isinstance(access_token, bytes) else access_token
        document_type = file_utils.get_file_type(filename)
        is_mobile = bool(re.search(_mobile_regex, request.httprequest.headers.get("User-Agent"), re.IGNORECASE))

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "mobile" if is_mobile else "desktop",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": odoo_url + "document/download/" + str(share_id) + "/" + access_token + "/" + str(document.id),
                "fileType": file_utils.get_file_ext(filename),
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

        if not role or role == "viewer":
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
        elif role == "editor":
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

        if role and role != "viewer":
            public_user = request.env.ref("base.public_user")
            security_token = jwt_utils.encode_payload(
                request.env, {"id": public_user.id}, config_utils.get_internal_jwt_secret(request.env)
            )
            security_token = security_token.decode("utf-8") if isinstance(security_token, bytes) else security_token
            root_config["editorConfig"]["callbackUrl"] = (
                odoo_url
                + "onlyoffice/documents/share/callback/"
                + str(share_id)
                + "/"
                + access_token
                + "/"
                + str(document.id)
                + "/"
                + security_token
            )

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        return {
            "docTitle": filename,
            "docIcon": f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico",
            "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
            "editorConfig": markupsafe.Markup(json.dumps(root_config)),
        }

    @http.route(
        "/onlyoffice/documents/share/callback/<int:share_id>/<access_token>/<int:document_id>/<oo_security_token>",
        auth="public",
        methods=["POST"],
        type="http",
        csrf=False,
    )
    def share_callback(self, share_id, access_token, document_id, oo_security_token):
        response_json = {"error": 0}

        try:
            body = request.get_json_data()
            user = self.get_user_from_token(oo_security_token)
            share = request.env["documents.share"].sudo().browse(int(share_id))
            document = share._get_documents_and_check_access(access_token, [int(document_id)], operation="read")

            access = (
                request.env["onlyoffice.odoo.documents.access"]
                .sudo()
                .search([("document_id", "=", document.id)], limit=1)
            )
            if access:
                if access.link_access == "viewer":
                    raise Exception("No access rights to overwrite this document for access via share link")
            else:
                raise Exception("No access rights to overwrite this document for access via share link")

            attachment = request.env["ir.attachment"].sudo().browse([document.attachment_id.id]).exists().ensure_one()

            if jwt_utils.is_jwt_enabled(request.env):
                token = body.get("token")

                if not token:
                    token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env))
                    if token:
                        token = token[len("Bearer ") :]

                if not token:
                    raise Exception("expected JWT")

                body = jwt_utils.decode_token(request.env, token)
                if body.get("payload"):
                    body = body["payload"]

            status = body["status"]

            if (status == 2) | (status == 3):  # mustsave, corrupted
                file_url = url_utils.replace_public_url_to_internal(request.env, body.get("url"))
                datas = base64.encodebytes(urlopen(file_url, timeout=120).read())
                document = request.env["documents.document"].sudo().browse(int(attachment.res_id))
                document.with_user(user).sudo().write(
                    {
                        "name": attachment.name,
                        "datas": datas,
                        "mimetype": guess_type(file_url)[0],
                    }
                )

        except Exception as ex:
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )


class OnlyOfficeShareRoute(ShareRoute):
    @http.route(["/document/share/<int:share_id>/<token>"], type="http", auth="public", website=True)
    def share_portal(self, share_id=None, token=None, **kwargs):
        response = super(OnlyOfficeShareRoute, self).share_portal(share_id, token, **kwargs)  # noqa: UP008

        if not hasattr(response, "qcontext"):
            return response

        share = http.request.env["documents.share"].sudo().browse(share_id)
        qcontext = response.qcontext

        if share.type == "domain":
            data = []
            for document in qcontext["document_ids"]:
                data.append({"document": document, "onlyoffice_supported": file_utils.can_view(document.name)})
            qcontext["onlyoffice_supported"] = data

        elif response.qcontext.get("is_files_shared"):
            document = qcontext.get("document_ids") and qcontext["document_ids"][0] or None

            if document and len(qcontext["document_ids"]) == 1:
                can_view = file_utils.can_view(document.name)
                if can_view:
                    qcontext["onlyoffice_supported"] = True

        return response
