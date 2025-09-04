#
# (c) Copyright Ascensio System SIA 2024
#

import json
import logging
import time

import markupsafe
import requests
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

_logger = logging.getLogger(__name__)


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
    @http.route("/onlyoffice/documents/gallery/preview", type="http", auth="user")
    def preview_documents_gallery(self, form_path, **kwargs):
        filename = self.filter_xss(form_path.split("/")[-1])
        document_type = file_utils.get_file_type(filename)

        key = str(int(time.time() * 1000))

        docserver_url = config_utils.get_doc_server_public_url(request.env)

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "embedded",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": form_path,
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

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        return request.render(
            "onlyoffice_odoo.onlyoffice_editor",
            {
                "docTitle": filename,
                "docIcon": f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico",
                "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
                "editorConfig": markupsafe.Markup(json.dumps(root_config)),
            },
        )

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
