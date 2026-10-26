# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import os

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, validation_utils

DOCSERVER_URL = os.environ.get("ONLYOFFICE_TEST_DOCSERVER_URL", "http://documentserver/")
# The JWT secret of that Document Server: empty in test.yml (JWT_ENABLED=false), the e2e secret on the e2e stack.
DOCSERVER_JWT_SECRET = os.environ.get("ONLYOFFICE_TEST_DOCSERVER_JWT_SECRET", "")


@tagged("post_install", "-at_install", "-standard", "external_docserver")
class TestOnlyofficeDocumentServer(TransactionCase):
    """Tests against a real ONLYOFFICE Document Server (no mocking).

    Only runs when ONLYOFFICE_TEST_LIVE_DOCSERVER is set (see tests/__init__.py).

    The "-standard" tag is required so Odoo's BaseCase does not patch
    requests.Session.send to block external HTTP calls: these tests
    deliberately hit a real Document Server over the network.
    The Document Server cannot call back into Odoo here (no HTTP server in a TransactionCase): conversions and
    saving are covered by the Playwright tests in e2e/.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config_utils.set_doc_server_public_url(cls.env, DOCSERVER_URL)
        config_utils.set_doc_server_inner_url(cls.env, DOCSERVER_URL)
        config_utils.set_jwt_secret(cls.env, DOCSERVER_JWT_SECRET)

    def test_healthcheck_is_reachable(self):
        url = config_utils.get_doc_server_public_url(self.env) + "healthcheck"
        response = onlyoffice_request(url=url, method="get", env=self.env)
        self.assertEqual((response.status_code, response.text.lower()), (200, "true"))

    def test_settings_checks_pass(self):
        """The healthcheck and the CommandService checks of the Settings save, signed when the server uses JWT."""
        url = config_utils.get_doc_server_public_url(self.env)
        validation_utils.check_doc_serv_url(url, False, False)
        validation_utils.check_doc_serv_command_service(
            self.env, url, DOCSERVER_JWT_SECRET, config_utils.get_jwt_header(self.env), False, False
        )

    def test_command_service_rejects_a_wrong_jwt_secret(self):
        if not DOCSERVER_JWT_SECRET:
            self.skipTest("this Document Server does not use JWT")
        url = config_utils.get_doc_server_public_url(self.env)
        with self.assertRaisesRegex(ValidationError, "Authorization error"):
            validation_utils.check_doc_serv_command_service(
                self.env, url, "wrong-secret", "Authorization", False, False
            )
