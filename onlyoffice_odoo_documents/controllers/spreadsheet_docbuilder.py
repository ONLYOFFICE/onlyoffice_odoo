# Copyright (C) 2026 Ascensio System SIA
"""DocBuilder-based conversion between Odoo Spreadsheet and XLSX.

Isolated from controllers.py so the DocBuilder cache/script-building logic
(token cache, script templating, cell-grid construction) is kept separate
from the HTTP routing layer. Routes in controllers.py delegate to
``spreadsheet_docbuilder`` (a module-level ``SpreadsheetDocBuilder`` instance).
"""

import base64
import json
import logging
import re
import secrets
import uuid
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from xml.etree import ElementTree as ET

import pytz

from odoo import fields
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import file_open
from odoo.tools.translate import _

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils, url_utils

from .spreadsheet_formulas import SpreadsheetFormulaEvaluator

_logger = logging.getLogger(__name__)

# ── DocBuilder data cache (DB-backed) ────────────────────────────────────────
# The DocBuilder callback arrives as a separate HTTP request, possibly on a
# different worker, so its payload is stored in the database instead of
# process memory.

_DOCBUILDER_CACHE_PREFIX = "onlyoffice_docbuilder_cache_"
_DOCBUILDER_CACHE_TTL_HOURS = 1

# Explicit mimetype for rewritten XLSX attachments, since Odoo re-guesses
# the mimetype from content and may otherwise detect it as a plain zip file.
XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _DateTimeEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime objects."""

    def default(self, o):
        if isinstance(o, datetime | date):
            return o.isoformat()
        return super().default(o)


def _store_docbuilder_data(token, data):
    """Persist a DocBuilder payload so any worker can serve the callback."""
    attachments = request.env["ir.attachment"].sudo()
    # Remove old entries from failed or abandoned conversions
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
    # Commit now so the callback request (a separate transaction) can see it.
    request.env.cr.commit()


def _load_docbuilder_data(token):
    """Load a previously stored DocBuilder payload. Returns dict or None."""
    attachment = request.env["ir.attachment"].sudo().search([("name", "=", _DOCBUILDER_CACHE_PREFIX + token)], limit=1)
    return json.loads(attachment.raw) if attachment else None


def _delete_docbuilder_data(token):
    """Remove a stored DocBuilder payload (no-op when already deleted).

    In "patch_formulas"/"insert_sheet" modes, get_cached_file() may delete
    this same row from another request. Ignore that race so both sides
    can safely try to delete it.
    """
    try:
        with request.env.cr.savepoint():
            request.env["ir.attachment"].sudo().search([("name", "=", _DOCBUILDER_CACHE_PREFIX + token)]).unlink()
    except Exception:
        _logger.debug("DocBuilder cache for token %s already deleted concurrently", token)


# JS helpers shared by convert_spreadsheet.docbuilder and insert_sheet.docbuilder.
# DocBuilder scripts have no module system, so this text is injected into
# both files instead of duplicating the code.
_SHARED_DOCBUILDER_HELPERS = """
// Convert a 0-based column index to its spreadsheet letter (0 -> "A").
function columnToLetter(column) {
  var temp,
    letter = ""
  while (column >= 0) {
    temp = column % 26
    letter = String.fromCharCode(temp + 65) + letter
    column = Math.floor(column / 26) - 1
  }
  return letter
}

