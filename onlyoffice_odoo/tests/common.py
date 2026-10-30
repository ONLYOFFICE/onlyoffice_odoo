# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).
# Shared by the tests of onlyoffice_odoo, onlyoffice_odoo_templates and onlyoffice_odoo_documents.

import json
import os
import re
import unittest
from unittest.mock import MagicMock

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, jwt_utils

INTERNAL_SECRET = "test-internal-secret"


def known_bug(description):
    """Skips a test of a known bug: it keeps the correct expectations. ONLYOFFICE_TEST_STRICT=1 runs it
    (Odoo's test runner counts an expected failure as a failure, so unittest.expectedFailure cannot be used)."""
    return unittest.skipUnless(os.environ.get("ONLYOFFICE_TEST_STRICT"), f"Known bug: {description}")


def ds_response(json_data=None, content=b"", status_code=200):
    """A response of onlyoffice_request: ``json()`` of a Document Server service, ``content`` of a downloaded file."""
    response = MagicMock(status_code=status_code, content=content)
    response.json.return_value = json_data
    return response


class OnlyofficeCase:
    """The Document Server JWT off and the internal secret preset: get_internal_jwt_secret never generates one and
    commits the test transaction. Mix into a TransactionCase or an HttpCase."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config_utils.set_jwt_secret(cls.env, "")
        cls.env["ir.config_parameter"].sudo().set_param(config_constants.INTERNAL_JWT_SECRET, INTERNAL_SECRET)

    def _internal_token(self, payload):
        """A token signed with the internal secret: ``{"id"}`` for oo_security_token, ``{"uid", "document_id"}`` for
        the ODOO_* formula requests of onlyoffice_odoo_documents."""
        return jwt_utils.encode_payload(self.env, payload, INTERNAL_SECRET)

    def _rpc(self, route, /, **params):
        """Body of a JSON-RPC call to a ``type="json"`` route (HttpCase); failures arrive as HTTP 200 with ``error``."""
        body = {"jsonrpc": "2.0", "method": "call", "params": params}
        response = self.url_open(route, data=json.dumps(body), headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200)
        return response.json()

    @staticmethod
    def _editor_config(html):
        """The ``config`` object that the onlyoffice_odoo.onlyoffice_editor page passes to DocsAPI.DocEditor."""
        return json.loads(re.search(r"var config = (.*);\n", html).group(1))
