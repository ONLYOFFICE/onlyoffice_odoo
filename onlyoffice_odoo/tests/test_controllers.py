# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.controllers.main import OnlyofficeConnector
from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, jwt_utils

LOGIN = "_oo_controller_test"
PASSWORD = "_oo_test_pass_123"


@tagged("post_install", "-at_install")
class TestOnlyofficeControllers(HttpCase):
    """HTTP tests of the connector routes; the Document Server is never contacted."""

    def setUp(self):
        super().setUp()
        self.http_user = (
            self.env["res.users"]
            .sudo()
            .create(
                {
                    "name": "OO Controller Test User",
                    "login": LOGIN,
                    "password": PASSWORD,
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("base.group_system").id])],
                }
            )
        )
        self.attachment = self._attachment("test_document.docx")
        # No DS JWT, so file-content and callback requests need no JWT header. A preset internal secret keeps
        # get_internal_jwt_secret from generating one and committing the test transaction.
        config_utils.set_jwt_secret(self.env, "")
        self.env["ir.config_parameter"].sudo().set_param(config_constants.INTERNAL_JWT_SECRET, "test-internal-secret")
        self.security_token = jwt_utils.encode_payload(
            self.env, {"id": self.http_user.id}, config_utils.get_internal_jwt_secret(self.env)
        )

    def _attachment(self, name):
        return self.env["ir.attachment"].sudo().create({"name": name, "datas": base64.b64encode(b"content")})

    def _get_config(self, attachment_id):
        body = {"jsonrpc": "2.0", "method": "call", "params": {"attachment_id": attachment_id}}
        response = self.url_open(
            "/onlyoffice/editor/get_config", data=json.dumps(body), headers={"Content-Type": "application/json"}
        )
        self.assertEqual(response.status_code, 200)  # JSON-RPC reports failures in the body
        return response.json()

    def _callback(self, body, token=None):
        query = f"?oo_security_token={token}" if token else ""
        return self.url_open(
            f"/onlyoffice/editor/callback/{self.attachment.id}{query}",
            data=json.dumps(body),
            headers={"Content-Type": "application/json"},
        )

    # -- POST /onlyoffice/editor/get_config (auth=user, type=json) --

    def test_editor_config_requires_auth(self):
        self.assertIn("error", self._get_config(self.attachment.id))

    def test_editor_config_for_docx_opens_in_edit_mode_with_callback(self):
        self.authenticate(LOGIN, PASSWORD)
        config = self._get_config(self.attachment.id)["result"]["editorConfig"]
        self.assertEqual(config["document"]["title"], "test_document.docx")
        self.assertEqual(config["editorConfig"]["mode"], "edit")
        self.assertIn(f"/onlyoffice/editor/callback/{self.attachment.id}", config["editorConfig"]["callbackUrl"])

    def test_editor_config_for_missing_attachment_is_not_found(self):
        gone = self._attachment("gone.docx")
        gone_id = gone.id
        gone.unlink()
        self.authenticate(LOGIN, PASSWORD)
        # get_config returns request.not_found() from a JSON route, which arrives as a "404 ..." string result.
        self.assertTrue(self._get_config(gone_id)["result"].startswith("404"))

    def test_editor_config_for_unsupported_format_is_an_error(self):
        self.authenticate(LOGIN, PASSWORD)
        self.assertIn("error", self._get_config(self._attachment("archive.zip").id))

    # -- GET /onlyoffice/file/content/<id> (auth=public, oo_security_token) --

    def test_file_content_without_token_is_forbidden(self):
        response = self.url_open(f"/onlyoffice/file/content/{self.attachment.id}", allow_redirects=False)
        self.assertEqual(response.status_code, 403)

    def test_file_content_with_token_returns_the_file(self):
        response = self.url_open(
            f"/onlyoffice/file/content/{self.attachment.id}?oo_security_token={self.security_token}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"content")

    def test_file_content_test_txt_is_public(self):
        """Used by the settings validation to test the converter."""
        response = self.url_open("/onlyoffice/file/content/test.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "test")

    # -- GET /onlyoffice/editor/<id> (auth=public, website) --

    def test_editor_page_for_visitor_is_forbidden(self):
        response = self.url_open(f"/onlyoffice/editor/{self.attachment.id}", allow_redirects=False)
        self.assertEqual(response.status_code, 403)

    def test_editor_page_for_user_returns_html(self):
        self.authenticate(LOGIN, PASSWORD)
        response = self.url_open(f"/onlyoffice/editor/{self.attachment.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))

    # -- GET /onlyoffice/preview (auth=user, website) --

    def test_preview_redirects_visitor_to_login(self):
        response = self.url_open("/onlyoffice/preview?url=https://docs.example.com&title=Test", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))

    def test_preview_for_user_returns_html(self):
        self.authenticate(LOGIN, PASSWORD)
        response = self.url_open("/onlyoffice/preview?url=https://docs.example.com&title=Test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))

    # -- POST /onlyoffice/editor/callback/<id> (auth=public, csrf=False) --

    def test_callback_without_token_answers_error(self):
        response = self._callback({"status": 1})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], 1)

    def test_callback_status_2_writes_the_edited_file(self):
        downloaded = MagicMock()
        downloaded.read.return_value = b"edited content"
        with patch("odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_urlopen", return_value=downloaded):
            response = self._callback({"status": 2, "url": "http://documentserver/cache/out.docx"}, self.security_token)

        self.assertEqual(response.json(), {"error": 0})
        self.attachment.invalidate_recordset()
        self.assertEqual(self.attachment.raw, b"edited content")

    def test_callback_with_jwt_enabled_rejects_unsigned_body(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        response = self._callback({"status": 2, "url": "http://documentserver/cache/out.docx"}, self.security_token)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"], 1)

    # -- OnlyofficeConnector.filter_xss --

    def test_filter_xss_strips_markup_and_keeps_filename_characters(self):
        connector = OnlyofficeConnector()
        self.assertEqual(connector.filter_xss("My Report 2024-Q1.docx"), "My Report 2024-Q1.docx")
        self.assertEqual(connector.filter_xss("<script>alert('x')</script>a.docx"), "scriptalertxscripta.docx")
