# Copyright (C) 2026 Ascensio System SIA
"""Compact server-side evaluator for ODOO.* spreadsheet formulas.

Designed to be portable across Odoo 17-19 with minimal dependencies.
Uses Odoo ORM methods (read_group, search, fields_get) and delegates
currency rate to the built-in res.currency.rate._get_rate_for_spreadsheet.
"""

import json
import logging
import re
from datetime import date as date_cls
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, fields
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.misc import babel_locale_parse
from odoo.tools.safe_eval import datetime as safe_datetime
from odoo.tools.safe_eval import safe_eval
from odoo.tools.safe_eval import time as safe_time

_logger = logging.getLogger(__name__)


# Date groupings whose groups are numbers (1 for January, ...), as Odoo groups them: no date range narrows them.
_NUMBER_GRANULARITIES = (
    "day_of_month",
    "day_of_week",
    "iso_week_number",
    "month_number",
    "quarter_number",
    "hour_number",
    "minute_number",
    "second_number",
)


def normalize_pivot_definition(pivot):
    """A pivot of the spreadsheet data in the shape the formulas read; None for a pivot not of Odoo data.

    Odoo keeps the groupings as dimensions (``rows`` / ``columns``) and the measures as objects: the formulas name a
    measure by its id ("amount_total:sum", or the field name in older data). A pivot already in this shape (inserted
    into an XLSX file, or converted before) is returned as it is.
    """
    if not isinstance(pivot, dict) or pivot.get("type", "ODOO") != "ODOO":
        return None
    if "rowGroupBys" in pivot or "colGroupBys" in pivot:
        return pivot

    def dimensions(items):
        return [
            item["fieldName"] + (f":{item['granularity']}" if item.get("granularity") else "")
            for item in items or []
            if isinstance(item, dict) and item.get("fieldName")
        ]

    measures, specs, labels = [], {}, {}
    for measure in pivot.get("measures") or []:
        if not isinstance(measure, dict):
            measures.append(str(measure))
            continue
        if measure.get("computedBy"):
            # A measure computed by a formula of the spreadsheet: there is no field to read.
            continue
        measure_id = measure.get("id") or measure.get("fieldName")
        field_name = measure.get("fieldName") or measure_id
        aggregator = measure.get("aggregator")
        measures.append(measure_id)
        specs[measure_id] = field_name if field_name == "__count" or not aggregator else f"{field_name}:{aggregator}"
        if measure.get("userDefinedName"):
            labels[measure_id] = measure["userDefinedName"]
    normalized = {key: pivot[key] for key in ("model", "domain", "context", "name", "formulaId") if key in pivot}
    normalized.update(
        rowGroupBys=dimensions(pivot.get("rows")),
        colGroupBys=dimensions(pivot.get("columns")),
        measures=measures,
        measureSpecs=specs,
        measureLabels=labels,
    )
    return normalized


def _get_lang_code(env):
    """Return the effective res.lang code for the current request/user."""
    return env.user.lang or env.context.get("lang") or "en_US"


def _user_today():
    """Return today's date in the current user's timezone."""
    return fields.Date.context_today(request.env.user)


def _domain_eval_context():
    """Return the evaluation context of a domain string, as the Odoo web client evaluates it.

    Only plain values and date helpers: the domain comes from the document data, which users can edit, and a record
    here (such as the user) would give the expression the whole environment, sudo() included.
    """
    return {
        "uid": request.env.uid,
        "allowed_company_ids": request.env.companies.ids,
        "context_today": _user_today,
        "datetime": safe_datetime,
        "relativedelta": relativedelta,
        "time": safe_time,
    }


_EXCEL_EPOCH = datetime(1899, 12, 30)


def _to_serial(env, value):
    """The spreadsheet serial number of a date, or of a datetime in the timezone of the user, as Odoo shows it."""
    if isinstance(value, datetime):
        local = fields.Datetime.context_timestamp(env.user, value).replace(tzinfo=None)
        delta = local - _EXCEL_EPOCH
        return delta.days + delta.seconds / 86400
    return (datetime(value.year, value.month, value.day) - _EXCEL_EPOCH).days


def _spreadsheet_locale(env):
    """Date and time formats of the language of the user, as Odoo Spreadsheet gets them, for ONLYOFFICE."""
    locale = env["res.lang"]._get_user_spreadsheet_locale()
    # The spreadsheet AM/PM code "a" is a plain letter for ONLYOFFICE.
    time_format = locale["timeFormat"][:-2] + " AM/PM" if locale["timeFormat"].endswith(" a") else locale["timeFormat"]
    return locale["dateFormat"], time_format


def currency_excel_format(currency):
    """The number format of a currency, as Odoo Spreadsheet builds it (createCurrencyFormat)."""
    if not currency:
        return "#,##0.00"
    decimals = currency.decimal_places
    number_format = "#,##0" + ("." + "0" * decimals if decimals else "")
    symbol = f"[${currency.symbol}]" if currency.symbol else ""
    return number_format + symbol if currency.position == "after" else symbol + number_format


