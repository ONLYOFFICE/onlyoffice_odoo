# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils


@tagged("post_install", "-at_install")
class TestOnlyofficeOdooModel(TransactionCase):
    """Tests for onlyoffice.odoo model — get_demo and get_same_tab methods."""

    # -- get_demo --

    def test_get_demo_returns_json(self):
        """get_demo returns a valid JSON string."""
        result = self.env["onlyoffice.odoo"].get_demo()
        data = json.loads(result)
        self.assertIn("mode", data)
        self.assertIn("date", data)

    def test_get_demo_mode_reflects_config(self):
        """get_demo mode field matches the configured demo parameter."""
        config_utils.set_demo(self.env, True)
        result = json.loads(self.env["onlyoffice.odoo"].get_demo())
        self.assertTrue(result["mode"])

    def test_get_demo_date_present_after_enable(self):
        """get_demo date is set after enabling demo mode."""
        config_utils.set_demo(self.env, True)
        result = json.loads(self.env["onlyoffice.odoo"].get_demo())
        self.assertTrue(result["date"])

    # -- get_same_tab --

    def test_get_same_tab_returns_json(self):
        """get_same_tab returns a valid JSON string."""
        result = self.env["onlyoffice.odoo"].get_same_tab()
        data = json.loads(result)
        self.assertIn("same_tab", data)

    def test_get_same_tab_reflects_config(self):
        """get_same_tab value matches the configured same_tab parameter."""
        config_utils.set_same_tab(self.env, True)
        result = json.loads(self.env["onlyoffice.odoo"].get_same_tab())
        self.assertTrue(result["same_tab"])


@tagged("post_install", "-at_install")
class TestResConfigSettings(TransactionCase):
    """Tests for res.config.settings ONLYOFFICE fields — get/set values."""

    def _get_settings(self):
        """Helper: create a res.config.settings record."""
        return self.env["res.config.settings"].create({})

    # -- get_values --

    def test_get_values_contains_onlyoffice_fields(self):
        """get_values returns all ONLYOFFICE config fields."""
        settings = self._get_settings()
        values = settings.get_values()
        self.assertIn("doc_server_public_url", values)
        self.assertIn("doc_server_jwt_secret", values)
        self.assertIn("doc_server_jwt_header", values)
        self.assertIn("doc_server_demo", values)
        self.assertIn("same_tab", values)

    def test_get_values_public_url_matches_config(self):
        """get_values returns the currently configured public URL."""
        config_utils.set_doc_server_public_url(self.env, "https://test-docs.example.com")
        settings = self._get_settings()
        values = settings.get_values()
        self.assertEqual(values["doc_server_public_url"], "https://test-docs.example.com/")

    # -- set_values (with validation skip via demo mode) --

    def test_set_values_updates_same_tab(self):
        """set_values correctly persists same_tab setting."""
        # Enable demo mode to skip document server validation
        config_utils.set_demo(self.env, True)
        settings = self._get_settings()
        settings.doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        settings.doc_server_odoo_url = config_utils.get_base_or_odoo_url(self.env)
        settings.doc_server_inner_url = config_utils.get_doc_server_inner_url(self.env)
        settings.doc_server_jwt_secret = config_utils.get_jwt_secret(self.env) or ""
        settings.doc_server_jwt_header = config_utils.get_jwt_header(self.env)
        settings.doc_server_demo = True
        settings.doc_server_disable_certificate = False
        settings.same_tab = True
        settings.set_values()

        result = config_utils.get_same_tab(self.env)
        self.assertTrue(result)

    # -- onchange validation --

    def test_onchange_invalid_url_returns_warning(self):
        """Setting a URL with spaces (invalid chars) triggers an onchange warning."""
        settings = self._get_settings()
        settings.doc_server_public_url = "https://bad url.com"
        result = settings._onchange_doc_server_public_url()
        self.assertIn("warning", result)
        self.assertIn("message", result["warning"])

    def test_onchange_valid_url_no_warning(self):
        """Setting a valid URL does not trigger a warning."""
        settings = self._get_settings()
        settings.doc_server_public_url = "https://docs.example.com"
        result = settings._onchange_doc_server_public_url()
        self.assertIsNone(result)

    def test_onchange_empty_url_no_warning(self):
        """Empty URL does not trigger a warning (allowed)."""
        settings = self._get_settings()
        settings.doc_server_public_url = ""
        result = settings._onchange_doc_server_public_url()
        self.assertIsNone(result)
