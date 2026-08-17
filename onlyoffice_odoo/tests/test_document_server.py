# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import os

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils

DOCSERVER_URL = os.environ.get("ONLYOFFICE_TEST_DOCSERVER_URL", "http://documentserver/")


@tagged("post_install", "-at_install", "external_docserver")
class TestOnlyofficeDocumentServer(TransactionCase):
    """Tests against a real ONLYOFFICE Document Server (no mocking).

    Only runs when ONLYOFFICE_TEST_LIVE_DOCSERVER is set (see tests/__init__.py).
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config_utils.set_doc_server_public_url(cls.env, DOCSERVER_URL)
        config_utils.set_doc_server_inner_url(cls.env, DOCSERVER_URL)
        config_utils.set_jwt_secret(cls.env, "")

    # -- Config wiring --

    def test_config_points_to_configured_server(self):
        """The config layer must return the Document Server URL set in setUpClass."""
        self.assertEqual(config_utils.get_doc_server_public_url(self.env), config_utils.fix_url(DOCSERVER_URL))

    # -- GET /healthcheck --

    def test_healthcheck_is_reachable(self):
        """The Document Server /healthcheck endpoint must respond 200 'true'."""
        url = config_utils.get_doc_server_public_url(self.env) + "healthcheck"
        response = onlyoffice_request(url=url, method="get", env=self.env)
        self.assertEqual(response.status_code, 200)
        self.assertIn("true", response.text.lower())

    # -- POST /coauthoring/CommandService.ashx --

    def test_command_service_returns_version(self):
        """CommandService.ashx must answer the 'version' command with a valid JSON payload."""
        url = config_utils.get_doc_server_public_url(self.env) + "coauthoring/CommandService.ashx"
        response = onlyoffice_request(
            url=url,
            method="post",
            opts={
                "json": {"c": "version"},
                "headers": {"Content-Type": "application/json"},
            },
            env=self.env,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("error"), 0)
        self.assertIn("version", data)
