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

from odoo.http import request
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

_MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


# ──────────────────────────────────────────────────────────────────────────────
# Public standalone helpers (used by controllers.py)
# ──────────────────────────────────────────────────────────────────────────────


def compute_filter_values(metadata):
    """Compute globalFilter values → {label: resolved_string}."""
    result = {}
    if not metadata:
        return result
    for gf in metadata.get("globalFilters", []):
        label = gf.get("label", "")
        if not label:
            continue
        value = gf.get("currentValue") or gf.get("defaultValue")
        if not value:
            result[label] = ""
            continue
        if isinstance(value, str):
            value = _resolve_date_shortcut(value)
            if isinstance(value, str):
                result[label] = value
                continue
        if isinstance(value, dict):
            if "yearOffset" in value:
                result[label] = str(datetime.now().year + int(value.get("yearOffset", 0)))
            elif "value" in value:
                result[label] = str(value["value"])
            else:
                result[label] = ""
        else:
            result[label] = str(value)
    return result


def load_metadata_for_document(document):
    """Load spreadsheet metadata for a document. Returns dict or {}."""
    if document.onlyoffice_spreadsheet_metadata:
        try:
            return json.loads(document.onlyoffice_spreadsheet_metadata)
        except Exception:
            pass
    if document.onlyoffice_spreadsheet_source_id:
        session_data = document.onlyoffice_spreadsheet_source_id.join_spreadsheet_session()
        return session_data.get("data", {})
    return {}


