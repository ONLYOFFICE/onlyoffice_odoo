# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from datetime import date
from unittest.mock import patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils

VALIDATION = "odoo.addons.onlyoffice_odoo.utils.validation_utils.settings_validation"
DEMO_URL = "https://onlinedocs.docs.onlyoffice.com/"


@tagged("post_install", "-at_install")
class TestOnlyofficeOdooModel(TransactionCase):
    """onlyoffice.odoo: the settings the web client reads (demo trial, opening in the same tab)."""

    def test_demo_state_for_the_web_client(self):
        self.assertEqual(json.loads(self.env["onlyoffice.odoo"].get_demo()), {"mode": False, "date": False})

        config_utils.set_demo(self.env, True)

        demo = json.loads(self.env["onlyoffice.odoo"].get_demo())
        self.assertEqual((demo["mode"], demo["date"]), (True, str(date.today())))

    def test_same_tab_for_the_web_client(self):
        config_utils.set_same_tab(self.env, True)
        self.assertEqual(json.loads(self.env["onlyoffice.odoo"].get_same_tab()), {"same_tab": True})


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

    def test_invalid_addresses_are_an_error(self):
        for values in ({"doc_server_public_url": "https://bad url.com"}, {"doc_server_odoo_url": "http://bad url"}):
            with self.subTest(values=values):
                settings = self._settings(**values)
                with patch(VALIDATION), self.assertRaisesRegex(ValidationError, "Incorrect address"):
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


