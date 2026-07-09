# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils


@tagged("post_install", "-at_install")
class TestConfigUtils(TransactionCase):
    """Tests for config_utils module тАФ reading and writing ONLYOFFICE config parameters."""

    # -- URL getters/setters --

    def test_get_doc_server_public_url_default(self):
        """Default public URL is 'http://documentserver/' when no custom URL is configured."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_PUBLIC_URL, "")
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertEqual(url, "http://documentserver/")

    def test_set_and_get_doc_server_public_url(self):
        """Setting a public URL and reading it back returns the same value."""
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertEqual(url, "https://docs.example.com/")

    def test_set_doc_server_public_url_adds_trailing_slash(self):
        """URL is normalized with a trailing slash."""
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertTrue(url.endswith("/"))

    def test_set_doc_server_public_url_empty_resets_to_default(self):
        """Setting empty URL resets to default document server URL."""
        config_utils.set_doc_server_public_url(self.env, "")
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertEqual(url, "http://documentserver/")

    def test_get_doc_server_inner_url_fallback(self):
        """Inner URL falls back to public URL when not configured."""
        config_utils.set_doc_server_public_url(self.env, "https://public.example.com")
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_INNER_URL, "")
        inner_url = config_utils.get_doc_server_inner_url(self.env)
        self.assertEqual(inner_url, "https://public.example.com/")

    def test_set_and_get_doc_server_inner_url(self):
        """Setting inner URL and reading it back returns the same value."""
        config_utils.set_doc_server_inner_url(self.env, "http://docserver-internal:8080")
        inner_url = config_utils.get_doc_server_inner_url(self.env)
        self.assertEqual(inner_url, "http://docserver-internal:8080/")

    def test_get_base_or_odoo_url_falls_back_to_web_base_url(self):
        """get_base_or_odoo_url falls back to web.base.url when no custom Odoo URL is set."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_ODOO_URL, "")
        web_base = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        result = config_utils.get_base_or_odoo_url(self.env)
        self.assertEqual(result, config_utils.fix_url(web_base))

    def test_set_and_get_odoo_url(self):
        """Setting custom Odoo URL and reading it back works correctly."""
        config_utils.set_doc_server_odoo_url(self.env, "https://myodoo.com")
        url = config_utils.get_base_or_odoo_url(self.env)
        self.assertEqual(url, "https://myodoo.com/")

    # -- JWT getters/setters --

    def test_get_jwt_secret_empty_by_default(self):
        """JWT secret is empty (falsy) by default."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_SECRET, "")
        secret = config_utils.get_jwt_secret(self.env)
        self.assertFalse(secret)

    def test_set_and_get_jwt_secret(self):
        """Setting JWT secret and reading it back works correctly."""
        config_utils.set_jwt_secret(self.env, "my_secret_key")
        secret = config_utils.get_jwt_secret(self.env)
        self.assertEqual(secret, "my_secret_key")

    def test_get_jwt_header_default(self):
        """Default JWT header is 'Authorization'."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_HEADER, "")
        header = config_utils.get_jwt_header(self.env)
        self.assertEqual(header, "Authorization")

    def test_set_and_get_jwt_header(self):
        """Setting custom JWT header and reading it back works correctly."""
        config_utils.set_jwt_header(self.env, "X-Custom-Header")
        header = config_utils.get_jwt_header(self.env)
        self.assertEqual(header, "X-Custom-Header")

    # -- Internal JWT secret --

    def test_get_internal_jwt_secret_generates_if_missing(self):
        """Internal JWT secret is auto-generated when not set."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.INTERNAL_JWT_SECRET, "")
        with patch.object(self.env.cr, "commit"):
            secret = config_utils.get_internal_jwt_secret(self.env)
        self.assertTrue(secret)
        self.assertIsInstance(secret, str)
        self.assertTrue(len(secret) > 0)

    def test_get_internal_jwt_secret_stable(self):
        """Internal JWT secret remains the same across multiple calls."""
        with patch.object(self.env.cr, "commit"):
            secret1 = config_utils.get_internal_jwt_secret(self.env)
            secret2 = config_utils.get_internal_jwt_secret(self.env)
        self.assertEqual(secret1, secret2)

    # -- Demo mode --

    def test_set_demo_mode_on(self):
        """Enabling demo mode sets the demo URL and secret."""
        config_utils.set_demo(self.env, True)
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertIn("onlinedocs.docs.onlyoffice.com", url)

    def test_set_demo_mode_off_resets_url(self):
        """Disabling demo mode resets URL to default."""
        config_utils.set_demo(self.env, True)
        config_utils.set_demo(self.env, False)
        url = config_utils.get_doc_server_public_url(self.env)
        self.assertEqual(url, "http://documentserver/")

    def test_get_demo_returns_param(self):
        """get_demo returns the current demo parameter value."""
        config_utils.set_demo(self.env, True)
        demo = config_utils.get_demo(self.env)
        self.assertTrue(demo)

    # -- Same tab --

    def test_set_and_get_same_tab(self):
        """Setting same_tab and reading it back works correctly."""
        config_utils.set_same_tab(self.env, True)
        result = config_utils.get_same_tab(self.env)
        self.assertTrue(result)

    # -- Certificate verification --

    def test_set_and_get_certificate_verify_disabled(self):
        """Setting certificate verification disabled flag works correctly."""
        config_utils.set_certificate_verify_disabled(self.env, True)
        result = config_utils.get_certificate_verify_disabled(self.env)
        self.assertTrue(result)

    # -- fix_url helper --

    def test_fix_url_adds_protocol(self):
        """fix_url adds http:// if no protocol is present."""
        result = config_utils.fix_url("example.com")
        self.assertEqual(result, "http://example.com/")

    def test_fix_url_adds_trailing_slash(self):
        """fix_url adds trailing slash if missing."""
        result = config_utils.fix_url("http://example.com")
        self.assertEqual(result, "http://example.com/")

    def test_fix_url_preserves_https(self):
        """fix_url preserves existing https protocol."""
        result = config_utils.fix_url("https://secure.example.com/")
        self.assertEqual(result, "https://secure.example.com/")

    def test_fix_url_none_returns_none(self):
        """fix_url with None input returns None."""
        result = config_utils.fix_url(None)
        self.assertIsNone(result)

    def test_fix_url_empty_returns_none(self):
        """fix_url with empty string returns None (falsy)."""
        result = config_utils.fix_url("")
        self.assertFalse(result)
