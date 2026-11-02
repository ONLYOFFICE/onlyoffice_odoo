# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import MagicMock, patch

import requests

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request, onlyoffice_urlopen
from odoo.addons.onlyoffice_odoo.utils import config_utils

from .common import known_bug

MAIN = "odoo.addons.onlyoffice_odoo.controllers.main"


@tagged("post_install", "-at_install")
class TestOnlyofficeRequest(TransactionCase):
    """onlyoffice_request / onlyoffice_urlopen: every request of Odoo to the Document Server goes through them."""

    def setUp(self):
        super().setUp()
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com/")
        config_utils.set_doc_server_inner_url(self.env, "http://documentserver/")

    def _request(self, method="get", url="https://docs.example.com/healthcheck", opts=None, response=None):
        response = response or MagicMock(status_code=200)
        with (
            patch(f"{MAIN}.requests.get", return_value=response) as get,
            patch(f"{MAIN}.requests.post", return_value=response) as post,
        ):
            result = onlyoffice_request(url=url, method=method, opts=opts, env=self.env)
        return result, get, post

    def test_requests_go_to_the_inner_address_with_a_default_timeout(self):
        result, get, post = self._request()

        post.assert_not_called()
        self.assertEqual(get.call_args.args, ("http://documentserver/healthcheck",))
        self.assertEqual(get.call_args.kwargs, {"timeout": 120})
        self.assertIs(result, get.return_value)

    def test_post_passes_its_options_and_own_timeout(self):
        _result, get, post = self._request("post", opts={"json": {"c": "version"}, "timeout": 5})

        get.assert_not_called()
        self.assertEqual(post.call_args.kwargs, {"timeout": 5, "json": {"c": "version"}})

    def test_certificate_check_is_disabled_only_for_https_when_asked(self):
        config_utils.set_doc_server_inner_url(self.env, "")
        config_utils.set_certificate_verify_disabled(self.env, True)
        cases = {
            "https": ("https://docs.example.com/x", None, False),
            "explicit verify kept": ("https://docs.example.com/x", {"verify": "/ca.pem"}, "/ca.pem"),
            "http": ("http://other.example.com/x", None, None),
        }
        for case, (url, opts, verify) in cases.items():
            with self.subTest(case=case):
                _result, get, _post = self._request(url=url, opts=opts)
                self.assertEqual(get.call_args.kwargs.get("verify"), verify)

    def test_failures_are_raised_with_the_request(self):
        refused = MagicMock(status_code=500)
        refused.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        with self.assertRaisesRegex(requests.exceptions.RequestException, "failed to GET http://documentserver/"):
            self._request(response=refused)

        with (
            patch(f"{MAIN}.requests.get", side_effect=ValueError("bad")),
            self.assertRaisesRegex(requests.exceptions.RequestException, "Unexpected error .* GET .*: bad"),
        ):
            onlyoffice_request(url="https://docs.example.com/x", method="get", env=self.env)

    @known_bug("a failed request logs its options, including the JWT of the Authorization header")
    def test_failed_request_does_not_log_the_jwt(self):
        refused = MagicMock(status_code=500)
        refused.raise_for_status.side_effect = requests.exceptions.HTTPError("500 Server Error")
        opts = {"headers": {"Authorization": "Bearer secret.jwt.token"}, "json": {"token": "secret.jwt.token"}}
        with self.assertLogs(MAIN, level="ERROR") as logs, self.assertRaises(requests.exceptions.RequestException):
            self._request(opts=opts, response=refused)
        self.assertNotIn("secret.jwt.token", "\n".join(logs.output))

    def test_urlopen_uses_the_inner_address_and_the_certificate_setting(self):
        cases = {
            "verified": (False, "https://docs.example.com/cache/a.docx", "http://documentserver/cache/a.docx", None),
            "unverified https": (True, "https://files.example.com/a.docx", "https://files.example.com/a.docx", "ctx"),
        }
        for case, (disabled, url, expected_url, context) in cases.items():
            with (
                self.subTest(case=case),
                patch(f"{MAIN}.urlopen") as urlopen,
                patch(f"{MAIN}.ssl._create_unverified_context", return_value="ctx"),
            ):
                config_utils.set_certificate_verify_disabled(self.env, disabled)
                onlyoffice_urlopen(url, env=self.env)
                self.assertEqual(urlopen.call_args.args, (expected_url,))
                self.assertEqual(urlopen.call_args.kwargs, {"timeout": 120, "context": context})
