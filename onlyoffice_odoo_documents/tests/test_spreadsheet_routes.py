# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.utils import jwt_utils
from odoo.addons.onlyoffice_odoo_documents.controllers import spreadsheet_docbuilder
from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_docbuilder import SpreadsheetDocBuilder

from .common import XLSX_MIMETYPE, DocumentsCase, blank

REF = "oo-routes"
LIST = {"model": "res.partner", "domain": [["ref", "=", REF]], "orderBy": [{"name": "name"}], "columns": ["name"]}


@tagged("post_install", "-at_install")
class TestSpreadsheetRoutes(DocumentsCase, HttpCase):
    """Routes behind ODOO_* formulas: evaluation from the editor, docbuilder rebuilds (the service itself is mocked)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.partner"].create([{"name": "Ann", "ref": REF}, {"name": "Bob", "ref": REF}])

    def _xlsx(self, metadata=None, **vals):
        if metadata:
            vals["onlyoffice_spreadsheet_metadata"] = json.dumps(metadata)
        return self._document("Sales.xlsx", mimetype=XLSX_MIMETYPE, **vals)

    def _docbuilder(self, result=(b"rebuilt xlsx", None)):
        """Mocks the docbuilder service call; returns the patch and the cached payloads it was called with."""
        payloads = []

        def call(_builder, token, _document_id):
            payloads.append(spreadsheet_docbuilder._load_docbuilder_data(token))
            return result

        return patch.object(SpreadsheetDocBuilder, "_call_docbuilder", autospec=True, side_effect=call), payloads

    # -- POST /onlyoffice/documents/evaluate_formulas_batch (public, called from the editor) --

    def _evaluate(self, document, formulas, token):
        return self._rpc(
            "/onlyoffice/documents/evaluate_formulas_batch", document_id=document.id, formulas=formulas, jwt_token=token
        )["result"]

    def test_formulas_are_evaluated_for_the_token_user(self):
        document = self._xlsx({"lists": {"1": LIST}})
        token = self._internal_token({"uid": self.owner.id, "document_id": document.id})

        result = self._evaluate(
            document, ['=ODOO_LIST(1,2,"name")', '=ODOO_LIST_HEADER(1,"name")', "=ODOO_X(1)"], token
        )

        self.assertEqual(
            result["values"],
            {
                '=ODOO_LIST(1,2,"name")': "Bob",
                '=ODOO_LIST_HEADER(1,"name")': "Name",
                "=ODOO_X(1)": "#ERROR: Unknown function X",
            },
        )

    def test_formulas_need_a_valid_token_for_the_document(self):
        document = self._xlsx({"lists": {"1": LIST}}, folder_id=False)  # private to the owner
        other = self._xlsx()
        formulas = ['=ODOO_LIST(1,1,"name")']
        cases = {
            None: "Security token required",
            self._internal_token({"uid": self.owner.id, "document_id": other.id}): "Token/document mismatch",
            jwt_utils.encode_payload(self.env, {"uid": self.owner.id, "document_id": document.id}, "forged"): (
                "Invalid security token"
            ),
            self._internal_token({"uid": self.colleague.id, "document_id": document.id}): "Access denied",
        }
        for token, error in cases.items():
            with self.subTest(error=error):
                self.assertEqual(self._evaluate(document, formulas, token), {"error": error})

    # -- Docbuilder callbacks (public, the token is the cache key) --

    def test_docbuilder_fetches_the_script_and_the_file_once(self):
        payload = {
            "mode": "patch_formulas",
            "_token": "tok",
            "xlsx_base64": base64.b64encode(b"native export").decode(),
            "patches_json": "[]",
            "metadata_json": None,
            "output_filename": "out.xlsx",
        }
        self.env["ir.attachment"].create(
            {"name": "onlyoffice_docbuilder_cache_tok", "raw": json.dumps(payload).encode()}
        )

        script = self.url_open("/onlyoffice/documents/docbuilder_callback/tok")
        self.assertEqual(script.status_code, 200)
        self.assertIn("onlyoffice/documents/docbuilder_file/tok", script.text)

        source = self.url_open("/onlyoffice/documents/docbuilder_file/tok")
        self.assertEqual((source.status_code, source.content), (200, b"native export"))
        self.assertEqual(self.url_open("/onlyoffice/documents/docbuilder_file/tok").status_code, 404)

    def test_unknown_docbuilder_tokens_are_not_found(self):
        for route in ("docbuilder_callback", "docbuilder_file"):
            with self.subTest(route=route):
                self.assertEqual(self.url_open(f"/onlyoffice/documents/{route}/unknown").status_code, 404)

    # -- POST /onlyoffice/documents/insert_list_in_xlsx, insert_pivot_in_xlsx --

    def test_insert_lists_into_an_xlsx(self):
        document = self._xlsx()
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        list_data = {"model": "res.partner", "domain": "[]", "columns": [{"name": "name"}, {"name": "color"}]}
        mock, payloads = self._docbuilder()

        with mock:
            first = self._rpc(
                "/onlyoffice/documents/insert_list_in_xlsx",
                document_id=document.id,
                list_data=list_data,
                threshold=2,
                name="Partners",
            )["result"]
            second = self._rpc(
                "/onlyoffice/documents/insert_list_in_xlsx", document_id=document.id, list_data=list_data, threshold=1
            )["result"]

        self.assertEqual(first, {"success": True, "document_id": document.id, "id": "1", "sheet_name": "Partners"})
        self.assertEqual((second["id"], second["sheet_name"]), ("2", "List"))
        self.assertEqual(payloads[0]["mode"], "insert_sheet")
        self.assertEqual(base64.b64decode(payloads[0]["xlsx_base64"]), blank("xlsx"))
        self.assertEqual(
            json.loads(payloads[0]["cells_json"]),
            [
                ['=ODOO_LIST_HEADER(1,"name")', '=ODOO_LIST_HEADER(1,"color")'],
                ['=ODOO_LIST(1,1,"name")', '=ODOO_LIST(1,1,"color")'],
                ['=ODOO_LIST(1,2,"name")', '=ODOO_LIST(1,2,"color")'],
            ],
        )
        self.env.invalidate_all()
        self.assertEqual(document.raw, b"rebuilt xlsx")
        metadata = json.loads(document.onlyoffice_spreadsheet_metadata)
        self.assertEqual(sorted(metadata["lists"]), ["1", "2"])
        self.assertEqual(metadata["lists"]["1"]["columnFormats"]["color"], {"format": "#,##0", "align": "right"})

    def test_insert_a_pivot_into_an_xlsx(self):
        document = self._xlsx({"lists": {"3": LIST}})
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        pivot_data = {"model": "res.partner", "domain": [["ref", "=", REF]], "rowGroupBys": [], "colGroupBys": []}
        mock, payloads = self._docbuilder()

        with mock:
            result = self._rpc(
                "/onlyoffice/documents/insert_pivot_in_xlsx", document_id=document.id, pivot_data=pivot_data
            )["result"]

        self.assertEqual((result["id"], result["sheet_name"]), ("4", "Pivot"), "ids are shared with the lists")
        self.assertEqual(
            json.loads(payloads[0]["cells_json"]),
            [["", '=ODOO_PIVOT_HEADER(4,"measure","__count")'], ["Total", '=ODOO_PIVOT(4,"__count")']],
        )
        self.env.invalidate_all()
        pivot = json.loads(document.onlyoffice_spreadsheet_metadata)["pivots"]["4"]
        self.assertEqual((pivot["measures"], pivot["columnFormats"]["__count"]["format"]), (["__count"], "#,##0"))

    def _insert_list(self, document, **list_data):
        list_data = {"model": "res.partner", "columns": ["name"], **list_data}
        return self._rpc("/onlyoffice/documents/insert_list_in_xlsx", document_id=document.id, list_data=list_data)[
            "result"
        ]

    def test_insert_needs_write_access(self):
        read_only = self._xlsx()
        read_only.action_update_access_rights(access_internal="view")
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")
        self.assertEqual(self._insert_list(read_only), {"error": "Access denied"})

    def test_insert_needs_columns_or_a_model(self):
        document = self._xlsx()
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        self.assertEqual(self._insert_list(document, columns=[]), {"error": "No columns provided"})
        pivot = self._rpc(
            "/onlyoffice/documents/insert_pivot_in_xlsx", document_id=document.id, pivot_data={"model": ""}
        )["result"]
        self.assertEqual(pivot, {"error": "No model provided"})

    def test_failed_rebuild_leaves_the_xlsx_unchanged(self):
        document = self._xlsx()
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        mock, _payloads = self._docbuilder(result=(None, "Invalid token"))
        with mock:
            self.assertEqual(self._insert_list(document), {"error": "DocBuilder error: Invalid token"})
        self.env.invalidate_all()
        self.assertEqual(document.raw, blank("xlsx"))
        self.assertFalse(document.onlyoffice_spreadsheet_metadata)

    # -- POST /onlyoffice/documents/convert_spreadsheet_via_docbuilder --

    def _spreadsheet(self):
        data = {
            "sheets": [
                {
                    "id": "s1",
                    "name": "Sheet1",
                    "cells": {"A1": {"content": '=ODOO.LIST(1,1,"name")'}, "A2": {"content": "plain"}},
                }
            ],
            "lists": {"1": {**LIST, "domain": "[('create_uid', '=', uid)]"}},
            "globalFilters": [{"label": "Region", "defaultValue": "EU"}],
        }
        return (
            self.env["documents.document"]
            .with_user(self.owner)
            .create(
                {
                    "name": "Sales",
                    "handler": "spreadsheet",
                    "mimetype": "application/o-spreadsheet",
                    "spreadsheet_data": json.dumps(data),
                    "folder_id": self.folder.id,
                }
            )
        )

    def _convert(self, document, xlsx_base64):
        return self._rpc(
            "/onlyoffice/documents/convert_spreadsheet_via_docbuilder", document_id=document.id, xlsx_base64=xlsx_base64
        )["result"]

    def test_spreadsheet_becomes_an_xlsx_with_live_formulas(self):
        spreadsheet = self._spreadsheet()
        native = base64.b64encode(b"native export").decode()
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        mock, payloads = self._docbuilder()

        with mock:
            result = self._convert(spreadsheet, native)

        self.assertFalse(result["error"])
        xlsx = self.env["documents.document"].browse(result["xlsx_id"])
        self.assertRegex(xlsx.name, r"^Sales_.+\.xlsx$")
        self.assertEqual((xlsx.folder_id, xlsx.onlyoffice_spreadsheet_source_id), (self.folder, spreadsheet))
        self.assertEqual((xlsx.mimetype, xlsx.raw), (XLSX_MIMETYPE, b"rebuilt xlsx"))
        # The ODOO.* cells of the native export are patched into the ONLYOFFICE functions.
        self.assertEqual((payloads[0]["mode"], payloads[0]["xlsx_base64"]), ("patch_formulas", native))
        self.assertEqual(
            json.loads(payloads[0]["patches_json"]),
            [{"sheet": "Sheet1", "cell": "A1", "formula": '=ODOO_LIST(1,1,"name")'}],
        )
        # Domains are resolved once, as the converting user.
        metadata = json.loads(xlsx.onlyoffice_spreadsheet_metadata)
        self.assertEqual(metadata["lists"]["1"]["domain"], [["create_uid", "=", self.owner.id]])
        self.assertEqual(metadata["globalFilters"], [{"label": "Region", "defaultValue": "EU"}])

    def test_spreadsheet_conversion_errors(self):
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        self.assertEqual(
            self._convert(self._spreadsheet(), None),
            {"error": "Native spreadsheet export is required for conversion", "xlsx_id": None},
        )
        self.assertEqual(self._convert(self._document(), "eA==")["error"], "Document is not a spreadsheet")
