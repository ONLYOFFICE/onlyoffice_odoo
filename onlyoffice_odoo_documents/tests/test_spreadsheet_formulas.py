# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from datetime import date, datetime, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_formulas import (
    SpreadsheetFormulaEvaluator,
    _date_to_range,
    _datetime_range,
    _infer_date_granularity,
    _to_serial,
    compute_filter_values,
    formula_context,
    get_field_excel_format,
    load_metadata_for_document,
    normalize_pivot_definition,
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
        # Since Odoo 20 is_company is computed: a partner with a VAT of its own is a company.
        cls.alpha = Partner.create({"name": "Alpha Corp", "vat": "OO-ALPHA", "color": 3, "ref": REF})
        cls.beta = Partner.create({"name": "Beta Corp", "vat": "OO-BETA", "color": 5, "ref": REF})
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
        # ODOO_LIST_VALUE is the Odoo 20 name of the same function.
        self.assertEqual(self._eval('=ODOO_LIST_VALUE(1,3,"name")'), "Carol")

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
            # A month is the serial number of its first day (the cell format shows "March 2026").
            '=ODOO_PIVOT_HEADER(2,"create_date:month","3/2026")': 46082,
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
        self.assertEqual(self._eval('=ODOO_FILTER_VALUE("Unknown")'), '#ERROR: Filter "Unknown" not found')
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

    def test_filters_of_odoo_19_give_their_value_and_their_label(self):
        """ODOO.FILTER.VALUE of Odoo 19 gives the value (a date filter: the first day of its period), ODOO.FILTER.LABEL
        and ODOO.FILTER.VALUE.V18 the label; the editor cannot spread the second cell Odoo gives a date filter."""
        today = fields.Date.context_today(self.env.user)
        last_month = today.replace(day=1) - timedelta(days=1)

        def serial(day):
            return (day - date(1899, 12, 30)).days

        snapshot = {
            "globalFilters": [
                {"label": "Month", "type": "date", "currentValue": {"type": "month", "year": 2026, "month": 9}},
                {"label": "Quarter", "type": "date", "currentValue": {"type": "quarter", "year": 2026, "quarter": 3}},
                {"label": "Year", "type": "date", "currentValue": {"type": "year", "year": 2026}},
                {"label": "Last month", "type": "date", "defaultValue": "last_month"},
                {"label": "Last 7 days", "type": "date", "defaultValue": "last_7_days"},
                {
                    "label": "Range",
                    "type": "date",
                    "currentValue": {"type": "range", "from": "2026-03-05", "to": "2026-03-20"},
                },
                {
                    "label": "Whole month",
                    "type": "date",
                    "currentValue": {"type": "range", "from": "2026-03-01", "to": "2026-03-31"},
                },
                {
                    "label": "Partner",
                    "type": "relation",
                    "modelName": "res.partner",
                    "currentValue": {"operator": "in", "ids": [self.alpha.id]},
                },
                {
                    "label": "Me",
                    "type": "relation",
                    "modelName": "res.users",
                    "defaultValue": {"operator": "in", "ids": "current_user"},
                },
                {"label": "Text", "type": "text", "currentValue": {"operator": "ilike", "strings": ["a", "b"]}},
                {"label": "Set", "type": "boolean", "currentValue": {"operator": "set"}},
                {
                    "label": "Between",
                    "type": "numeric",
                    "currentValue": {"operator": "between", "minimumValue": 2, "maximumValue": 5},
                },
                {"label": "Empty", "type": "date"},
            ]
        }
        cases = {
            "Month": (serial(date(2026, 9, 1)), "09/2026"),
            "Quarter": (serial(date(2026, 7, 1)), "Q3/2026"),
            "Year": (serial(date(2026, 1, 1)), "2026"),
            "Last month": (serial(last_month.replace(day=1)), f"{last_month.month:02d}/{last_month.year}"),
            "Last 7 days": (serial(today - timedelta(days=6)), serial(today - timedelta(days=6))),
            "Range": (serial(date(2026, 3, 5)), serial(date(2026, 3, 5))),
            "Whole month": (serial(date(2026, 3, 1)), "03/2026"),
            "Partner": (str(self.alpha.id), "Alpha Corp"),
            "Me": (str(self.env.uid), self.env.user.name),
            "Text": ("a, b", "a, b"),
            "Set": (True, True),
            "Between": (2, 2),
            "Empty": ("", ""),
        }
        for name, (value, label) in cases.items():
            with self.subTest(filter=name):
                evaluate = self.evaluator.evaluate_single_formula
                self.assertEqual(evaluate(snapshot, f'=ODOO_FILTER_VALUE("{name}")'), value)
                self.assertEqual(evaluate(snapshot, f'=ODOO_FILTER_LABEL("{name}")'), label)
                self.assertEqual(evaluate(snapshot, f'=ODOO_FILTER_VALUE_V18("{name}")'), label)
        self.assertEqual(compute_filter_values(snapshot)["Quarter"], "Q3/2026")
        # The editor quotes the name of a filter as the spreadsheet does: a quote doubled, a backslash as it is.
        snapshot["globalFilters"].append(
            {"label": 'Say "hi" \\', "type": "text", "currentValue": {"operator": "ilike", "strings": ["x"]}}
        )
        for function in ("ODOO_FILTER_VALUE", "ODOO_FILTER_LABEL", "ODOO_FILTER_VALUE_V18"):
            with self.subTest(function=function):
                self.assertEqual(self.evaluator.evaluate_single_formula(snapshot, f'={function}("Say ""hi"" \\")'), "x")

    def test_currency_rate_is_odoo_rate_for_the_date_and_company(self):
        currency = self.env["res.currency"].create({"name": "OOX", "symbol": "X", "active": True})
        company = self.env.company
        other_company = self.env["res.company"].create({"name": "OO Rates Co", "currency_id": company.currency_id.id})
        Rate = self.env["res.currency.rate"]
        for day, rate, rate_company in (("2020-01-01", 2.0, company), ("2021-01-01", 4.0, company)):
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
        # A rate dated today is not taken by Odoo 20 in a test transaction: compare two past dates instead.
        self.assertNotEqual(expected(company_code, "OOX", "2021-06-01"), expected(company_code, "OOX", "2020-06-01"))
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
        # A quote inside a text is doubled, as the spreadsheet writes it; a backslash is a character like another.
        self.assertEqual(parse('"say ""hi""", 1.5'), ['say "hi"', 1.5])
        self.assertEqual(parse(r'"C:\dir\", "(a, b)"'), ["C:\\dir\\", "(a, b)"])
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
        # Days of a datetime in the time zone of the context, in UTC, as read_group groups them.
        model = self.env["res.partner"].with_context(tz="Europe/Brussels")
        domain = [["create_date", "=", "03/2026"], ["write_date", "=", "2025"], ["name", "=", "2025"]]
        self.assertEqual(
            self.evaluator._resolve_domain(domain, model),
            [
                ("create_date", ">=", "2026-02-28 23:00:00"),
                ("create_date", "<", "2026-03-31 22:00:00"),
                ("write_date", ">=", "2024-12-31 23:00:00"),
                ("write_date", "<", "2025-12-31 23:00:00"),
                ["name", "=", "2025"],
            ],
        )

    # -- Column formats --

    def test_excel_formats_by_field_type(self):
        model = self.env["res.partner"]
        cases = {
            "color": ("0", "right"),
            "is_company": (None, "center"),
            # The time format of en_US in Odoo 19 has AM/PM.
            "create_date": ("mm/dd/yyyy hh:mm:ss AM/PM", "right"),
            "create_date:day": ("dd mmm yyyy", "right"),
            "create_date:month": ("mmmm yyyy", "right"),
            "create_date:year": ("0", "right"),
            "create_date:quarter": (None, "left"),
            "create_date:day_of_month": ("0", "right"),
            "create_date:month_number": (None, "left"),
            "name": (None, "left"),
            "no_such_field": (None, None),
            None: (None, None),
        }
        for field_name, expected in cases.items():
            with self.subTest(field=field_name):
                self.assertEqual(get_field_excel_format(model, field_name), expected)

    def test_float_format_uses_the_field_precision(self):
        self.assertEqual(get_field_excel_format(self.env["res.partner"], "partner_latitude")[0], "#,##0.0000000")

    def test_column_formats_of_lists_and_pivots(self):
        left = {"format": None, "align": "left"}
        self.assertEqual(
            self.evaluator.get_list_column_formats(self.snapshot["lists"]["1"]),
            {
                "name": {**left, "type": "char"},
                "parent_id": {**left, "type": "many2one"},
                "type": {**left, "type": "selection"},
            },
        )
        integer = {"format": "0", "align": "right", "type": "integer"}
        self.assertEqual(
            self.evaluator.get_pivot_column_formats(self.snapshot["pivots"]["2"]),
            {"__count": integer, "color": integer},
        )


