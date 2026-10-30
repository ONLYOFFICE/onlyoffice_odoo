# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_documents.controllers import spreadsheet_docbuilder
from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_docbuilder import (
    SpreadsheetDocBuilder,
    _expand_group_paths,
    _format_date_group_value,
    _group_value_literal,
)
from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_formulas import SpreadsheetFormulaEvaluator

from .common import fake_request, make_xlsx

REQUEST = "odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_docbuilder.onlyoffice_request"


def _response(json_data=None, content=b""):
    response = MagicMock(content=content)
    response.json.return_value = json_data
    return response


@tagged("post_install", "-at_install")
class TestDocBuilderScripts(TransactionCase):
    """Building the cells and scripts for the docbuilder service; the service itself is mocked."""

    def setUp(self):
        super().setUp()
        request = fake_request(self.env)
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        # The cache is committed so that the docbuilder callback, another request, can read it.
        commit = patch.object(self.env.cr, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.builder = SpreadsheetDocBuilder(SpreadsheetFormulaEvaluator())

    # -- Formula patches of a native export --

    def test_odoo_formulas_are_rewritten_for_the_onlyoffice_functions(self):
        convert = SpreadsheetDocBuilder._convert_odoo_formula
        self.assertEqual(
            convert('=ODOO.PIVOT.HEADER(1,"measure","__count")'), '=ODOO_PIVOT_HEADER(1,"measure","__count")'
        )
        self.assertEqual(
            convert('=-ODOO.LIST(1,2,"name")+ODOO.LIST(1,3,"name")'), '=-ODOO_LIST(1,2,"name")+ODOO_LIST(1,3,"name")'
        )

    def test_patches_cover_only_odoo_formula_cells(self):
        snapshot = {
            "sheets": [
                {
                    "name": "Sales",
                    "cells": {
                        "A1": {"content": '=ODOO.LIST(1,1,"name")'},
                        "A2": {"content": '=-ODOO.PIVOT(2,"__count")'},
                        "B1": {"content": "=SUM(A1:A2)"},
                        "C1": {"content": "ODOO.LIST text"},
                        "D1": {},
                    },
                }
            ]
        }
        self.assertEqual(
            self.builder._build_formula_patches(snapshot),
            [
                {"sheet": "Sales", "cell": "A1", "formula": '=ODOO_LIST(1,1,"name")'},
                {"sheet": "Sales", "cell": "A2", "formula": '=-ODOO_PIVOT(2,"__count")'},
            ],
        )

    # -- Inserted sheets --

    def test_list_sheet_is_a_header_row_and_one_row_per_record(self):
        cells = SpreadsheetDocBuilder._build_list_cells("3", [{"name": "name"}, "email"], 2)
        self.assertEqual(
            cells,
            [
                ['=ODOO_LIST_HEADER(3,"name")', '=ODOO_LIST_HEADER(3,"email")'],
                ['=ODOO_LIST(3,1,"name")', '=ODOO_LIST(3,1,"email")'],
                ['=ODOO_LIST(3,2,"name")', '=ODOO_LIST(3,2,"email")'],
            ],
        )

    def test_pivot_sheet_replicates_the_pivot_layout(self):
        Partner = self.env["res.partner"]
        Partner.create([{"name": n, "is_company": c, "ref": "oo-pivot"} for n, c in (("A", True), ("B", False))])
        pivot = {"model": "res.partner", "domain": [["ref", "=", "oo-pivot"]]}

        cells = self.builder._build_pivot_cells("4", pivot, ["__count"], ["is_company"], [])

        self.assertEqual(
            cells,
            [
                ["", '=ODOO_PIVOT_HEADER(4,"measure","__count")'],
                ['=ODOO_PIVOT_HEADER(4,"is_company","false")', '=ODOO_PIVOT(4,"__count","is_company","false")'],
                ['=ODOO_PIVOT_HEADER(4,"is_company","true")', '=ODOO_PIVOT(4,"__count","is_company","true")'],
                ["Total", '=ODOO_PIVOT(4,"__count")'],
            ],
        )

    def test_pivot_sheet_with_column_groups(self):
        self.env["res.partner"].create({"name": "C", "is_company": True, "ref": "oo-pivot-cols"})
        pivot = {"model": "res.partner", "domain": [["ref", "=", "oo-pivot-cols"]]}

        cells = self.builder._build_pivot_cells("5", pivot, ["__count"], [], ["is_company"])

        self.assertEqual(
            cells,
            [
                ["", '=ODOO_PIVOT_HEADER(5,"is_company","true")', "Total"],
                [
                    "",
                    '=ODOO_PIVOT_HEADER(5,"is_company","true","measure","__count")',
                    '=ODOO_PIVOT_HEADER(5,"measure","__count")',
                ],
                ["Total", '=ODOO_PIVOT(5,"__count","is_company","true")', '=ODOO_PIVOT(5,"__count")'],
            ],
        )

    def test_group_paths_are_expanded_parents_first(self):
        paths = [(("a", 1), ("b", 1)), (("a", 1), ("b", 2)), (("a", 2), ("b", 1))]
        self.assertEqual(
            _expand_group_paths(paths),
            [
                (("a", 1),),
                (("a", 1), ("b", 1)),
                (("a", 1), ("b", 2)),
                (("a", 2),),
                (("a", 2), ("b", 1)),
            ],
        )

    def test_group_values_become_formula_literals(self):
        model = self.env["res.partner"]
        cases = [
            ("parent_id", {"parent_id": (7, "Parent")}, "7"),
            ("parent_id", {"parent_id": False}, '"false"'),
            ("is_company", {"is_company": True}, '"true"'),
            ("color", {"color": 4}, "4"),
            ("type", {"type": "contact"}, '"contact"'),
            (
                "create_date:quarter",
                {"create_date:quarter": "Q2 2026", "__range": {"create_date:quarter": {"from": "2026-04-15 12:00:00"}}},
                '"2/2026"',
            ),
        ]
        for spec, group, literal in cases:
            with self.subTest(spec=spec, group=group):
                self.assertEqual(_group_value_literal(model, spec, group), literal)

    def test_date_group_values_use_the_pivot_date_format(self):
        def group(start):
            return {"__range": {"d": {"from": start}}, "d": "label"}

        self.assertEqual(_format_date_group_value(group("2026-03-15"), "d", "year"), "2026")
        self.assertEqual(_format_date_group_value(group("2026-03-15"), "d", "month"), "3/2026")
        self.assertEqual(_format_date_group_value(group("2026-03-15"), "d", "day"), "3/15/2026")
        self.assertEqual(_format_date_group_value(group("2026-01-01"), "d", "week"), "1/2026")
        self.assertEqual(_format_date_group_value({"d": "label"}, "d", "month"), "label", "no range")

    def test_datetime_groups_are_read_in_the_user_timezone(self):
        self.env.user.tz = "Asia/Tokyo"
        group = {"__range": {"d": {"from": "2026-02-28 15:00:00"}}}  # 2026-03-01 00:00 in Tokyo
        self.assertEqual(_format_date_group_value(group, "d", "month", is_datetime=True), "3/2026")

    def test_new_ids_follow_lists_and_pivots(self):
        Document = self.env["documents.document"]
        self.assertEqual(SpreadsheetDocBuilder._load_metadata_with_new_id(Document.new({}))[1], "1")
        document = Document.new(
            {"onlyoffice_spreadsheet_metadata": json.dumps({"lists": {"1": {}}, "pivots": {"4": {}}})}
        )
        metadata, new_id = SpreadsheetDocBuilder._load_metadata_with_new_id(document)
        self.assertEqual((sorted(metadata), new_id), (["lists", "pivots"], "5"))

    def test_sheet_names_are_valid_and_unique(self):
        xlsx = make_xlsx({"Sheet1": [], "Partners": [], "Partners (2)": []})
        document = self.env["documents.document"].create({"name": "a.xlsx", "raw": xlsx})
        name = SpreadsheetDocBuilder._unique_sheet_name
        self.assertEqual(name(document, "Partners"), "Partners (3)")
        self.assertEqual(name(document, "Q1: [draft]/v2"), "Q1   draft  v2")
        self.assertEqual(name(document, "x" * 40), "x" * 31)
        self.assertEqual(name(document, "///"), "Sheet")

    # -- Cache and callback scripts --

    def _store(self, token, **data):
        spreadsheet_docbuilder._store_docbuilder_data(token, {"_token": token, **data})

    def test_patch_formulas_script_embeds_the_patches(self):
        patches = json.dumps([{"sheet": "S", "cell": "A1", "formula": '=ODOO_LIST(1,1,"name")'}])
        self._store("tok1", mode="patch_formulas", patches_json=patches, metadata_json=None, output_filename="out.xlsx")

        script = self.builder.build_callback_script("tok1")

        self.assertIn(f"var patches = {patches}", script)
        self.assertIn("var metadata = null", script)
        self.assertIn('builder.SaveFile("xlsx", "out.xlsx")', script)
        self.assertIn("onlyoffice/documents/docbuilder_file/tok1", script)
        self.assertNotIn("PLACEHOLDER", script)

    def test_insert_sheet_script_embeds_the_cells(self):
        cells = json.dumps([['=ODOO_LIST_HEADER(1,"name")']])
        self._store(
            "tok2",
            mode="insert_sheet",
            sheet_name='Sheet "x"',
            cells_json=cells,
            metadata_json="{}",
            output_filename="out.xlsx",
        )

        script = self.builder.build_callback_script("tok2")

        self.assertIn(cells, script)
        self.assertIn(json.dumps('Sheet "x"'), script)
        self.assertNotIn("PLACEHOLDER", script)

    def test_unknown_tokens_and_modes_have_no_script(self):
        self._store("tok3", mode="convert")
        self.assertIsNone(self.builder.build_callback_script("tok3"))
        self.assertIsNone(self.builder.build_callback_script("missing"))
        self.assertIsNone(self.builder.get_cached_file("tok3"))

    def test_cached_file_is_served_once(self):
        self._store("tok4", mode="insert_sheet", xlsx_base64=base64.b64encode(b"xlsx bytes").decode())
        self.assertEqual(self.builder.get_cached_file("tok4"), b"xlsx bytes")
        self.assertIsNone(self.builder.get_cached_file("tok4"))

    # -- Docbuilder service call --

    def test_docbuilder_result_is_downloaded(self):
        config_utils.set_doc_server_public_url(self.env, "http://documentserver/")
        build = _response({"end": True, "urls": {"log.txt": "http://ds/log", "out.xlsx": "http://ds/out.xlsx"}})
        with patch(REQUEST, side_effect=[build, _response(content=b"xlsx")]) as request:
            self.assertEqual(self.builder._call_docbuilder("tok", 1), (b"xlsx", None))

        call = request.call_args_list[0].kwargs
        self.assertEqual(call["url"], "http://documentserver/docbuilder")
        self.assertEqual(call["opts"]["json"]["async"], False)
        self.assertTrue(call["opts"]["json"]["url"].endswith("onlyoffice/documents/docbuilder_callback/tok"))
        self.assertNotIn("token", call["opts"]["json"])
        self.assertEqual(request.call_args_list[1].kwargs["url"], "http://ds/out.xlsx")

    def test_docbuilder_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        with patch(REQUEST, side_effect=[_response({"urls": {"out.xlsx": "u"}}), _response(content=b"x")]) as request:
            self.builder._call_docbuilder("tok", 1)

        opts = request.call_args_list[0].kwargs["opts"]
        self.assertEqual(
            jwt_utils.decode_token(self.env, opts["json"]["token"], "ds-secret")["url"], opts["json"]["url"]
        )
        self.assertTrue(opts["headers"][config_utils.get_jwt_header(self.env)].startswith("Bearer "))

    def test_docbuilder_failures_are_reported(self):
        cases = [
            ([_response({"error": -8})], "Invalid token"),
            ([_response({"error": -99})], "Error code: -99"),
            ([_response({"urls": {}})], "No XLSX file in output"),
            ([Exception("refused")], "DocBuilder conversion failed: refused"),
            ([_response({"urls": {"out.xlsx": "u"}}), Exception("gone")], "Failed to download converted file"),
        ]
        for responses, error in cases:
            with self.subTest(error=error), patch(REQUEST, side_effect=responses):
                self.assertEqual(self.builder._call_docbuilder("tok", 1), (None, error))
