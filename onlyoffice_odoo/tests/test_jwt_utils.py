# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import jwt

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils


@tagged("post_install", "-at_install")
class TestJwtUtils(TransactionCase):
    """Tests for jwt_utils module — JWT token encoding and decoding."""

    def setUp(self):
        super().setUp()
        # Set a known JWT secret for testing
        self.test_secret = "test_jwt_secret_key_12345"
        config_utils.set_jwt_secret(self.env, self.test_secret)

    # -- is_jwt_enabled --

    def test_jwt_enabled_when_secret_set(self):
        """JWT is enabled when a secret is configured."""
        self.assertTrue(jwt_utils.is_jwt_enabled(self.env))

    def test_jwt_disabled_when_no_secret(self):
        """JWT is disabled when no secret is configured."""
        config_utils.set_jwt_secret(self.env, "")
        self.assertFalse(jwt_utils.is_jwt_enabled(self.env))

    # -- encode_payload --

    def test_encode_payload_returns_string(self):
        """Encoding a payload returns a string token."""
        payload = {"key": "value"}
        token = jwt_utils.encode_payload(self.env, payload)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    def test_encode_payload_with_custom_secret(self):
        """Encoding with a custom secret produces a valid token."""
        payload = {"user_id": 42}
        custom_secret = "custom_secret_abc"
        token = jwt_utils.encode_payload(self.env, payload, secret=custom_secret)
        self.assertIsInstance(token, str)
        self.assertTrue(len(token) > 0)

    # -- decode_token --

    def test_decode_token_returns_payload(self):
        """Decoding a valid token returns the original payload data."""
        payload = {"document_id": 123, "action": "edit"}
        token = jwt_utils.encode_payload(self.env, payload)
        decoded = jwt_utils.decode_token(self.env, token)
        self.assertEqual(decoded["document_id"], 123)
        self.assertEqual(decoded["action"], "edit")

    def test_decode_token_contains_iat_and_exp(self):
        """Decoded token contains 'iat' (issued at) and 'exp' (expiration) claims."""
        payload = {"test": True}
        token = jwt_utils.encode_payload(self.env, payload)
        decoded = jwt_utils.decode_token(self.env, token)
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        # exp must be greater than iat (token expires in the future)
        self.assertGreater(decoded["exp"], decoded["iat"])

    def test_decode_token_with_custom_secret(self):
        """Token encoded with custom secret can be decoded with the same secret."""
        custom_secret = "another_secret_xyz"
        payload = {"id": 7}
        token = jwt_utils.encode_payload(self.env, payload, secret=custom_secret)
        decoded = jwt_utils.decode_token(self.env, token, secret=custom_secret)
        self.assertEqual(decoded["id"], 7)

    def test_decode_token_wrong_secret_raises(self):
        """Decoding a token with wrong secret raises an exception."""
        payload = {"id": 1}
        token = jwt_utils.encode_payload(self.env, payload, secret="correct_secret")
        with self.assertRaises(jwt.exceptions.InvalidSignatureError):
            jwt_utils.decode_token(self.env, token, secret="wrong_secret")

    def test_encode_decode_roundtrip(self):
        """Encode then decode preserves all custom payload fields."""
        payload = {
            "user_id": 5,
            "attachment_id": 100,
            "mode": "edit",
        }
        token = jwt_utils.encode_payload(self.env, payload)
        decoded = jwt_utils.decode_token(self.env, token)
        self.assertEqual(decoded["user_id"], 5)
        self.assertEqual(decoded["attachment_id"], 100)
        self.assertEqual(decoded["mode"], "edit")