@tagged("post_install", "-at_install")
class TestOdooSpreadsheetPivots(TransactionCase):
    """Pivots as an Odoo Spreadsheet keeps them: named by their formulaId, dimensions, measures by id."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        # Since Odoo 20 is_company is computed: a partner with a VAT of its own is a company.
        cls.partners = Partner.create(
            [
                {"name": "Alpha Corp", "vat": "OO-ALPHA", "color": 3, "ref": REF},
                {"name": "Beta Corp", "vat": "OO-BETA", "color": 5, "ref": REF},
                {"name": "Carol", "ref": REF},
            ]
        )
        cls.created = cls.partners[0].create_date
        cls.snapshot = {
            "pivots": {
                # The key is not what the formulas use.
                "pivot-a": {
                    "type": "ODOO",
                    "formulaId": "1",
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "measures": [
                        {"id": "color:sum", "fieldName": "color", "aggregator": "sum"},
                        {"id": "color:max", "fieldName": "color", "aggregator": "max", "userDefinedName": "Top"},
                        {"id": "__count", "fieldName": "__count"},
                        {"id": "parent_id:count_distinct", "fieldName": "parent_id", "aggregator": "count_distinct"},
                        {"id": "share", "fieldName": "share", "computedBy": {"formula": "=color:sum*2"}},
                    ],
                    "rows": [{"fieldName": "is_company"}],
                    "columns": [{"fieldName": "create_date", "granularity": "month_number"}],
                },
                "pivot-b": {"type": "SPREADSHEET", "formulaId": "2", "dataSet": {"sheetId": "s1"}},
            }
        }

    def setUp(self):
        super().setUp()
        request = fake_request(self.env)
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        self.evaluator = SpreadsheetFormulaEvaluator()

    def _eval(self, formula):
        return self.evaluator.evaluate_single_formula(self.snapshot, formula)

    def test_measures_by_id_with_their_aggregator(self):
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"color:sum")'), 8)
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"color:max")'), 5)
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"__count")'), 3)
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"color:sum","is_company","true")'), 8)
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"__count","is_company","false")'), 1)

    def test_what_the_pivot_does_not_have_is_an_error(self):
        cases = {
            '=ODOO_PIVOT(1,"color")': "#ERROR: Field color does not exist",
            '=ODOO_PIVOT(1,"share")': "#ERROR: Field share does not exist",
            '=ODOO_PIVOT(2,"__count")': "#ERROR: Pivot '2' not found",
            '=ODOO_PIVOT("pivot-a","__count")': "#ERROR: Pivot 'pivot-a' not found",
        }
        for formula, error in cases.items():
            with self.subTest(formula=formula):
                self.assertEqual(self._eval(formula), error)

    def test_measure_headers(self):
        self.assertEqual(self._eval('=ODOO_PIVOT_HEADER(1,"measure","color:sum")'), "Color Index")
        self.assertEqual(self._eval('=ODOO_PIVOT_HEADER(1,"measure","color:max")'), "Top")
        self.assertEqual(self._eval('=ODOO_PIVOT_HEADER(1,"measure","__count")'), "Count")

    def test_groupings_by_number(self):
        month, hour = self.created.month, self.created.hour
        other_month = month % 12 + 1
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:month_number",{month})'), 3)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:month_number",{other_month})'), 0)
        self.assertEqual(
            self._eval(f'=ODOO_PIVOT(1,"color:sum","is_company","true","create_date:month_number",{month})'), 8
        )
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:hour_number",{hour})'), 3)
        self.assertEqual(self._eval('=ODOO_PIVOT(1,"__count","create_date:month_number","false")'), 0)
        headers = {
            '=ODOO_PIVOT_HEADER(1,"create_date:month_number",3)': "March",
            '=ODOO_PIVOT_HEADER(1,"create_date:quarter_number",2)': "Q2",
            '=ODOO_PIVOT_HEADER(1,"create_date:hour_number",13)': "13h",
            '=ODOO_PIVOT_HEADER(1,"create_date:minute_number",5)': "5'",
            '=ODOO_PIVOT_HEADER(1,"create_date:day_of_month",31)': 31,
            # en_US weeks start on Sunday.
            '=ODOO_PIVOT_HEADER(1,"create_date:day_of_week",1)': "Sunday",
            '=ODOO_PIVOT_HEADER(1,"create_date:day_of_week",2)': "Monday",
        }
        for formula, label in headers.items():
            with self.subTest(formula=formula):
                self.assertEqual(self._eval(formula), label)

    def test_a_day_is_its_serial_number(self):
        serial = (self.created.date() - datetime(1899, 12, 30).date()).days
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:day",{serial})'), 3)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:day",{serial + 1})'), 0)
        day = self.created.strftime("%m/%d/%Y")
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:day","{day}")'), 3)
        self.assertEqual(self._eval(f'=ODOO_PIVOT_HEADER(1,"create_date:day",{serial})'), serial)

    def test_a_month_of_odoo_19_is_a_date(self):
        # "Convert to individual formulas" of Odoo 19 writes DATE(year,month,1): the editor passes its serial number.
        first = self.created.date().replace(day=1)
        serial = (first - datetime(1899, 12, 30).date()).days
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:month",{serial})'), 3)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:month",{serial - 40})'), 0)
        self.assertEqual(self._eval(f'=ODOO_PIVOT_HEADER(1,"create_date:month",{serial})'), serial)
        self.assertEqual(self._eval(f'=ODOO_PIVOT(1,"__count","create_date:year",{serial})'), 3)

    def test_column_formats_by_measure_id(self):
        integer = {"format": "0", "align": "right", "type": "integer"}
        self.assertEqual(
            self.evaluator.get_pivot_column_formats(self.snapshot["pivots"]["pivot-a"]),
            {
                "color:sum": integer,
                "color:max": integer,
                "__count": integer,
                "parent_id:count_distinct": integer,
                "create_date:month_number": {"format": None, "align": "left", "type": "datetime"},
            },
        )

    def test_normalized_definition(self):
        self.assertIsNone(normalize_pivot_definition(self.snapshot["pivots"]["pivot-b"]))
        definition = normalize_pivot_definition(self.snapshot["pivots"]["pivot-a"])
        self.assertEqual(
            (definition["rowGroupBys"], definition["colGroupBys"], definition["measures"]),
            (
                ["is_company"],
                ["create_date:month_number"],
                ["color:sum", "color:max", "__count", "parent_id:count_distinct"],
            ),
        )
        self.assertEqual(definition["measureSpecs"]["__count"], "__count")
        self.assertIs(normalize_pivot_definition(definition), definition, "already normalized")


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
            ("day", "46082"): ("2026-03-01", "2026-03-02"),
            # Odoo 19 writes a month as a date, DATE(2026,9,1), and takes a year over 3000 as a date.
            ("month", "46266"): ("2026-09-01", "2026-10-01"),
            ("year", "46266"): ("2026-01-01", "2027-01-01"),
            ("month", "13/x"): None,
            ("hour", "1"): None,
        }
        for (granularity, value), expected in cases.items():
            with self.subTest(granularity=granularity, value=value):
                self.assertEqual(_date_to_range(granularity, value), expected)

    def test_time_zones_of_the_formulas(self):
        # Pivot groups in the time zone of the user, without it in that of the browser; lists in that of the browser.
        cases = {
            ("Europe/Brussels", "Europe/Moscow"): {"tz": "Europe/Brussels", "onlyoffice_browser_tz": "Europe/Moscow"},
            (False, "Europe/Moscow"): {"tz": "Europe/Moscow", "onlyoffice_browser_tz": "Europe/Moscow"},
            ("Europe/Brussels", None): {"tz": "Europe/Brussels"},
            (False, "Not/A_Zone"): {},
        }
        for (user_tz, browser_tz), expected in cases.items():
            with self.subTest(user_tz=user_tz, browser_tz=browser_tz):
                context = formula_context({"tz": "UTC", "onlyoffice_browser_tz": "UTC"}, user_tz, browser_tz)
                self.assertEqual(context, expected)

    def test_a_datetime_of_a_list_is_in_the_time_zone_of_the_browser(self):
        value = datetime(2026, 11, 3, 14, 0)  # UTC
        with_browser = self.env(context={"tz": "Europe/Brussels", "onlyoffice_browser_tz": "Europe/Moscow"})
        without_browser = self.env(context={"tz": "Europe/Brussels"})
        self.assertAlmostEqual(_to_serial(with_browser, value), 46329 + 17 / 24)
        self.assertAlmostEqual(_to_serial(without_browser, value), 46329 + 15 / 24)

    def test_groups_of_a_datetime_are_days_of_the_time_zone_of_the_context(self):
        days = ("2026-11-01", "2026-12-01")
        self.assertEqual(
            _datetime_range(self.env(context={"tz": "Europe/Brussels"}), days),
            ("2026-10-31 23:00:00", "2026-11-30 23:00:00"),
        )
        self.assertEqual(_datetime_range(self.env(context={}), days), ("2026-11-01 00:00:00", "2026-12-01 00:00:00"))

    def test_granularity_is_inferred_from_the_value(self):
        cases = {"3/2025": "month", "2/28/2025": "day", "2025": "year", "Q1": None, "20/2025": None}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(_infer_date_granularity(value), expected)

    def test_metadata_of_a_document(self):
        Document = self.env["documents.document"]
        # Since Odoo 20 a file document cannot be created without its file.
        file = {"raw": b"not an xlsx"}
        metadata = {"lists": {"1": {"model": "res.partner", "domain": [], "columns": ["name"], "orderBy": []}}}
        with_metadata = Document.create(
            {"name": "a.xlsx", "onlyoffice_spreadsheet_metadata": json.dumps(metadata), **file}
        )
        self.assertEqual(load_metadata_for_document(with_metadata), metadata)

        broken = Document.create({"name": "b.xlsx", "onlyoffice_spreadsheet_metadata": "{broken", **file})
        self.assertEqual(load_metadata_for_document(broken), {})

        source = Document.create(
            {
                "name": "Source",
                "handler": "spreadsheet",
                "mimetype": "application/o-spreadsheet",
                "spreadsheet_data": json.dumps({"sheets": [{"id": "s1", "name": "Sheet1"}], **metadata}),
            }
        )
        copy = Document.create({"name": "c.xlsx", "onlyoffice_spreadsheet_source_id": source.id, **file})
        self.assertEqual(load_metadata_for_document(copy)["lists"], metadata["lists"])

        # From the file: anything but an object is no metadata.
        not_an_object = Document.create({"name": "d.xlsx", "onlyoffice_spreadsheet_metadata": "[1, 2]"})
        self.assertEqual(load_metadata_for_document(not_an_object), {})

    def test_the_source_spreadsheet_is_read_with_the_rights_of_the_user(self):
        # The source of a copy the user may read can be a spreadsheet they may not: its filters and definitions stay
        # hidden.
        Document = self.env["documents.document"]
        user = new_test_user(
            self.env, login="oo_formula_reader", groups="base.group_user,documents.group_documents_user"
        )
        lists = {"1": {"model": "res.partner", "domain": [], "columns": ["name"], "orderBy": []}}
        source = Document.create(
            {
                "name": "Private source",
                "handler": "spreadsheet",
                "mimetype": "application/o-spreadsheet",
                "spreadsheet_data": json.dumps({"sheets": [{"id": "s1", "name": "Sheet1"}], "lists": lists}),
                "access_internal": "none",
            }
        )
        copy = Document.create(
            {"name": "c.xlsx", "onlyoffice_spreadsheet_source_id": source.id, "access_internal": "view"}
        )
        self.assertFalse(source.with_user(user).has_access("read"))
        self.assertEqual(load_metadata_for_document(copy.with_user(user)), {})
        self.assertIn("lists", load_metadata_for_document(copy))


@tagged("post_install", "-at_install")
class TestGlobalFiltersAndGroups(TransactionCase):
    """The global filters of a spreadsheet narrow its lists and pivots as Odoo does; groups of a many2many."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Partner = cls.env["res.partner"]
        cls.tag_a, cls.tag_b = cls.env["res.partner.category"].create([{"name": "OO A"}, {"name": "OO B"}])
        cls.alpha = Partner.create(
            {"name": "Alpha Corp", "ref": REF, "category_id": [(6, 0, (cls.tag_a | cls.tag_b).ids)]}
        )
        cls.beta = Partner.create({"name": "Beta Corp", "ref": REF, "category_id": [(6, 0, cls.tag_b.ids)]})
        cls.carol = Partner.create({"name": "Carol", "ref": REF, "parent_id": cls.alpha.id, "user_id": cls.env.uid})

    def setUp(self):
        super().setUp()
        request = fake_request(self.env)
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        self.evaluator = SpreadsheetFormulaEvaluator()

    def _count(self, global_filter, matching):
        """How many records the list and the pivot of a spreadsheet with ``global_filter`` show."""
        global_filter = {"id": "f1", "label": "Filter", **global_filter}
        field_matching = {"f1": matching}
        snapshot = {
            "globalFilters": [global_filter],
            "lists": {
                "1": {
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "orderBy": [{"name": "name", "asc": True}],
                    "columns": ["name"],
                    "fieldMatching": field_matching,
                }
            },
            "pivots": {
                "p": {
                    "type": "ODOO",
                    "formulaId": "2",
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "measures": [{"id": "__count", "fieldName": "__count"}],
                    "rows": [],
                    "columns": [],
                    "fieldMatching": field_matching,
                }
            },
        }
        listed = [self.evaluator.evaluate_single_formula(snapshot, f'=ODOO_LIST(1,{i},"name")') for i in (1, 2, 3)]
        counted = self.evaluator.evaluate_single_formula(snapshot, '=ODOO_PIVOT(2,"__count")')
        self.assertEqual(len([name for name in listed if name]), counted, "the list and the pivot agree")
        return counted

    def test_text_and_relation_filters(self):
        self.assertEqual(self._count({"type": "text", "defaultValue": "corp"}, {"chain": "name", "type": "char"}), 2)
        relation = {"type": "relation", "modelName": "res.partner", "defaultValue": [self.alpha.id]}
        self.assertEqual(self._count(relation, {"chain": "id", "type": "many2one"}), 1)
        # "Include children": the records under the chosen ones too.
        self.assertEqual(self._count({**relation, "includeChildren": True}, {"chain": "id", "type": "many2one"}), 2)
        current_user = {"type": "relation", "modelName": "res.users", "defaultValue": "current_user"}
        self.assertEqual(self._count(current_user, {"chain": "user_id", "type": "many2one"}), 1)
        # A value that is not a list of ids is no value of the filter.
        self.assertEqual(self._count({**relation, "defaultValue": ["1 OR 1"]}, {"chain": "id"}), 3)

    def test_current_value_comes_before_the_default_one(self):
        text = {"type": "text", "defaultValue": "corp", "currentValue": "carol"}
        self.assertEqual(self._count(text, {"chain": "name", "type": "char"}), 1)

    def test_date_filters_with_their_offset(self):
        matching = {"chain": "create_date", "type": "datetime"}
        this_year = {"type": "date", "rangeType": "fixedPeriod", "defaultValue": "this_year"}
        self.assertEqual(self._count(this_year, matching), 3)
        self.assertEqual(self._count(this_year, {**matching, "offset": -1}), 0)
        relative = {"type": "date", "rangeType": "relative", "defaultValue": "last_week"}
        self.assertEqual(self._count(relative, matching), 3)
        self.assertEqual(self._count(relative, {**matching, "offset": -1}), 0)
        today = fields.Date.today().isoformat()
        from_to = {"type": "date", "rangeType": "from_to", "currentValue": {"from": today, "to": today}}
        self.assertEqual(self._count(from_to, matching), 3)
        self.assertEqual(self._count({**from_to, "currentValue": {"to": "2000-01-01"}}, matching), 0)
        # As in Odoo, a from-to filter has no default value.
        no_value = {**from_to, "currentValue": None, "defaultValue": {"to": "2000-01-01"}}
        self.assertEqual(self._count(no_value, matching), 3)

    def test_filters_of_odoo_19_by_their_operator(self):
        text = {"type": "text", "defaultValue": {"operator": "ilike", "strings": ["alpha", "beta"]}}
        self.assertEqual(self._count(text, {"chain": "name", "type": "char"}), 2)
        cases = [
            ({"type": "text", "defaultValue": {"operator": "not ilike", "strings": ["corp"]}}, "name", 1),
            ({"type": "text", "defaultValue": {"operator": "starts with", "strings": ["car"]}}, "name", 1),
            ({"type": "text", "defaultValue": {"operator": "in", "strings": ["Carol", "Beta Corp"]}}, "name", 2),
            ({"type": "text", "defaultValue": {"operator": "ilike", "strings": []}}, "name", 3),
            ({"type": "relation", "defaultValue": {"operator": "in", "ids": [self.alpha.id]}}, "id", 1),
            ({"type": "relation", "defaultValue": {"operator": "not in", "ids": [self.alpha.id]}}, "id", 2),
            ({"type": "relation", "defaultValue": {"operator": "child_of", "ids": [self.alpha.id]}}, "id", 2),
            ({"type": "relation", "defaultValue": {"operator": "in", "ids": "current_user"}}, "user_id", 1),
            ({"type": "relation", "defaultValue": {"operator": "set"}}, "parent_id", 1),
            ({"type": "relation", "defaultValue": {"operator": "not set"}}, "parent_id", 2),
            ({"type": "relation", "defaultValue": {"operator": "ilike", "strings": ["oo a"]}}, "category_id", 1),
            ({"type": "selection", "defaultValue": {"operator": "in", "selectionValues": ["contact"]}}, "type", 3),
            ({"type": "selection", "defaultValue": {"operator": "not in", "selectionValues": ["contact"]}}, "type", 0),
            ({"type": "boolean", "defaultValue": {"operator": "set"}}, "active", 3),
            ({"type": "numeric", "defaultValue": {"operator": ">", "targetValue": 0}}, "color", 0),
            (
                {"type": "numeric", "defaultValue": {"operator": "between", "minimumValue": 0, "maximumValue": 1}},
                "color",
                3,
            ),
        ]
        for global_filter, chain, count in cases:
            with self.subTest(global_filter=global_filter, chain=chain):
                self.assertEqual(self._count(global_filter, {"chain": chain}), count)

    def test_filters_of_odoo_19_from_a_file_give_only_their_operators_and_values(self):
        # The metadata of an XLSX comes from whoever uploads it.
        cases = [
            {"type": "relation", "defaultValue": {"operator": "=like", "ids": [self.alpha.id]}},
            {"type": "relation", "defaultValue": {"operator": "in", "ids": ["1 OR 1", 1.5]}},
            {"type": "text", "defaultValue": {"operator": "ilike", "strings": [{"x": 1}]}},
            {"type": "numeric", "defaultValue": {"operator": "=", "targetValue": "1"}},
            {"type": "selection", "defaultValue": {"operator": "in", "selectionValues": "contact"}},
        ]
        for global_filter in cases:
            with self.subTest(global_filter=global_filter):
                count = self._count(global_filter, {"chain": "name"})
                self.assertIn(count, (0, 3), "no domain, or one that matches nothing")
        self.assertEqual(self._count(cases[0], {"chain": "id"}), 3)

    def test_date_filters_of_odoo_19_with_their_offset(self):
        matching = {"chain": "create_date", "type": "datetime"}
        today = fields.Date.today()
        this_year = {"type": "date", "defaultValue": "this_year"}
        self.assertEqual(self._count(this_year, matching), 3)
        self.assertEqual(self._count(this_year, {**matching, "offset": -1}), 0)
        for default in ("this_month", "this_quarter", "today", "last_7_days", "month_to_date", "year_to_date"):
            with self.subTest(default=default):
                period = {"type": "date", "defaultValue": default}
                self.assertEqual(self._count(period, matching), 3)
                self.assertEqual(self._count(period, {**matching, "offset": -1}), 0)
                self.assertEqual(self._count(period, {**matching, "offset": 1}), 0)
        month = {"type": "date", "currentValue": {"type": "month", "year": today.year, "month": today.month}}
        self.assertEqual(self._count(month, matching), 3)
        last_month = {"type": "date", "defaultValue": "last_month"}
        self.assertEqual(self._count(last_month, matching), 0)
        self.assertEqual(self._count(last_month, {**matching, "offset": 1}), 3)
        day = today.isoformat()
        self.assertEqual(self._count({"type": "date", "currentValue": {"type": "range", "from": day}}, matching), 3)
        self.assertEqual(
            self._count({"type": "date", "currentValue": {"type": "range", "to": "2000-01-01"}}, matching), 0
        )
        # A month without its number is its year, which Odoo does not move.
        whole_year = {"type": "date", "currentValue": {"type": "month", "year": today.year}}
        self.assertEqual(self._count(whole_year, {**matching, "offset": -1}), 3)
        self.assertEqual(self._count({"type": "date", "currentValue": {"type": "month"}}, matching), 3)

    def test_a_filter_the_data_does_not_match_changes_nothing(self):
        self.assertEqual(self._count({"type": "text", "defaultValue": "corp"}, {}), 3)

    def test_a_pivot_cell_of_a_many2many_group_is_that_of_its_value(self):
        # Alpha has both tags: each tag has its own group, the cell takes the one of its value.
        snapshot = {
            "pivots": {
                "p": {
                    "type": "ODOO",
                    "formulaId": "1",
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "measures": [{"id": "__count", "fieldName": "__count"}],
                    "rows": [{"fieldName": "category_id"}],
                    "columns": [],
                }
            }
        }
        evaluate = self.evaluator.evaluate_single_formula
        self.assertEqual(evaluate(snapshot, f'=ODOO_PIVOT(1,"__count","category_id",{self.tag_a.id})'), 1)
        self.assertEqual(evaluate(snapshot, f'=ODOO_PIVOT(1,"__count","category_id",{self.tag_b.id})'), 2)
        self.assertEqual(evaluate(snapshot, '=ODOO_PIVOT(1,"__count","category_id","false")'), 1)

    def test_normalized_pivot_keeps_its_field_matching(self):
        pivot = {"type": "ODOO", "model": "res.partner", "rows": [], "measures": [], "fieldMatching": {"f1": {}}}
        self.assertEqual(normalize_pivot_definition(pivot)["fieldMatching"], {"f1": {}})


