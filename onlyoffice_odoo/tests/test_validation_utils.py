# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import conversion_utils, jwt_utils, validation_utils

from .common import known_bug


@tagged("post_install", "-at_install")
class TestValidationUtils(TransactionCase):
    """Tests for validation_utils module — URL validation and error messages."""

    # -- valid_url --

    def test_valid_url_accepts_docserver_addresses_and_empty_values(self):
        for url in (
            "http://localhost:8080",
            "https://docs.example.com",
            "https://example.com/path/to/api",
            "http://192.168.1.100:8080",
            "192.168.1.100",
            "",
            None,
        ):
            with self.subTest(url=url):
                self.assertTrue(validation_utils.valid_url(url))

    def test_valid_url_rejects_spaces_and_query_strings(self):
        for url in ("http://doc server.com", "http://server.com/path?query=1&foo=bar"):
            with self.subTest(url=url):
                self.assertFalse(validation_utils.valid_url(url))

    # -- get_conversion_error_message --

    def test_error_message_unknown_error(self):
        """Error code -1 returns 'Unknown error' message."""
        msg = conversion_utils.get_conversion_error_message(-1)
        self.assertEqual(msg, "Unknown error")

    def test_error_message_undefined_code(self):
        """Unrecognized error code returns the fallback 'Undefined error code' message."""
        msg = conversion_utils.get_conversion_error_message(-99)
        self.assertEqual(msg, "Undefined error code")

    def test_all_defined_error_codes_return_message(self):
        """Every error code defined by the ONLYOFFICE conversion API returns a non-empty string."""
        defined_codes = [-1, -2, -3, -4, -5, -6, -7, -8]
        for code in defined_codes:
            msg = conversion_utils.get_conversion_error_message(code)
            self.assertIsInstance(msg, str, f"Code {code} must return a string")
            self.assertTrue(len(msg) > 0, f"Code {code} must return a non-empty message")

    # -- get_region --

    def test_get_region_underscore_lang(self):
        """Odoo-style underscore lang codes are converted to dash-separated region codes."""
        self.assertEqual(conversion_utils.get_region("en_US"), "en-US")
        self.assertEqual(conversion_utils.get_region("fr_FR"), "fr-FR")
        self.assertEqual(conversion_utils.get_region("pt_BR"), "pt-BR")

    def test_get_region_empty_lang_returns_none(self):
        """Empty or falsy lang returns None (no region sent to the converter)."""
        self.assertIsNone(conversion_utils.get_region(""))
        self.assertIsNone(conversion_utils.get_region(None))

    def test_get_region_invalid_lang_returns_none(self):
        """Lang codes that don't resolve to a valid 'xx-XX' region return None."""
        self.assertIsNone(conversion_utils.get_region("es_419"))
        self.assertIsNone(conversion_utils.get_region("sr@latin"))
        self.assertIsNone(conversion_utils.get_region("en"))

    # -- check_mixed_content --

    def test_check_mixed_content_raises_when_odoo_https_and_docserver_http(self):
        """If Odoo runs on HTTPS but DocServer is on HTTP, a mixed-content ValidationError is raised."""
        with self.assertRaises(ValidationError):
            validation_utils.check_mixed_content("https://myodoo.com", "http://docserver/", False)

    def test_check_mixed_content_no_error_when_both_https(self):
        """No error when both Odoo and DocServer use HTTPS."""
        validation_utils.check_mixed_content("https://myodoo.com", "https://docserver/", False)

    def test_check_mixed_content_no_error_when_odoo_is_http(self):
        """No error when Odoo itself is on HTTP — the mixed-content rule only applies to HTTPS Odoo."""
        validation_utils.check_mixed_content("http://myodoo.com", "http://docserver/", False)

    # -- get_message_error --

    def test_get_message_error_raises_plain_message_in_normal_mode(self):
        """In normal mode, get_message_error raises ValidationError containing the plain message."""
        with self.assertRaises(ValidationError) as ctx:
            validation_utils.get_message_error("Connection refused", False)
        self.assertIn("Connection refused", str(ctx.exception))

    def test_get_message_error_prefixes_demo_server_in_demo_mode(self):
        """In demo mode, the error message includes 'demo server' to identify the source."""
        with self.assertRaises(ValidationError) as ctx:
            validation_utils.get_message_error("Timeout", True)
        self.assertIn("demo server", str(ctx.exception).lower())

    # -- check_doc_serv_url --

    def test_check_doc_serv_url_passes_when_healthcheck_returns_content(self):
        """No error is raised when the healthcheck endpoint responds with a non-empty body."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"true"
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp) as urlopen:
            validation_utils.check_doc_serv_url("http://docserver/", False, False)
        self.assertEqual(urlopen.call_args.args, ("http://docserver/healthcheck",))
        self.assertIsNone(urlopen.call_args.kwargs["context"])

    @known_bug("the error message repeats the healthcheck path")
    def test_empty_healthcheck_message_names_the_healthcheck_url(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        with (
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp),
            self.assertRaises(ValidationError) as error,
        ):
            validation_utils.check_doc_serv_url("http://docserver/", False, False)
        self.assertEqual(str(error.exception), "http://docserver/healthcheck returned false.")

    def test_unreachable_healthcheck_is_reported(self):
        with (
            patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", side_effect=OSError("refused")),
            self.assertRaises(ValidationError) as error,
        ):
            validation_utils.check_doc_serv_url("http://docserver/", False, False)
        self.assertEqual(str(error.exception), "ONLYOFFICE cannot be reached")

    def test_check_doc_serv_url_raises_when_healthcheck_returns_empty_body(self):
        """ValidationError is raised when the healthcheck endpoint returns an empty body."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            with self.assertRaises(ValidationError):
                validation_utils.check_doc_serv_url("http://docserver/", False, False)

    def test_check_doc_serv_url_creates_ssl_context_when_certificate_disabled_and_https(self):
        """An unverified SSL context is created when certificate check is disabled for an HTTPS URL."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"true"
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            with patch("ssl._create_unverified_context", return_value=MagicMock()) as mock_ssl:
                validation_utils.check_doc_serv_url("https://docserver/", False, True)
                mock_ssl.assert_called_once()

    # -- check_doc_serv_convert_service --

    def test_check_doc_serv_convert_service_passes_when_convert_succeeds(self):
        """The conversion check converts the public test.txt of this Odoo, as the Document Server sees it."""
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.convert", return_value=None) as convert:
            validation_utils.check_doc_serv_convert_service(
                self.env, "http://docserver/", "http://odoo/", "", "Authorization", False, False
            )
        self.assertEqual(
            convert.call_args.args[1:3], ("http://odoo/onlyoffice/file/content/test.txt", "http://docserver/")
        )

    def test_check_doc_serv_convert_service_raises_when_convert_returns_error(self):
        """ValidationError is raised when the conversion service returns an error message."""
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.convert", return_value="Conversion error"):
            with self.assertRaises(ValidationError):
                validation_utils.check_doc_serv_convert_service(
                    self.env, "http://docserver/", "http://odoo/", "", "Authorization", False, False
                )

    # -- convert --

    def test_convert_returns_none_on_successful_200_response(self):
        """convert returns None when DocServer responds with 200 and no error field."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            result = validation_utils.convert(
                self.env, "http://odoo/test.txt", "http://docserver/", "", "Authorization", False
            )
        self.assertIsNone(result)

    def test_convert_returns_error_string_when_response_contains_error_code(self):
        """convert returns a human-readable error string when DocServer reports a conversion error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"error": -3}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            result = validation_utils.convert(
                self.env, "http://odoo/test.txt", "http://docserver/", "", "Authorization", False
            )
        self.assertIsInstance(result, str)
        self.assertIn("Conversion error", result)

    def test_convert_returns_error_string_on_non_200_status(self):
        """convert returns an error string that includes the HTTP status code when DocServer returns non-200."""
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            result = validation_utils.convert(
                self.env, "http://odoo/test.txt", "http://docserver/", "", "Authorization", False
            )
        self.assertIsInstance(result, str)
        self.assertIn("503", result)

    def test_convert_adds_jwt_token_to_request_when_jwt_secret_provided(self):
        """When a JWT secret is given, convert signs the request body and adds an Authorization header."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch(
            "odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp
        ) as mock_post:
            validation_utils.convert(
                self.env, "http://odoo/test.txt", "http://docserver/", "test_jwt_secret_value", "Authorization", False
            )
            called_headers = mock_post.call_args[1]["headers"]
            self.assertIn("Authorization", called_headers)
            self.assertTrue(called_headers["Authorization"].startswith("Bearer "))

    # -- check_doc_serv_command_service --

    def test_command_service_passes_when_error_code_is_zero(self):
        """No error is raised when the command service responds with error code 0 (success)."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 0}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            validation_utils.check_doc_serv_command_service(
                self.env, "http://docserver/", "", "Authorization", False, False
            )

    def test_command_service_request_is_signed_with_the_jwt_secret(self):
        """With a JWT secret the version command carries a token in the body and in the configured header."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 0}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp) as post:
            validation_utils.check_doc_serv_command_service(
                self.env, "http://docserver/", "my_test_jwt_secret_key", "X-Custom", False, False
            )
        self.assertEqual(post.call_args.args, ("http://docserver/coauthoring/CommandService.ashx",))
        secret = "my_test_jwt_secret_key"
        body = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(jwt_utils.decode_token(self.env, body.pop("token"), secret)["c"], "version")
        self.assertEqual(body["c"], "version")
        header = post.call_args.kwargs["headers"]["X-Custom"]
        self.assertTrue(header.startswith("Bearer "))
        self.assertEqual(
            jwt_utils.decode_token(self.env, header[len("Bearer ") :], secret)["payload"], {"c": "version"}
        )

    def test_command_service_raises_on_authorization_error_code_six(self):
        """ValidationError mentioning 'Authorization error' is raised when command service returns error 6."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 6}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            with self.assertRaises(ValidationError) as ctx:
                validation_utils.check_doc_serv_command_service(
                    self.env, "http://docserver/", "", "Authorization", False, False
                )
        self.assertIn("Authorization error", str(ctx.exception))

    def test_command_service_raises_on_any_nonzero_error_code(self):
        """ValidationError is raised when the command service returns any non-zero error code."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 5}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            with self.assertRaises(ValidationError):
                validation_utils.check_doc_serv_command_service(
                    self.env, "http://docserver/", "", "Authorization", False, False
                )

    # -- settings_validation --

    def _validate(self, **values):
        settings = self.env["res.config.settings"].new(
            {
                "doc_server_public_url": "https://docs.example.com/",
                "doc_server_inner_url": False,
                "doc_server_odoo_url": "https://odoo.example.com/",
                "doc_server_jwt_secret": "secret",
                "doc_server_jwt_header": "Authorization",
                "doc_server_demo": False,
                "doc_server_disable_certificate": False,
                **values,
            }
        )
        checks = {}
        names = ("check_mixed_content", "check_doc_serv_url", "check_doc_serv_command_service")
        patches = [patch(f"odoo.addons.onlyoffice_odoo.utils.validation_utils.{name}") for name in names]
        patches.append(patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.check_doc_serv_convert_service"))
        mocks = [p.start() for p in patches]
        try:
            validation_utils.settings_validation(settings)
        finally:
            for p in patches:
                p.stop()
        for name, mock in zip((*names, "check_doc_serv_convert_service"), mocks, strict=True):
            checks[name] = mock.call_args.args
        return checks

    def test_settings_are_checked_against_the_public_address(self):
        checks = self._validate()
        self.assertEqual(
            checks["check_mixed_content"], ("https://odoo.example.com/", "https://docs.example.com/", False)
        )
        self.assertEqual(checks["check_doc_serv_url"], ("https://docs.example.com/", False, False))
        self.assertEqual(
            checks["check_doc_serv_command_service"][1:4], ("https://docs.example.com/", "secret", "Authorization")
        )
        self.assertEqual(
            checks["check_doc_serv_convert_service"][1:3], ("https://docs.example.com/", "https://odoo.example.com/")
        )

    def test_settings_are_checked_against_the_inner_address_when_set(self):
        checks = self._validate(doc_server_inner_url="http://documentserver/", doc_server_demo=True)
        self.assertEqual(checks["check_doc_serv_url"], ("http://documentserver/", True, False))
        self.assertEqual(checks["check_doc_serv_convert_service"][1], "http://documentserver/")
