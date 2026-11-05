# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from datetime import datetime
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

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

    def test_date_filter_values_are_shown_like_odoo(self):
        today = fields.Date.context_today(self.env.user)
        quarter = (today.month - 1) // 3 + 1
        snapshot = {
            "globalFilters": [
                {"label": "Q", "type": "date", "currentValue": {"yearOffset": -1, "period": "third_quarter"}},
                {"label": "M", "type": "date", "currentValue": {"yearOffset": 0, "period": "march"}},
                {"label": "Y", "type": "date", "currentValue": {"yearOffset": 1}},
                {"label": "This month", "type": "date", "defaultValue": "this_month"},
                {"label": "This quarter", "type": "date", "defaultValue": "this_quarter"},
                {"label": "Relative", "type": "date", "defaultValue": "last_year"},
                {"label": "Unknown range", "type": "date", "defaultValue": "next_century"},
                {"label": "Text", "type": "text", "defaultValue": "last_year"},
            ]
        }
        self.assertEqual(
            compute_filter_values(snapshot),
            {
                "Q": f"Q3/{today.year - 1}",
                "M": f"03/{today.year}",
                "Y": str(today.year + 1),
                "This month": f"{today.month:02d}/{today.year}",
                "This quarter": f"Q{quarter}/{today.year}",
                "Relative": "Last 365 Days",
                "Unknown range": "",
                "Text": "last_year",
            },
        )
        self.assertEqual(
            self.evaluator.evaluate_single_formula(snapshot, '=ODOO_FILTER_VALUE("Q")'), f"Q3/{today.year - 1}"
        )

    def test_currency_rate_is_odoo_rate_for_the_date_and_company(self):
        currency = self.env["res.currency"].create({"name": "OOX", "symbol": "X", "active": True})
        company = self.env.company
        other_company = self.env["res.company"].create({"name": "OO Rates Co", "currency_id": company.currency_id.id})
        Rate = self.env["res.currency.rate"]
        for day, rate, rate_company in (("2020-01-01", 2.0, company), (fields.Date.today(), 4.0, company)):
            Rate.create({"currency_id": currency.id, "name": day, "rate": rate, "company_id": rate_company.id})
        Rate.create({"currency_id": currency.id, "name": "2020-01-01", "rate": 8.0, "company_id": other_company.id})
        company_code = self.env.company.currency_id.name
        expected = Rate._get_rate_for_spreadsheet

        self.assertEqual(self._eval(f'=ODOO_CURRENCY_RATE("{company_code}","OOX")'), expected(company_code, "OOX"))
        for date_arg in ('"2020-06-01"', '"06/01/2020"', "43983"):
            with self.subTest(date=date_arg):
                self.assertEqual(
                    self._eval(f'=ODOO_CURRENCY_RATE("{company_code}","OOX",{date_arg})'),
                    expected(company_code, "OOX", "2020-06-01"),
                )
        self.assertEqual(
            self._eval(f'=ODOO_CURRENCY_RATE("{company_code}","OOX","2020-06-01",{other_company.id})'),
            expected(company_code, "OOX", "2020-06-01", other_company.id),
        )
        self.assertNotEqual(expected(company_code, "OOX"), expected(company_code, "OOX", "2020-06-01"))
        self.assertNotEqual(
            expected(company_code, "OOX", "2020-06-01"), expected(company_code, "OOX", "2020-06-01", other_company.id)
        )

    def test_currency_rate_errors(self):
        cases = {
            '=ODOO_CURRENCY_RATE("XXX","USD")': "#ERROR: Currency rate unavailable.",
            '=ODOO_CURRENCY_RATE("","USD")': "#ERROR: Currency rate unavailable.",
            '=ODOO_CURRENCY_RATE("USD")': "#ERROR: ODOO.CURRENCY.RATE requires at least 2 args",
            '=ODOO_CURRENCY_RATE("USD","EUR","not a date")': "#ERROR: Invalid date: not a date",
        }
        for formula, error in cases.items():
            with self.subTest(formula=formula):
                self.assertEqual(self._eval(formula), error)

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
        self.assertEqual(resolve(42), [])
        with self.assertRaisesRegex(ValueError, "Invalid domain"):
            resolve("not a domain(")

    def test_relative_date_domains_are_evaluated_on_each_call(self):
        """Odoo stores domains like "the last 365 days" as Python expressions; they must not be dropped."""
        pivot = {"model": "res.partner", "measures": [{"field": "__count"}], "rowGroupBys": [], "colGroupBys": []}
        since = "(context_today() + relativedelta(days={})).strftime('%Y-%m-%d')"
        self.snapshot = {
            "pivots": {
                "1": {**pivot, "domain": f"[('ref', '=', '{REF}'), ('create_date', '>=', {since.format(-1)})]"},
                "2": {**pivot, "domain": f"[('ref', '=', '{REF}'), ('create_date', '>=', {since.format(1)})]"},
                "3": {**pivot, "domain": "[('ref', '=', no_such_name)]"},
            }
        }
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"__count")'), 3)
        self.assertEqual(self._eval('=ODOO_PIVOT(2,"__count")'), 0)
        self.assertRegex(self._eval('=ODOO_PIVOT(3,"__count")'), "^#ERROR: Invalid domain")

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
class TestFormulaAccess(TransactionCase):
    """The formulas read with the rights of the user who opens the file, as Odoo Spreadsheet does."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login="oo_formula_user", groups="base.group_user")
        Partner = cls.env["res.partner"]
        Partner.create([{"name": "Alpha Corp", "color": 3, "ref": REF}, {"name": "Beta Corp", "color": 5, "ref": REF}])
        pivot = {"model": "res.partner", "rowGroupBys": [], "colGroupBys": []}
        cls.snapshot = {
            "lists": {
                "1": {"model": "ir.config_parameter", "domain": [], "columns": ["key"]},
                "2": {"model": "res.partner", "domain": [["ref", "=", REF]], "columns": ["name", "color"]},
                "3": {"model": "res.partner", "domain": [["ref", "=", REF], ["color", ">", 4]], "columns": ["name"]},
            },
            "pivots": {
                "4": {**pivot, "domain": [["ref", "=", REF]], "measures": [{"field": "color"}]},
                "5": {**pivot, "domain": [["ref", "=", REF]], "measures": [{"field": "__count"}]},
                "6": {**pivot, "domain": "[('id', '=', user.id)]", "measures": [{"field": "__count"}]},
            },
        }

    def setUp(self):
        super().setUp()
        request = fake_request(self.env(user=self.user))
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        # A field the user may not read, as a field with groups in Odoo.
        groups = patch.object(self.env["res.partner"]._fields["color"], "groups", "base.group_system")
        groups.start()
        self.addCleanup(groups.stop)
        self.evaluator = SpreadsheetFormulaEvaluator()

    def _eval(self, formula):
        return self.evaluator.evaluate_single_formula(self.snapshot, formula)

    def test_a_model_or_a_field_the_user_cannot_read_gives_an_error(self):
        formulas = [
            '=ODOO_LIST(1,1,"key")',
            '=ODOO_LIST_HEADER(1,"key")',
            '=ODOO_LIST(2,1,"color")',
            '=ODOO_LIST_HEADER(2,"color")',
            '=ODOO_PIVOT(4,"color")',
            '=ODOO_PIVOT(5,"__count","color","3")',
            '=ODOO_PIVOT_HEADER(5,"color","3")',
        ]
        for formula in formulas:
            with self.subTest(formula=formula):
                self.assertRegex(str(self._eval(formula)), "^#ERROR: ")

    def test_a_domain_on_a_field_the_user_cannot_read_gives_an_error(self):
        """Odoo checks the fields of a search domain too: a filter must not reveal a hidden value."""
        self.assertRegex(self._eval('=ODOO_LIST(3,1,"name")'), "^#ERROR: ")

    def test_what_the_user_can_read_is_evaluated(self):
        self.assertEqual(self._eval('=ODOO_LIST(2,1,"name")'), "Alpha Corp")
        self.assertEqual(self._eval('=ODOO_PIVOT(5,"__count")'), 2)

    def test_a_domain_gets_no_records_to_evaluate(self):
        """A record such as the user would give the expression the whole environment, sudo() included."""
        self.assertRegex(self._eval('=ODOO_PIVOT(6,"__count")'), "^#ERROR: Invalid domain")


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