@tagged("post_install", "-at_install")
class TestFormulaBatch(TransactionCase):
    """The formulas of one request: the records of a list are read once, one bad cell fails only itself."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.partner"].create([{"name": f"Batch {i:02}", "ref": REF} for i in range(30)])
        cls.snapshot = {
            "lists": {
                "1": {
                    "model": "res.partner",
                    "domain": [["ref", "=", REF]],
                    "orderBy": [{"name": "name", "asc": True}],
                    "columns": ["name", "email"],
                }
            }
        }

    def setUp(self):
        super().setUp()
        request = fake_request(self.env)
        self.request = request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        self.evaluator = SpreadsheetFormulaEvaluator()

    def _batch(self, formulas):
        """The values of ``formulas`` evaluated as one request, and the number of queries it took."""
        self.request._rg_cache = {}
        self.env.invalidate_all()
        queries = self.env.cr.sql_log_count
        values = [self.evaluator.evaluate_single_formula(self.snapshot, formula) for formula in formulas]
        return values, self.env.cr.sql_log_count - queries

    def test_records_of_a_list_are_read_once_per_request(self):
        few, few_queries = self._batch([f'=ODOO_LIST(1,{i},"{f}")' for i in (1, 2) for f in ("name", "email")])
        many, many_queries = self._batch([f'=ODOO_LIST(1,{i},"{f}")' for i in range(1, 31) for f in ("name", "email")])
        self.assertEqual((few[0], many[-2]), ("Batch 00", "Batch 29"))
        self.assertEqual(many_queries, few_queries)

    def test_one_bad_cell_fails_only_itself(self):
        values, _queries = self._batch(['=ODOO_LIST(1,0,"name")', '=ODOO_LIST(1,1,"name")', '=ODOO_LIST(9,1,"name")'])
        self.assertTrue(values[0].startswith("#ERROR"))
        self.assertEqual(values[1], "Batch 00")
        self.assertTrue(values[2].startswith("#ERROR"))
        self.assertEqual(self.evaluator.evaluate_single_formula(self.snapshot, '=ODOO_LIST(1,2,"name")'), "Batch 01")