def _resolve_date_shortcut(value):
    """Resolve string date shortcuts (this_year, last_year, etc.) to dicts."""
    shortcuts = {
        "this_year": lambda: {"yearOffset": 0},
        "last_year": lambda: {"yearOffset": -1},
        "this_month": lambda: {"yearOffset": 0, "period": f"{datetime.now().month:02d}"},
        "this_quarter": lambda: {
            "yearOffset": 0,
            "period": f"q{(datetime.now().month - 1) // 3 + 1}",
        },
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
            if negate and isinstance(result, (int, float)):
                result = -result
            return result
        except Exception as e:
            _logger.warning("Formula error %s: %s", formula, e)
            return f"#ERROR: {e}"

    def evaluate_odoo_formulas_in_snapshot(self, snapshot):
        """Evaluate all ODOO.* formulas in snapshot cells (for DocBuilder conversion)."""
        for sheet in snapshot.get("sheets", []):
            for cell_data in sheet.get("cells", {}).values():
                content = cell_data.get("content", "")
                if not isinstance(content, str) or "ODOO." not in content:
                    continue
                if not (content.startswith("=ODOO.") or content.startswith("=-ODOO.")):
                    continue
                try:
                    negate = content.startswith("=-")
                    clean = ("=" + content[2:].lstrip()) if negate else content
                    clean = self._resolve_nested(snapshot, clean)

                    match = re.match(r"^=ODOO\.([A-Z._]+)\((.*)\)$", clean)
                    if not match:
                        continue

                    func_name = match.group(1).replace(".", "_")
                    value = self._dispatch(snapshot, func_name, self._parse_args(match.group(2)))

                    if negate and isinstance(value, (int, float)):
                        value = -value
                    if value is not None:
                        cell_data["value"] = value
                except Exception as e:
                    _logger.warning("Snapshot formula error %s: %s", content, e)
                    cell_data["value"] = ""

    def _parse_and_resolve_domain(self, domain_value):
        """Parse domain from snapshot, resolve 'uid' placeholder. Public for controllers.py."""
        uid = request.env.user.id
        if isinstance(domain_value, str):
            domain_value = domain_value.strip()
            if not domain_value or domain_value == "[]":
                return []
            try:
                domain_value = safe_eval(domain_value, {"uid": uid, "user": request.env.user})
            except Exception:
                return []
        if not isinstance(domain_value, (list, tuple)):
            return []
        return [
            [item[0], item[1], uid]
            if (isinstance(item, (list, tuple)) and len(item) == 3 and item[2] == "uid")
            else list(item)
            if isinstance(item, (list, tuple))
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
        """Parse comma-separated formula args, respecting quoted strings."""
        if not args_str:
            return []
        args = []
        current = ""
        in_quotes = False
        for ch in args_str:
            if ch == '"':
                in_quotes = not in_quotes
            elif ch == "," and not in_quotes:
                args.append(_coerce(current.strip()))
                current = ""
                continue
            current += ch
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
            raise ValueError(f"List '{list_id}' not found")

        model = request.env[list_data["model"]].sudo()
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
        info = request.env[list_data["model"]].sudo().fields_get([str(args[1])])
        return info.get(str(args[1]), {}).get("string", str(args[1]))

    def _eval_pivot(self, snapshot, args):
        """ODOO.PIVOT(pivot_id, measure, [field1, value1, ...])"""
        if len(args) < 2:
            raise ValueError("ODOO.PIVOT requires at least 2 args")

        pivot_id, measure = str(args[0]), str(args[1])
        pivot_data = snapshot.get("pivots", {}).get(pivot_id)
        if not pivot_data:
            raise ValueError(f"Pivot '{pivot_id}' not found")

        model = request.env[pivot_data["model"]].sudo()
        raw_domain = pivot_data.get("domain", [])
        _logger.info("PIVOT %s raw_domain: %r (type=%s)", pivot_id, raw_domain, type(raw_domain).__name__)
        base_domain = self._resolve_domain(raw_domain, model)
        _logger.info("PIVOT %s base_domain after resolve: %r", pivot_id, base_domain)

        # Parse field/value pairs from args[2:]
        pairs = []
        i = 2
        while i + 1 < len(args):
            fs = str(args[i])
            if fs != "measure":
                pairs.append((fs, args[i + 1]))
            i += 2

        measure_field = measure.split(":")[0] if ":" in measure else measure
        fields_to_read = [] if measure == "__count" else [measure]

        if not pairs:
            result = self._safe_read_group(model, base_domain, fields_to_read, [])
            if not result:
                return 0
            return result[0].get("__count" if measure == "__count" else measure_field, 0)

        # Build narrow domain from pairs and execute
        _logger.info("PIVOT %s pairs: %r", pivot_id, pairs)
        extra = self._pairs_to_domain(pairs, model)
        combined = base_domain + extra
        _logger.info("PIVOT %s combined domain: %r", pivot_id, combined)
        group_bys = [fs for fs, _ in pairs]

        groups = self._safe_read_group(model, combined, fields_to_read, group_bys)
        if not groups:
            return 0

        key = "__count" if measure == "__count" else measure_field
        return groups[0].get(key, 0)

    def _eval_pivot_table(self, snapshot, args):
        """ODOO.PIVOT.TABLE(pivot_id, ...) — returns 2D array."""
        if len(args) < 1:
            raise ValueError("ODOO.PIVOT.TABLE requires at least 1 arg")

        pivot_id = str(args[0])
        pivot_data = snapshot.get("pivots", {}).get(pivot_id)
        if not pivot_data:
            raise ValueError(f"Pivot '{pivot_id}' not found")

        model = request.env[pivot_data["model"]].sudo()
        base_domain = self._resolve_domain(pivot_data.get("domain", []), model)
        measures = self._get_measures(pivot_data)
        measure_fields = [m for m in measures if m != "__count"]
        all_group_bys = pivot_data.get("rowGroupBys", []) + pivot_data.get("colGroupBys", [])

        if not all_group_bys:
            result = model.read_group(base_domain, measure_fields, [], lazy=False)
            if not result:
                return [["Total", 0]]
            row = ["Total"]
            for m in measures:
                k = m.split(":")[0] if ":" in m else m
                row.append(result[0].get(k if m != "__count" else "__count", 0))
            return [row]

        try:
            groups = model.read_group(base_domain, measure_fields, all_group_bys, lazy=False)
        except Exception as e:
            _logger.warning("PIVOT.TABLE read_group error: %s", e)
            return [["Error", str(e)]]

        table = [list(all_group_bys) + measures]
        for group in groups:
            row = []
            for gb in all_group_bys:
                val = group.get(gb)
                row.append(val[1] if isinstance(val, (list, tuple)) and len(val) == 2 else val)
            for m in measures:
                k = m.split(":")[0] if ":" in m else m
                row.append(group.get(k if m != "__count" else "__count", 0))
            table.append(row)
        return table

    def _eval_pivot_header(self, snapshot, args):
        """ODOO.PIVOT.HEADER(pivot_id, [field1, value1, ...])"""
        if len(args) < 1:
            return "Total"

        pivot_id = str(args[0])
        domain_args = args[1:]
        pivot_data = snapshot.get("pivots", {}).get(pivot_id)
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
        model = request.env[pivot_data["model"]].sudo()
        field_obj = model._fields.get(field_name)

        if not field_obj:
            return str(value)
        if field_obj.type in ("date", "datetime") and granularity:
            return _format_date_header(granularity, value)
        if field_obj.type in ("many2one", "many2many", "one2many") and field_obj.comodel_name:
            try:
                rec = request.env[field_obj.comodel_name].sudo().browse(int(value))
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
            value = f.get("currentValue") or f.get("defaultValue")
            if not value:
                return ""
            if isinstance(value, str):
                value = _resolve_date_shortcut(value)
                if isinstance(value, str):
                    return value
            if isinstance(value, dict):
                if "yearOffset" in value:
                    return str(datetime.now().year + int(value.get("yearOffset", 0)))
                return str(value.get("value", ""))
            return str(value)
        return ""

    def _eval_currency_rate(self, _snapshot, args):
        """ODOO.CURRENCY.RATE(from, to) — delegates to Odoo built-in."""
        if len(args) < 2:
            return 1.0
        try:
            rate = request.env["res.currency.rate"].sudo()._get_rate_for_spreadsheet(str(args[0]), str(args[1]))
            return rate or 1.0
        except Exception:
            return 1.0

    # ── Domain & date helpers ────────────────────────────────────────────────

    def _resolve_domain(self, domain_value, model):
        """Parse + resolve uid + sanitize dates in one step."""
        domain = self._parse_and_resolve_domain(domain_value)
        return self._sanitize_dates(domain, model)

    def _sanitize_dates(self, domain, model):
        """Convert date-like strings (MM/YYYY, YYYY) in domain to proper ranges."""
        month_re = re.compile(r"^(\d{1,2})/(\d{4})$")
        result = []
        _logger.info("_sanitize_dates input: %r", domain)
        for item in domain:
            if not (isinstance(item, (list, tuple)) and len(item) == 3):
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
                except (ValueError, TypeError):
                    pass
            if rng:
                _logger.info("_sanitize_dates: converted %r to range %r", item, rng)
                result.append((field_name, ">=", rng[0]))
                result.append((field_name, "<", rng[1]))
            else:
                _logger.info("_sanitize_dates: date field %s but no range for value %r", field_name, value)
                result.append(item)
        _logger.info("_sanitize_dates output: %r", result)
        return result

    def _pairs_to_domain(self, pairs, model):
        """Convert pivot field/value pairs to domain conditions."""
        domain = []
        for field_spec, value in pairs:
            fname = field_spec.split(":")[0] if ":" in field_spec else field_spec
            gran = field_spec.split(":")[1] if ":" in field_spec else None
            fobj = model._fields.get(fname)
            _logger.info(
                "_pairs_to_domain: spec=%r val=%r(%s) fname=%s gran=%s fobj=%s ftype=%s",
                field_spec,
                value,
                type(value).__name__,
                fname,
                gran,
                bool(fobj),
                fobj.type if fobj else None,
            )

            if value == "false" or value is False:
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
        """read_group inside a savepoint to not poison the transaction."""
        cr = request.env.cr
        try:
            cr.execute("SAVEPOINT pivot_rg")
            result = model.read_group(domain, fields, group_bys, lazy=False)
            cr.execute("RELEASE SAVEPOINT pivot_rg")
            return result
        except Exception as e:
            _logger.warning("read_group error: %s", e)
            cr.execute("ROLLBACK TO SAVEPOINT pivot_rg")
            return None

    @staticmethod
    def _order_string(order_by):
        """Convert orderBy list to Odoo order string."""
        if not order_by:
            return None
        parts = [f"{o['name']} {'ASC' if o.get('asc', True) else 'DESC'}" for o in order_by if o.get("name")]
        return ", ".join(parts) or None

    @staticmethod
    def _format_value(record, field_name, model):
        """Format a record field value for display."""
        fobj = model._fields.get(field_name)
        val = record[field_name] if field_name in record else None
        if val is None or val is False:
            return ""
        if fobj and fobj.type == "selection":
            sel = dict(fobj._description_selection(model.env))
            return sel.get(val, val)
        if hasattr(val, "_name"):
            if not val:
                return ""
            if len(val) > 1:
                return ", ".join(r.display_name or str(r) for r in val)
            return val.display_name or str(val)
        return val

    @staticmethod
    def _get_measures(pivot_data):
        """Extract measure field names from pivot definition."""
        raw = pivot_data.get("measures", [])
        return [m.get("field", m.get("name", "")) if isinstance(m, dict) else str(m) for m in raw]

    @staticmethod
    def _measure_label(pivot_data, measure):
        if measure == "__count":
            return "Count"
        mf = measure.split(":")[0] if ":" in measure else measure
        fobj = request.env[pivot_data["model"]].sudo()._fields.get(mf)
        return fobj.string if fobj else measure

    def _resolve_nested(self, snapshot, content):
        """Resolve nested ODOO.FILTER.VALUE calls and & concatenation."""

        def _repl(m):
            try:
                v = self._eval_filter_value(snapshot, [m.group(1)])
                return str(v) if v else ""
            except Exception:
                return ""

        resolved = re.sub(r'ODOO\.FILTER\.VALUE\("([^"]*)"\)', _repl, content)
        for _ in range(10):
            prev = resolved
            resolved = re.sub(r'"([^"]*)"&"([^"]*)"', r'"\1\2"', resolved)
            resolved = re.sub(r'"([^"]*)"&(\w+)', lambda m: f'"{m.group(1)}{m.group(2)}"', resolved)
            resolved = re.sub(r'(\w+)&"([^"]*)"', lambda m: f'"{m.group(1)}{m.group(2)}"', resolved)
            if resolved == prev:
                break
        return resolved


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


def _infer_date_granularity(value):
    """Infer date granularity from value pattern when not explicitly specified.

    Returns 'month', 'year', 'quarter', 'day', or None.
    """
    parts = str(value).split("/")
    if len(parts) == 2:
        try:
            left, right = int(parts[0]), int(parts[1])
            if 1 <= left <= 12 and 1900 <= right <= 2200:
                return "month"
            if 1 <= left <= 4 and 1900 <= right <= 2200:
                return "quarter"
        except (ValueError, TypeError):
            pass
    elif len(parts) == 3:
        return "day"
    elif len(parts) == 1:
        try:
            y = int(value)
            if 1900 <= y <= 2200:
                return "year"
        except (ValueError, TypeError):
            pass
    return None


def _date_to_range(granularity, value):
    """Convert pivot date value (e.g. '2/2026') to (from, to) date strings.

    Returns tuple ('YYYY-MM-DD', 'YYYY-MM-DD') or None.
    """
    try:
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


def _format_date_header(granularity, value):
    """Format pivot date header for display."""
    s = str(value)
    try:
        parts = s.split("/")
        if granularity == "month" and len(parts) == 2:
            return f"{_MONTH_NAMES[int(parts[0])]} {parts[1]}"
        if granularity == "quarter" and len(parts) == 2:
            return f"Q{parts[0]} {parts[1]}"
        if granularity == "week" and len(parts) == 2:
            return f"W{parts[0]} {parts[1]}"
    except (IndexError, ValueError):
        pass
    return s