@tagged("post_install", "-at_install")
class TestSettingsSavePaths(TransactionCase):
    """Every way of saving the ONLYOFFICE settings: what is saved, and how often the Document Server is checked."""

    def _own_server(self):
        config_utils.set_demo(self.env, False)
        config_utils.set_doc_server_public_url(self.env, "http://docs.own.test/")
        config_utils.set_doc_server_inner_url(self.env, False)  # the inner address follows the public one
        config_utils.set_jwt_secret(self.env, "own-secret")
        config_utils.set_jwt_header(self.env, "Authorization")

    def _save(self, **values):
        """Saves the settings form with ``values`` changed; returns how many times the server was checked."""
        settings = self.env["res.config.settings"].create({})
        settings.write(values)
        with patch(VALIDATION) as validation:
            settings.set_values()
        return validation.call_count

    def _saved(self):
        return (
            config_utils.get_demo(self.env),
            config_utils.get_doc_server_public_url(self.env),
            config_utils.get_jwt_secret(self.env),
            config_utils.get_jwt_header(self.env),
        )

    def test_demo_on_uses_the_demo_server_unchecked(self):
        self._own_server()
        self.assertEqual(self._save(doc_server_demo=True), 0)
        self.assertEqual(self._saved(), (True, DEMO_URL, "sn2puSUF7muF5Jas", "AuthorizationJWT"))

    def test_demo_off_with_an_own_server_saves_it_checked(self):
        config_utils.set_demo(self.env, True)
        checks = self._save(
            doc_server_demo=False,
            doc_server_public_url="https://docs.company.test:8443/ds/",
            doc_server_jwt_secret="company-secret",
            doc_server_jwt_header="AuthorizationCompany",
        )
        self.assertEqual(checks, 1)
        self.assertEqual(
            self._saved(), (False, "https://docs.company.test:8443/ds/", "company-secret", "AuthorizationCompany")
        )

    def test_demo_off_with_an_empty_address_saves_the_default_one(self):
        config_utils.set_demo(self.env, True)
        self.assertEqual(self._save(doc_server_demo=False, doc_server_public_url="", doc_server_jwt_secret=""), 0)
        self.assertEqual(self._saved()[:3], (False, "http://documentserver/", False))

    def test_demo_off_with_only_the_address_cleared_does_not_keep_the_demo_secret(self):
        # The secret and header fields still show the demo values: an empty address is no server of one's own.
        config_utils.set_demo(self.env, True)
        for address in ("", "   "):
            with self.subTest(address=address):
                self.assertEqual(self._save(doc_server_demo=False, doc_server_public_url=address), 0)
                self.assertEqual(self._saved(), (False, "http://documentserver/", False, "Authorization"))
                config_utils.set_demo(self.env, True)

    def test_demo_off_with_only_an_own_inner_address_is_an_error(self):
        # The editor is loaded from the public address: the inner one alone (public left as the demo) is not enough.
        config_utils.set_demo(self.env, True)
        with self.assertRaisesRegex(ValidationError, "Enter the ONLYOFFICE Docs address"):
            self._save(doc_server_demo=False, doc_server_inner_url="http://docs.inner.test/")
        self.assertTrue(config_utils.get_demo(self.env))

    def test_demo_off_with_the_demo_address_spelt_otherwise_is_no_own_server(self):
        for address in ("HTTPS://onlinedocs.docs.onlyoffice.com/", "https://onlinedocs.docs.onlyoffice.com:443"):
            with self.subTest(address=address):
                config_utils.set_demo(self.env, True)
                self.assertEqual(self._save(doc_server_demo=False, doc_server_public_url=address), 0)
                self.assertEqual(self._saved(), (False, "http://documentserver/", False, "Authorization"))

    def test_demo_off_alone_does_not_keep_the_demo_server(self):
        # The form shows the address, secret and header of the demo server: unticking the demo only must not save
        # them as an own server (no demo period then).
        config_utils.set_demo(self.env, True)
        self.assertEqual(self._save(doc_server_demo=False), 0)
        self.assertEqual(self._saved(), (False, "http://documentserver/", False, "Authorization"))
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://documentserver/")

    def test_demo_off_with_an_own_server_drops_the_demo_secret_and_header(self):
        # Left in the form they are the demo values: a public secret, and a header the own server does not send.
        config_utils.set_demo(self.env, True)
        checks = self._save(doc_server_demo=False, doc_server_public_url="http://docs.own.test/")
        self.assertEqual(checks, 1)
        self.assertEqual(self._saved(), (False, "http://docs.own.test/", False, "Authorization"))
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://docs.own.test/")

    def test_demo_off_with_an_own_public_and_inner_server(self):
        config_utils.set_demo(self.env, True)
        settings = self.env["res.config.settings"].create({})
        settings.write(
            {
                "doc_server_demo": False,
                "doc_server_public_url": "https://docs.own.test/",
                "doc_server_inner_url": "http://docs-inner:80",
                "doc_server_jwt_secret": "own",
                "doc_server_jwt_header": "AuthorizationOwn",
            }
        )
        with patch(VALIDATION) as validation:
            settings.set_values()
        self.assertEqual(validation.call_args.args[0].doc_server_inner_url, "http://docs-inner:80")
        self.assertEqual(self._saved(), (False, "https://docs.own.test/", "own", "AuthorizationOwn"))
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://docs-inner:80/")

    def test_a_padded_or_blank_header_is_trimmed(self):
        self._own_server()
        self._save(doc_server_jwt_header="  AuthorizationOwn ")
        self.assertEqual(config_utils.get_jwt_header(self.env), "AuthorizationOwn")
        self._save(doc_server_jwt_header="   ")
        self.assertEqual(config_utils.get_jwt_header(self.env), "Authorization")

    def test_an_inner_address_equal_to_the_public_one_is_not_stored(self):
        # Older versions stored the inner address shown (the public one) on every save: such a copy adds nothing.
        self._own_server()
        config_utils.set_doc_server_inner_url(self.env, "http://docs.own.test/")
        self._save(same_tab=True)
        self.assertFalse(self.env["ir.config_parameter"].sudo().get_str(config_constants.DOC_SERVER_INNER_URL))
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://docs.own.test/")
        # Typed equal to a new public address, it follows that one.
        self._save(doc_server_public_url="http://docs.moved.test/", doc_server_inner_url="docs.moved.test")
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://docs.moved.test/")

    def test_a_blank_header_with_a_secret_is_checked_with_the_default_one(self):
        self._own_server()
        settings = self.env["res.config.settings"].create({})
        settings.doc_server_jwt_header = "   "
        with (
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_mixed_content"),
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_url"),
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_command_service") as command,
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_convert_service"),
        ):
            settings.set_values()
        self.assertEqual(command.call_args.args[3], "Authorization")
        self.assertEqual(config_utils.get_jwt_header(self.env), "Authorization")

    def test_spaces_around_addresses_are_not_saved(self):
        self._own_server()
        params = self.env["ir.config_parameter"].sudo()
        odoo_url = config_utils.get_base_or_odoo_url(self.env)
        self.assertEqual(self._save(doc_server_public_url=" http://docs.padded.test/ ", doc_server_odoo_url="   "), 1)
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://docs.padded.test/")
        # A blank Odoo address is empty: it goes back to web.base.url, never "http://   /".
        self.assertNotIn(" ", params.get_str(config_constants.DOC_SERVER_ODOO_URL) or "")
        self.assertEqual(
            config_utils.get_base_or_odoo_url(self.env), config_utils.fix_url(params.get_str("web.base.url"))
        )
        self.assertTrue(odoo_url)

    def test_a_public_address_for_browsers_keeps_the_inner_one(self):
        # Docker and similar: Odoo reaches the server by its inner name, browsers by another address. The inner
        # address shown (here the former public one) is kept, the check goes to it.
        self._own_server()
        settings = self.env["res.config.settings"].create({})
        settings.doc_server_public_url = "http://docs.browsers.test:8100/"
        with patch(VALIDATION) as validation:
            settings.set_values()
        self.assertEqual(validation.call_args.args[0].doc_server_inner_url, "http://docs.own.test/")
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://docs.browsers.test:8100/")
        self.assertEqual(config_utils.get_doc_server_inner_url(self.env), "http://docs.own.test/")

    def test_an_emptied_odoo_address_goes_back_to_web_base_url(self):
        self._own_server()
        params = self.env["ir.config_parameter"].sudo()
        self._save(doc_server_odoo_url="http://odoo.internal.test:8069")
        self.assertEqual(params.get_str(config_constants.DOC_SERVER_ODOO_URL), "http://odoo.internal.test:8069/")
        self._save(doc_server_odoo_url=False)
        self.assertFalse(params.get_str(config_constants.DOC_SERVER_ODOO_URL))
        self.assertEqual(
            config_utils.get_base_or_odoo_url(self.env), config_utils.fix_url(params.get_str("web.base.url"))
        )

    def test_demo_on_ignores_a_wrong_server_address(self):
        # The demo server is used: the addresses entered for an own server are not saved, so not checked either.
        self._own_server()
        self.assertEqual(self._save(doc_server_demo=True, doc_server_public_url="http://docs server/"), 0)
        self.assertEqual(self._saved()[:2], (True, DEMO_URL))

    def test_an_address_saved_before_does_not_stop_saving(self):
        # The Odoo address falls back to web.base.url, which the address check may refuse: it is not entered here.
        self._own_server()
        params = self.env["ir.config_parameter"].sudo()
        params.set_str(config_constants.DOC_SERVER_ODOO_URL, False)
        params.set_str("web.base.url", "http://odoo.local./")
        self.assertEqual(self._save(same_tab=True), 1)
        self.assertTrue(config_utils.get_same_tab(self.env))
        # It is not saved as the address of Odoo for the Document Server either.
        self.assertFalse(params.get_str(config_constants.DOC_SERVER_ODOO_URL))

    def test_demo_off_with_a_wrong_address_is_an_error(self):
        config_utils.set_demo(self.env, True)
        with self.assertRaisesRegex(ValidationError, "Incorrect address"):
            self._save(doc_server_demo=False, doc_server_public_url="http://docs server/")
        self.assertTrue(config_utils.get_demo(self.env))

    def test_demo_off_with_an_unreachable_server_saves_nothing(self):
        config_utils.set_demo(self.env, True)
        settings = self.env["res.config.settings"].create({})
        settings.write({"doc_server_demo": False, "doc_server_public_url": "http://unreachable.test/"})
        with (
            patch(VALIDATION, side_effect=ValidationError("ONLYOFFICE cannot be reached")),
            self.assertRaises(ValidationError),
        ):
            settings.set_values()
        self.assertEqual(self._saved()[:2], (True, DEMO_URL))

    def test_own_server_changes_are_saved_checked(self):
        for values in (
            {"doc_server_public_url": "http://docs.other.test/"},
            {"doc_server_jwt_secret": "rotated-secret"},
            {"doc_server_jwt_secret": ""},
            {"doc_server_jwt_header": "AuthorizationOther"},
        ):
            with self.subTest(values=values):
                self._own_server()
                self.assertEqual(self._save(**values), 1)
                field, value = next(iter(values.items()))
                saved = dict(
                    zip(
                        ("doc_server_demo", "doc_server_public_url", "doc_server_jwt_secret", "doc_server_jwt_header"),
                        self._saved(),
                        strict=True,
                    )
                )
                self.assertEqual(saved[field] or "", value)

    def test_saving_without_a_change_does_not_check_with_the_flags_on(self):
        # Any settings page (of any app) saves this form: the boxes must compare equal to what is stored.
        self._own_server()
        config_utils.set_same_tab(self.env, True)
        config_utils.set_certificate_verify_disabled(self.env, True)
        self.assertEqual(self._save(), 0)
        self.assertEqual(self._saved(), (False, "http://docs.own.test/", "own-secret", "Authorization"))

    def test_the_check_reaches_the_address_as_saved(self):
        self._own_server()
        settings = self.env["res.config.settings"].create({})
        settings.doc_server_public_url = "docs.noscheme.test:8080"
        settings.doc_server_inner_url = ""  # else the server requests go to the inner address
        with (
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_mixed_content"),
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_url") as check_url,
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_command_service"),
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_convert_service"),
        ):
            settings.set_values()
        self.assertEqual(check_url.call_args.args[0], "http://docs.noscheme.test:8080/")
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), "http://docs.noscheme.test:8080/")
