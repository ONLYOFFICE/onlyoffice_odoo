# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, url_utils


@tagged("post_install", "-at_install")
class TestUrlUtils(TransactionCase):
    """Tests for url_utils module тАФ replacing public URL with internal URL."""

    def setUp(self):
        super().setUp()
        # Set known URLs for testing
        self.public_url = "https://docs.example.com/"
        self.inner_url = "http://docserver-internal:8080/"
        config_utils.set_doc_server_public_url(self.env, self.public_url)

    # -- replace_public_url_to_internal --

    def test_replace_url_when_inner_url_configured(self):
        """Public URL in a string is replaced with internal URL when configured."""
        config_utils.set_doc_server_inner_url(self.env, self.inner_url)
        input_url = "https://docs.example.com/web-apps/apps/api/documents/api.js"
        result = url_utils.replace_public_url_to_internal(self.env, input_url)
        self.assertEqual(result, "http://docserver-internal:8080/web-apps/apps/api/documents/api.js")

    def test_no_replace_when_inner_url_same_as_public(self):
        """URL is unchanged when inner URL equals public URL."""
        config_utils.set_doc_server_inner_url(self.env, self.public_url)
        input_url = "https://docs.example.com/healthcheck"
        result = url_utils.replace_public_url_to_internal(self.env, input_url)
        self.assertEqual(result, input_url)

    def test_no_replace_when_inner_url_not_configured(self):
        """URL is unchanged when inner URL is not configured (falls back to public)."""
        self.env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_INNER_URL, "")
        input_url = "https://docs.example.com/some/path"
        result = url_utils.replace_public_url_to_internal(self.env, input_url)
        self.assertEqual(result, input_url)

    def test_replace_preserves_unrelated_urls(self):
        """URLs not matching public URL are left unchanged."""
        config_utils.set_doc_server_inner_url(self.env, self.inner_url)
        input_url = "https://other-server.com/api/endpoint"
        result = url_utils.replace_public_url_to_internal(self.env, input_url)
        self.assertEqual(result, input_url)

    def test_replace_url_ip_with_port(self):
        """DocServer on a bare IP+port (common in LAN): public and internal are different IPs."""
        config_utils.set_doc_server_public_url(self.env, "http://192.168.1.100:8080")
        config_utils.set_doc_server_inner_url(self.env, "http://10.0.0.5:8080")
        callback_url = "http://192.168.1.100:8080/cache/files/output.docx"
        result = url_utils.replace_public_url_to_internal(self.env, callback_url)
        self.assertEqual(result, "http://10.0.0.5:8080/cache/files/output.docx")

    def test_replace_url_reverse_proxy_path_prefix(self):
        """DocServer behind a reverse proxy with a path prefix: sub-path URLs are rewritten correctly."""
        config_utils.set_doc_server_public_url(self.env, "https://company.com/onlyoffice")
        config_utils.set_doc_server_inner_url(self.env, "http://192.168.0.10:8080")
        callback_url = "https://company.com/onlyoffice/cache/files/convert/output.docx"
        result = url_utils.replace_public_url_to_internal(self.env, callback_url)
        self.assertEqual(result, "http://192.168.0.10:8080/cache/files/convert/output.docx")

    def test_replace_url_in_docserver_callback_url(self):
        """Replacement works on a realistic DocServer callback file URL with a versioned path."""
        config_utils.set_doc_server_inner_url(self.env, self.inner_url)
        docserver_url = "https://docs.example.com/cache/files/5.0/convert_abc123/output.docx"
        result = url_utils.replace_public_url_to_internal(self.env, docserver_url)
        self.assertEqual(result, "http://docserver-internal:8080/cache/files/5.0/convert_abc123/output.docx")
