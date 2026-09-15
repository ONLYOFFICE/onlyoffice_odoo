# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import MagicMock, patch

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import conversion_utils, network_utils, validation_utils

VALIDATION = "odoo.addons.onlyoffice_odoo.utils.validation_utils"
GETADDRINFO = "odoo.addons.onlyoffice_odoo.utils.network_utils.socket.getaddrinfo"


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

    def test_check_mixed_content_uses_official_message(self):
        """The mixed-content message matches the text ONLYOFFICE connectors use for this check."""
        with self.assertRaises(ValidationError) as ctx:
            validation_utils.check_mixed_content("https://myodoo.com", "http://docserver/", False)
        self.assertEqual(
            str(ctx.exception),
            "Mixed Active Content is not allowed. HTTPS address for ONLYOFFICE Document Server is required.",
        )

    # -- check_api_js --

    def test_check_api_js_passes_when_reachable(self):
        """No error is raised when api.js responds with HTTP 200."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        with patch(f"{VALIDATION}.urlopen", return_value=mock_resp):
            validation_utils.check_api_js("http://docserver/", False, False)

    def test_check_api_js_raises_official_message_when_unreachable(self):
        """An unreachable api.js file raises the exact client-facing ONLYOFFICE message."""
        with patch(f"{VALIDATION}.urlopen", side_effect=ConnectionRefusedError("refused")):
            with self.assertRaises(ValidationError) as ctx:
                validation_utils.check_api_js("http://docserver/", False, False)
        self.assertEqual(str(ctx.exception), "The API JavaScript file cannot be reached.")

    def test_check_api_js_raises_when_status_not_200(self):
        """A non-200 response from api.js is treated as unreachable."""
        mock_resp = MagicMock()
        mock_resp.status = 404
        with patch(f"{VALIDATION}.urlopen", return_value=mock_resp), self.assertRaises(ValidationError) as ctx:
            validation_utils.check_api_js("http://docserver/", False, False)
        self.assertEqual(str(ctx.exception), "The API JavaScript file cannot be reached.")

    def test_check_api_js_creates_ssl_context_when_certificate_disabled_and_https(self):
        """An unverified SSL context is created when certificate check is disabled for an HTTPS URL."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        with patch(f"{VALIDATION}.urlopen", return_value=mock_resp):
            with patch("ssl._create_unverified_context", return_value=MagicMock()) as mock_ssl:
                validation_utils.check_api_js("https://docserver/", False, True)
                mock_ssl.assert_called_once()

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

    # -- check_doc_serv_healthcheck --

    def test_check_doc_serv_healthcheck_passes_when_healthcheck_returns_content(self):
        """No error is raised when the healthcheck endpoint responds with a non-empty body."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"true"
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            validation_utils.check_doc_serv_healthcheck("http://docserver/", False, False)

    def test_check_doc_serv_healthcheck_raises_when_healthcheck_returns_empty_body(self):
        """ValidationError is raised when the healthcheck endpoint returns an empty body."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            with self.assertRaises(ValidationError):
                validation_utils.check_doc_serv_healthcheck("http://docserver/", False, False)

    def test_check_doc_serv_healthcheck_creates_ssl_context_when_certificate_disabled_and_https(self):
        """An unverified SSL context is created when certificate check is disabled for an HTTPS URL."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"true"
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.urlopen", return_value=mock_resp):
            with patch("ssl._create_unverified_context", return_value=MagicMock()) as mock_ssl:
                validation_utils.check_doc_serv_healthcheck("https://docserver/", False, True)
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

    def test_command_service_hides_invalid_token_error_from_client(self):
        """Error code 6 (invalid token) is a request error: masked to the client, logged in full."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 6}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_command_service(
                        self.env, "http://docserver/", "", "Authorization", False, False
                    )
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("Error when trying to check CommandService(Invalid token).", logs.output[0])

    def test_command_service_raises_on_any_nonzero_error_code(self):
        """ValidationError is raised when the command service returns any non-zero error code."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 5}
        with patch("odoo.addons.onlyoffice_odoo.utils.validation_utils.requests.post", return_value=mock_resp):
            with self.assertRaises(ValidationError):
                validation_utils.check_doc_serv_command_service(
                    self.env, "http://docserver/", "", "Authorization", False, False
                )

    # -- check_local_address --

    def test_check_local_address_rejects_loopback(self):
        """A loopback Document Server address is rejected with the explicit local-address message."""
        with patch.dict(network_utils.config.misc, {}, clear=True), self.assertRaises(ValidationError) as ctx:
            validation_utils.check_local_address("http://127.0.0.1:8080/", False)
        self.assertIn("Local and private addresses are not allowed", str(ctx.exception))
        self.assertIn("allow_local_address", str(ctx.exception))

    def test_check_local_address_rejects_private_range(self):
        """A private LAN address is rejected."""
        with patch.dict(network_utils.config.misc, {}, clear=True), self.assertRaises(ValidationError):
            validation_utils.check_local_address("http://192.168.1.100:8080/", False)

    def test_check_local_address_rejects_docker_service_name(self):
        """The default 'documentserver' Docker name resolving to a private address is rejected."""
        with patch.dict(network_utils.config.misc, {}, clear=True):
            with patch(GETADDRINFO, return_value=[(2, 1, 6, "", ("172.18.0.2", 0))]):
                with self.assertRaises(ValidationError):
                    validation_utils.check_local_address("http://documentserver/", False)

    def test_check_local_address_accepts_public_address(self):
        """A public Document Server address passes the local-address check."""
        with patch.dict(network_utils.config.misc, {}, clear=True):
            validation_utils.check_local_address("https://93.184.216.34/", False)

    def test_check_local_address_normalizes_url_without_scheme(self):
        """A bare host without scheme is normalized before the check, like the stored setting."""
        with patch.dict(network_utils.config.misc, {}, clear=True), self.assertRaises(ValidationError):
            validation_utils.check_local_address("10.0.0.5:8080", False)

    def test_check_local_address_logs_rejection(self):
        """The rejected address is written to the server log."""
        with patch.dict(network_utils.config.misc, {}, clear=True):
            with self.assertLogs(validation_utils._logger, level="WARNING") as logs:
                with self.assertRaises(ValidationError):
                    validation_utils.check_local_address("http://127.0.0.1/", False)
        self.assertIn("127.0.0.1", logs.output[0])

    def test_check_local_address_demo_prefix(self):
        """In demo mode the local-address message carries the demo server prefix."""
        with patch.dict(network_utils.config.misc, {}, clear=True), self.assertRaises(ValidationError) as ctx:
            validation_utils.check_local_address("http://127.0.0.1/", True)
        self.assertIn("demo server", str(ctx.exception).lower())

    def test_check_local_address_disabled_by_config_file(self):
        """allow_local_address = True in odoo.conf turns the ban off and lets a local address through."""
        with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": True}}):
            with self.assertLogs(validation_utils._logger, level="INFO") as logs:
                validation_utils.check_local_address("http://127.0.0.1:8080/", False)
        self.assertIn("disabled", logs.output[0])

    # -- settings_validation --

    def _settings(self, public_url, inner_url="", odoo_url="http://odoo.example.com/"):
        settings = self.env["res.config.settings"].create({})
        settings.doc_server_public_url = public_url
        settings.doc_server_inner_url = inner_url
        settings.doc_server_odoo_url = odoo_url
        settings.doc_server_jwt_secret = ""
        settings.doc_server_jwt_header = "Authorization"
        settings.doc_server_disable_certificate = False
        settings.doc_server_demo = False
        return settings

    def test_settings_validation_rejects_local_address_before_any_request(self):
        """A local address is rejected before the healthcheck or any other request is sent."""
        settings = self._settings("http://127.0.0.1:8080/")
        with patch.dict(network_utils.config.misc, {}, clear=True):
            with patch(f"{VALIDATION}.urlopen") as mock_urlopen:
                with patch(f"{VALIDATION}.requests.post") as mock_post:
                    with self.assertRaises(ValidationError):
                        validation_utils.settings_validation(settings)
        mock_urlopen.assert_not_called()
        mock_post.assert_not_called()

    def test_settings_validation_checks_inner_url_when_set(self):
        """The address Odoo connects to is the inner URL, so a local inner URL is rejected."""
        settings = self._settings("https://docs.example.com/", inner_url="http://10.0.0.5/")
        with patch.dict(network_utils.config.misc, {}, clear=True):
            with patch(GETADDRINFO, return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
                with patch(f"{VALIDATION}.urlopen") as mock_urlopen:
                    with self.assertRaises(ValidationError) as ctx:
                        validation_utils.settings_validation(settings)
        self.assertIn("Local and private addresses", str(ctx.exception))
        mock_urlopen.assert_not_called()

    def test_settings_validation_ignores_local_odoo_url(self):
        """The Odoo URL is used by the Document Server, not by Odoo, so a local Odoo URL is fine."""
        settings = self._settings("https://93.184.216.34/", odoo_url="http://odoo:8069/")
        with patch.dict(network_utils.config.misc, {}, clear=True), patch(f"{VALIDATION}.check_mixed_content"):
            with patch(f"{VALIDATION}.check_api_js"), patch(f"{VALIDATION}.check_doc_serv_healthcheck") as mock_health:
                with patch(f"{VALIDATION}.check_doc_serv_command_service"):
                    with patch(f"{VALIDATION}.check_doc_serv_convert_service"):
                        validation_utils.settings_validation(settings)
        mock_health.assert_called_once()

    def test_settings_validation_runs_network_checks_when_ban_disabled(self):
        """With the ban disabled in odoo.conf a local address reaches the regular connection checks."""
        settings = self._settings("http://127.0.0.1:8080/")
        with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": True}}):
            with patch(f"{VALIDATION}.check_api_js"), patch(f"{VALIDATION}.check_doc_serv_healthcheck") as mock_health:
                with patch(f"{VALIDATION}.check_doc_serv_command_service") as mock_command:
                    with patch(f"{VALIDATION}.check_doc_serv_convert_service") as mock_convert:
                        validation_utils.settings_validation(settings)
        mock_health.assert_called_once()
        mock_command.assert_called_once()
        mock_convert.assert_called_once()

    # -- request errors are hidden from the client --

    def test_get_request_error_hides_details_and_logs_them(self):
        """Request errors reach the client as one generic message; the details go to the server log."""
        with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
            with self.assertRaises(ValidationError) as ctx:
                validation_utils.get_request_error("http://10.0.0.5:5432/healthcheck returned false.", False)
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertNotIn("10.0.0.5", str(ctx.exception))
        self.assertIn("10.0.0.5:5432", logs.output[0])

    def test_get_request_error_demo_prefix(self):
        """In demo mode the generic message carries the demo server prefix."""
        with self.assertLogs(validation_utils._logger, level="ERROR"):
            with self.assertRaises(ValidationError) as ctx:
                validation_utils.get_request_error("details", True)
        self.assertIn("demo server", str(ctx.exception).lower())
        self.assertIn(validation_utils.REQUEST_ERROR_MESSAGE, str(ctx.exception))

    def test_check_doc_serv_healthcheck_unreachable_returns_generic_message(self):
        """A connection failure on healthcheck is reported generically; the official message is logged."""
        with patch(f"{VALIDATION}.urlopen", side_effect=ConnectionRefusedError("refused")):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_healthcheck("http://docserver/", False, False)
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("refused", logs.output[0])
        self.assertIn("Document Server cannot be reached.", "\n".join(logs.output))

    def test_check_doc_serv_healthcheck_empty_body_returns_generic_message(self):
        """An empty healthcheck body is reported generically; the official bad-healthcheck message is logged."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        with patch(f"{VALIDATION}.urlopen", return_value=mock_resp):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_healthcheck("http://docserver/", False, False)
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("returned false", logs.output[0])
        self.assertIn("Document Server return bad healthcheck status.", "\n".join(logs.output))

    def test_check_doc_serv_healthcheck_demo_prefix_not_doubled(self):
        """In demo mode the demo prefix appears once, even though the error is raised inside the try block."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = b""
        with patch(f"{VALIDATION}.urlopen", return_value=mock_resp):
            with self.assertLogs(validation_utils._logger, level="ERROR"):
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_healthcheck("http://docserver/", True, False)
        self.assertEqual(str(ctx.exception).count("Demo server error"), 1)

    def test_command_service_nonzero_error_returns_generic_message(self):
        """A non-zero, non-authorization command service error code is hidden behind the generic message."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": 5}
        with patch(f"{VALIDATION}.requests.post", return_value=mock_resp):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_command_service(
                        self.env, "http://docserver/", "", "Authorization", False, False
                    )
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("Error when trying to check CommandService(Command not correct).", logs.output[0])

    def test_command_service_request_failure_returns_generic_message(self):
        """A failed command service request is hidden behind the generic message and logged."""
        with patch(f"{VALIDATION}.requests.post", side_effect=ConnectionError("no route")):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_command_service(
                        self.env, "http://docserver/", "", "Authorization", False, False
                    )
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("no route", logs.output[0])

    def test_convert_service_error_returns_generic_message(self):
        """A conversion service error message is logged and replaced by the generic message."""
        with patch(f"{VALIDATION}.convert", return_value="Document conversion service cannot be reached"):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                with self.assertRaises(ValidationError) as ctx:
                    validation_utils.check_doc_serv_convert_service(
                        self.env, "http://docserver/", "http://odoo/", "", "Authorization", False, False
                    )
        self.assertEqual(str(ctx.exception), validation_utils.REQUEST_ERROR_MESSAGE)
        self.assertIn("Error when trying to check ConvertService", logs.output[0])
        self.assertIn("cannot be reached", logs.output[0])

    def test_convert_logs_request_failure(self):
        """A failed converter request is logged with the exception before the error string is returned."""
        with patch(f"{VALIDATION}.requests.post", side_effect=ConnectionError("timeout")):
            with self.assertLogs(validation_utils._logger, level="ERROR") as logs:
                result = validation_utils.convert(
                    self.env, "http://odoo/test.txt", "http://docserver/", "", "Authorization", False
                )
        self.assertEqual(result, "Connection error")
        self.assertIn("timeout", logs.output[0])

    def test_command_service_error_codes_match_official_messages(self):
        """Each documented CommandService error code maps to the exact ONLYOFFICE message text."""
        expected = {
            1: "Document key is missing or no document with such key could be found",
            2: "Callback url not correct",
            3: "Internal server error",
            4: "No changes were applied to the document before the forcesave command was received",
            5: "Command not correct",
            6: "Invalid token",
        }
        self.assertEqual(validation_utils.COMMAND_SERVICE_ERROR_CODES, expected)
