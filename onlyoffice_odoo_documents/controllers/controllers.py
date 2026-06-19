# Copyright (C) 2026 Ascensio System SIA
import base64
import io
import json
import logging
import re
import secrets
import uuid
import zipfile
from datetime import date, datetime
from mimetypes import guess_type
from urllib.request import urlopen
from xml.etree import ElementTree as ET

import markupsafe
import requests
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_open
from odoo.tools.translate import _

from odoo.addons.documents.controllers.documents import ShareRoute
from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils

from .spreadsheet_formulas import (
    SpreadsheetFormulaEvaluator,
    compute_filter_values,
    load_metadata_for_document,
)

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501

# Global cache for DocBuilder conversion data (token -> data)
_docbuilder_cache = {}


class _DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, o):
        if isinstance(o, datetime | date):
            return o.isoformat()
        return super().default(o)


# Shared formula evaluator instance
_formula_evaluator = SpreadsheetFormulaEvaluator()


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
    @http.route("/onlyoffice/editor/get_config", auth="user", methods=["POST"], type="json", csrf=False)
    def get_config(self, document_id=None, attachment_id=None, access_token=None):
        """Override to add ODOO custom formula support when a document with metadata is present."""
        config = super().get_config(document_id=document_id, attachment_id=attachment_id, access_token=access_token)

        # Resolve document from document_id or attachment
        document = None
        if document_id:
            document = request.env["documents.document"].browse(int(document_id))
        elif attachment_id:
            attachment = request.env["ir.attachment"].browse(int(attachment_id))
            if attachment.exists() and attachment.res_model == "documents.document":
                document = request.env["documents.document"].browse(int(attachment.res_id))

        if document and document.exists():
            config["document_id"] = document.id
            config["jwt_token"] = jwt_utils.encode_payload(
                request.env,
                {"uid": request.env.user.id, "document_id": document.id},
                config_utils.get_internal_jwt_secret(request.env),
            )
            if document.onlyoffice_spreadsheet_metadata or document.onlyoffice_spreadsheet_source_id:
                config["has_odoo_formulas"] = True
                try:
                    metadata = load_metadata_for_document(document)
                    config["filter_values_json"] = json.dumps(compute_filter_values(metadata))
                except Exception:
                    config["filter_values_json"] = "{}"

        return config

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
            editor_values = self.prepare_editor_values(attachment, access_token, True)
        except AccessError:
            _logger.debug("Current user has no write access")
            editor_values = self.prepare_editor_values(attachment, access_token, False)

        # Add document_id and security token for ODOO custom functions
        editor_values["document_id"] = document_id
        editor_values["jwt_token"] = jwt_utils.encode_payload(
            request.env,
            {"uid": request.env.user.id, "document_id": document_id},
            config_utils.get_internal_jwt_secret(request.env),
        )

        # Pre-compute filter values so ODOO_FILTER_VALUE is synchronous on the client.
        # This avoids the async dependency issue where ODOO_PIVOT gets incomplete args.
        if document.onlyoffice_spreadsheet_metadata or document.onlyoffice_spreadsheet_source_id:
            # Flag: document has ODOO custom formulas (pivots, lists, or filters in metadata)
            editor_values["has_odoo_formulas"] = True
            try:
                metadata = load_metadata_for_document(document)
                editor_values["filter_values_json"] = markupsafe.Markup(json.dumps(compute_filter_values(metadata)))
            except Exception:
                editor_values["filter_values_json"] = markupsafe.Markup("{}")

        return editor_values

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
            "docApiJS": f"{docserver_url}web-apps/apps/api/documents/api.js?shardkey={key}",
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

    @http.route(["/Products/Files/", "/Products/Files"], auth="user", methods=["GET"], type="http")
    def desktop_editor_redirect(self, **kwargs):
        return request.redirect("/web#action=documents.document_action&menu_id=documents.menu_root")

    @http.route("/onlyoffice/documents/convert_spreadsheet_via_docbuilder", auth="user", methods=["POST"], type="json")
    def convert_spreadsheet_via_docbuilder(self, document_id):
        """
        Convert Odoo Spreadsheet to XLSX using DocBuilder.
        This preserves formulas and creates a native XLSX file.
        """
        result = {"error": None, "xlsx_id": None}

        try:
            document = request.env["documents.document"].browse(document_id)

            if not document.exists() or document.handler != "spreadsheet":
                result["error"] = _("Document is not a spreadsheet")
                return result

            # Get spreadsheet data with revisions
            session_data = document.join_spreadsheet_session()
            snapshot = session_data.get("data", {})

            if not snapshot or "sheets" not in snapshot:
                result["error"] = _("Spreadsheet has no data or invalid structure")
                return result

            # Evaluate ODOO.* formulas and add their values to cells
            _formula_evaluator.evaluate_odoo_formulas_in_snapshot(snapshot)

            spreadsheet_json = json.dumps(snapshot, cls=_DateTimeEncoder)
            metadata_json = self._prepare_docbuilder_metadata(snapshot)

            # Store data in global cache for callback
            oo_security_token = secrets.token_urlsafe(32)
            output_filename = f"{document.name}_{uuid.uuid4().hex[:8]}.xlsx"
            _docbuilder_cache[oo_security_token] = {
                "document_id": document_id,
                "spreadsheet_json": spreadsheet_json,
                "metadata_json": metadata_json,
                "output_filename": output_filename,
            }

            # Call DocBuilder service
            xlsx_content, error = self._call_docbuilder(oo_security_token, document_id)
            if error:
                result["error"] = error
                return result

            # Save or update XLSX document
            result["xlsx_id"] = self._save_xlsx_document(document, document_id, xlsx_content, metadata_json)
            _logger.info("Converted spreadsheet %s to XLSX %s", document_id, result["xlsx_id"])

        except Exception as e:
            _logger.exception("Error converting spreadsheet via DocBuilder: %s", e)
            result["error"] = str(e)

        return result

    def _prepare_docbuilder_metadata(self, snapshot):
        """Prepare metadata JSON with resolved domains for DocBuilder conversion."""
        metadata = {}
        if snapshot.get("lists"):
            lists_with_computed_domain = {}
            for list_id, list_data in snapshot["lists"].items():
                list_copy = dict(list_data)
                list_copy["domain"] = _formula_evaluator._parse_and_resolve_domain(list_copy.get("domain", []))
                lists_with_computed_domain[list_id] = list_copy
            metadata["lists"] = lists_with_computed_domain
        if snapshot.get("pivots"):
            pivots_with_computed_domain = {}
            for pivot_id, pivot_data in snapshot["pivots"].items():
                pivot_copy = dict(pivot_data)
                pivot_copy["domain"] = _formula_evaluator._parse_and_resolve_domain(pivot_copy.get("domain", []))
                pivots_with_computed_domain[pivot_id] = pivot_copy
            metadata["pivots"] = pivots_with_computed_domain
        if snapshot.get("globalFilters"):
            metadata["globalFilters"] = snapshot["globalFilters"]
        return json.dumps(metadata, cls=_DateTimeEncoder) if metadata else None

    def _call_docbuilder(self, oo_security_token, document_id):
        """Call DocBuilder service and download the resulting XLSX. Returns (content, error)."""
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        docserver_url = url_utils.replace_public_url_to_internal(request.env, docserver_url)
        docbuilder_url = f"{docserver_url}docbuilder"

        jwt_header = config_utils.get_jwt_header(request.env)
        jwt_secret = config_utils.get_jwt_secret(request.env)

        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        callback_url = f"{odoo_url}onlyoffice/documents/docbuilder_callback/{oo_security_token}"

        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        payload = {"async": False, "url": callback_url}

        if jwt_secret:
            payload["token"] = jwt_utils.encode_payload(request.env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(request.env, {"payload": payload}, jwt_secret)

        _logger.info("Calling DocBuilder to convert spreadsheet %s", document_id)
        response = requests.post(docbuilder_url, json=payload, headers=headers, timeout=300)

        if response.status_code != 200:
            _logger.error("DocBuilder error: %s - %s", response.status_code, response.text)
            return None, _("DocBuilder conversion failed: %s") % response.text

        response_json = response.json()
        if response_json.get("error"):
            error_code = response_json["error"]
            error_messages = {
                -1: _("Unknown error"),
                -2: _("Conversion timeout"),
                -3: _("Conversion error"),
                -4: _("Error downloading file"),
                -6: _("Error accessing database"),
                -8: _("Invalid token"),
            }
            return None, error_messages.get(error_code, _("Error code: %s") % error_code)

        # Download the generated XLSX file
        urls = response_json.get("urls", {})
        xlsx_url = next((url for key, url in urls.items() if key.endswith(".xlsx")), None)
        if not xlsx_url:
            xlsx_url = next(iter(urls.values()), None) if urls else None
        if not xlsx_url:
            return None, _("No XLSX file in output")

        xlsx_response = requests.get(xlsx_url, timeout=60)
        if xlsx_response.status_code != 200:
            return None, _("Failed to download converted file")

        return xlsx_response.content, None

    def _save_xlsx_document(self, document, document_id, xlsx_content, metadata_json):
        """Save or update the XLSX document in Odoo. Returns document ID."""
        existing_xlsx = request.env["documents.document"].search(
            [
                ("onlyoffice_spreadsheet_source_id", "=", document_id),
                ("name", "like", f"{document.name}_docbuilder%.xlsx"),
            ],
            limit=1,
        )

        if existing_xlsx:
            existing_xlsx.write(
                {
                    "datas": base64.b64encode(xlsx_content),
                    "onlyoffice_spreadsheet_metadata": metadata_json,
                }
            )
            return existing_xlsx.id

        xlsx_doc = request.env["documents.document"].create(
            {
                "name": f"{document.name}_docbuilder.xlsx",
                "folder_id": document.folder_id.id,
                "datas": base64.b64encode(xlsx_content),
                "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "onlyoffice_spreadsheet_source_id": document_id,
                "onlyoffice_spreadsheet_metadata": metadata_json,
            }
        )
        return xlsx_doc.id

    @http.route("/onlyoffice/documents/docbuilder_callback/<string:oo_security_token>", auth="public", methods=["GET"])
    def docbuilder_callback(self, oo_security_token):
        """
        Callback endpoint for DocBuilder to get the conversion script.
        Supports two modes: 'convert_spreadsheet' (default) and 'insert_list'.
        """
        try:
            cache_data = _docbuilder_cache.get(oo_security_token)

            if not cache_data:
                _logger.error("DocBuilder callback: token not found: %s", oo_security_token)
                return request.make_response("Token not found or expired", status=404)

            mode = cache_data.get("mode", "convert_spreadsheet")
            output_filename = cache_data["output_filename"]

            if mode == "insert_list":
                docbuilder_script = self._build_insert_list_script(cache_data, oo_security_token)
            else:
                # Default: convert_spreadsheet mode
                spreadsheet_json = cache_data["spreadsheet_json"]
                metadata_json = cache_data.get("metadata_json")
                with file_open("onlyoffice_odoo_documents/controllers/convert_spreadsheet.docbuilder", "r") as f:
                    docbuilder_script = f.read()
                docbuilder_script = docbuilder_script.replace("SPREADSHEET_DATA_PLACEHOLDER", spreadsheet_json)
                docbuilder_script = docbuilder_script.replace("METADATA_PLACEHOLDER", metadata_json or "null")
                docbuilder_script = docbuilder_script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{output_filename}"')
                del _docbuilder_cache[oo_security_token]

            headers = {
                "Content-Disposition": "attachment; filename='docbuilder_script.docbuilder'",
                "Content-Type": "text/plain; charset=utf-8",
            }
            return request.make_response(docbuilder_script.encode("utf-8"), headers)

        except Exception as e:
            _logger.exception("DocBuilder callback error: %s", e)
            return request.make_response(str(e), status=500)

    def _build_insert_list_script(self, cache_data, oo_security_token):
        """Build a DocBuilder script that opens an existing XLSX and inserts a list sheet."""
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        file_url = f"{odoo_url}onlyoffice/documents/docbuilder_file/{oo_security_token}"

        with file_open("onlyoffice_odoo_documents/controllers/insert_list.docbuilder", "r") as f:
            script = f.read()

        script = script.replace("FILE_URL_PLACEHOLDER", f'"{file_url}"')
        script = script.replace("LIST_ID_PLACEHOLDER", cache_data["list_id"])
        script = script.replace("SHEET_NAME_PLACEHOLDER", json.dumps(cache_data["sheet_name"]))
        script = script.replace("COLUMNS_PLACEHOLDER", cache_data["columns_json"])
        script = script.replace("THRESHOLD_PLACEHOLDER", str(cache_data["threshold"]))
        script = script.replace("METADATA_PLACEHOLDER", cache_data["metadata_json"])
        script = script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{cache_data["output_filename"]}"')

        # Don't delete cache yet — the file-serving route needs it
        # It will be cleaned up after the file is served
        return script

    @http.route("/onlyoffice/documents/docbuilder_file/<string:oo_security_token>", auth="public", methods=["GET"])
    def docbuilder_file(self, oo_security_token):
        """Serve the existing XLSX file for DocBuilder to open via builder.OpenFile()."""
        cache_data = _docbuilder_cache.get(oo_security_token)
        if not cache_data or cache_data.get("mode") != "insert_list":
            return request.make_response("Not found", status=404)

        xlsx_data = base64.b64decode(cache_data["xlsx_base64"])

        # Clean up cache now that both callback and file have been served
        del _docbuilder_cache[oo_security_token]

        headers = {
            "Content-Disposition": "attachment; filename='source.xlsx'",
            "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }
        return request.make_response(xlsx_data, headers)

    @http.route(
        "/onlyoffice/documents/evaluate_formulas_batch",
        auth="public",
        methods=["POST", "OPTIONS"],
        type="json",
        csrf=False,
        cors="*",
    )
    def evaluate_formulas_batch(self, document_id, formulas, jwt_token=None):
        """Evaluate multiple ODOO formulas in a single HTTP request.

        Snapshot is loaded once and shared across all formulas.
        read_group results are cached and reused across pivot cells.
        """
        if request.httprequest.method == "OPTIONS":
            return {}

        # Validate security token
        if not jwt_token:
            _logger.warning("evaluate_formulas_batch: no jwt_token provided for document %s", document_id)
            return {"error": "Security token required"}
        try:
            payload = jwt_utils.decode_token(request.env, jwt_token, config_utils.get_internal_jwt_secret(request.env))
            token_uid = payload.get("uid")
            token_doc_id = payload.get("document_id")
            if str(token_doc_id) != str(document_id):
                _logger.warning(
                    "evaluate_formulas_batch: token doc_id=%s != request doc_id=%s", token_doc_id, document_id
                )
                return {"error": "Token/document mismatch"}
            user = request.env["res.users"].sudo().browse(token_uid)
            document = request.env["documents.document"].with_user(user).browse(int(document_id))
            document.check_access_rule("read")
        except AccessError:
            _logger.warning("evaluate_formulas_batch: access denied for uid=%s doc=%s", token_uid, document_id)
            return {"error": "Access denied"}
        except Exception as e:
            _logger.warning("evaluate_formulas_batch: token validation failed for doc %s: %s", document_id, e)
            return {"error": "Invalid security token"}

        # Switch request env to authenticated user so domain resolution uses correct uid
        request.update_env(user=token_uid)

        # Load snapshot once for the whole batch
        snapshot = _formula_evaluator.load_document_snapshot(document_id)

        # Attach a read_group cache so pivot evaluations share results
        request._rg_cache = {}

        values = {}
        for formula in formulas or []:
            try:
                values[formula] = _formula_evaluator.evaluate_single_formula(snapshot, formula)
            except Exception as e:
                _logger.warning("Batch formula error for %s: %s", formula, e)
                values[formula] = f"#ERROR: {e}"

        return {"values": values}

    @http.route(
        "/onlyoffice/documents/insert_list_in_xlsx",
        auth="user",
        methods=["POST"],
        type="json",
        csrf=False,
    )
    def insert_list_in_xlsx(self, document_id, list_data, threshold=10, name="List"):
        """Insert an Odoo list as ODOO_LIST formulas into an existing XLSX document.

        Rebuilds the XLSX via DocBuilder: opens the existing file, adds a new
        sheet with formulas, and updates the _OdooMetadata hidden sheet.

        Args:
            document_id: target XLSX document ID
            list_data: dict with model, domain, orderBy, columns, context
            threshold: number of rows to insert
            name: name for the new sheet and list
        """
        try:
            document = request.env["documents.document"].browse(int(document_id))
            document.check_access_rule("write")
        except AccessError:
            return {"error": "Access denied"}

        if not document.exists() or not document.attachment_id:
            return {"error": "Document not found or has no attachment"}

        columns = list_data.get("columns", [])
        if not columns:
            return {"error": "No columns provided"}

        # Determine list_id from existing metadata
        existing_metadata = {}
        if document.onlyoffice_spreadsheet_metadata:
            try:
                existing_metadata = json.loads(document.onlyoffice_spreadsheet_metadata)
            except Exception:
                pass

        existing_lists = existing_metadata.get("lists", {})
        existing_pivots = existing_metadata.get("pivots", {})
        # Use a shared ID space: pick the next ID after the max of both lists and pivots
        all_ids = [int(k) for k in existing_lists.keys()] + [int(k) for k in existing_pivots.keys()]
        list_id = str(max(all_ids, default=0) + 1)

        # Add the new list definition to metadata
        existing_lists[list_id] = {
            "model": list_data.get("model", ""),
            "domain": list_data.get("domain", "[]"),
            "orderBy": list_data.get("orderBy", []),
            "columns": columns,
            "name": name,
        }
        existing_metadata["lists"] = existing_lists

        # Determine a unique sheet name by inspecting the existing XLSX
        sheet_name = name
        try:
            xlsx_data = base64.b64decode(document.attachment_id.datas)
            with zipfile.ZipFile(io.BytesIO(xlsx_data), "r") as zf:
                wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
                ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                sheets_el = wb_xml.find(f"{{{ns}}}sheets")
                existing_names = [s.get("name") for s in sheets_el.findall(f"{{{ns}}}sheet")]
                if sheet_name in existing_names:
                    i = 2
                    while f"{sheet_name} ({i})" in existing_names:
                        i += 1
                    sheet_name = f"{sheet_name} ({i})"
        except Exception:
            pass  # If parsing fails, DocBuilder will try the original name

        # Store data in cache for DocBuilder callback
        oo_security_token = secrets.token_urlsafe(32)
        output_filename = f"insert_list_{uuid.uuid4().hex[:8]}.xlsx"
        _docbuilder_cache[oo_security_token] = {
            "mode": "insert_list",
            "document_id": document_id,
            "xlsx_base64": document.attachment_id.datas,
            "list_id": list_id,
            "sheet_name": sheet_name,
            "columns_json": json.dumps(columns, cls=_DateTimeEncoder),
            "threshold": int(threshold),
            "metadata_json": json.dumps(existing_metadata, cls=_DateTimeEncoder),
            "output_filename": output_filename,
        }

        # Call DocBuilder
        xlsx_content, error = self._call_docbuilder(oo_security_token, document_id)
        if error:
            return {"error": f"DocBuilder error: {error}"}

        # Update the document's attachment with the rebuilt XLSX
        document.attachment_id.write({"datas": base64.b64encode(xlsx_content)})

        # Update metadata in DB
        document.write(
            {
                "onlyoffice_spreadsheet_metadata": json.dumps(existing_metadata, cls=_DateTimeEncoder),
            }
        )

        _logger.info("Inserted list '%s' (id=%s) into document %s via DocBuilder", name, list_id, document_id)

        return {
            "success": True,
            "document_id": document.id,
            "list_id": list_id,
            "sheet_name": sheet_name,
        }
