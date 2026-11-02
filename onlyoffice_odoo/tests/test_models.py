# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from datetime import date
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils

VALIDATION = "odoo.addons.onlyoffice_odoo.utils.validation_utils.settings_validation"


@tagged("post_install", "-at_install")
class TestOnlyofficeOdooModel(TransactionCase):
    """onlyoffice.odoo: the settings the web client reads (demo trial, opening in the same tab)."""

    def test_demo_state_for_the_web_client(self):
        self.assertEqual(json.loads(self.env["onlyoffice.odoo"].get_demo()), {"mode": False, "date": False})

        config_utils.set_demo(self.env, True)

        demo = json.loads(self.env["onlyoffice.odoo"].get_demo())
        self.assertEqual((demo["mode"], demo["date"]), ("True", str(date.today())))

    def test_same_tab_for_the_web_client(self):
        config_utils.set_same_tab(self.env, True)
        self.assertEqual(json.loads(self.env["onlyoffice.odoo"].get_same_tab()), {"same_tab": "True"})


@tagged("post_install", "-at_install")
class TestResConfigSettings(TransactionCase):
    """res.config.settings: the ONLYOFFICE section of Settings; the Document Server checks are mocked."""

    def setUp(self):
        super().setUp()
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com")
        config_utils.set_jwt_secret(self.env, "secret")

    def _settings(self, **values):
        return self.env["res.config.settings"].create(values)

    def test_form_shows_the_current_settings(self):
        settings = self._settings()
        self.assertEqual(settings.doc_server_public_url, "https://docs.example.com/")
        self.assertEqual(settings.doc_server_jwt_secret, "secret")
        self.assertEqual(settings.doc_server_jwt_header, "Authorization")
        self.assertFalse(settings.same_tab)

    def test_changed_settings_are_checked_then_saved(self):
        settings = self._settings(
            doc_server_public_url="https://new.example.com", doc_server_jwt_header="X-Custom", same_tab=True
        )
        with patch(VALIDATION) as validation:
            settings.set_values()

        validation.assert_called_once_with(settings)
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "https://new.example.com/")
        self.assertEqual(config_utils.get_jwt_header(self.env), "X-Custom")
        self.assertTrue(config_utils.get_same_tab(self.env))

    def test_failed_check_saves_nothing(self):
        settings = self._settings(doc_server_public_url="https://unreachable.example.com")
        with patch(VALIDATION, side_effect=ValidationError("cannot be reached")), self.assertRaises(ValidationError):
            settings.set_values()
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "https://docs.example.com/")

    def test_unchanged_settings_are_not_checked(self):
        with patch(VALIDATION) as validation:
            self._settings().set_values()
        validation.assert_not_called()

    def test_demo_server_is_not_checked(self):
        settings = self._settings(doc_server_demo=True)
        with patch(VALIDATION) as validation:
            settings.set_values()
        validation.assert_not_called()
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "https://onlinedocs.docs.onlyoffice.com/")

    def test_invalid_addresses_are_not_saved(self):
        settings = self._settings(doc_server_public_url="https://bad url.com", doc_server_odoo_url="http://bad url")
        with patch(VALIDATION):
            settings.set_values()
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "https://docs.example.com/")
        self.assertNotIn("bad", config_utils.get_base_or_odoo_url(self.env))

    def test_invalid_url_is_warned_about_while_typing(self):
        settings = self._settings()
        for url, warns in {"https://bad url.com": True, "https://docs.example.com": False, "": False}.items():
            with self.subTest(url=url):
                settings.doc_server_public_url = url
                result = settings._onchange_doc_server_public_url()
                self.assertEqual(bool(result and "warning" in result), warns)
