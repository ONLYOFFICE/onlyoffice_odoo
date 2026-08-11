# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import conversion_utils, validation_utils


@tagged("post_install", "-at_install")
class TestValidationUtils(TransactionCase):
    """Tests for validation_utils module — URL validation and error messages."""

    # -- valid_url --

    def test_valid_url_http(self):
        """HTTP URL is recognized as valid."""
        self.assertTrue(validation_utils.valid_url("http://localhost:8080"))

    def test_valid_url_https(self):
        """HTTPS URL is recognized as valid."""
        self.assertTrue(validation_utils.valid_url("https://docs.example.com"))

    def test_valid_url_with_path(self):
        """URL with path is recognized as valid."""
        self.assertTrue(validation_utils.valid_url("https://example.com/path/to/api"))

    def test_valid_url_empty_string_is_valid(self):
        """Empty string is considered valid (no URL means no validation needed)."""
        self.assertTrue(validation_utils.valid_url(""))

    def test_valid_url_none_is_valid(self):
        """None is considered valid (no URL means no validation needed)."""
        self.assertTrue(validation_utils.valid_url(None))

    def test_valid_url_with_spaces_invalid(self):
        """URL with spaces is invalid."""
        self.assertFalse(validation_utils.valid_url("http://doc server.com"))

    def test_valid_url_special_chars_invalid(self):
        """URL with unsupported special characters is invalid."""
        self.assertFalse(validation_utils.valid_url("http://server.com/path?query=1&foo=bar"))

    def test_valid_url_ip_with_port(self):
        """DocServer deployed on a bare IP address with port is a valid URL (common in LAN setups)."""
        self.assertTrue(validation_utils.valid_url("http://192.168.1.100:8080"))

    def test_valid_url_ip_without_scheme(self):
        """DocServer on bare IP without http:// prefix is valid (fix_url will add the scheme)."""
        self.assertTrue(validation_utils.valid_url("192.168.1.100"))

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
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            validation_utils.check_doc_serv_url("http://docserver/", False, False)

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
        """No error is raised when the conversion service responds without an error."""
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.convert", return_value=None):
            validation_utils.check_doc_serv_convert_service(
                self.env, "http://docserver/", "http://odoo/", "", "Authorization", False, False
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

    def test_command_service_passes_with_jwt_secret_and_error_zero(self):
        """Command service check succeeds when a JWT secret is provided — token is signed and sent."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 0}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            validation_utils.check_doc_serv_command_service(
                self.env, "http://docserver/", "my_test_jwt_secret_key", "Authorization", False, False
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
