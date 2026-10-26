# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from datetime import datetime

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.tests.common import known_bug
from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_formulas import (
    SpreadsheetFormulaEvaluator,
    _date_to_range,
    _infer_date_granularity,
    compute_filter_values,
    get_field_excel_format,
    load_metadata_for_document,
)

from .common import fake_request

REF = "oo-formula"


@tagged("post_install", "-at_install")
class TestFormulaEvaluator(TransactionCase):
    """The server-side ODOO_* formulas behind the custom functions of the ONLYOFFICE spreadsheet editor."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.alpha = Partner.create({"name": "Alpha Corp", "is_company": True, "color": 3, "ref": REF})
        cls.beta = Partner.create({"name": "Beta Corp", "is_company": True, "color": 5, "ref": REF})
        cls.carol = Partner.create({"name": "Carol", "parent_id": cls.alpha.id, "ref": REF})
        cls.snapshot = {
            "lists": {
                "1": {
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "orderBy": [{"name": "name", "asc": True}],
                    "columns": ["name", "parent_id", "type"],
                }
            },
            "pivots": {
                "2": {
                    "model": "res.partner",
                    "domain": f"[('ref', '=', '{REF}')]",
                    "measures": [{"field": "__count"}, {"field": "color"}],
                    "rowGroupBys": ["is_company"],
                    "colGroupBys": [],
                }
            },
            "globalFilters": [
                {"label": "Region", "currentValue": "EU", "defaultValue": "US"},
                {"label": "Year", "defaultValue": "this_year"},
                {"label": "Stage", "defaultValue": {"value": 3}},
            ],
        }

    def setUp(self):
        super().setUp()
        request = fake_request(self.env)
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        self.evaluator = SpreadsheetFormulaEvaluator()

    def _eval(self, formula):
        return self.evaluator.evaluate_single_formula(self.snapshot, formula)

    # -- ODOO_LIST / ODOO_LIST_HEADER --

    def test_list_returns_the_nth_record_in_the_list_order(self):
        self.assertEqual(self._eval('=ODOO_LIST(1,1,"name")'), "Alpha Corp")
        self.assertEqual(self._eval('=ODOO_LIST(1,3,"name")'), "Carol")
        self.assertEqual(self._eval('=ODOO_LIST(1,4,"name")'), "", "past the end of the list")

    def test_list_formats_relations_and_selections(self):
        self.assertEqual(self._eval('=ODOO_LIST(1,3,"parent_id")'), "Alpha Corp")
        self.assertEqual(self._eval('=ODOO_LIST(1,3,"type")'), "Contact")
        self.assertEqual(self._eval('=ODOO_LIST(1,1,"parent_id")'), "", "empty many2one")

    def test_list_header_is_the_field_label(self):
        self.assertEqual(self._eval('=ODOO_LIST_HEADER(1,"color")'), "Color Index")

    # -- ODOO_PIVOT --

    def test_pivot_total_and_measures(self):
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count")'), 3)
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"color")'), 8)
        self.assertEqual(self._eval('=-ODOO_PIVOT(2,"__count")'), -3)

    def test_pivot_cell_is_narrowed_by_field_value_pairs(self):
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count","is_company","true")'), 2)
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count","is_company","false")'), 1)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(2,"color","parent_id",{self.alpha.id})'), 0)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(2,"__count","parent_id",{self.alpha.id})'), 1)

    def test_pivot_cell_without_data_is_zero(self):
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count","parent_id",999999999)'), 0)

    def test_pivot_table_lists_every_group(self):
        table = self._eval("=ODOO_PIVOT_TABLE(2)")
        self.assertEqual(table[0], ["is_company", "__count", "color"])
        self.assertCountEqual(table[1:], [[False, 1, 0], [True, 2, 8]])

    def test_pivot_header_labels(self):
        cases = {
            '=ODOO_PIVOT_HEADER(2,"measure","__count")': "Count",
            '=ODOO_PIVOT_HEADER(2,"measure","color")': "Color Index",
            '=ODOO_PIVOT_HEADER(2,"type","contact")': "Contact",
            f'=ODOO_PIVOT_HEADER(2,"parent_id",{self.alpha.id})': "Alpha Corp",
            '=ODOO_PIVOT_HEADER(2,"is_company","false")': "None",
            '=ODOO_PIVOT_HEADER(2,"create_date:month","3/2026")': "03/01/2026",
            '=ODOO_PIVOT_HEADER(2,"create_date:quarter","1/2026")': "Q1 2026",
            "=ODOO_PIVOT_HEADER(2)": "Total",
            '=ODOO_PIVOT_HEADER(9,"type","contact")': "contact",
        }
        for formula, label in cases.items():
            with self.subTest(formula=formula):
                self.assertEqual(self._eval(formula), label)

    # -- ODOO_FILTER_VALUE / ODOO_CURRENCY_RATE --

    def test_filter_values(self):
        self.assertEqual(self._eval('=ODOO_FILTER_VALUE("Region")'), "EU", "the current value wins")
        self.assertEqual(self._eval('=ODOO_FILTER_VALUE("Year")'), str(datetime.now().year))
        self.assertEqual(self._eval('=ODOO_FILTER_VALUE("Stage")'), "3")
        self.assertEqual(self._eval('=ODOO_FILTER_VALUE("Unknown")'), "")
        self.assertEqual(
            compute_filter_values(self.snapshot), {"Region": "EU", "Year": str(datetime.now().year), "Stage": "3"}
        )

    def test_currency_rate_without_both_currencies_is_one(self):
        self.assertEqual(self._eval('=ODOO_CURRENCY_RATE("USD")'), 1.0)

    # -- Errors --

    def test_errors_are_returned_as_cell_values(self):
        self.assertEqual(self._eval("=SUM(A1:A2)"), "#ERROR: Invalid formula")
        self.assertEqual(self._eval("=ODOO_NOPE(1)"), "#ERROR: Unknown function NOPE")
        self.assertEqual(self._eval('=ODOO_LIST(7,1,"name")'), "#ERROR: List '7' not found")
        self.assertEqual(self._eval("=ODOO_LIST(1)"), "#ERROR: ODOO.LIST requires 3 args")
        self.assertEqual(self._eval('=ODOO_PIVOT(9,"__count")'), "#ERROR: Pivot '9' not found")

    def test_failed_read_group_does_not_break_the_transaction(self):
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count","no_such_field","x")'), "#ERROR: read_group failed")
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count")'), 3)

    # -- Arguments and domains --

    def test_arguments_keep_quoted_commas_and_escaped_quotes(self):
        parse = SpreadsheetFormulaEvaluator._parse_args
        self.assertEqual(parse('1,2,"a, b"'), [1, 2, "a, b"])
        self.assertEqual(parse(r'"say \"hi\"", 1.5'), ['say "hi"', 1.5])
        self.assertEqual(parse(""), [])

    def test_domain_placeholders_are_resolved(self):
        uid = self.env.uid
        resolve = self.evaluator.parse_and_resolve_domain
        self.assertEqual(resolve("[('user_id', '=', uid)]"), [["user_id", "=", uid]])
        self.assertEqual(resolve([["user_id", "=", "uid"]]), [["user_id", "=", uid]])
        self.assertEqual(resolve("[]"), [])
        self.assertEqual(resolve("not a domain("), [])
        self.assertEqual(resolve(42), [])

    def test_month_and_year_values_become_date_ranges(self):
        model = self.env["res.partner"]
        domain = [["create_date", "=", "03/2026"], ["write_date", "=", "2025"], ["name", "=", "2025"]]
        self.assertEqual(
            self.evaluator._resolve_domain(domain, model),
            [
                ("create_date", ">=", "2026-03-01"),
                ("create_date", "<", "2026-04-01"),
                ("write_date", ">=", "2025-01-01"),
                ("write_date", "<", "2026-01-01"),
                ["name", "=", "2025"],
            ],
        )

    # -- Column formats --

    def test_excel_formats_by_field_type(self):
        model = self.env["res.partner"]
        cases = {
            "color": ("#,##0", "right"),
            "is_company": (None, "center"),
            "create_date": (None, "right"),
            "create_date:month": (None, "right"),
            "name": (None, "left"),
            "no_such_field": (None, None),
            None: (None, None),
        }
        for field_name, expected in cases.items():
            with self.subTest(field=field_name):
                self.assertEqual(get_field_excel_format(model, field_name), expected)

    @known_bug("get_field_excel_format reads Float.digits, gone in Odoo 18 (get_digits(env))")
    def test_float_format_uses_the_field_precision(self):
        self.assertEqual(get_field_excel_format(self.env["res.partner"], "partner_latitude")[0], "#,##0.0000000")

    def test_column_formats_of_lists_and_pivots(self):
        left = {"format": None, "align": "left"}
        self.assertEqual(
            self.evaluator.get_list_column_formats(self.snapshot["lists"]["1"]),
            {"name": left, "parent_id": left, "type": left},
        )
        self.assertEqual(
            self.evaluator.get_pivot_column_formats(self.snapshot["pivots"]["2"]),
            {"__count": {"format": "#,##0", "align": "right"}, "color": {"format": "#,##0", "align": "right"}},
        )


@tagged("post_install", "-at_install")
class TestFormulaHelpers(TransactionCase):
    """Module-level helpers of spreadsheet_formulas."""

    def test_date_ranges(self):
        cases = {
            ("year", "2025"): ("2025-01-01", "2026-01-01"),
            ("quarter", "4/2025"): ("2025-10-01", "2026-01-01"),
            ("quarter", "2/2025"): ("2025-04-01", "2025-07-01"),
            ("month", "12/2025"): ("2025-12-01", "2026-01-01"),
            ("month", "2/2025"): ("2025-02-01", "2025-03-01"),
            ("week", "1/2026"): ("2025-12-29", "2026-01-05"),
            ("day", "2/28/2025"): ("2025-02-28", "2025-03-01"),
            ("month", "13/x"): None,
            ("hour", "1"): None,
        }
        for (granularity, value), expected in cases.items():
            with self.subTest(granularity=granularity, value=value):
                self.assertEqual(_date_to_range(granularity, value), expected)

    def test_granularity_is_inferred_from_the_value(self):
        cases = {"3/2025": "month", "2/28/2025": "day", "2025": "year", "Q1": None, "20/2025": None}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(_infer_date_granularity(value), expected)

    def test_metadata_of_a_document(self):
        Document = self.env["documents.document"]
        metadata = {"lists": {"1": {"model": "res.partner", "domain": [], "columns": ["name"], "orderBy": []}}}
        with_metadata = Document.create({"name": "a.xlsx", "onlyoffice_spreadsheet_metadata": json.dumps(metadata)})
        self.assertEqual(load_metadata_for_document(with_metadata), metadata)

        broken = Document.create({"name": "b.xlsx", "onlyoffice_spreadsheet_metadata": "{broken"})
        self.assertEqual(load_metadata_for_document(broken), {})

        source = Document.create(
            {
                "name": "Source",
                "handler": "spreadsheet",
                "mimetype": "application/o-spreadsheet",
                "spreadsheet_data": json.dumps({"sheets": [{"id": "s1", "name": "Sheet1"}], **metadata}),
            }
        )
        copy = Document.create({"name": "c.xlsx", "onlyoffice_spreadsheet_source_id": source.id})
        self.assertEqual(load_metadata_for_document(copy)["lists"], metadata["lists"])
