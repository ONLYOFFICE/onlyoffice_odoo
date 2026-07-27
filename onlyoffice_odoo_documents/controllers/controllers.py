# Copyright (C) 2026 Ascensio System SIA
import base64
import io
import json
import logging
import re
import secrets
import uuid
import zipfile
from datetime import date, datetime, timedelta
from mimetypes import guess_type
from urllib.request import urlopen
from xml.etree import ElementTree as ET

import markupsafe
import pytz
import requests
from werkzeug.exceptions import Forbidden

from odoo import fields, http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_open
from odoo.tools.translate import _

from odoo.addons.documents.controllers.documents import ShareRoute
from odoo.addons.onlyoffice_odoo.controllers.main import OnlyofficeConnector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils

from .spreadsheet_formulas import (
    SpreadsheetFormulaEvaluator,
    compute_filter_values,
    load_metadata_for_document,
)

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501


class _DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, o):
        if isinstance(o, datetime | date):
            return o.isoformat()
        return super().default(o)


# ── DocBuilder data cache (DB-backed) ────────────────────────────────────────
# The DocBuilder callback is a separate HTTP request that can be served by
# another Odoo worker, so the payload must be stored in the database and not
# in process memory.

_DOCBUILDER_CACHE_PREFIX = "onlyoffice_docbuilder_cache_"
_DOCBUILDER_CACHE_TTL_HOURS = 1

# Explicit mimetype for rewritten XLSX attachments: when writing 'datas' Odoo
# re-guesses the mimetype from content and may detect DocBuilder output as
# 'application/zip', which breaks the documents thumbnail and mimetype filters.
_XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _store_docbuilder_data(token, data):
    """Persist a DocBuilder payload so any worker can serve the callback."""
    attachments = request.env["ir.attachment"].sudo()
    # Drop stale entries left over from failed conversions
    stale_before = datetime.now() - timedelta(hours=_DOCBUILDER_CACHE_TTL_HOURS)
    attachments.search(
        [
            ("name", "like", _DOCBUILDER_CACHE_PREFIX + "%"),
            ("create_date", "<", fields.Datetime.to_string(stale_before)),
        ]
    ).unlink()
    attachments.create(
        {
            "name": _DOCBUILDER_CACHE_PREFIX + token,
            "raw": json.dumps(data, cls=_DateTimeEncoder).encode(),
        }
    )
    # Commit so the DocBuilder callback (served in a separate transaction,
    # possibly by another worker) can see the data immediately.
    request.env.cr.commit()


def _load_docbuilder_data(token):
    """Load a previously stored DocBuilder payload. Returns dict or None."""
    attachment = request.env["ir.attachment"].sudo().search([("name", "=", _DOCBUILDER_CACHE_PREFIX + token)], limit=1)
    return json.loads(attachment.raw) if attachment else None


def _delete_docbuilder_data(token):
    """Remove a stored DocBuilder payload (no-op when already deleted)."""
    request.env["ir.attachment"].sudo().search([("name", "=", _DOCBUILDER_CACHE_PREFIX + token)]).unlink()


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
            _logger.exception(f"Failed to create document {ex!s}")
            result["error"] = _("Failed to create document")

        return json.dumps(result)


