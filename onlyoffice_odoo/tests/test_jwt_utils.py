# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import jwt

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils


@tagged("post_install", "-at_install")
class TestJwtUtils(TransactionCase):
    """Tests for jwt_utils — JWT token encoding and decoding."""

    def setUp(self):
        super().setUp()
        config_utils.set_jwt_secret(self.env, "test_jwt_secret_key_12345")

    def test_jwt_is_enabled_only_with_a_secret(self):
        self.assertTrue(jwt_utils.is_jwt_enabled(self.env))
        config_utils.set_jwt_secret(self.env, "")
        self.assertFalse(jwt_utils.is_jwt_enabled(self.env))

    def test_decode_returns_the_payload_with_iat_before_exp(self):
        token = jwt_utils.encode_payload(self.env, {"document_id": 123, "action": "edit"})
        decoded = jwt_utils.decode_token(self.env, token)
        self.assertEqual((decoded["document_id"], decoded["action"]), (123, "edit"))
        self.assertGreater(decoded["exp"], decoded["iat"])

    def test_token_signed_with_a_custom_secret_decodes_with_it(self):
        token = jwt_utils.encode_payload(self.env, {"id": 7}, secret="another_secret_xyz")
        self.assertEqual(jwt_utils.decode_token(self.env, token, secret="another_secret_xyz")["id"], 7)

    def test_decode_with_wrong_secret_raises(self):
        token = jwt_utils.encode_payload(self.env, {"id": 1}, secret="correct_secret")
        with self.assertRaises(jwt.exceptions.InvalidSignatureError):
            jwt_utils.decode_token(self.env, token, secret="wrong_secret")
