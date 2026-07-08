# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import validation_utils


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
        msg = validation_utils.get_conversion_error_message(-1)
        self.assertEqual(msg, "Unknown error")

    def test_error_message_undefined_code(self):
        """Unrecognized error code returns the fallback 'Undefined error code' message."""
        msg = validation_utils.get_conversion_error_message(-99)
        self.assertEqual(msg, "Undefined error code")

    def test_all_defined_error_codes_return_message(self):
        """Every error code defined by the ONLYOFFICE conversion API returns a non-empty string."""
        defined_codes = [-1, -2, -3, -4, -5, -6, -7, -8]
        for code in defined_codes:
            msg = validation_utils.get_conversion_error_message(code)
            self.assertIsInstance(msg, str, f"Code {code} must return a string")
            self.assertTrue(len(msg) > 0, f"Code {code} must return a non-empty message")