class OnlyofficeDocuments_Inherited_Connector(OnlyofficeConnector):
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

            values = self.prepare_share_editor(document, access_token, share_id)
            values["editorConfig"] = markupsafe.Markup(json.dumps(values["editorConfig"]))
            try:
                session_info = request.env["ir.http"].get_frontend_session_info()
            except Exception:
                session_info = {}
            values["session_info"] = markupsafe.Markup(json.dumps(session_info))
            return request.render("onlyoffice_odoo.onlyoffice_editor", values)

        except Exception as ex:
            _logger.error("Failed to open shared document: %s", ex)

        return request.not_found()

    @http.route("/onlyoffice/editor/document/<int:document_id>", auth="public", type="http", website=True)
    def render_document_editor(self, document_id, access_token=None):
        values = self.prepare_document_editor(document_id, access_token)
        values["editorConfig"] = markupsafe.Markup(json.dumps(values["editorConfig"]))
        values["session_info"] = markupsafe.Markup(json.dumps(values["session_info"]))
        return request.render("onlyoffice_odoo.onlyoffice_editor", values)

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
            raise Forbidden()

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
        role = "viewer"
        access = (
            request.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if access:
            if access.link_access != "none":
                role = access.link_access
            else:
                role = None

        public_user = request.env.ref("base.public_user")
        current_user = request.env.user
        if current_user and current_user.id != public_user.id:
            access_user = (
                request.env["onlyoffice.odoo.documents.access.user"]
                .sudo()
                .search([("document_id", "=", document.id), ("user_id", "=", current_user.id)], limit=1)
            )
            if access_user and access_user.role != "none":
                role = access_user.role

        if not role:
            raise AccessError(_("User has no read access rights to open this document"))

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
            token_user = current_user if current_user and current_user.id != public_user.id else public_user
            security_token = jwt_utils.encode_payload(
                request.env, {"id": token_user.id}, config_utils.get_internal_jwt_secret(request.env)
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
            "editorConfig": root_config,
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
            can_write = False
            if access:
                if access.link_access in ("editor", "custom_filter"):
                    can_write = True

            if not can_write and user:
                access_user = (
                    request.env["onlyoffice.odoo.documents.access.user"]
                    .sudo()
                    .search([("document_id", "=", document.id), ("user_id", "=", user.id)], limit=1)
                )
                if access_user and access_user.role in ("editor", "custom_filter"):
                    can_write = True

            if not can_write:
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

            # Store data for the DocBuilder callback
            oo_security_token = secrets.token_urlsafe(32)
            output_filename = f"{document.name}_{uuid.uuid4().hex[:8]}.xlsx"
            _store_docbuilder_data(
                oo_security_token,
                {
                    "document_id": document_id,
                    "spreadsheet_json": spreadsheet_json,
                    "metadata_json": metadata_json,
                    "output_filename": output_filename,
                },
            )

            # Call DocBuilder service
            xlsx_content, error = self._call_docbuilder(oo_security_token, document_id)
            _delete_docbuilder_data(oo_security_token)
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
                    "mimetype": _XLSX_MIMETYPE,
                    "onlyoffice_spreadsheet_metadata": metadata_json,
                }
            )
            return existing_xlsx.id

        xlsx_doc = request.env["documents.document"].create(
            {
                "name": f"{document.name}_docbuilder.xlsx",
                "folder_id": document.folder_id.id,
                "datas": base64.b64encode(xlsx_content),
                "mimetype": _XLSX_MIMETYPE,
                "onlyoffice_spreadsheet_source_id": document_id,
                "onlyoffice_spreadsheet_metadata": metadata_json,
            }
        )
        return xlsx_doc.id

    @http.route("/onlyoffice/documents/docbuilder_callback/<string:oo_security_token>", auth="public", methods=["GET"])
    def docbuilder_callback(self, oo_security_token):
        """
        Callback endpoint for DocBuilder to get the conversion script.
        Supports two modes: 'convert_spreadsheet' (default) and 'insert_sheet'.
        """
        try:
            cache_data = _load_docbuilder_data(oo_security_token)

            if not cache_data:
                _logger.error("DocBuilder callback: token not found: %s", oo_security_token)
                return request.make_response("Token not found or expired", status=404)

            mode = cache_data.get("mode", "convert_spreadsheet")
            output_filename = cache_data["output_filename"]

            if mode == "insert_sheet":
                docbuilder_script = self._build_insert_sheet_script(cache_data, oo_security_token)
            else:
                # Default: convert_spreadsheet mode
                spreadsheet_json = cache_data["spreadsheet_json"]
                metadata_json = cache_data.get("metadata_json")
                with file_open("onlyoffice_odoo_documents/controllers/convert_spreadsheet.docbuilder", "r") as f:
                    docbuilder_script = f.read()
                docbuilder_script = docbuilder_script.replace("SPREADSHEET_DATA_PLACEHOLDER", spreadsheet_json)
                docbuilder_script = docbuilder_script.replace("METADATA_PLACEHOLDER", metadata_json or "null")
                docbuilder_script = docbuilder_script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{output_filename}"')

            headers = {
                "Content-Disposition": "attachment; filename='docbuilder_script.docbuilder'",
                "Content-Type": "text/plain; charset=utf-8",
            }
            return request.make_response(docbuilder_script.encode("utf-8"), headers)

        except Exception as e:
            _logger.exception("DocBuilder callback error: %s", e)
            return request.make_response(str(e), status=500)

    def _build_insert_sheet_script(self, cache_data, oo_security_token):
        """Build a DocBuilder script that opens an existing XLSX and adds a new sheet."""
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        file_url = f"{odoo_url}onlyoffice/documents/docbuilder_file/{oo_security_token}"

        with file_open("onlyoffice_odoo_documents/controllers/insert_sheet.docbuilder", "r") as f:
            script = f.read()

        script = script.replace("FILE_URL_PLACEHOLDER", f'"{file_url}"')
        script = script.replace("SHEET_NAME_PLACEHOLDER", json.dumps(cache_data["sheet_name"]))
        script = script.replace("CELLS_PLACEHOLDER", cache_data["cells_json"])
        script = script.replace("METADATA_PLACEHOLDER", cache_data["metadata_json"])
        script = script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{cache_data["output_filename"]}"')

        # Don't delete the cache entry yet — the file-serving route needs it
        return script

    @http.route("/onlyoffice/documents/docbuilder_file/<string:oo_security_token>", auth="public", methods=["GET"])
    def docbuilder_file(self, oo_security_token):
        """Serve the existing XLSX file for DocBuilder to open via builder.OpenFile()."""
        cache_data = _load_docbuilder_data(oo_security_token)
        if not cache_data or cache_data.get("mode") != "insert_sheet":
            return request.make_response("Not found", status=404)

        xlsx_data = base64.b64decode(cache_data["xlsx_base64"])

        # Clean up now that both the script and the file have been served
        _delete_docbuilder_data(oo_security_token)

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
        document, error = self._get_writable_document(document_id)
        if error:
            return {"error": error}

        columns = list_data.get("columns", [])
        if not columns:
            return {"error": "No columns provided"}

        # Add the new list definition to metadata (lists and pivots share the ID space)
        metadata, new_id = self._load_metadata_with_new_id(document)
        metadata.setdefault("lists", {})[new_id] = {
            "model": list_data.get("model", ""),
            "domain": list_data.get("domain", "[]"),
            "orderBy": list_data.get("orderBy", []),
            "context": list_data.get("context", {}),
            "columns": columns,
            "name": name,
        }

        cells = self._build_list_cells(new_id, columns, int(threshold))
        return self._insert_sheet_via_docbuilder(document, name, cells, metadata, new_id)

    @http.route(
        "/onlyoffice/documents/insert_pivot_in_xlsx",
        auth="user",
        methods=["POST"],
        type="json",
        csrf=False,
    )
    def insert_pivot_in_xlsx(self, document_id, pivot_data, name="Pivot"):
        """Insert an Odoo pivot as ODOO_PIVOT formulas into an existing XLSX document.

        Args:
            document_id: target XLSX document ID
            pivot_data: dict with model, domain, context, rowGroupBys, colGroupBys, measures
            name: name for the new sheet and pivot
        """
        document, error = self._get_writable_document(document_id)
        if error:
            return {"error": error}

        if not pivot_data.get("model"):
            return {"error": "No model provided"}

        measures = pivot_data.get("measures") or ["__count"]
        row_group_bys = pivot_data.get("rowGroupBys") or []
        col_group_bys = pivot_data.get("colGroupBys") or []

        # Add the new pivot definition to metadata (lists and pivots share the ID space)
        metadata, new_id = self._load_metadata_with_new_id(document)
        metadata.setdefault("pivots", {})[new_id] = {
            "model": pivot_data["model"],
            "domain": pivot_data.get("domain", "[]"),
            "context": pivot_data.get("context", {}),
            "measures": measures,
            "rowGroupBys": row_group_bys,
            "colGroupBys": col_group_bys,
            "name": name,
        }

        try:
            cells = self._build_pivot_cells(new_id, pivot_data, measures, row_group_bys, col_group_bys)
        except Exception as e:
            _logger.exception("Failed to build pivot cells: %s", e)
            return {"error": str(e)}

        return self._insert_sheet_via_docbuilder(document, name, cells, metadata, new_id)

    # ── Insert helpers ──────────────────────────────────────────────────────────

    @staticmethod
    def _get_writable_document(document_id):
        """Return (document, error) after checking write access and attachment."""
        try:
            document = request.env["documents.document"].browse(int(document_id))
            document.check_access_rule("write")
        except AccessError:
            return None, "Access denied"
        if not document.exists() or not document.attachment_id:
            return None, "Document not found or has no attachment"
        return document, None

    @staticmethod
    def _load_metadata_with_new_id(document):
        """Load existing metadata and allocate the next free list/pivot ID.

        Lists and pivots share the same ID space, like in documents_spreadsheet.
        """
        metadata = {}
        if document.onlyoffice_spreadsheet_metadata:
            try:
                metadata = json.loads(document.onlyoffice_spreadsheet_metadata)
            except Exception:
                metadata = {}
        used_ids = [int(k) for k in metadata.get("lists", {})] + [int(k) for k in metadata.get("pivots", {})]
        return metadata, str(max(used_ids, default=0) + 1)

    @staticmethod
    def _build_list_cells(list_id, columns, threshold):
        """Build the 2D cell grid (ODOO_LIST formulas) for a list sheet."""
        field_names = [col.get("name") if isinstance(col, dict) else str(col) for col in columns]
        header = [f'=ODOO_LIST_HEADER({list_id},"{fn}")' for fn in field_names]
        rows = [[f'=ODOO_LIST({list_id},{index},"{fn}")' for fn in field_names] for index in range(1, threshold + 1)]
        return [header] + rows

    def _build_pivot_cells(self, pivot_id, pivot_data, measures, row_group_bys, col_group_bys):
        """Build the 2D cell grid (ODOO_PIVOT formulas) replicating the Odoo pivot layout.

        Layout: one header row per column group level, one row with measure
        labels, then one row per row group path (parents before children,
        like the Odoo pivot view) and a final Total row.
        """
        model = request.env[pivot_data["model"]].sudo()
        domain = _formula_evaluator._parse_and_resolve_domain(pivot_data.get("domain", []))

        col_paths = self._pivot_group_paths(model, domain, col_group_bys)
        row_paths = _expand_group_paths(self._pivot_group_paths(model, domain, row_group_bys))

        # Data columns: one block of measures per column path, plus a Total block
        column_blocks = [list(path) for path in col_paths] + [[]]

        def pairs_literal(pairs):
            # Turn [(field_spec, value_literal), ...] into '"field",value,...'
            return ",".join(f'"{spec}",{value}' for spec, value in pairs)

        def header_formula(pairs, extra=""):
            args = pairs_literal(pairs)
            parts = [str(pivot_id)] + ([args] if args else []) + ([extra] if extra else [])
            return "=ODOO_PIVOT_HEADER(" + ",".join(parts) + ")"

        cells = []

        # Column group header rows (one per level)
        for level in range(len(col_group_bys)):
            row = [""]
            for block in column_blocks:
                if len(block) > level:
                    formula = header_formula(block[: level + 1])
                elif not block and level == 0:
                    formula = "Total"
                else:
                    formula = ""
                row.extend([formula] + [""] * (len(measures) - 1))
            cells.append(row)

        # Measure labels row
        measure_row = [""]
        for block in column_blocks:
            for measure in measures:
                measure_row.append(header_formula(block, f'"measure","{measure}"'))
        cells.append(measure_row)

        # Data rows (group paths in tree order) and the final Total row
        for path in [*row_paths, ()]:
            pairs = list(path)
            row = [header_formula(pairs) if pairs else "Total"]
            for block in column_blocks:
                for measure in measures:
                    args = pairs_literal(pairs + block)
                    parts = [str(pivot_id), f'"{measure}"'] + ([args] if args else [])
                    row.append("=ODOO_PIVOT(" + ",".join(parts) + ")")
            cells.append(row)

        return cells

    @staticmethod
    def _pivot_group_paths(model, domain, group_bys):
        """Return ordered unique group value paths as tuples of (field_spec, literal)."""
        if not group_bys:
            return []
        groups = SpreadsheetFormulaEvaluator._safe_read_group(model, domain, [], group_bys)
        paths = []
        seen = set()
        for group in groups or []:
            path = tuple((spec, _group_value_literal(model, spec, group)) for spec in group_bys)
            if path not in seen:
                seen.add(path)
                paths.append(path)
        return paths

    @staticmethod
    def _unique_sheet_name(document, name):
        """Pick a valid sheet name that does not clash with existing sheets in the XLSX."""
        # XLSX sheet names are limited to 31 chars and cannot contain []:*?/\
        sheet_name = re.sub(r"[\[\]:*?/\\]", " ", name or "Sheet").strip()[:31] or "Sheet"
        try:
            xlsx_data = base64.b64decode(document.attachment_id.datas)
            with zipfile.ZipFile(io.BytesIO(xlsx_data), "r") as zf:
                wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
                ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
                sheets_el = wb_xml.find(f"{{{ns}}}sheets")
                existing_names = [s.get("name") for s in sheets_el.findall(f"{{{ns}}}sheet")]
                if sheet_name in existing_names:
                    i = 2
                    while True:
                        suffix = f" ({i})"
                        candidate = sheet_name[: 31 - len(suffix)] + suffix
                        if candidate not in existing_names:
                            sheet_name = candidate
                            break
                        i += 1
        except Exception as ex:
            _logger.debug("Could not check existing sheet names: %s", ex)
        return sheet_name

    def _insert_sheet_via_docbuilder(self, document, name, cells, metadata, new_id):
        """Rebuild the XLSX via DocBuilder adding a new sheet, then save the result."""
        sheet_name = self._unique_sheet_name(document, name)
        metadata_json = json.dumps(metadata, cls=_DateTimeEncoder)

        oo_security_token = secrets.token_urlsafe(32)
        _store_docbuilder_data(
            oo_security_token,
            {
                "mode": "insert_sheet",
                "document_id": document.id,
                "xlsx_base64": document.attachment_id.datas.decode(),
                "sheet_name": sheet_name,
                "cells_json": json.dumps(cells, cls=_DateTimeEncoder),
                "metadata_json": metadata_json,
                "output_filename": f"insert_sheet_{uuid.uuid4().hex[:8]}.xlsx",
            },
        )

        xlsx_content, error = self._call_docbuilder(oo_security_token, document.id)
        _delete_docbuilder_data(oo_security_token)
        if error:
            return {"error": f"DocBuilder error: {error}"}

        # Update the document's attachment with the rebuilt XLSX and save metadata
        document.attachment_id.write({"datas": base64.b64encode(xlsx_content), "mimetype": _XLSX_MIMETYPE})
        document.write({"onlyoffice_spreadsheet_metadata": metadata_json})

        _logger.info("Inserted sheet '%s' (id=%s) into document %s via DocBuilder", sheet_name, new_id, document.id)

        return {
            "success": True,
            "document_id": document.id,
            "id": new_id,
            "sheet_name": sheet_name,
        }