// Apply the number format and horizontal alignment for an ODOO_PIVOT/ODOO_LIST
// value cell, based on the underlying Odoo field's type.
function applyOdooColumnFormat(oRange, formula, metadata) {
  if (!metadata) return
  // Accept both quoted and unquoted numeric IDs, and an optional leading minus.
  var m = formula.match(/^=\\s*-?\\s*ODOO_PIVOT\\(\\s*"?(\\d+)"?\\s*,\\s*"([^"]+)"/)
  if (m) {
    var pivotMeta = metadata.pivots && metadata.pivots[m[1]]
    var info = pivotMeta && pivotMeta.columnFormats && pivotMeta.columnFormats[m[2]]
    if (info) {
      if (info.format) oRange.SetNumberFormat(info.format)
      if (info.align) oRange.SetAlignHorizontal(info.align)
    }
    return
  }
  m = formula.match(/^=\\s*-?\\s*ODOO_LIST\\(\\s*"?(\\d+)"?\\s*,\\s*"?\\d+"?\\s*,\\s*"([^"]+)"\\s*\\)/)
  if (m) {
    var listMeta = metadata.lists && metadata.lists[m[1]]
    var lInfo = listMeta && listMeta.columnFormats && listMeta.columnFormats[m[2]]
    if (lInfo) {
      if (lInfo.format) oRange.SetNumberFormat(lInfo.format)
      if (lInfo.align) oRange.SetAlignHorizontal(lInfo.align)
    }
  }
}
"""


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
    """Convert a read_group date value into the pivot string format understood by the formula evaluator."""
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


class SpreadsheetDocBuilder:
    """Builds DocBuilder scripts and manages the cache for spreadsheet <-> XLSX conversions."""

    def __init__(self, formula_evaluator: SpreadsheetFormulaEvaluator):
        self._formula_evaluator = formula_evaluator

    # ── Public entry points (called from controllers.py routes) ─────────────

    def convert_spreadsheet_to_xlsx(self, document_id, xlsx_base64=None):
        """Convert an Odoo Spreadsheet to XLSX, keeping formulas.

        If ``xlsx_base64`` is given (a native browser export, with charts
        and other formatting already in it), just patch the ODOO.* formula
        cells back to live ODOO_* formulas.

        Otherwise, rebuild the whole workbook from the raw snapshot. This
        fallback loses charts, images and other advanced formatting.
        """
        result = {"error": None, "xlsx_id": None}

        try:
            # The request context's language can be stale compared to the
            # user's current setting; keep it in sync so translated values
            # (display names, selection labels, field labels) are correct.
            current_lang = request.env.user.lang
            if current_lang and request.env.context.get("lang") != current_lang:
                request.update_env(context=dict(request.env.context, lang=current_lang))

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

            metadata_json = self._prepare_docbuilder_metadata(snapshot)
            oo_security_token = secrets.token_urlsafe(32)
            output_filename = f"{document.name}_{uuid.uuid4().hex[:8]}.xlsx"

            if xlsx_base64:
                # Patch the native export in place.
                patches = self._build_formula_patches(snapshot)
                _store_docbuilder_data(
                    oo_security_token,
                    {
                        "mode": "patch_formulas",
                        "document_id": document_id,
                        "xlsx_base64": xlsx_base64,
                        "patches_json": json.dumps(patches, cls=_DateTimeEncoder),
                        "metadata_json": metadata_json,
                        "output_filename": output_filename,
                        "_token": oo_security_token,
                    },
                )
            else:
                # Fallback: rebuild the workbook from the snapshot.
                self._formula_evaluator.evaluate_odoo_formulas_in_snapshot(snapshot)
                spreadsheet_json = json.dumps(snapshot, cls=_DateTimeEncoder)
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

    @staticmethod
    def _convert_odoo_formula(content):
        """Rewrite '=ODOO.PIVOT(...)' to '=ODOO_PIVOT(...)' (dot to underscore)."""
        return re.sub(r"ODOO\.([A-Z._]+)(\()", lambda m: "ODOO_" + m.group(1).replace(".", "_") + m.group(2), content)

    def _build_formula_patches(self, snapshot):
        """Collect {sheet, cell, formula} for every ODOO.* formula cell in the snapshot."""
        patches = []
        for sheet in snapshot.get("sheets", []):
            sheet_name = sheet.get("name") or ""
            for cell_address, cell_data in sheet.get("cells", {}).items():
                content = cell_data.get("content", "")
                if isinstance(content, str) and content.startswith(("=ODOO.", "=-ODOO.")):
                    patches.append(
                        {
                            "sheet": sheet_name,
                            "cell": cell_address,
                            "formula": self._convert_odoo_formula(content),
                        }
                    )
        return patches

    def insert_list(self, document_id, list_data, threshold, name):
        """Insert an Odoo list as ODOO_LIST formulas into an existing XLSX document.

        Rebuilds the XLSX via DocBuilder: opens the existing file, adds a new
        sheet with formulas, and updates the _OdooMetadata hidden sheet.
        """
        document, error = self._get_writable_document(document_id)
        if error:
            return {"error": error}

        columns = list_data.get("columns", [])
        if not columns:
            return {"error": "No columns provided"}

        # Add the new list definition to metadata (lists and pivots share the ID space)
        metadata, new_id = self._load_metadata_with_new_id(document)
        list_entry = {
            "model": list_data.get("model", ""),
            "domain": list_data.get("domain", "[]"),
            "orderBy": list_data.get("orderBy", []),
            "context": list_data.get("context", {}),
            "columns": columns,
            "name": name,
        }
        try:
            list_entry["columnFormats"] = self._formula_evaluator.get_list_column_formats(list_entry)
        except Exception as e:
            _logger.debug("Could not compute column formats for new list %s: %s", new_id, e)
        metadata.setdefault("lists", {})[new_id] = list_entry

        cells = self._build_list_cells(new_id, columns, int(threshold))
        return self._insert_sheet_via_docbuilder(document, name, cells, metadata, new_id)

    def insert_pivot(self, document_id, pivot_data, name):
        """Insert an Odoo pivot as ODOO_PIVOT formulas into an existing XLSX document."""
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
        pivot_entry = {
            "model": pivot_data["model"],
            "domain": pivot_data.get("domain", "[]"),
            "context": pivot_data.get("context", {}),
            "measures": measures,
            "rowGroupBys": row_group_bys,
            "colGroupBys": col_group_bys,
            "name": name,
        }
        try:
            pivot_entry["columnFormats"] = self._formula_evaluator.get_pivot_column_formats(pivot_entry)
        except Exception as e:
            _logger.debug("Could not compute column formats for new pivot %s: %s", new_id, e)
        metadata.setdefault("pivots", {})[new_id] = pivot_entry

        try:
            cells = self._build_pivot_cells(new_id, pivot_data, measures, row_group_bys, col_group_bys)
        except Exception as e:
            _logger.exception("Failed to build pivot cells: %s", e)
            return {"error": str(e)}

        return self._insert_sheet_via_docbuilder(document, name, cells, metadata, new_id)

    def build_callback_script(self, oo_security_token):
        """Build the DocBuilder script text for a cached token, or None if the token is unknown."""
        cache_data = _load_docbuilder_data(oo_security_token)
        if not cache_data:
            return None

        mode = cache_data.get("mode", "convert_spreadsheet")
        if mode == "insert_sheet":
            return self._build_insert_sheet_script(cache_data)
        if mode == "patch_formulas":
            return self._build_patch_formulas_script(cache_data)

        spreadsheet_json = cache_data["spreadsheet_json"]
        metadata_json = cache_data.get("metadata_json")
        with file_open("onlyoffice_odoo_documents/controllers/convert_spreadsheet.docbuilder", "r") as f:
            docbuilder_script = f.read()
        docbuilder_script = docbuilder_script.replace("SHARED_HELPERS_PLACEHOLDER", _SHARED_DOCBUILDER_HELPERS)
        docbuilder_script = docbuilder_script.replace("SPREADSHEET_DATA_PLACEHOLDER", spreadsheet_json)
        docbuilder_script = docbuilder_script.replace("METADATA_PLACEHOLDER", metadata_json or "null")
        docbuilder_script = docbuilder_script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{cache_data["output_filename"]}"')
        return docbuilder_script

    def get_cached_file(self, oo_security_token):
        """Return the cached XLSX bytes for "insert_sheet"/"patch_formulas" modes.

        Returns None if the token is unknown or in another mode.
        """
        cache_data = _load_docbuilder_data(oo_security_token)
        if not cache_data or cache_data.get("mode") not in ("insert_sheet", "patch_formulas"):
            return None

        xlsx_data = base64.b64decode(cache_data["xlsx_base64"])
        _delete_docbuilder_data(oo_security_token)
        return xlsx_data

    # ── Metadata / DocBuilder call helpers ───────────────────────────────────

    def _prepare_docbuilder_metadata(self, snapshot):
        """Build metadata JSON (lists, pivots, filters) with domains resolved for DocBuilder."""
        metadata = {}
        if snapshot.get("lists"):
            lists_with_computed_domain = {}
            for list_id, list_data in snapshot["lists"].items():
                list_copy = dict(list_data)
                list_copy["domain"] = self._formula_evaluator.parse_and_resolve_domain(list_copy.get("domain", []))
                try:
                    list_copy["columnFormats"] = self._formula_evaluator.get_list_column_formats(list_copy)
                except Exception as e:
                    _logger.debug("Could not compute column formats for list %s: %s", list_id, e)
                lists_with_computed_domain[list_id] = list_copy
            metadata["lists"] = lists_with_computed_domain
        if snapshot.get("pivots"):
            pivots_with_computed_domain = {}
            for pivot_id, pivot_data in snapshot["pivots"].items():
                pivot_copy = dict(pivot_data)
                pivot_copy["domain"] = self._formula_evaluator.parse_and_resolve_domain(pivot_copy.get("domain", []))
                try:
                    pivot_copy["columnFormats"] = self._formula_evaluator.get_pivot_column_formats(pivot_copy)
                except Exception as e:
                    _logger.debug("Could not compute column formats for pivot %s: %s", pivot_id, e)
                pivots_with_computed_domain[pivot_id] = pivot_copy
            metadata["pivots"] = pivots_with_computed_domain
        if snapshot.get("globalFilters"):
            metadata["globalFilters"] = snapshot["globalFilters"]
        return json.dumps(metadata, cls=_DateTimeEncoder) if metadata else None

    def _call_docbuilder(self, oo_security_token, document_id):
        """Call the DocBuilder service and download the resulting XLSX.

        Uses the shared ``onlyoffice_request`` helper (instead of calling
        ``requests`` directly) so SSL-certificate-verification settings and
        test-time HTTP blocking apply consistently with the rest of the app.

        Returns (content, error).
        """
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
        try:
            response = onlyoffice_request(
                url=docbuilder_url,
                method="post",
                opts={"json": payload, "headers": headers, "timeout": 300},
                env=request.env,
            )
        except Exception as e:
            _logger.error("DocBuilder request failed: %s", e)
            return None, _("DocBuilder conversion failed: %s") % str(e)

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

        # Fetch the generated XLSX file
        urls = response_json.get("urls", {})
        xlsx_url = next((url for key, url in urls.items() if key.endswith(".xlsx")), None)
        if not xlsx_url:
            xlsx_url = next(iter(urls.values()), None) if urls else None
        if not xlsx_url:
            return None, _("No XLSX file in output")

        try:
            xlsx_response = onlyoffice_request(url=xlsx_url, method="get", opts={"timeout": 60}, env=request.env)
        except Exception as e:
            _logger.error("Failed to download converted file: %s", e)
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
                    "mimetype": XLSX_MIMETYPE,
                    "onlyoffice_spreadsheet_metadata": metadata_json,
                }
            )
            return existing_xlsx.id

        xlsx_doc = request.env["documents.document"].create(
            {
                "name": f"{document.name}_docbuilder.xlsx",
                "folder_id": document.folder_id.id,
                "datas": base64.b64encode(xlsx_content),
                "mimetype": XLSX_MIMETYPE,
                "onlyoffice_spreadsheet_source_id": document_id,
                "onlyoffice_spreadsheet_metadata": metadata_json,
            }
        )
        return xlsx_doc.id

    def _build_insert_sheet_script(self, cache_data):
        """Build a DocBuilder script that opens an existing XLSX and adds a new sheet."""
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        oo_security_token = cache_data.get("_token")
        file_url = f"{odoo_url}onlyoffice/documents/docbuilder_file/{oo_security_token}"

        with file_open("onlyoffice_odoo_documents/controllers/insert_sheet.docbuilder", "r") as f:
            script = f.read()

        script = script.replace("SHARED_HELPERS_PLACEHOLDER", _SHARED_DOCBUILDER_HELPERS)
        script = script.replace("FILE_URL_PLACEHOLDER", f'"{file_url}"')
        script = script.replace("SHEET_NAME_PLACEHOLDER", json.dumps(cache_data["sheet_name"]))
        script = script.replace("CELLS_PLACEHOLDER", cache_data["cells_json"])
        script = script.replace("METADATA_PLACEHOLDER", cache_data["metadata_json"])
        script = script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{cache_data["output_filename"]}"')

        # Don't delete the cache entry yet — the file-serving route needs it
        return script

    def _build_patch_formulas_script(self, cache_data):
        """Build a DocBuilder script that opens a natively-exported XLSX and patches
        back only the cells that originally held ODOO.* formulas."""
        odoo_url = config_utils.get_base_or_odoo_url(request.env)
        oo_security_token = cache_data.get("_token")
        file_url = f"{odoo_url}onlyoffice/documents/docbuilder_file/{oo_security_token}"

        with file_open("onlyoffice_odoo_documents/controllers/patch_formulas.docbuilder", "r") as f:
            script = f.read()

        script = script.replace("SHARED_HELPERS_PLACEHOLDER", _SHARED_DOCBUILDER_HELPERS)
        script = script.replace("FILE_URL_PLACEHOLDER", f'"{file_url}"')
        script = script.replace("PATCHES_PLACEHOLDER", cache_data["patches_json"])
        script = script.replace("METADATA_PLACEHOLDER", cache_data.get("metadata_json") or "null")
        script = script.replace("OUTPUT_PATH_PLACEHOLDER", f'"{cache_data["output_filename"]}"')

        # Don't delete the cache entry yet — the file-serving route needs it
        return script

    # ── Insert helpers ────────────────────────────────────────────────────────

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
        domain = self._formula_evaluator.parse_and_resolve_domain(pivot_data.get("domain", []))

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
            with zipfile.ZipFile(BytesIO(xlsx_data), "r") as zf:
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
                "_token": oo_security_token,
            },
        )

        xlsx_content, error = self._call_docbuilder(oo_security_token, document.id)
        _delete_docbuilder_data(oo_security_token)
        if error:
            return {"error": f"DocBuilder error: {error}"}

        # Update the document's attachment with the rebuilt XLSX and save metadata
        document.attachment_id.write({"datas": base64.b64encode(xlsx_content), "mimetype": XLSX_MIMETYPE})
        document.write({"onlyoffice_spreadsheet_metadata": metadata_json})

        _logger.info("Inserted sheet '%s' (id=%s) into document %s via DocBuilder", sheet_name, new_id, document.id)

        return {
            "success": True,
            "document_id": document.id,
            "id": new_id,
            "sheet_name": sheet_name,
        }