def _float_excel_format(env, fobj):
    """Format of a float field by its precision (Odoo always shows two decimals; here the field decides)."""
    digits = fobj.get_digits(env)
    if digits is None:
        return "#,##0.00"
    if not digits:
        # digits=0: the full precision, as stored.
        return "General"
    scale = digits[1]
    return "#,##0." + "0" * scale if scale else "#,##0"


def get_field_excel_format(model, field_name):
    """Return (excel_number_format, horizontal_align) for a model field, as Odoo Spreadsheet formats its values.

    A date grouping (``date:month``) gets the format of its period. Monetary fields get the company currency (as a
    pivot measure); a list sets the currency of each record itself. Returns (None, None) when nothing applies.
    """
    if not field_name:
        return None, None
    field_name, granularity = (field_name.split(":", 1) + [None])[:2]
    fobj = model._fields.get(field_name)
    if not fobj:
        return None, None
    env = model.env
    ftype = fobj.type

    if ftype in ("date", "datetime"):
        date_format, time_format = _spreadsheet_locale(env)
        if granularity == "day":
            return "dd mmm yyyy", "right"
        if granularity == "month":
            return "mmmm yyyy", "right"
        if granularity in ("year", "day_of_month", "iso_week_number"):
            return "0", "right"
        if granularity in ("week", "quarter") or granularity in _NUMBER_GRANULARITIES:
            return None, "left"
        if ftype == "datetime" and not granularity:
            return f"{date_format} {time_format}", "right"
        return date_format, "right"
    if ftype == "monetary":
        return currency_excel_format(env.company.currency_id), "right"
    if ftype == "integer":
        return "0", "right"
    if ftype == "float":
        return _float_excel_format(env, fobj), "right"
    if ftype == "boolean":
        return None, "center"
    return None, "left"


# ──────────────────────────────────────────────────────────────────────────────
# Public standalone helpers (used by controllers.py)
# ──────────────────────────────────────────────────────────────────────────────


def compute_filter_values(metadata):
    """Resolve all global filters in metadata to {label: string_value}."""
    result = {}
    if not metadata:
        return result
    for gf in metadata.get("globalFilters", []):
        label = gf.get("label", "")
        if not label:
            continue
        try:
            result[label] = _resolve_filter_value(gf.get("currentValue") or gf.get("defaultValue"), gf.get("type"), gf)
        except AccessError:
            result[label] = ""
    return result


def load_metadata_for_document(document):
    """Load spreadsheet metadata (lists, pivots, filters) for a document."""
    if document.onlyoffice_spreadsheet_metadata:
        try:
            return json.loads(document.onlyoffice_spreadsheet_metadata)
        except Exception as e:
            _logger.debug("Could not load spreadsheet metadata: %s", e)
    if document.onlyoffice_spreadsheet_source_id:
        # documents.document / spreadsheet.mixin has no join_spreadsheet_session in Odoo 19;
        # read the current serialized snapshot (falls back to spreadsheet_data) instead.
        try:
            return json.loads(document.onlyoffice_spreadsheet_source_id._get_spreadsheet_serialized_snapshot())
        except Exception as e:
            _logger.debug("Could not load source spreadsheet snapshot: %s", e)
    return {}


_FILTER_MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_FILTER_QUARTERS = ("first_quarter", "second_quarter", "third_quarter", "fourth_quarter")


def _relative_date_range_label(value):
    """Return the label of a relative date filter value ("last_month", ...), as Odoo shows it."""
    labels = {
        "year_to_date": _("Year to Date"),
        "last_week": _("Last 7 Days"),
        "last_month": _("Last 30 Days"),
        "last_three_months": _("Last 90 Days"),
        "last_six_months": _("Last 180 Days"),
        "last_year": _("Last 365 Days"),
        "last_three_years": _("Last 3 Years"),
    }
    return labels.get(value, "")


def _resolve_filter_value(value, filter_type=None, global_filter=None):
    """Resolve a global filter's raw value (currentValue/defaultValue) to a display string.

    Shared by compute_filter_values (all filters at once) and
    SpreadsheetFormulaEvaluator._eval_filter_value (single filter by name).
    Date filters are shown like Odoo's getFilterDisplayValue: "Q3/2026",
    "09/2026", "2026", or the label of a relative range.
    """
    if not value:
        return ""
    if filter_type == "relation" and isinstance(value, list):
        # The names of the records, as Odoo shows a relation filter.
        model_name = (global_filter or {}).get("modelName")
        if model_name and model_name in request.env:
            records = request.env[model_name].browse([v for v in value if isinstance(v, int)]).exists()
            return ", ".join(records.mapped("display_name"))
        return ""
    if isinstance(value, str):
        value = _resolve_date_shortcut(value)
        if isinstance(value, str):
            return _relative_date_range_label(value) if filter_type == "date" else value
    if isinstance(value, dict):
        if "yearOffset" in value:
            year = str(_user_today().year + int(value.get("yearOffset") or 0))
            period = value.get("period")
            if period in _FILTER_QUARTERS:
                return f"Q{_FILTER_QUARTERS.index(period) + 1}/{year}"
            if period in _FILTER_MONTHS:
                return f"{_FILTER_MONTHS.index(period) + 1:02d}/{year}"
            return year
        if "value" in value:
            return str(value["value"])
        return ""
    return str(value)