def _expand_group_paths(leaf_paths):
    """Expand leaf group paths into tree order: every prefix appears once,
    parents before their children (like the Odoo pivot row headers)."""
    ordered = []
    seen = set()
    for path in leaf_paths:
        for depth in range(1, len(path) + 1):
            prefix = path[:depth]
            if prefix not in seen:
                seen.add(prefix)
                ordered.append(prefix)
    return ordered


def _group_value_literal(model, field_spec, group):
    """Convert a read_group value into an ODOO_PIVOT formula argument literal.

    Numbers are emitted bare, everything else as a quoted string matching the
    format that the server-side formula evaluator understands.
    """
    value = group.get(field_spec)
    field_name = field_spec.split(":")[0]
    granularity = field_spec.split(":")[1] if ":" in field_spec else None
    field_obj = model._fields.get(field_name)

    if value is None or value is False:
        return '"false"'
    if isinstance(value, list | tuple):  # many2one -> (id, display_name)
        return str(int(value[0]))
    if field_obj is not None and field_obj.type in ("date", "datetime"):
        is_datetime = field_obj.type == "datetime"
        return json.dumps(_format_date_group_value(group, field_spec, granularity or "month", is_datetime))
    if isinstance(value, bool):
        return '"true"'
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(str(value))


def _format_date_group_value(group, field_spec, granularity, is_datetime=False):
    """Convert a read_group date value into the pivot string format understood
    by the formula evaluator (e.g. '2/2026' for February 2026)."""
    range_info = (group.get("__range") or {}).get(field_spec) or {}
    start = str(range_info.get("from") or "")
    d = None
    if start:
        try:
            if is_datetime and len(start) >= 19:
                # Datetime ranges are returned in UTC while grouping is done in
                # the user's timezone: convert so month/day boundaries match.
                dt = pytz.utc.localize(datetime.strptime(start[:19], "%Y-%m-%d %H:%M:%S"))
                tz = pytz.timezone(request.env.user.tz or "UTC")
                d = dt.astimezone(tz).date()
            else:
                d = datetime.strptime(start[:10], "%Y-%m-%d").date()
        except (ValueError, pytz.UnknownTimeZoneError):
            d = None
    if d:
        if granularity == "year":
            return str(d.year)
        if granularity == "quarter":
            return f"{(d.month - 1) // 3 + 1}/{d.year}"
        if granularity == "week":
            iso = d.isocalendar()
            return f"{iso[1]}/{iso[0]}"
        if granularity == "day":
            return f"{d.month}/{d.day}/{d.year}"
        return f"{d.month}/{d.year}"  # month (default)
    return str(group.get(field_spec) or "")
