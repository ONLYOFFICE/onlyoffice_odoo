# Copyright (C) 2026 Ascensio System SIA
import base64
import calendar
import json
import logging
import re
import secrets
import uuid
from datetime import date, datetime
from mimetypes import guess_type
from urllib.request import urlopen

import markupsafe
import requests
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_open
from odoo.tools.safe_eval import safe_eval
from odoo.tools.translate import _

from odoo.addons.documents.controllers.documents import ShareRoute
from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils, url_utils

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501

# Global cache for DocBuilder conversion data (token -> data)
_docbuilder_cache = {}


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
            revisions = session_data.get("revisions", [])

            _logger.debug("Spreadsheet snapshot keys: %s, revisions: %d", list(snapshot.keys()), len(revisions))
            if not snapshot or "sheets" not in snapshot:
                result["error"] = _("Spreadsheet has no data or invalid structure")
                return result

            # Evaluate ODOO.* formulas and add their values to cells
            self._evaluate_odoo_formulas_in_snapshot(snapshot)

            class DateTimeEncoder(json.JSONEncoder):
                def default(self, obj):
                    if isinstance(obj, (datetime, date)):
                        return obj.isoformat()
                    return super().default(obj)

            spreadsheet_json = json.dumps(snapshot, cls=DateTimeEncoder)

            # Get DocBuilder URL
            docserver_url = config_utils.get_doc_server_public_url(request.env)
            docserver_url = url_utils.replace_public_url_to_internal(request.env, docserver_url)
            docbuilder_url = f"{docserver_url}docbuilder"

            # JWT settings
            jwt_header = config_utils.get_jwt_header(request.env)
            jwt_secret = config_utils.get_jwt_secret(request.env)

            # Generate unique security token
            oo_security_token = secrets.token_urlsafe(32)
            output_filename = f"{document.name}_{uuid.uuid4().hex[:8]}.xlsx"

            # Prepare metadata: resolve domains for lists and pivots
            metadata = {}
            if snapshot.get("lists"):
                lists_with_computed_domain = {}
                for list_id, list_data in snapshot["lists"].items():
                    list_copy = dict(list_data)
                    list_copy["domain"] = self._parse_and_resolve_domain(list_copy.get("domain", []))
                    lists_with_computed_domain[list_id] = list_copy
                metadata["lists"] = lists_with_computed_domain
            if snapshot.get("pivots"):
                pivots_with_computed_domain = {}
                for pivot_id, pivot_data in snapshot["pivots"].items():
                    pivot_copy = dict(pivot_data)
                    original_domain = pivot_copy.get("domain", [])
                    computed_domain = self._parse_and_resolve_domain(original_domain)
                    pivot_copy["domain"] = computed_domain
                    pivots_with_computed_domain[pivot_id] = pivot_copy
                metadata["pivots"] = pivots_with_computed_domain
            if snapshot.get("globalFilters"):
                metadata["globalFilters"] = snapshot["globalFilters"]

            metadata_json = json.dumps(metadata, cls=DateTimeEncoder) if metadata else None

            # Store data in global cache for callback
            _docbuilder_cache[oo_security_token] = {
                "document_id": document_id,
                "spreadsheet_json": spreadsheet_json,
                "metadata_json": metadata_json,
                "output_filename": output_filename,
            }

            # Prepare DocBuilder callback URL
            odoo_url = config_utils.get_base_or_odoo_url(request.env)
            docbuilder_callback_url = f"{odoo_url}onlyoffice/documents/docbuilder_callback/{oo_security_token}"

            # Prepare DocBuilder request with async callback
            docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
            docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

            if jwt_secret:
                docbuilder_payload["token"] = jwt_utils.encode_payload(request.env, docbuilder_payload, jwt_secret)
                docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
                    request.env, {"payload": docbuilder_payload}, jwt_secret
                )

            _logger.info("Calling DocBuilder to convert spreadsheet %s", document_id)

            response = requests.post(
                docbuilder_url,
                json=docbuilder_payload,
                headers=docbuilder_headers,
                timeout=300,  # 5 minutes timeout for large spreadsheets
            )

            if response.status_code != 200:
                _logger.error(f"DocBuilder error: {response.status_code} - {response.text}")
                result["error"] = _("DocBuilder conversion failed: %s") % response.text
                return result

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
                error_msg = error_messages.get(error_code, _("Error code: %s") % error_code)
                result["error"] = error_msg
                return result

            # Get the generated file URL
            urls = response_json.get("urls", {})
            if not urls:
                result["error"] = _("No output file generated")
                return result

            # Download the generated XLSX file
            xlsx_url = None
            for key, url in urls.items():
                if key.endswith(".xlsx"):
                    xlsx_url = url
                    break

            if not xlsx_url:
                # Try to get the first URL
                xlsx_url = list(urls.values())[0] if urls else None

            if not xlsx_url:
                result["error"] = _("No XLSX file in output")
                return result

            _logger.debug("Downloading converted XLSX from %s", xlsx_url)
            xlsx_response = requests.get(xlsx_url, timeout=60)

            if xlsx_response.status_code != 200:
                result["error"] = _("Failed to download converted file")
                return result

            xlsx_content = xlsx_response.content

            # Check if XLSX copy already exists
            existing_xlsx = request.env["documents.document"].search(
                [
                    ("onlyoffice_spreadsheet_source_id", "=", document_id),
                    ("name", "like", f"{document.name}_docbuilder%.xlsx"),
                ],
                limit=1,
            )

            if existing_xlsx:
                # Update existing
                existing_xlsx.write(
                    {
                        "datas": base64.b64encode(xlsx_content),
                        "onlyoffice_spreadsheet_metadata": metadata_json,
                    }
                )
                result["xlsx_id"] = existing_xlsx.id
            else:
                # Create new document
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
                result["xlsx_id"] = xlsx_doc.id

            _logger.info("Converted spreadsheet %s to XLSX %s", document_id, result["xlsx_id"])

        except Exception as e:
            _logger.exception("Error converting spreadsheet via DocBuilder: %s", e)
            result["error"] = str(e)

        return result

    @http.route("/onlyoffice/documents/docbuilder_callback/<string:oo_security_token>", auth="public", methods=["GET"])
    def docbuilder_callback(self, oo_security_token):
        """
        Callback endpoint for DocBuilder to get the conversion script.
        """
        try:
            # Get data from cache
            cache_data = _docbuilder_cache.get(oo_security_token)

            if not cache_data:
                _logger.error("DocBuilder callback: token not found: %s", oo_security_token)
                return request.make_response("Token not found or expired", status=404)

            spreadsheet_json = cache_data["spreadsheet_json"]
            output_filename = cache_data["output_filename"]

            # Read DocBuilder script template
            with file_open("onlyoffice_odoo_documents/controllers/convert_spreadsheet.docbuilder", "r") as f:
                docbuilder_script = f.read()

            # Replace placeholders in script
            docbuilder_script = docbuilder_script.replace("SPREADSHEET_DATA_PLACEHOLDER", spreadsheet_json)
            docbuilder_script = docbuilder_script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{output_filename}"')

            del _docbuilder_cache[oo_security_token]

            headers = {
                "Content-Disposition": "attachment; filename='convert_spreadsheet.docbuilder'",
                "Content-Type": "text/plain; charset=utf-8",
            }
            return request.make_response(docbuilder_script.encode("utf-8"), headers)

        except Exception as e:
            _logger.exception("DocBuilder callback error: %s", e)
            return request.make_response(str(e), status=500)

    def _parse_formula_args(self, args_str):
        """
        Parse formula arguments string into a list

        Examples:
            '1,"name"' -> [1, "name"]
            '1,5,"partner_id"' -> [1, 5, "partner_id"]

        Args:
            args_str: String of comma-separated arguments

        Returns:
            list: Parsed arguments
        """
        args = []
        pattern = r'"([^"]*)"|\'([^\']*)\'|([^,]+)'

        for match in re.finditer(pattern, args_str):
            if match.group(1):  # Double quoted string
                args.append(match.group(1))
            elif match.group(2):  # Single quoted string
                args.append(match.group(2))
            elif match.group(3):  # Number or identifier
                value = match.group(3).strip()
                # Try to convert to int/float
                try:
                    if "." in value:
                        args.append(float(value))
                    else:
                        args.append(int(value))
                except ValueError:
                    args.append(value)

        return args

    def _evaluate_single_formula(self, snapshot, formula):
        """Evaluate a single ODOO formula"""
        try:
            # Handle unary minus prefix
            negate = False
            clean_formula = formula
            if re.match(r"^=-\s*ODOO_", clean_formula):
                negate = True
                clean_formula = "=" + clean_formula[2:].lstrip()

            match = re.match(r"=ODOO_(\w+)\((.*)\)", clean_formula)
            if not match:
                return "#ERROR: Invalid formula"

            func_name = match.group(1)
            args_str = match.group(2)

            # Parse arguments
            args = self._parse_formula_args(args_str)

            # Call appropriate evaluation function
            result = None
            if func_name == "LIST":
                result = self._evaluate_odoo_list(snapshot, args)
            elif func_name == "LIST_HEADER":
                result = self._evaluate_odoo_list_header(snapshot, args)
            elif func_name == "PIVOT":
                result = self._evaluate_odoo_pivot(snapshot, args)
            elif func_name == "PIVOT_HEADER":
                result = self._evaluate_odoo_pivot_header(snapshot, args)
            elif func_name == "FILTER_VALUE":
                result = self._evaluate_odoo_filter_value(snapshot, args)
            elif func_name == "CURRENCY_RATE":
                result = self._evaluate_odoo_currency_rate(args)
            else:
                return f"#ERROR: Unknown function {func_name}"

            if negate and isinstance(result, (int, float)):
                result = -result
            return result

        except Exception as e:
            _logger.exception("Error evaluating formula %s: %s", formula, e)
            return f"#ERROR: {str(e)}"

    def _load_document_snapshot(self, document_id):
        """Load the spreadsheet snapshot for a document.

        Returns the snapshot dict (pivots, lists, etc.).
        Caches the result on the request object so repeated calls are free.
        """
        cache_key = f"_doc_snapshot_{document_id}"
        cached = getattr(request, cache_key, None)
        if cached is not None:
            return cached

        document = request.env["documents.document"].sudo().browse(int(document_id))

        if document.onlyoffice_spreadsheet_metadata:
            try:
                snapshot = json.loads(document.onlyoffice_spreadsheet_metadata)
                setattr(request, cache_key, snapshot)
                return snapshot
            except Exception:
                pass

        source_document = document
        if document.onlyoffice_spreadsheet_source_id:
            source_document = document.onlyoffice_spreadsheet_source_id

        session_data = source_document.join_spreadsheet_session()
        snapshot = session_data.get("data", {})
        setattr(request, cache_key, snapshot)
        return snapshot

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

        This dramatically reduces overhead compared to one request per formula:
        - Snapshot is loaded once and shared across all formulas
        - read_group results are cached and reused across pivot cells

        Args:
            document_id: ID of the document
            formulas: List of formula strings
            jwt_token: JWT security token (required)

        Returns:
            dict: {"values": {formula: result, ...}}
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
            # Verify user still has access to the document
            user = request.env["res.users"].sudo().browse(token_uid)
            document = request.env["documents.document"].with_user(user).browse(int(document_id))
            document.check_access_rule("read")
        except AccessError:
            _logger.warning("evaluate_formulas_batch: access denied for uid=%s doc=%s", token_uid, document_id)
            return {"error": "Access denied"}
        except Exception as e:
            _logger.warning("evaluate_formulas_batch: token validation failed for doc %s: %s", document_id, e)
            return {"error": "Invalid security token"}

        _logger.info(
            "Batch evaluating %d formulas for document %s",
            len(formulas) if formulas else 0,
            document_id,
        )

        # Load snapshot once for the whole batch
        snapshot = self._load_document_snapshot(document_id)

        # Attach a read_group cache to the request so _evaluate_odoo_pivot
        # can reuse results across multiple cells in the same pivot
        request._rg_cache = {}

        values = {}
        for formula in formulas or []:
            try:
                value = self._evaluate_single_formula(snapshot, formula)
                values[formula] = value
            except Exception as e:
                _logger.warning("Batch formula error for %s: %s", formula, e)
                values[formula] = f"#ERROR: {e}"

        _logger.info("Batch evaluation complete: %d results", len(values))
        return {"values": values}

    def _replace_filter_refs_in_snapshot(self, snapshot):
        """Replace ``ODOO.FILTER.VALUE("X")`` in cell *content* with references
        to a dedicated ``_Filters`` sheet (e.g. ``'_Filters'!B1``).

        This keeps filter values **dynamic** — the user can edit the value on
        the ``_Filters`` sheet and every formula that references it will
        recalculate.  At the same time it avoids the async-custom-function
        problem: ``&`` concatenation with a cell reference is synchronous, so
        ``"01/"&'_Filters'!B1`` resolves correctly before being passed to
        ``ODOO_PIVOT``.

        Example::

            =ODOO.PIVOT("1","bal","date:month","01/"&ODOO.FILTER.VALUE("Year"))
            →  =ODOO.PIVOT("1","bal","date:month","01/"&'_Filters'!B1)

            ="Budget Report - "&ODOO.FILTER.VALUE("Year")
            →  ="Budget Report - "&'_Filters'!B1
        """
        # Collect unique filter names across all sheets
        pattern = re.compile(r'ODOO\.FILTER\.VALUE\("([^"]*)"\)')
        filter_names = set()
        for sheet in snapshot.get("sheets", []):
            for cell_data in sheet.get("cells", {}).values():
                content = cell_data.get("content", "")
                if isinstance(content, str) and "ODOO.FILTER.VALUE" in content:
                    filter_names.update(m.group(1) for m in pattern.finditer(content))

        if not filter_names:
            return

        # --- Step 2: evaluate each filter value, build mapping --------------
        filter_names = sorted(filter_names)
        filter_map = {}  # name  → cell reference string
        filters_cells = {}  # cell addr → cell data for the _Filters sheet

        for idx, name in enumerate(filter_names):
            row = idx + 1
            try:
                value = self._evaluate_odoo_filter_value(snapshot, [name])
            except Exception:
                value = ""
            cell_ref = f"'_Filters'!B{row}"
            filter_map[name] = cell_ref
            filters_cells[f"A{row}"] = {"content": name}
            filters_cells[f"B{row}"] = {"content": str(value) if value else ""}

        _logger.debug("_Filters sheet: %s", filter_map)

        # Append _Filters sheet to snapshot
        snapshot.setdefault("sheets", []).append(
            {
                "id": "_filters_sheet_id",
                "name": "_Filters",
                "cells": filters_cells,
            }
        )

        # Replace ODOO.FILTER.VALUE("X") with cell references
        def _replace(m):
            return filter_map.get(m.group(1), m.group(0))

        for sheet in snapshot.get("sheets", []):
            if sheet.get("id") == "_filters_sheet_id":
                continue
            for cell_data in sheet.get("cells", {}).values():
                content = cell_data.get("content", "")
                if not isinstance(content, str) or "ODOO.FILTER.VALUE" not in content:
                    continue
                new_content = pattern.sub(_replace, content)
                if new_content != content:
                    _logger.debug("Filter ref: %s -> %s", content, new_content)
                    cell_data["content"] = new_content

    def _evaluate_odoo_formulas_in_snapshot(self, snapshot):
        """
        Evaluate all ODOO.* formulas in the snapshot and add their values to cells
        This is needed for DocBuilder conversion where custom functions are not available
        """
        for sheet in snapshot.get("sheets", []):
            cells = sheet.get("cells", {})

            for _cell_address, cell_data in cells.items():
                content = cell_data.get("content", "")

                # Check if it's an ODOO formula (also handle =-ODOO. prefix)
                if not isinstance(content, str):
                    continue
                if "ODOO." not in content:
                    continue
                if not (content.startswith("=ODOO.") or content.startswith("=-ODOO.")):
                    continue

                try:
                    # Handle unary minus prefix: =-ODOO.PIVOT(...)
                    negate = False
                    clean_content = content
                    if clean_content.startswith("=-"):
                        negate = True
                        clean_content = "=" + clean_content[2:].lstrip()

                    # Resolve nested ODOO calls and & concatenation
                    # e.g. "1/"&ODOO.FILTER.VALUE("Year") → "1/2024"
                    clean_content = self._resolve_nested_odoo_calls(snapshot, clean_content)

                    # Parse the formula to extract function name and arguments
                    # Format: =ODOO.FUNCTION(arg1, arg2, ...)
                    match = re.match(r"^=ODOO\.([A-Z._]+)\((.*)\)$", clean_content)
                    if not match:
                        _logger.warning("Could not parse ODOO formula: %s", content)
                        continue

                    function_name = f"ODOO.{match.group(1)}"
                    args_str = match.group(2)

                    # Simple argument parsing (handles strings and numbers)
                    # Note: This is simplified and may not handle all cases
                    args = []
                    if args_str:
                        # Split by comma, but respect quoted strings
                        current_arg = ""
                        in_quotes = False
                        for char in args_str:
                            if char == '"':
                                in_quotes = not in_quotes
                            elif char == "," and not in_quotes:
                                args.append(self._parse_formula_arg(current_arg.strip()))
                                current_arg = ""
                                continue
                            current_arg += char
                        if current_arg:
                            args.append(self._parse_formula_arg(current_arg.strip()))

                    # Evaluate the function
                    value = None
                    if function_name == "ODOO.LIST":
                        value = self._evaluate_odoo_list(snapshot, args)
                    elif function_name == "ODOO.LIST.HEADER":
                        value = self._evaluate_odoo_list_header(snapshot, args)
                    elif function_name == "ODOO.PIVOT":
                        value = self._evaluate_odoo_pivot(snapshot, args)
                    elif function_name == "ODOO.PIVOT.HEADER":
                        value = self._evaluate_odoo_pivot_header(snapshot, args)
                    elif function_name == "ODOO.PIVOT.TABLE":
                        value = self._evaluate_odoo_pivot_table(snapshot, args)
                    elif function_name == "ODOO.FILTER.VALUE":
                        value = self._evaluate_odoo_filter_value(snapshot, args)
                    elif function_name == "ODOO.CURRENCY.RATE":
                        value = self._evaluate_odoo_currency_rate(args)

                    # Apply negation if formula had =-ODOO. prefix
                    if negate and value is not None and isinstance(value, (int, float)):
                        value = -value

                    # Add the evaluated value to the cell
                    if value is not None:
                        cell_data["value"] = value
                        _logger.debug("Evaluated %s = %s", content, value)

                except Exception as e:
                    _logger.warning("Error evaluating formula %s: %s", content, e)
                    cell_data["value"] = ""

    def _parse_and_resolve_domain(self, domain_value):
        """
        Parse domain from snapshot (may be a string or list) and resolve
        special placeholders like 'uid' with actual values.

        Returns a proper Python list suitable for Odoo ORM search().
        """
        user_id = request.env.user.id
        eval_context = {"uid": user_id, "user": request.env.user}

        # String domain — use safe_eval which handles uid, user, etc.
        if isinstance(domain_value, str):
            domain_str = domain_value.strip()
            if not domain_str or domain_str == "[]":
                return []
            try:
                domain_value = safe_eval(domain_str, eval_context)
            except Exception:
                _logger.warning("Failed to parse domain string: %s", domain_str)
                return []

        # List/tuple domain — replace "uid" string values in leaf tuples
        if isinstance(domain_value, (list, tuple)):
            result = []
            for item in domain_value:
                if isinstance(item, (list, tuple)) and len(item) == 3:
                    field, operator, value = item
                    if value == "uid":
                        result.append([field, operator, user_id])
                    else:
                        result.append(list(item))
                else:
                    result.append(item)
            return result

        return []

    def _resolve_nested_odoo_calls(self, snapshot, content):
        """Resolve nested ODOO function calls and & concatenation in a formula.

        Handles patterns like:
          "1/"&ODOO.FILTER.VALUE("Year")  →  "1/2024"
          ODOO.FILTER.VALUE("Year")       →  "2024"

        This is called before the main formula is parsed, so that nested
        calls are replaced with their evaluated values.
        """

        def _replace_filter_value(m):
            filter_name = m.group(1)
            try:
                val = self._evaluate_odoo_filter_value(snapshot, [filter_name])
                return str(val) if val is not None else ""
            except Exception:
                return ""

        # Replace all ODOO.FILTER.VALUE("name") calls with their values
        resolved = re.sub(r'ODOO\.FILTER\.VALUE\("([^"]*)"\)', _replace_filter_value, content)

        # Evaluate & (concatenation) between string literals:
        # "1/"&"2024" → "1/2024"
        # Process until no more & concatenation is possible
        while "&" in resolved:
            # Pattern: "str1"&"str2" or "str1"& value or value &"str2"
            new_resolved = re.sub(r'"([^"]*)"&"([^"]*)"', r'"\1\2"', resolved)
            if new_resolved == resolved:
                # Try: "str"&bareword or bareword&"str"
                new_resolved = re.sub(r'"([^"]*)"&(\w+)', lambda m: f'"{m.group(1)}{m.group(2)}"', new_resolved)
                new_resolved = re.sub(r'(\w+)&"([^"]*)"', lambda m: f'"{m.group(1)}{m.group(2)}"', new_resolved)
                if new_resolved == resolved:
                    break
            resolved = new_resolved

        return resolved

    def _parse_formula_arg(self, arg):
        """Parse a single formula argument (string or number)"""
        # Remove quotes from strings
        if arg.startswith('"') and arg.endswith('"'):
            return arg[1:-1]
        # Try to parse as number
        try:
            if "." in arg:
                return float(arg)
            return int(arg)
        except ValueError:
            return arg

    def _evaluate_odoo_list(self, snapshot, args):
        """Evaluate ODOO.LIST function - fetch LIVE data from database"""
        if len(args) < 3:
            raise ValueError("ODOO.LIST requires 3 arguments: list_id, index, field_name")

        list_id = str(args[0])
        index = int(args[1]) - 1  # Convert to 0-based index
        field_name = str(args[2])

        # Get list data from snapshot
        lists = snapshot.get("lists", {})
        if list_id not in lists:
            raise ValueError(f"List with id '{list_id}' not found")

        list_data = lists[list_id]
        model_name = list_data.get("model")
        raw_domain = list_data.get("domain", [])
        order_by = list_data.get("orderBy", [])

        # Parse and resolve domain (handles string domains and uid placeholder)
        domain = self._parse_and_resolve_domain(raw_domain)

        # Convert orderBy to Odoo order string
        # orderBy format: [{"name": "field_name", "asc": true/false}, ...]
        order_str = None
        if order_by:
            order_parts = []
            for order_item in order_by:
                field_name_order = order_item.get("name", "")
                asc = order_item.get("asc", True)
                if field_name_order:
                    order_parts.append(f"{field_name_order} {'ASC' if asc else 'DESC'}")
            if order_parts:
                order_str = ", ".join(order_parts)

        _logger.debug("ODOO_LIST: model=%s, domain=%s, order=%s, offset=%s", model_name, domain, order_str, index)

        # Fetch records from database with proper order
        records = request.env[model_name].sudo().search(domain, limit=1, offset=index, order=order_str)

        if not records:
            return ""

        record = records[0]
        model = request.env[model_name].sudo()
        field_obj = model._fields.get(field_name)
        field_value = record[field_name] if field_name in record else None

        # Handle different field types
        if field_value is None or field_value is False:
            return ""
        elif field_obj and field_obj.type == "selection":
            # Return human-readable label instead of raw value
            selection = dict(model._fields[field_name]._description_selection(model.env))
            return selection.get(field_value, field_value)
        elif hasattr(field_value, "_name"):  # Odoo recordset (Many2one, Many2many, One2many)
            if len(field_value) == 0:
                return ""
            elif len(field_value) == 1:
                return field_value.display_name if hasattr(field_value, "display_name") else str(field_value)
            else:
                return ", ".join([r.display_name if hasattr(r, "display_name") else str(r) for r in field_value])
        else:
            return field_value

    def _evaluate_odoo_list_header(self, snapshot, args):
        """Evaluate ODOO.LIST.HEADER function - get field label"""
        if len(args) < 2:
            raise ValueError("ODOO.LIST.HEADER requires 2 arguments: list_id, field_name")

        list_id = str(args[0])
        field_name = str(args[1])

        # Get list data from snapshot
        lists = snapshot.get("lists", {})
        if list_id not in lists:
            raise ValueError(f"List with id '{list_id}' not found")

        list_data = lists[list_id]
        model_name = list_data.get("model")

        # Get field label from model
        model = request.env[model_name].sudo()
        field = model._fields.get(field_name)
        return field.string if field else field_name

    def _evaluate_odoo_pivot(self, snapshot, args):
        """Evaluate ODOO.PIVOT function using read_group with actual groupBy fields.

        This replicates the original Odoo pivot behavior: instead of converting
        formula domain args to date-range conditions (which can mismatch Odoo's
        internal date_trunc grouping), we call read_group with the same groupBy
        fields and then find the matching group in the results.

        Formula: =ODOO.PIVOT(pivot_id, measure, field1, value1, field2, value2, ...)
        The field/value pairs identify the exact cell in the pivot table.
        """
        if len(args) < 2:
            raise ValueError("ODOO.PIVOT requires at least 2 arguments: pivot_id, measure_name")

        pivot_id = str(args[0])
        measure = str(args[1])
        domain_args = args[2:] if len(args) > 2 else []

        pivots = snapshot.get("pivots", {})
        if pivot_id not in pivots:
            raise ValueError(f"Pivot with id '{pivot_id}' not found")

        pivot_data = pivots[pivot_id]
        model_name = pivot_data.get("model")
        base_domain = self._parse_and_resolve_domain(pivot_data.get("domain", []))

        # Parse formula domain args into field/value pairs
        pairs = []
        i = 0
        while i + 1 < len(domain_args):
            field_spec = str(domain_args[i])
            value = domain_args[i + 1]
            if field_spec != "measure":
                pairs.append((field_spec, value))
            i += 2

        # Determine measure field for read_group
        measure_field = measure.split(":")[0] if ":" in measure else measure
        fields_to_read = [] if measure == "__count" else [measure]

        model = request.env[model_name].sudo()

        if not pairs:
            # Grand total — no groupBy needed
            _logger.debug("ODOO_PIVOT grand total: model=%s, measure=%s", model_name, measure)
            try:
                result = model.read_group(base_domain, fields_to_read, [], lazy=False)
            except Exception as e:
                _logger.warning("ODOO_PIVOT read_group error: %s", e)
                return 0
            if not result:
                return 0
            if measure == "__count":
                return result[0].get("__count", 0)
            return result[0].get(measure_field, 0)

        # Collect groupBy specs from formula domain args
        extra_domain = []
        group_bys = []
        for field_spec, value in pairs:
            if ":" in field_spec:
                field_name = field_spec.split(":")[0]
            else:
                field_name = field_spec
            field_obj = model._fields.get(field_name)

            if field_obj and field_obj.type in ("date", "datetime") and ":" in field_spec:
                group_bys.append(field_spec)
            else:
                group_bys.append(field_spec)
                # Build extra_domain for non-batch (single request) mode
                if value == "false" or value is False:
                    extra_domain.append((field_name, "=", False))
                elif field_obj and field_obj.type in ("many2one", "many2many", "one2many", "integer"):
                    try:
                        extra_domain.append((field_name, "=", int(value)))
                    except (ValueError, TypeError):
                        extra_domain.append((field_name, "=", value))
                elif field_obj and field_obj.type == "boolean":
                    extra_domain.append((field_name, "=", str(value).lower() == "true"))
                else:
                    extra_domain.append((field_name, "=", value))

        # Check for batch-level read_group cache
        _rg_cache = getattr(request, "_rg_cache", None)

        if _rg_cache is not None:
            # Batch mode: use only base_domain for broader cache hits.
            # One read_group result serves ALL cells with the same pivot+groupBys.
            cache_key = (model_name, str(base_domain), tuple(group_bys), tuple(fields_to_read))
            if cache_key in _rg_cache:
                groups = _rg_cache[cache_key]
                _logger.debug("ODOO_PIVOT cache HIT: %s (%d groups)", cache_key[:2], len(groups))
            else:
                _logger.debug(
                    "ODOO_PIVOT batch: model=%s, measure=%s, group_bys=%s",
                    model_name,
                    measure,
                    group_bys,
                )
                try:
                    groups = model.read_group(base_domain, fields_to_read, group_bys, lazy=False)
                except Exception as e:
                    _logger.warning("ODOO_PIVOT read_group error: %s", e)
                    return 0
                _rg_cache[cache_key] = groups
                _logger.debug("ODOO_PIVOT cache STORE: %d groups", len(groups))
        else:
            # Single-request mode: narrow domain for efficiency
            combined_domain = base_domain + extra_domain
            _logger.debug(
                "ODOO_PIVOT single: model=%s, measure=%s, group_bys=%s",
                model_name,
                measure,
                group_bys,
            )
            try:
                groups = model.read_group(combined_domain, fields_to_read, group_bys, lazy=False)
            except Exception as e:
                _logger.warning("ODOO_PIVOT read_group error: %s", e)
                return 0

        if not groups:
            return 0

        # Find the matching group by comparing values
        for group in groups:
            if self._pivot_group_matches(group, pairs, model):
                if measure == "__count":
                    return group.get("__count", 0)
                return group.get(measure_field, 0)

        _logger.debug("ODOO_PIVOT: no matching group among %d groups", len(groups))
        return 0

    def _pivot_group_matches(self, group, pairs, model):
        """Check if a read_group result matches the formula's field/value pairs.

        Handles date fields (using __range or label parsing), relational fields
        (comparing IDs from [id, name] tuples), and simple fields.
        """
        for field_spec, expected_value in pairs:
            group_value = group.get(field_spec)

            if ":" in field_spec:
                field_name, granularity = field_spec.split(":", 1)
                field_obj = model._fields.get(field_name)

                if field_obj and field_obj.type in ("date", "datetime"):
                    if not self._pivot_date_matches(group, field_spec, granularity, expected_value):
                        return False
                    continue

            # Handle "false" value
            if (expected_value == "false" or expected_value is False) and group_value is False:
                continue

            # Relational field: read_group returns [id, name] tuple
            if isinstance(group_value, (list, tuple)) and len(group_value) >= 2:
                try:
                    if int(group_value[0]) != int(expected_value):
                        return False
                except (ValueError, TypeError):
                    if str(group_value[0]) != str(expected_value):
                        return False
            else:
                # Simple field — string comparison
                if str(group_value) != str(expected_value):
                    return False

        return True

    def _pivot_date_matches(self, group, field_spec, granularity, expected_value):
        """Check if a read_group result's date field matches the expected value.

        Uses __range (reliable raw dates) for month/day/quarter/year,
        and label parsing for week (since Odoo week numbering may differ from ISO).
        """
        expected_str = str(expected_value)

        if granularity == "week":
            # Odoo always formats week as "W{N} {YYYY}" regardless of locale
            label = group.get(field_spec)
            if not label or not isinstance(label, str):
                return False
            try:
                parts = label.split(" ")
                week_num = int(parts[0][1:])  # Remove 'W'
                year = parts[1]
                normalized = f"{week_num}/{year}"
                exp_parts = expected_str.split("/")
                exp_normalized = f"{int(exp_parts[0])}/{exp_parts[1]}"
                return normalized == exp_normalized
            except (IndexError, ValueError):
                return False

        # For month/day/quarter/year — use __range which has raw from/to dates
        range_data = group.get("__range", {}).get(field_spec, {})
        from_date = range_data.get("from", "") if range_data else ""

        if not from_date:
            return group.get(field_spec) is False and (expected_str == "false")

        try:
            # from_date is "2010-01-01 00:00:00" or "2010-01-01"
            date_part = from_date.split(" ")[0]
            parts = date_part.split("-")
            year_s, month_s, day_s = parts[0], parts[1], parts[2]

            if granularity == "month":
                # Expected: "01/2010", from_date starts "2010-01-01"
                return f"{month_s}/{year_s}" == expected_str

            elif granularity == "quarter":
                # Expected: "1/2010"
                quarter = (int(month_s) - 1) // 3 + 1
                exp_parts = expected_str.split("/")
                return f"{quarter}/{year_s}" == f"{int(exp_parts[0])}/{exp_parts[1]}"

            elif granularity == "year":
                return str(int(year_s)) == str(int(float(expected_str)))

            elif granularity == "day":
                # Expected: "MM/dd/yyyy"
                return f"{month_s}/{day_s}/{year_s}" == expected_str

        except (IndexError, ValueError) as e:
            _logger.warning("_pivot_date_matches parse error: %s", e)
            return False

        return False

    def _evaluate_odoo_pivot_header(self, snapshot, args):
        """Evaluate ODOO.PIVOT.HEADER function — returns display names for pivot groups.

        Formula: =ODOO.PIVOT.HEADER(pivot_id, field1, value1, field2, value2, ...)
        - No domain args → "Total"
        - field == "measure" → label of the measure field
        - Relation field → display_name of the related record
        - Date field → formatted date string
        - Selection field → selection label
        """
        if len(args) < 1:
            raise ValueError("ODOO.PIVOT.HEADER requires at least 1 argument: pivot_id")

        pivot_id = str(args[0])
        domain_args = args[1:] if len(args) > 1 else []

        pivots = snapshot.get("pivots", {})
        if pivot_id not in pivots:
            raise ValueError(f"Pivot with id '{pivot_id}' not found")

        pivot_data = pivots[pivot_id]

        if not domain_args or len(domain_args) < 2:
            return "Total"

        field_spec = str(domain_args[-2])
        value = domain_args[-1]

        # Handle "measure" pseudo-field
        if field_spec == "measure":
            return self._get_pivot_measure_label(pivot_data, str(value))

        # Handle "false" value
        if value == "false" or value is False:
            return "None"

        # Parse field:granularity
        if ":" in field_spec:
            field_name, granularity = field_spec.split(":", 1)
        else:
            field_name = field_spec
            granularity = None

        model_name = pivot_data.get("model")
        model = request.env[model_name].sudo()
        field_obj = model._fields.get(field_name)

        if not field_obj:
            return str(value)

        # Date/datetime fields — format based on granularity
        if field_obj.type in ("date", "datetime") and granularity:
            return self._format_pivot_date_header(granularity, value)

        # Relational fields — get display_name of the related record
        if field_obj.type in ("many2one", "many2many", "one2many") and field_obj.comodel_name:
            try:
                record = request.env[field_obj.comodel_name].sudo().browse(int(value))
                if record.exists():
                    return record.display_name or str(value)
            except (ValueError, TypeError):
                pass
            return str(value)

        # Selection — get the human-readable label
        if field_obj.type == "selection":
            try:
                fields_info = model.fields_get([field_name])
                selection = dict(fields_info.get(field_name, {}).get("selection", []))
                return selection.get(str(value), str(value))
            except Exception:
                pass

        return str(value)

    def _evaluate_odoo_pivot_table(self, snapshot, args):
        """Evaluate ODOO.PIVOT.TABLE function — returns a 2D array of pivot data.

        This is a complex function. We build a full pivot table by running
        read_group queries for each combination of row and column group values.
        """
        if len(args) < 1:
            raise ValueError("ODOO.PIVOT.TABLE requires at least 1 argument: pivot_id")

        pivot_id = str(args[0])

        pivots = snapshot.get("pivots", {})
        if pivot_id not in pivots:
            raise ValueError(f"Pivot with id '{pivot_id}' not found")

        pivot_data = pivots[pivot_id]
        model_name = pivot_data.get("model")
        base_domain = self._parse_and_resolve_domain(pivot_data.get("domain", []))
        measures = self._get_pivot_measures(pivot_data)
        row_group_bys = pivot_data.get("rowGroupBys", [])
        col_group_bys = pivot_data.get("colGroupBys", [])

        model = request.env[model_name].sudo()
        measure_fields = [m for m in measures if m != "__count"]

        # Simple implementation: read_group by all groupbys combined
        all_group_bys = row_group_bys + col_group_bys
        if not all_group_bys:
            # No groupby — just return totals
            result = model.read_group(base_domain, measure_fields, [], lazy=False)
            if not result:
                return [["Total", 0]]
            row = ["Total"]
            for m in measures:
                key = m.split(":")[0] if ":" in m else m
                row.append(result[0].get(key if m != "__count" else "__count", 0))
            return [row]

        try:
            groups = model.read_group(base_domain, measure_fields, all_group_bys, lazy=False)
        except Exception as e:
            _logger.warning("ODOO.PIVOT.TABLE read_group error: %s", e)
            return [["Error", str(e)]]

        # Build table rows
        table = []
        # Header row
        header = list(all_group_bys) + measures
        table.append(header)
        for group in groups:
            row = []
            for gb in all_group_bys:
                val = group.get(gb)
                if isinstance(val, (list, tuple)) and len(val) == 2:
                    row.append(val[1])  # display name for Many2one
                else:
                    row.append(val)
            for m in measures:
                key = m.split(":")[0] if ":" in m else m
                row.append(group.get(key if m != "__count" else "__count", 0))
            table.append(row)

        return table

    def _evaluate_odoo_filter_value(self, snapshot, args):
        """Evaluate ODOO.FILTER.VALUE function — returns the current value of a filter.

        Note: In the original Odoo spreadsheet, ODOO.FILTER.VALUE returns the
        *currently selected* filter value.  We only have the snapshot, so we
        check ``currentValue`` first (set when the user changes a filter),
        then fall back to ``defaultValue``.

        Odoo stores date-type filter values as dicts:
          {"yearOffset": 0}            → current year
          {"yearOffset": -1}           → last year
          {"yearOffset": 0, "period": "february"}  → February of current year
        String shortcuts in defaultValue ("this_year", "this_month",
        "this_quarter") are resolved to the corresponding yearOffset dict.
        """
        if len(args) < 1:
            raise ValueError("ODOO.FILTER.VALUE requires 1 argument: filter_name")

        filter_name = str(args[0])

        global_filters = snapshot.get("globalFilters", [])

        for filter_data in global_filters:
            if filter_data.get("label") == filter_name:
                # Prefer currentValue (runtime selection) over defaultValue
                value = filter_data.get("currentValue") or filter_data.get("defaultValue")
                _logger.debug("FILTER.VALUE('%s'): using=%s", filter_name, value)

                if not value:
                    return ""

                # Handle string shortcuts stored in defaultValue
                if isinstance(value, str):
                    if value == "this_year":
                        value = {"yearOffset": 0}
                    elif value == "last_year":
                        value = {"yearOffset": -1}
                    elif value == "this_month":
                        now = datetime.now()
                        value = {"yearOffset": 0, "period": f"{now.month:02d}"}
                    elif value == "this_quarter":
                        q = (datetime.now().month - 1) // 3 + 1
                        value = {"yearOffset": 0, "period": f"q{q}"}
                    else:
                        return str(value)

                if isinstance(value, dict):
                    # Date filter: {"yearOffset": N, "period": "..."}
                    if "yearOffset" in value:
                        year = datetime.now().year + int(value.get("yearOffset", 0))
                        return str(year)
                    # Relation filter: {"value": 123, "label": "..."}
                    if "value" in value:
                        return str(value["value"])
                    # Unknown dict format — log and return empty
                    _logger.warning(
                        "FILTER.VALUE('%s'): unhandled dict format: %s",
                        filter_name,
                        value,
                    )
                    return ""

                return str(value)

        _logger.warning("FILTER.VALUE('%s'): filter not found in globalFilters", filter_name)
        return ""

    def _evaluate_odoo_currency_rate(self, args):
        """Evaluate ODOO.CURRENCY.RATE function — returns exchange rate between currencies."""
        if len(args) < 2:
            raise ValueError("ODOO.CURRENCY.RATE requires at least 2 arguments: currency_from, currency_to")

        currency_from = str(args[0])
        currency_to = str(args[1])

        try:
            from_currency = request.env["res.currency"].sudo().search([("name", "=", currency_from)], limit=1)
            to_currency = request.env["res.currency"].sudo().search([("name", "=", currency_to)], limit=1)

            if not from_currency or not to_currency:
                _logger.warning("Currency not found: %s or %s", currency_from, currency_to)
                return 1.0

            rate = to_currency.rate / from_currency.rate if from_currency.rate else 0
            return rate
        except Exception as e:
            _logger.error("Error getting currency rate: %s", e)
            return 1.0

    # ------------------------------------------------------------------
    # Pivot helper methods
    # ------------------------------------------------------------------

    def _get_pivot_measures(self, pivot_data):
        """Extract measure field names from pivot definition.
        Handles both old format (list of strings) and new format (list of dicts).
        """
        raw_measures = pivot_data.get("measures", [])
        measures = []
        for m in raw_measures:
            if isinstance(m, dict):
                measures.append(m.get("field", m.get("name", "")))
            else:
                measures.append(str(m))
        return measures

    def _get_pivot_measure_label(self, pivot_data, measure):
        """Get the human-readable label of a pivot measure."""
        if measure == "__count":
            return "Count"
        model_name = pivot_data.get("model")
        measure_field = measure.split(":")[0] if ":" in measure else measure
        model = request.env[model_name].sudo()
        field_obj = model._fields.get(measure_field)
        return field_obj.string if field_obj else measure

    def _format_pivot_date_header(self, granularity, value):
        """Format a pivot date group value for display in PIVOT.HEADER."""
        str_val = str(value)
        try:
            if granularity == "day":
                return str_val  # already "MM/dd/yyyy"

            elif granularity == "week":
                parts = str_val.split("/")
                return f"W{parts[0]} {parts[1]}"

            elif granularity == "month":
                parts = str_val.split("/")
                month_num = int(parts[0])
                year = parts[1]
                month_name = calendar.month_name[month_num]
                return f"{month_name} {year}"

            elif granularity == "quarter":
                parts = str_val.split("/")
                return f"Q{parts[0]} {parts[1]}"

            elif granularity == "year":
                return str_val

        except Exception:
            pass
        return str_val
