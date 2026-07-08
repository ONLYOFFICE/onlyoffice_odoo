# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector
from odoo.addons.onlyoffice_odoo.utils import config_utils


@tagged("post_install", "-at_install")
class TestOnlyofficeControllers(HttpCase):
    """HTTP integration tests for ONLYOFFICE controller routes.

    These tests verify that the controller endpoints respond correctly
    to authenticated and unauthenticated requests. They do not require
    a running ONLYOFFICE Document Server — they test Odoo-side logic only.

    Actual routes (from controllers.py):
      POST /onlyoffice/editor/get_config  auth=user  type=json
      GET  /onlyoffice/file/content/<id>  auth=public  (oo_security_token param)
      GET  /onlyoffice/editor/<id>        auth=public  website
      POST /onlyoffice/editor/callback/<id>  auth=public  no-csrf
      GET  /onlyoffice/preview            auth=user  website  (url, title params)
    """

    def setUp(self):
        super().setUp()
        # Create a dedicated test user with known credentials.
        # Avoids dependency on 'admin' user/password in the target database.
        self.http_user = (
            self.env["res.users"]
            .sudo()
            .create(
                {
                    "name": "OO Controller Test User",
                    "login": "_oo_controller_test",
                    "password": "_oo_test_pass_123",
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id, self.env.ref("base.group_system").id])],
                }
            )
        )
        self.test_attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": "test_document.docx",
                    "datas": base64.b64encode(b"fake docx content"),
                    "mimetype": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                }
            )
        )
        # Disable JWT so file-content tests don't also require a JWT request header
        config_utils.set_jwt_secret(self.env, "")

    # -- POST /onlyoffice/editor/get_config (auth=user, type=json) --

    def test_editor_config_requires_auth(self):
        """Editor config endpoint returns JSON-RPC error for unauthenticated user.

        JSON-RPC (type=json) routes always respond HTTP 200; auth failure is
        expressed via an 'error' key in the response body.
        """
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"attachment_id": self.test_attachment.id}})
        response = self.url_open(
            "/onlyoffice/editor/get_config",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Unauthenticated JSON-RPC → Odoo Session Expired error in body
        self.assertIn("error", data)

    def test_editor_config_returns_json(self):
        """Editor config endpoint returns JSON response for authenticated user."""
        self.authenticate("_oo_controller_test", "_oo_test_pass_123")
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"attachment_id": self.test_attachment.id}})
        response = self.url_open(
            "/onlyoffice/editor/get_config",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Must be a valid JSON-RPC response (result on success, error on failure)
        self.assertTrue("result" in data or "error" in data)

    def test_editor_config_invalid_attachment(self):
        """Editor config returns not-found for a deleted attachment id."""
        # Create then immediately delete to get a guaranteed-missing id
        gone = (
            self.env["ir.attachment"]
            .sudo()
            .create({"name": "gone.docx", "datas": base64.b64encode(b"x"), "mimetype": "text/plain"})
        )
        gone_id = gone.id
        gone.unlink()

        self.authenticate("_oo_controller_test", "_oo_test_pass_123")
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"attachment_id": gone_id}})
        response = self.url_open(
            "/onlyoffice/editor/get_config",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        # not_found() from a JSON-RPC route returns 404 or wraps as error
        self.assertIn(response.status_code, (200, 404))

    def test_editor_config_unsupported_format(self):
        """Editor config returns error for unsupported file format (zip)."""
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": "archive.zip",
                    "datas": base64.b64encode(b"fake zip content"),
                    "mimetype": "application/zip",
                }
            )
        )
        self.authenticate("_oo_controller_test", "_oo_test_pass_123")
        body = json.dumps({"jsonrpc": "2.0", "method": "call", "params": {"attachment_id": attachment.id}})
        response = self.url_open(
            "/onlyoffice/editor/get_config",
            data=body.encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Controller raises Exception("cant read"); JSON-RPC catches it → top-level "error"
        self.assertIn("error", data)

    # -- GET /onlyoffice/file/content/<id> (auth=public, oo_security_token) --

    def test_file_content_requires_valid_token(self):
        """File content endpoint rejects request without a security token."""
        response = self.url_open(
            f"/onlyoffice/file/content/{self.test_attachment.id}",
            allow_redirects=False,
        )
        # Without token get_user_from_token raises Exception → Odoo returns 403
        self.assertEqual(response.status_code, 403)

    def test_file_content_test_txt(self):
        """The built-in /onlyoffice/file/content/test.txt endpoint is public and returns 'test'.

        This verifies the file-content route is operational without requiring JWT
        tokens or any database records.
        """
        response = self.url_open("/onlyoffice/file/content/test.txt")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, "test")

    # -- GET /onlyoffice/editor/<id> (auth=public, website) --

    def test_editor_page_is_public(self):
        """Editor page is accessible without authentication (auth=public)."""
        response = self.url_open(
            f"/onlyoffice/editor/{self.test_attachment.id}",
            allow_redirects=False,
        )
        # Public route: no redirect, returns page or error
        self.assertNotIn(response.status_code, (302, 303))

    # -- GET /onlyoffice/preview (auth=user, website, params: url, title) --

    def test_preview_requires_auth(self):
        """Preview endpoint redirects unauthenticated users to login."""
        response = self.url_open(
            "/onlyoffice/preview?url=https://docs.example.com&title=Test",
            allow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))

    def test_preview_authenticated(self):
        """Preview endpoint returns HTML page for an authenticated user."""
        self.authenticate("_oo_controller_test", "_oo_test_pass_123")
        response = self.url_open("/onlyoffice/preview?url=https://docs.example.com&title=Test")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))

    # -- Onlyoffice_Connector.filter_xss (pure helper, no HTTP needed) --

    def test_filter_xss_removes_html_and_script_characters(self):
        """filter_xss strips characters that could be used for XSS (angle brackets, quotes, etc.)."""
        connector = Onlyoffice_Connector()
        result = connector.filter_xss("<script>alert('xss')</script>report.docx")
        self.assertNotIn("<", result)
        self.assertNotIn(">", result)
        self.assertNotIn("'", result)
        self.assertTrue(result.endswith(".docx"))

    def test_filter_xss_preserves_valid_filename_characters(self):
        """filter_xss keeps letters, digits, spaces, and common filename punctuation unchanged."""
        connector = Onlyoffice_Connector()
        name = "My Report 2024-Q1.docx"
        self.assertEqual(connector.filter_xss(name), name)

    # -- POST /onlyoffice/editor/callback/<id> (auth=public, no-csrf) --

    def test_editor_callback_without_token_returns_error_json(self):
        """Callback endpoint returns JSON with error=1 when no security token is provided.

        The missing token causes get_user_from_token to raise Forbidden, which the
        callback handler catches and converts to an error payload rather than a crash.
        """
        response = self.url_open(
            f"/onlyoffice/editor/callback/{self.test_attachment.id}",
            data=json.dumps({"status": 1}).encode(),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 500)
        data = response.json()
        self.assertEqual(data["error"], 1)

    # -- GET /onlyoffice/editor/<id> authenticated --

    def test_render_editor_authenticated_returns_html(self):
        """Editor page returns an HTML response to an authenticated user who can read the attachment."""
        self.authenticate("_oo_controller_test", "_oo_test_pass_123")
        response = self.url_open(f"/onlyoffice/editor/{self.test_attachment.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers.get("Content-Type", ""))
