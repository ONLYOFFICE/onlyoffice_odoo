# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from datetime import date
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils


@tagged("post_install", "-at_install")
class TestConfigUtils(TransactionCase):
    """config_utils: the connector settings stored in ir.config_parameter, their defaults and normalisation."""

    def _clear(self, *keys):
        for key in keys:
            self.env["ir.config_parameter"].sudo().set_param(key, False)

    def test_defaults(self):
        self._clear(
            config_constants.DOC_SERVER_PUBLIC_URL,
            config_constants.DOC_SERVER_INNER_URL,
            config_constants.DOC_SERVER_ODOO_URL,
            config_constants.DOC_SERVER_JWT_SECRET,
            config_constants.DOC_SERVER_JWT_HEADER,
            config_constants.SAME_TAB,
            config_constants.DOC_SERVER_DISABLE_CERTIFICATE,
        )
        web_base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")

        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://documentserver/")
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://documentserver/", "falls back")
        self.assertEqual(config_utils.get_base_or_odoo_url(self.env), config_utils.fix_url(web_base_url))
        self.assertFalse(config_utils.get_jwt_secret(self.env))
        self.assertEqual(config_utils.get_jwt_header(self.env), "Authorization")
        self.assertFalse(config_utils.get_same_tab(self.env))
        self.assertFalse(config_utils.get_certificate_verify_disabled(self.env))

    def test_settings_are_stored_and_read_back(self):
        cases = [
            ("public URL", config_utils.set_doc_server_public_url, config_utils.get_doc_server_public_url,
             "docs.example.com", "http://docs.example.com/"),
            ("inner URL", config_utils.set_doc_server_inner_url, config_utils.get_doc_server_inner_url,
             "http://documentserver:8080", "http://documentserver:8080/"),
            ("Odoo URL", config_utils.set_doc_server_odoo_url, config_utils.get_base_or_odoo_url,
             "https://odoo.example.com", "https://odoo.example.com/"),
            ("JWT secret", config_utils.set_jwt_secret, config_utils.get_jwt_secret, "secret", "secret"),
            ("JWT header", config_utils.set_jwt_header, config_utils.get_jwt_header, "X-Custom", "X-Custom"),
            ("same tab", config_utils.set_same_tab, config_utils.get_same_tab, True, "True"),
            ("certificate check disabled", config_utils.set_certificate_verify_disabled,
             config_utils.get_certificate_verify_disabled, True, "True"),
        ]  # fmt: skip
        for name, setter, getter, value, expected in cases:
            with self.subTest(setting=name):
                setter(self.env, value)
                self.assertEqual(getter(self.env), expected)

    def test_empty_public_url_falls_back_to_the_default(self):
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        config_utils.set_doc_server_public_url(self.env, "")
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://documentserver/")

    def test_inner_url_falls_back_to_the_public_url(self):
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        self._clear(config_constants.DOC_SERVER_INNER_URL)
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "https://docs.example.com/")

    def test_internal_secret_is_generated_once_and_committed(self):
        self._clear(config_constants.INTERNAL_JWT_SECRET)
        with patch.object(self.env.cr, "commit") as commit:
            secret = config_utils.get_internal_jwt_secret(self.env)
            self.assertEqual(config_utils.get_internal_jwt_secret(self.env), secret)
        self.assertRegex(secret, r"^[0-9a-f]{32}$")
        commit.assert_called_once()

    def test_demo_server_replaces_and_restores_the_connection(self):
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        self._clear(config_constants.DOC_SERVER_DEMO_DATE)

        config_utils.set_demo(self.env, True)
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "https://onlinedocs.docs.onlyoffice.com/")
        self.assertEqual(config_utils.get_jwt_header(self.env), "AuthorizationJWT")
        self.assertTrue(config_utils.get_jwt_secret(self.env))
        self.assertEqual(config_utils.get_demo_date(self.env), str(date.today()))

        config_utils.set_demo(self.env, False)
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://documentserver/")
        self.assertEqual(config_utils.get_jwt_header(self.env), "Authorization")
        self.assertFalse(config_utils.get_jwt_secret(self.env))
        self.assertFalse(config_utils.get_demo(self.env))

    def test_demo_date_is_kept_when_the_demo_is_enabled_again(self):
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_DEMO_DATE, "2026-01-01")
        config_utils.set_demo(self.env, True)
        self.assertEqual(config_utils.get_demo_date(self.env), "2026-01-01", "the 30-day trial does not restart")

    def test_fix_url(self):
        cases = {
            "example.com": "http://example.com/",
            "http://example.com": "http://example.com/",
            "https://secure.example.com/": "https://secure.example.com/",
            "": None,
            None: None,
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(config_utils.fix_url(url), expected)
