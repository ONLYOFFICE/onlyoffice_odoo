# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from unittest.mock import patch

from psycopg2 import IntegrityError

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

from odoo.addons.onlyoffice_odoo_documents.controllers import spreadsheet_docbuilder
from odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_docbuilder import SpreadsheetDocBuilder

from .common import XLSX_MIMETYPE, DocumentsCase, blank, fake_request, xlsx_with_metadata

REF = "oo-freeze"
LIST = {"model": "res.partner", "domain": [["ref", "=", REF]], "orderBy": [{"name": "name"}], "columns": ["name"]}
METADATA = {"lists": {"1": LIST}, "globalFilters": [{"label": "Month", "defaultValue": "03/2026"}]}
# The cells with Odoo functions, as freeze_collect.docbuilder reads them from the file.
COLLECTED = [
    {"s": 0, "c": "A1", "f": '=ODOO_LIST(1,1,"name")'},
    {"s": 0, "c": "B1", "f": '=LEN(ODOO_LIST(1,2,"name"))'},
    {"s": 0, "c": "C1", "f": '=ODOO_LIST(9,1,"name")'},
    {"s": 1, "c": "A1", "f": "=SUM(A2:A3)"},
]


@tagged("post_install", "-at_install")
class TestFreezeSpreadsheet(DocumentsCase, TransactionCase):
    """Freeze and share of an XLSX with Odoo functions: a read-only copy with the values (Document Builder mocked)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.partner"].create([{"name": "Ann", "ref": REF}, {"name": "Bob", "ref": REF}])

    def setUp(self):
        super().setUp()
        request = fake_request(self.env(user=self.owner))
        request.__enter__()
        self.addCleanup(request.__exit__, None, None, None)
        # The cache is committed so that the docbuilder callback, another request, can read it.
        commit = patch.object(self.env.cr, "commit")
        commit.start()
        self.addCleanup(commit.stop)

    def _xlsx(self, name="Sales.xlsx", content=None, **vals):
        return self._document(name, content=content or xlsx_with_metadata(METADATA), mimetype=XLSX_MIMETYPE, **vals)

    def _freeze(self, document, user=None):
        payloads = []

        def call(_builder, token, _document_id):
            data = spreadsheet_docbuilder._load_docbuilder_data(token)
            payloads.append(data)
            if data["mode"] == "freeze_collect":
                return json.dumps(COLLECTED).encode(), None
            return b"frozen xlsx", None

        with patch.object(SpreadsheetDocBuilder, "_call_docbuilder", autospec=True, side_effect=call):
            result = document.with_user(user or self.owner).action_onlyoffice_freeze_and_copy()
        return result, payloads

    def test_the_copy_has_the_values_the_user_sees(self):
        source = self._xlsx()

        result, payloads = self._freeze(source)

        frozen = self.env["documents.document"].browse(result["id"])
        today = fields.Date.today().strftime("%Y-%m-%d")
        self.assertEqual(
            (frozen.name, frozen.onlyoffice_frozen, frozen.raw),
            (f"Frozen at {today}: Sales.xlsx", True, b"frozen xlsx"),
        )
        self.assertEqual(frozen.mimetype, XLSX_MIMETYPE)
        self.assertEqual(result["shortcut_document_id"], False)
        # A formula that is one call becomes its value; in a longer formula the call becomes a literal; an error stays.
        self.assertEqual([payload["mode"] for payload in payloads], ["freeze_collect", "freeze"])
        self.assertEqual(
            json.loads(payloads[1]["cells_json"]),
            [
                {"s": 0, "c": "A1", "v": "Ann"},
                {"s": 0, "c": "B1", "f": '=LEN("Bob")'},
                {"s": 0, "c": "C1", "f": "=NA()"},
            ],
        )
        # The filters as Odoo shows them, as text ("03/2026" must not become a date).
        filters = json.loads(payloads[1]["filters_json"])
        self.assertEqual((filters["title"], filters["rows"]), ("Active Filters", [["Month", '="03/2026"']]))

    def test_the_copy_goes_to_the_frozen_folder_of_the_folder_view_only(self):
        source = self._xlsx()

        frozen = self.env["documents.document"].browse(self._freeze(source)[0]["id"])

        folder = frozen.folder_id
        self.assertEqual(
            (folder.name, folder.handler, folder.folder_id), ("Frozen spreadsheets", "frozen_folder", self.folder)
        )
        self.assertEqual((folder.access_internal, folder.access_via_link), ("none", "none"))
        self.assertEqual(
            (frozen.access_internal, frozen.access_via_link, frozen.is_access_via_link_hidden), ("view", "view", True)
        )
        self.assertEqual(set(frozen.access_ids.filtered("role").mapped("role")) - {"view"}, set(), "edit becomes view")
        second = self._xlsx("Budget.xlsx")
        self.assertEqual(self.env["documents.document"].browse(self._freeze(second)[0]["id"]).folder_id, folder)

    def test_what_cannot_be_frozen(self):
        cases = {
            "a document": (self._document("Report.docx"), "Only an XLSX file with Odoo data can be frozen"),
            "a plain XLSX": (self._xlsx("Plain.xlsx", content=blank("xlsx")), "This file has no Odoo data to freeze"),
        }
        for label, (document, error) in cases.items():
            with self.subTest(document=label), self.assertRaisesRegex(UserError, error):
                self._freeze(document)
        frozen = self.env["documents.document"].browse(self._freeze(self._xlsx())[0]["id"])
        with self.assertRaisesRegex(UserError, "can not be frozen again"):
            self._freeze(frozen.sudo(), user=self.env.ref("base.user_root"))

    def test_freezing_needs_the_right_to_edit_the_folder(self):
        read_only = self.env["documents.document"].create(
            {"name": "OO Read-only", "type": "folder", "access_internal": "view"}
        )
        document = self._xlsx(folder_id=read_only.id, user=self.env.ref("base.user_root"))

        with self.assertRaisesRegex(AccessError, "You are not allowed to freeze spreadsheets in OO Read-only"):
            self._freeze(document, user=self.colleague)

    def test_the_copy_stays_read_only(self):
        source = self._xlsx()
        frozen = self.env["documents.document"].browse(self._freeze(source)[0]["id"])

        self.assertTrue(source.onlyoffice_can_freeze)
        self.assertFalse(frozen.onlyoffice_can_freeze)
        with self.assertRaisesRegex(UserError, "You can not edit a frozen spreadsheet"):
            frozen.with_user(self.owner).write({"raw": b"changed"})
        with self.assertRaisesRegex(UserError, "The frozen spreadsheets are readonly."):
            frozen.action_update_access_rights(access_internal="edit")
        role = self.env["onlyoffice.odoo.documents"]._get_user_role(frozen, self.owner, True)
        self.assertEqual(role, "view")
        with self.assertRaisesRegex(UserError, "The frozen spreadsheets are readonly."):
            self.env["onlyoffice.odoo.documents"].advanced_share_save(
                {"document_id": frozen.id, "internal_users": "edit", "link_access": "view", "user_accesses": []}
            )
        # The share panel shows it as Odoo shows its frozen spreadsheets: view only, without the ONLYOFFICE roles.
        panel = frozen.permission_panel_data()
        self.assertEqual(panel["record"]["handler"], "frozen_spreadsheet")
        self.assertNotIn("commenter", dict(panel["selections"]["access_internal"]))
        self.assertIn("commenter", dict(source.permission_panel_data()["selections"]["access_internal"]))
        # The database refuses it too.
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"), self.env.cr.savepoint():
            frozen.sudo().write({"access_internal": "edit"})
            frozen.flush_recordset()

    def test_the_access_of_the_folder_does_not_reach_the_copy(self):
        frozen = self.env["documents.document"].browse(self._freeze(self._xlsx())[0]["id"])

        self.folder.action_update_access_rights(access_internal="edit", access_via_link="edit")

        self.assertEqual((frozen.access_internal, frozen.access_via_link), ("view", "view"))

    def test_frozen_copies_are_not_offered_to_insert_into(self):
        source = self._xlsx("OO frozen selector.xlsx")
        self._freeze(source)
        domain = [("name", "like", "OO frozen selector")]
        Document = self.env["documents.document"]

        self.assertEqual(Document.get_onlyoffice_spreadsheets_count(domain), 1)
        self.assertEqual([row["id"] for row in Document.get_onlyoffice_spreadsheets_to_display(domain)], [source.id])