def _resolve_date_shortcut(value):
    """Convert a default date filter value ("this_year", ...) to its period form, like Odoo."""
    today = _user_today()
    shortcuts = {
        "this_year": lambda: {"yearOffset": 0},
        "this_month": lambda: {"yearOffset": 0, "period": _FILTER_MONTHS[today.month - 1]},
        "this_quarter": lambda: {"yearOffset": 0, "period": _FILTER_QUARTERS[(today.month - 1) // 3]},
    }
    fn = shortcuts.get(value)
    return fn() if fn else value


# ──────────────────────────────────────────────────────────────────────────────
# SpreadsheetFormulaEvaluator
# ──────────────────────────────────────────────────────────────────────────────


class SpreadsheetFormulaEvaluator:
    """Evaluates ODOO.* spreadsheet formulas against live Odoo data."""

    # ── Public interface ─────────────────────────────────────────────────────

    def load_document_snapshot(self, document_id):
        """Load snapshot for a document (with per-request caching)."""
        cache_key = f"_doc_snapshot_{document_id}"
        cached = getattr(request, cache_key, None)
        if cached is not None:
            return cached
        document = request.env["documents.document"].sudo().browse(int(document_id))
        snapshot = load_metadata_for_document(document)
        setattr(request, cache_key, snapshot)
        return snapshot

    def evaluate_single_formula(self, snapshot, formula):
        """Evaluate a single ODOO_ formula string. Returns value or error string."""
        try:
            negate = formula.startswith("=-")
            clean = ("=" + formula[2:].lstrip()) if negate else formula
            match = re.match(r"=ODOO_(\w+)\((.*)\)", clean)
            if not match:
                return "#ERROR: Invalid formula"
            result = self._dispatch(snapshot, match.group(1), self._parse_args(match.group(2)))
            if negate and isinstance(result, int | float):
                result = -result
            return result
        except AccessError as e:
            # As in Odoo Spreadsheet, data the user may not read is an error in the cell, not a value.
            return f"#ERROR: {str(e).splitlines()[0]}"
        except Exception as e:
            _logger.warning("Formula error %s: %s", formula, e)
            return f"#ERROR: {e}"

    def get_pivot_column_formats(self, pivot_data):
        """Return {measure or grouping: {format, align, type}} for a pivot's measures and date groupings."""
        model = request.env[pivot_data["model"]]
        formats = {}
        pivot_data = normalize_pivot_definition(pivot_data) or pivot_data
        group_bys = pivot_data.get("rowGroupBys", []) + pivot_data.get("colGroupBys", [])
        specs = pivot_data.get("measureSpecs") or {}
        for key in self._get_measures(pivot_data) + [gb for gb in group_bys if ":" in str(gb)]:
            spec = specs.get(key, key)
            field_name, aggregator = (str(spec).split(":", 1) + [None])[:2]
            if field_name == "__count" or aggregator in ("count", "count_distinct"):
                formats[key] = {"format": "0", "align": "right", "type": "integer"}
                continue
            excel_format, align = get_field_excel_format(model, spec)
            fobj = model._fields.get(field_name)
            if (excel_format or align) and fobj:
                formats[key] = {"format": excel_format, "align": align, "type": fobj.type}
        return formats

    def get_list_column_formats(self, list_data, rows=0):
        """Return {field_name: {format, align, type}} for a list's columns.

        A monetary column gets the currency of each record, ``formats`` by position, for the first ``rows`` records.
        """
        model = request.env[list_data["model"]]
        formats = {}
        for col in list_data.get("columns", []):
            field_name = col.get("name") if isinstance(col, dict) else str(col)
            excel_format, align = get_field_excel_format(model, field_name)
            fobj = model._fields.get(field_name)
            if not (excel_format or align) or not fobj:
                continue
            formats[field_name] = {"format": excel_format, "align": align, "type": fobj.type}
            if fobj.type == "monetary" and rows:
                formats[field_name]["formats"] = self._list_currency_formats(list_data, model, fobj, rows)
        return formats

    def _list_currency_formats(self, list_data, model, fobj, rows):
        """The currency format of each of the first ``rows`` records of a list (getListCurrency of Odoo)."""
        currency_field = fobj.get_currency_field(model) if hasattr(fobj, "get_currency_field") else fobj.currency_field
        domain = self._resolve_domain(list_data.get("domain", []), model)
        records = model.search(domain, limit=rows, order=self._order_string(list_data.get("orderBy", [])))
        return [
            currency_excel_format(record[currency_field]) if currency_field in record else "#,##0.00"
            for record in records
        ]

    def parse_and_resolve_domain(self, domain_value):
        """Parse a domain from the snapshot and resolve the 'uid' placeholder.

        A domain stored as a string is evaluated on every call, like Odoo
        does, so relative dates (context_today(), relativedelta) stay
        relative. A domain that cannot be evaluated raises instead of
        silently matching every record.
        """
        uid = request.env.user.id
        if isinstance(domain_value, str):
            domain_value = domain_value.strip()
            if not domain_value or domain_value == "[]":
                return []
            try:
                domain_value = safe_eval(domain_value, _domain_eval_context())
            except Exception as e:
                raise ValueError(f"Invalid domain: {e}") from e
        if not isinstance(domain_value, list | tuple):
            return []
        return [
            [item[0], item[1], uid]
            if (isinstance(item, list | tuple) and len(item) == 3 and item[2] == "uid")
            else list(item)
            if isinstance(item, list | tuple)
            else item
            for item in domain_value
        ]

    # ── Dispatch ─────────────────────────────────────────────────────────────

    _HANDLERS = {
        "LIST": "_eval_list",
        "LIST_HEADER": "_eval_list_header",
        "PIVOT": "_eval_pivot",
        "PIVOT_HEADER": "_eval_pivot_header",
        "PIVOT_TABLE": "_eval_pivot_table",
        "FILTER_VALUE": "_eval_filter_value",
        "CURRENCY_RATE": "_eval_currency_rate",
    }

    def _dispatch(self, snapshot, func_name, args):
        handler_name = self._HANDLERS.get(func_name)
        if not handler_name:
            return f"#ERROR: Unknown function {func_name}"
        return getattr(self, handler_name)(snapshot, args)

    # ── Argument parsing (single universal parser) ───────────────────────────

    @staticmethod
    def _parse_args(args_str):
        """Split comma-separated formula arguments, ignoring commas inside quotes.

        Supports backslash-escaped quotes (\\") inside string literals, so
        values containing a literal '"' (e.g. field labels) round-trip
        correctly instead of breaking argument boundaries.
        """
        if not args_str:
            return []
        args = []
        current = ""
        in_quotes = False
        i = 0
        n = len(args_str)
        while i < n:
            ch = args_str[i]
            if ch == "\\" and in_quotes and i + 1 < n and args_str[i + 1] == '"':
                current += '"'
                i += 2
                continue
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == "," and not in_quotes:
                args.append(_coerce(current.strip()))
                current = ""
                i += 1
                continue
            current += ch
            i += 1
        if current:
            args.append(_coerce(current.strip()))
        return args

    # ── Formula implementations ──────────────────────────────────────────────

    def _eval_list(self, snapshot, args):
        """ODOO.LIST(list_id, index, field_name)"""
        if len(args) < 3:
            raise ValueError("ODOO.LIST requires 3 args")
        list_id, index, field_name = str(args[0]), int(args[1]) - 1, str(args[2])

        list_data = snapshot.get("lists", {}).get(list_id)
        if not list_data:
            _logger.warning("LIST %s not found. Available lists: %s", list_id, list(snapshot.get("lists", {}).keys()))
            raise ValueError(f"List '{list_id}' not found")

        model = self._data_model(list_data["model"])
        self._check_fields(model, field_name)
        domain = self._resolve_domain(list_data.get("domain", []), model)
        order = self._order_string(list_data.get("orderBy", []))

        records = model.search(domain, limit=1, offset=index, order=order)
        if not records:
            return ""
        return self._format_value(records[0], field_name, model)

    def _eval_list_header(self, snapshot, args):
        """ODOO.LIST.HEADER(list_id, field_name)"""
        if len(args) < 2:
            raise ValueError("ODOO.LIST.HEADER requires 2 args")
        list_data = snapshot.get("lists", {}).get(str(args[0]))
        if not list_data:
            raise ValueError(f"List '{args[0]}' not found")
        model = self._data_model(list_data["model"])
        self._check_fields(model, str(args[1]))
        info = model.fields_get([str(args[1])])
        return info.get(str(args[1]), {}).get("string", str(args[1]))

    def _eval_pivot(self, snapshot, args):
        """ODOO.PIVOT(pivot_id, measure, [field1, value1, ...])"""
        if len(args) < 2:
            raise ValueError("ODOO.PIVOT requires at least 2 args")

        pivot_id, measure = str(args[0]), str(args[1])
        pivot_data = self._find_pivot(snapshot, pivot_id)
        if not pivot_data:
            raise ValueError(f"Pivot '{pivot_id}' not found")

        model = self._data_model(pivot_data["model"])
        base_domain = self._resolve_domain(pivot_data.get("domain", []), model)

        # Parse field/value pairs from args[2:]
        pairs = []
        i = 2
        while i + 1 < len(args):
            fs = str(args[i])
            if fs != "measure":
                pairs.append((fs, args[i + 1]))
            i += 2

        spec = self._measure_spec(pivot_data, measure)
        measure_field = spec.split(":")[0]
        fields_to_read = [] if measure_field == "__count" else [spec]
        self._check_fields(model, spec, *(fs for fs, _value in pairs))

        if not pairs:
            # Return a plain, unformatted number here: formulas that do
            # arithmetic on this cell must keep working even when there
            # is no matching data.
            result = self._safe_read_group(model, base_domain, fields_to_read, [])
            if not result:
                return 0
            return self._format_measure_value(model, measure_field, result[0].get(measure_field, 0), domain=base_domain)

        # Build narrow domain from pairs and execute
        extra = self._pairs_to_domain(pairs, model)
        combined = base_domain + extra
        _logger.debug("PIVOT %s combined domain: %r", pivot_id, combined)
        group_bys = [fs for fs, _ in pairs]

        groups = self._safe_read_group(model, combined, fields_to_read, group_bys)
        if groups is None:
            # The query itself failed. Report it instead of hiding it as an
            # empty or zero value.
            _logger.warning("PIVOT %s: read_group failed for domain %r, group_bys %r", pivot_id, combined, group_bys)
            raise ValueError("read_group failed")
        # A grouping by number (month_number, ...) is not in the domain: its group is picked here.
        number_pairs = [(fs, value) for fs, value in pairs if _granularity(fs) in _NUMBER_GRANULARITIES]
        groups = [group for group in groups if all(_same_number(group.get(fs), value) for fs, value in number_pairs)]
        if not groups:
            # No data for this combination. Return a plain, unformatted
            # number so arithmetic formulas built on this cell keep working.
            return 0

        return self._format_measure_value(model, measure_field, groups[0].get(measure_field, 0), domain=combined)

    def _eval_pivot_table(self, snapshot, args):
        """ODOO.PIVOT.TABLE(pivot_id, ...) — returns the whole pivot as a 2D array."""
        if len(args) < 1:
            raise ValueError("ODOO.PIVOT.TABLE requires at least 1 arg")

        pivot_id = str(args[0])
        pivot_data = self._find_pivot(snapshot, pivot_id)
        if not pivot_data:
            raise ValueError(f"Pivot '{pivot_id}' not found")

        model = self._data_model(pivot_data["model"])
        base_domain = self._resolve_domain(pivot_data.get("domain", []), model)
        measures = [self._measure_spec(pivot_data, m) for m in self._get_measures(pivot_data)]
        measure_fields = [m for m in measures if m.split(":")[0] != "__count"]
        all_group_bys = pivot_data.get("rowGroupBys", []) + pivot_data.get("colGroupBys", [])
        self._check_fields(model, *measures, *all_group_bys)

        if not all_group_bys:
            result = self._safe_read_group(model, base_domain, measure_fields, [])
            if not result:
                return [["Total", 0]]
            row = ["Total"]
            for m in measures:
                k = "__count" if m == "__count" else (m.split(":")[0] if ":" in m else m)
                row.append(self._format_measure_value(model, k, result[0].get(k, 0), domain=base_domain))
            return [row]

        groups = self._safe_read_group(model, base_domain, measure_fields, all_group_bys)
        if groups is None:
            raise ValueError("read_group failed")

        table = [list(all_group_bys) + measures]
        for group in groups:
            row = []
            for gb in all_group_bys:
                val = group.get(gb)
                row.append(val[1] if isinstance(val, list | tuple) and len(val) == 2 else val)
            for m in measures:
                k = "__count" if m == "__count" else (m.split(":")[0] if ":" in m else m)
                row.append(self._format_measure_value(model, k, group.get(k, 0), domain=base_domain))
            table.append(row)
        return table

    def _eval_pivot_header(self, snapshot, args):
        """ODOO.PIVOT.HEADER(pivot_id, [field1, value1, ...])"""
        if len(args) < 1:
            return "Total"

        pivot_id = str(args[0])
        domain_args = args[1:]
        pivot_data = self._find_pivot(snapshot, pivot_id)
        if not pivot_data:
            return str(args[-1]) if domain_args else "Total"

        if not domain_args or len(domain_args) < 2:
            return "Total"

        field_spec, value = str(domain_args[-2]), domain_args[-1]

        if field_spec == "measure":
            return self._measure_label(pivot_data, str(value))
        if value == "false" or value is False:
            return "None"

        field_name, granularity = (field_spec.split(":", 1) + [None])[:2]
        model = self._data_model(pivot_data["model"])
        self._check_fields(model, field_name)
        field_obj = model._fields.get(field_name)

        if not field_obj:
            return str(value)
        if field_obj.type in ("date", "datetime") and granularity in _NUMBER_GRANULARITIES:
            return _format_number_header(model.env, granularity, value)
        if field_obj.type in ("date", "datetime") and granularity:
            return _format_date_header(model.env, granularity, value)
        if field_obj.type in ("many2one", "many2many", "one2many") and field_obj.comodel_name:
            try:
                rec = request.env[field_obj.comodel_name].browse(int(value))
                return rec.display_name or str(value) if rec.exists() else str(value)
            except (ValueError, TypeError):
                return str(value)
        if field_obj.type == "selection":
            sel = dict(model.fields_get([field_name]).get(field_name, {}).get("selection", []))
            return sel.get(str(value), str(value))
        return str(value)

    def _eval_filter_value(self, snapshot, args):
        """ODOO.FILTER.VALUE(filter_name)"""
        if not args:
            return ""
        name = str(args[0])
        for f in snapshot.get("globalFilters", []):
            if f.get("label") != name:
                continue
            return _resolve_filter_value(f.get("currentValue") or f.get("defaultValue"), f.get("type"), f)
        raise ValueError(f'Filter "{name}" not found')

    def _eval_currency_rate(self, _snapshot, args):
        """ODOO.CURRENCY.RATE(from, to, [date], [company_id]) — uses Odoo's own currency rate lookup."""
        if len(args) < 2:
            raise ValueError("ODOO.CURRENCY.RATE requires at least 2 args")
        rate_date = _to_server_date(args[2]) if len(args) > 2 and args[2] not in ("", None) else None
        company_id = int(float(args[3])) if len(args) > 3 and args[3] not in ("", None) else None
        # As the Odoo client: get_rates_for_spreadsheet runs with the rights of the user.
        rate = request.env["res.currency.rate"]._get_rate_for_spreadsheet(
            str(args[0]), str(args[1]), rate_date and rate_date.isoformat(), company_id
        )
        if rate is False:
            raise ValueError("Currency rate unavailable.")
        return rate

    # ── Domain & date helpers ────────────────────────────────────────────────

    def _resolve_domain(self, domain_value, model):
        """Parse a domain, resolve 'uid', and normalize any date values."""
        domain = self.parse_and_resolve_domain(domain_value)
        return self._sanitize_dates(domain, model)

    def _sanitize_dates(self, domain, model):
        """Replace date-like string values (MM/YYYY, YYYY) in a domain with date ranges."""
        month_re = re.compile(r"^(\d{1,2})/(\d{4})$")
        result = []
        for item in domain:
            if not (isinstance(item, list | tuple) and len(item) == 3):
                result.append(item)
                continue
            field_name, op, value = item
            if op != "=" or not isinstance(value, str):
                result.append(item)
                continue
            fobj = model._fields.get(field_name)
            if not fobj or fobj.type not in ("date", "datetime"):
                result.append(item)
                continue

            rng = None
            m = month_re.match(value)
            if m and 1 <= int(m.group(1)) <= 12:
                rng = _date_to_range("month", value)
            if not rng:
                try:
                    y = int(value)
                    if 1900 <= y <= 2200:
                        rng = _date_to_range("year", value)
                except (ValueError, TypeError) as e:
                    _logger.debug("Could not parse year value %r: %s", value, e)
            if rng:
                result.append((field_name, ">=", rng[0]))
                result.append((field_name, "<", rng[1]))
            else:
                result.append(item)
        _logger.debug("_sanitize_dates output: %r", result)
        return result

    def _pairs_to_domain(self, pairs, model):
        """Convert pivot field/value pairs into domain conditions."""
        domain = []
        for field_spec, value in pairs:
            fname = field_spec.split(":")[0] if ":" in field_spec else field_spec
            gran = field_spec.split(":")[1] if ":" in field_spec else None
            fobj = model._fields.get(fname)

            if gran in _NUMBER_GRANULARITIES:
                # Picked from the groups (see _eval_pivot); "false" is the group without a date.
                if value == "false" or value is False:
                    domain.append((fname, "=", False))
            elif value == "false" or value is False:
                domain.append((fname, "=", False))
            elif fobj and fobj.type in ("date", "datetime"):
                # Infer granularity from value if not explicitly specified
                effective_gran = gran
                if not effective_gran and isinstance(value, str):
                    effective_gran = _infer_date_granularity(value)
                if effective_gran:
                    rng = _date_to_range(effective_gran, str(value))
                    if rng:
                        domain.append((fname, ">=", rng[0]))
                        domain.append((fname, "<", rng[1]))
                    else:
                        domain.append((fname, "=", value))
                else:
                    domain.append((fname, "=", value))
            elif fobj and fobj.type in ("many2one", "many2many", "one2many", "integer"):
                try:
                    domain.append((fname, "=", int(value)))
                except (ValueError, TypeError):
                    domain.append((fname, "=", value))
            elif fobj and fobj.type == "boolean":
                domain.append((fname, "=", str(value).lower() == "true"))
            else:
                domain.append((fname, "=", value))
        return domain

    # ── Utility helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _safe_read_group(model, domain, fields, group_bys):
        """Run read_group in a savepoint so a failed query doesn't break the transaction.

        Caches the result on the request (if a cache dict is attached) so
        identical pivot cells reuse one query.
        """
        cache = getattr(request, "_rg_cache", None)
        cache_key = None
        if cache is not None:
            cache_key = (model._name, repr(domain), tuple(fields), tuple(group_bys))
            if cache_key in cache:
                return cache[cache_key]
        cr = request.env.cr
        try:
            cr.execute("SAVEPOINT pivot_rg")
            result = model.read_group(domain, fields, group_bys, lazy=False)
            cr.execute("RELEASE SAVEPOINT pivot_rg")
        except AccessError:
            cr.execute("ROLLBACK TO SAVEPOINT pivot_rg")
            raise
        except Exception as e:
            _logger.warning("read_group error: %s", e)
            cr.execute("ROLLBACK TO SAVEPOINT pivot_rg")
            result = None
        if cache is not None:
            cache[cache_key] = result
        return result

    @staticmethod
    def _order_string(order_by):
        """Convert orderBy list to Odoo order string."""
        if not order_by:
            return None
        parts = [f"{o['name']} {'ASC' if o.get('asc', True) else 'DESC'}" for o in order_by if o.get("name")]
        return ", ".join(parts) or None

    @staticmethod
    def _format_value(record, field_name, model):
        """The value of a record field in a list cell, as Odoo Spreadsheet gives it (getListCellValue).

        Numbers stay numbers and dates become serial numbers (a datetime in the timezone of the user): the format of
        the cell shows them, so sums, sorting and date functions work. A boolean is the text TRUE / FALSE.
        """
        fobj = model._fields.get(field_name)
        val = record[field_name] if field_name in record else None
        if fobj and fobj.type == "boolean":
            return "TRUE" if val else "FALSE"
        if val is None or val is False:
            return ""
        env = model.env
        if fobj and fobj.type == "selection":
            sel = dict(fobj._description_selection(env))
            return sel.get(val, val)
        if fobj and fobj.type in ("date", "datetime"):
            return _to_serial(env, val)
        if fobj and fobj.type == "many2one":
            # As Odoo reads a many2one: its name is shown whatever the rights on the related record.
            if not val:
                return ""
            return val.sudo().display_name or str(val)
        if hasattr(val, "_name"):
            if not val:
                return ""
            if len(val) > 1:
                return ", ".join(r.display_name or str(r) for r in val)
            return val.display_name or str(val)
        return val

    @staticmethod
    def _format_measure_value(model, measure_field, value, domain=None):
        """An aggregated pivot measure, as Odoo Spreadsheet gives it: the number itself (the cell format shows it)."""
        return value

    @staticmethod
    def _data_model(model_name):
        """The model of a list or pivot with the rights of the current user, as Odoo Spreadsheet reads it."""
        model = request.env[model_name]
        model.browse().check_access("read")
        return model

    @staticmethod
    def _check_fields(model, *field_specs):
        """Raise AccessError for fields the user may not read (their groups); unknown fields are left to the caller."""
        names = {str(spec).split(":")[0] for spec in field_specs if spec and spec not in ("__count", "measure")}
        names = {name for name in names if name in model._fields}
        if not names:
            return
        hidden = names - set(model.fields_get(list(names), attributes=["type"]))
        if hidden:
            raise AccessError(_("You do not have access to the field %s.", ", ".join(sorted(hidden))))

    @staticmethod
    def _find_pivot(snapshot, pivot_id):
        """The pivot a formula names, in the shape the formulas read: Odoo names it by its formulaId."""
        pivots = snapshot.get("pivots") or {}
        for pivot in pivots.values():
            if isinstance(pivot, dict) and str(pivot.get("formulaId")) == pivot_id:
                return normalize_pivot_definition(pivot)
        pivot = pivots.get(pivot_id)
        if isinstance(pivot, dict) and "formulaId" not in pivot:
            return normalize_pivot_definition(pivot)
        return None

    @staticmethod
    def _measure_spec(pivot_data, measure):
        """The read_group measure ("amount_total:sum") of a measure a formula names.

        A measure the pivot does not have is an error, as in Odoo.
        """
        specs = pivot_data.get("measureSpecs")
        if specs is None:
            return measure
        if measure not in specs:
            raise ValueError(_("Field %s does not exist", measure))
        return specs[measure]

    @staticmethod
    def _get_measures(pivot_data):
        """Extract measure field names from pivot definition."""
        raw = pivot_data.get("measures", [])
        return [m.get("field", m.get("name", "")) if isinstance(m, dict) else str(m) for m in raw]

    @staticmethod
    def _measure_label(pivot_data, measure):
        label = (pivot_data.get("measureLabels") or {}).get(measure)
        if label:
            return label
        mf = SpreadsheetFormulaEvaluator._measure_spec(pivot_data, measure).split(":")[0]
        if mf == "__count":
            return "Count"
        model = SpreadsheetFormulaEvaluator._data_model(pivot_data["model"])
        SpreadsheetFormulaEvaluator._check_fields(model, mf)
        fobj = model._fields.get(mf)
        return fobj.string if fobj else measure


# ──────────────────────────────────────────────────────────────────────────────
# Module-level utilities
# ──────────────────────────────────────────────────────────────────────────────


def _coerce(arg):
    """Coerce a formula argument string to typed value."""
    if arg.startswith('"') and arg.endswith('"'):
        return arg[1:-1]
    try:
        return float(arg) if "." in arg else int(arg)
    except ValueError:
        return arg


def _to_server_date(value):
    """Convert a spreadsheet date argument (serial number or date text) to a date.

    Accepts what Odoo's toJsDate accepts in practice: an Excel serial
    number, an ISO date, or a date in the user's language format.
    """
    text = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return date_cls(1899, 12, 30) + timedelta(days=int(float(text)))
    lang = request.env["res.lang"]._lang_get(_get_lang_code(request.env))
    for date_format in ("%Y-%m-%d", "%Y/%m/%d", lang.date_format if lang else None):
        if not date_format:
            continue
        try:
            return datetime.strptime(text, date_format).date()
        except ValueError:
            continue
    raise ValueError(f"Invalid date: {value}")


def _infer_date_granularity(value):
    """Guess the date granularity ('month', 'year', 'quarter', 'day') from a value's shape."""
    parts = str(value).split("/")
    if len(parts) == 2:
        try:
            left, right = int(parts[0]), int(parts[1])
            if 1 <= left <= 12 and 1900 <= right <= 2200:
                return "month"
            if 1 <= left <= 4 and 1900 <= right <= 2200:
                return "quarter"
        except (ValueError, TypeError) as e:
            _logger.debug("Could not infer date granularity from %r: %s", value, e)
    elif len(parts) == 3:
        return "day"
    elif len(parts) == 1:
        try:
            y = int(value)
            if 1900 <= y <= 2200:
                return "year"
        except (ValueError, TypeError) as e:
            _logger.debug("Could not infer year from %r: %s", value, e)
    return None


def _date_to_range(granularity, value):
    """Convert a pivot date value to a (from, to) pair of 'YYYY-MM-DD' strings, or None."""
    try:
        if granularity == "day" and re.fullmatch(r"\d+(\.\d+)?", value):
            # A day of Odoo 18 functions: its serial number.
            start = date_cls(1899, 12, 30) + timedelta(days=int(float(value)))
            return (start.isoformat(), (start + timedelta(days=1)).isoformat())
        parts = value.split("/")
        if granularity == "year":
            y = int(float(value))
            return (f"{y}-01-01", f"{y + 1}-01-01")
        if granularity == "quarter" and len(parts) == 2:
            q, y = int(parts[0]), int(parts[1])
            sm = (q - 1) * 3 + 1
            em = sm + 3
            if em > 12:
                return (f"{y}-{sm:02d}-01", f"{y + 1}-01-01")
            return (f"{y}-{sm:02d}-01", f"{y}-{em:02d}-01")
        if granularity == "month" and len(parts) == 2:
            mo, y = int(parts[0]), int(parts[1])
            if mo == 12:
                return (f"{y}-{mo:02d}-01", f"{y + 1}-01-01")
            return (f"{y}-{mo:02d}-01", f"{y}-{mo + 1:02d}-01")
        if granularity == "week" and len(parts) == 2:
            start = date_cls.fromisocalendar(int(parts[1]), int(parts[0]), 1)
            return (start.isoformat(), (start + timedelta(days=7)).isoformat())
        if granularity == "day" and len(parts) == 3:
            start = date_cls(int(parts[2]), int(parts[0]), int(parts[1]))
            return (start.isoformat(), (start + timedelta(days=1)).isoformat())
    except (ValueError, IndexError):
        return None
    return None


def _format_date_header(env, granularity, value):
    """A pivot group's date header, as Odoo Spreadsheet gives it (pivotTimeAdapter).

    Day: the serial number of the date; month: that of its first day; year: the number; quarter and week: text.
    """
    s = str(value)
    try:
        parts = s.split("/")
        if granularity == "day" and re.fullmatch(r"\d+(\.\d+)?", s):
            return int(float(s))
        if granularity == "day" and len(parts) == 3:
            return _to_serial(env, date_cls(int(parts[2]), int(parts[0]), int(parts[1])))
        if granularity == "month" and len(parts) == 2:
            month, year = int(parts[0]), int(parts[1])
            return _to_serial(env, date_cls(year, month, 1))
        if granularity == "year":
            return int(float(s))
        if granularity == "quarter" and len(parts) == 2:
            return f"Q{parts[0]} {parts[1]}"
        if granularity == "week" and len(parts) == 2:
            return f"W{parts[0]} {parts[1]}"
    except (IndexError, ValueError) as e:
        _logger.debug("Could not format date header %r (%r): %s", granularity, value, e)
    return s


def _granularity(field_spec):
    """The granularity of a pivot grouping ("date_order:month" -> "month"), or None."""
    return str(field_spec).split(":", 1)[1] if ":" in str(field_spec) else None


def _same_number(group_value, value):
    """Whether a group of a grouping by number is the value of a formula ("false": the group without a date)."""
    if value == "false" or value is False:
        return group_value is False or group_value is None
    try:
        return group_value is not False and group_value is not None and int(group_value) == int(float(value))
    except (TypeError, ValueError):
        return False


def _format_number_header(env, granularity, value):
    """A header of a grouping by number, as Odoo Spreadsheet shows it (its time adapters): "January", "Q1", "13h"..."""
    if value == "false" or value is False:
        return _("None")
    number = int(float(value))
    locale = babel_locale_parse(_get_lang_code(env))
    if granularity == "month_number":
        return locale.months["format"]["wide"][number]
    if granularity == "quarter_number":
        return _("Q%(quarter_number)s", quarter_number=number)
    if granularity == "day_of_week":
        # 1 is the first day of the week of the language of the user (1 Monday ... 7 Sunday); babel counts from
        # Monday (0).
        lang = env["res.lang"]._lang_get(_get_lang_code(env))
        week_start = int(lang.week_start) if lang and lang.week_start else 7
        return locale.days["format"]["wide"][(number - 1 + week_start - 1) % 7]
    if granularity == "hour_number":
        return _("%(hour_number)sh", hour_number=number)
    if granularity == "minute_number":
        return _("%(minute_number)s'", minute_number=number)
    if granularity == "second_number":
        return _("%(second_number)s''", second_number=number)
    return number
