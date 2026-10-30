# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_templates.utils import keys_utils, pdf_utils

from .common import PLAIN_PDF, bundled_pdf, ds_response, plain_pdf

REQUEST = "odoo.addons.onlyoffice_odoo_templates.utils.keys_utils.onlyoffice_request"


@tagged("post_install", "-at_install")
class TestFetchFieldKeys(TransactionCase):
    """keys_utils.fetch_field_keys: the docbuilder run that lists the form field keys of a template PDF."""

    def _fetch(self, docbuilder, keys_file=b""):
        calls = []

        def onlyoffice_request(url, method, opts=None, env=None):
            calls.append({"url": url, "opts": opts})
            return docbuilder if url.endswith("docbuilder") else ds_response(content=keys_file)

        with patch(REQUEST, side_effect=onlyoffice_request):
            return keys_utils.fetch_field_keys(self.env, 42, "token"), calls

    def test_keys_are_read_from_the_generated_text_file(self):
        docbuilder = ds_response({"end": True, "urls": {"keys.txt": "http://ds/keys.txt"}})
        keys, calls = self._fetch(docbuilder, b'\xef\xbb\xbf["name", "parent_id name"]')

        self.assertEqual(keys, ["name", "parent_id name"])
        payload = calls[0]["opts"]["json"]
        self.assertIn(
            "/onlyoffice/template/callback/docbuilder/get_keys?attachment_id=42&oo_security_token=token", payload["url"]
        )
        self.assertNotIn("headers", calls[0]["opts"])
        self.assertEqual(calls[1]["url"], "http://ds/keys.txt")

    def test_docbuilder_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        docbuilder = ds_response({"urls": {"keys.txt": "http://ds/keys.txt"}})
        _keys, calls = self._fetch(docbuilder, b"[]")

        opts = calls[0]["opts"]
        self.assertEqual(
            jwt_utils.decode_token(self.env, opts["json"]["token"], "ds-secret")["url"], opts["json"]["url"]
        )
        self.assertTrue(opts["headers"][config_utils.get_jwt_header(self.env)].startswith("Bearer "))

    def test_docbuilder_error_is_raised(self):
        with self.assertRaisesRegex(Exception, "docbuilder error while fetching field keys: -3"):
            self._fetch(ds_response({"error": -3}))


@tagged("post_install", "-at_install")
class TestIsPdfForm(TransactionCase):
    """pdf_utils.is_pdf_form: an ONLYOFFICE PDF form is kept as is, any other PDF is converted into one."""

    def test_onlyoffice_forms_are_recognised(self):
        self.assertTrue(pdf_utils.is_pdf_form(bundled_pdf()))

    def test_other_files_are_not_forms(self):
        header = b"%\xcd\xca\xd2\xa9\x0d"
        cases = {
            "empty": b"",
            "plain PDF": PLAIN_PDF,
            "reportlab PDF": plain_pdf("x"),
            "header only": header,
            "no form signature": header + b"1 0 obj\x0a<<\x0a/Type /Catalog >>\x0astream\x0d\x0a",
        }
        for case, content in cases.items():
            with self.subTest(case=case):
                self.assertFalse(pdf_utils.is_pdf_form(content))
