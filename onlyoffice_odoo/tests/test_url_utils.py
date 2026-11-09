# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, url_utils


@tagged("post_install", "-at_install")
class TestUrlUtils(TransactionCase):
    """Tests for url_utils module — replacing public URL with internal URL."""

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
        self.env["ir.config_parameter"].sudo().set_str(config_constants.DOC_SERVER_INNER_URL, "")
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


class _Answer:
    """A streamed ``requests`` answer."""

    def __init__(self, status_code=200, chunks=(b"form",)):
        self.status_code = status_code
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_content(self, chunk_size=None):
        return iter(self.chunks)


@tagged("post_install", "-at_install")
class TestFormFileUrl(TransactionCase):
    """Only files of the form gallery, or of a mirror set by an administrator, are downloaded for a user."""

    GALLERY_FILE = "https://static-oforms.onlyoffice.com/uploads/form.docx"

    def _set_mirror(self, url):
        self.env["ir.config_parameter"].sudo().set_param(config_constants.FORM_FILES_URL, url)

    def test_check_download_url(self):
        for url in ("http://documentserver/cache/file.docx", "https://docs.example.com/file.docx"):
            self.assertEqual(url_utils.check_download_url(url), url)
        for url in ("file:///etc/passwd", "ftp://host/file.docx", "data:text/plain,x", "", None, "/cache/file.docx"):
            with self.assertRaises(ValueError, msg=url):
                url_utils.check_download_url(url)

    def test_gallery_files(self):
        self.assertTrue(url_utils.is_form_file_url(self.GALLERY_FILE, self.env))
        self.assertTrue(url_utils.is_form_file_url("https://STATIC-OFORMS.onlyoffice.com:443/form.pdf", self.env))
        for url in (
            "http://static-oforms.onlyoffice.com/form.docx",
            "https://static-oforms.onlyoffice.com:8443/form.docx",
            "https://static-oforms.onlyoffice.com.attacker.com/form.docx",
            "https://static-oforms.onlyoffice.com@attacker.com/form.docx",
            "https://user:pass@static-oforms.onlyoffice.com/form.docx",
            "https://attacker.com/static-oforms.onlyoffice.com/form.docx",
            "http://localhost:8069/web/content/1",
            "file:///etc/passwd",
            "",
            None,
        ):
            self.assertFalse(url_utils.is_form_file_url(url, self.env), url)

    def test_mirror_folder(self):
        self.assertFalse(url_utils.is_form_file_url("https://forms.company.com/forms/a.docx", self.env))
        self._set_mirror("https://forms.company.com/forms/")
        for url in ("https://forms.company.com/forms/a.docx", "https://forms.company.com:443/forms/sub/a.pdf"):
            self.assertTrue(url_utils.is_form_file_url(url, self.env), url)
        for url in (
            "https://forms.company.com.attacker.com/forms/a.docx",
            "https://forms.company.com@attacker.com/forms/a.docx",
            "https://user@forms.company.com/forms/a.docx",
            "http://forms.company.com/forms/a.docx",
            "https://forms.company.com:8443/forms/a.docx",
            "https://forms.company.com/forms-evil/a.docx",
            "https://forms.company.com/forms",
            "https://forms.company.com/admin/a.docx",
            "https://forms.company.com/forms/../admin/a.docx",
            "https://forms.company.com/forms/..;/admin/a.docx",
            "https://forms.company.com/forms/%2e%2e/admin/a.docx",
            "https://forms.company.com/forms/..%5cadmin/a.docx",
        ):
            self.assertFalse(url_utils.is_form_file_url(url, self.env), url)

    def test_mirror_without_path_and_wrong_mirror(self):
        self._set_mirror("http://localhost:8069")
        self.assertTrue(url_utils.is_form_file_url("http://localhost:8069/forms/a.docx", self.env))
        self.assertFalse(url_utils.is_form_file_url("http://localhost:8070/forms/a.docx", self.env))
        for mirror in ("ftp://forms.company.com/", "https://admin@forms.company.com/", "forms.company.com"):
            self._set_mirror(mirror)
            self.assertFalse(url_utils.is_form_file_url("https://forms.company.com/a.docx", self.env), mirror)

    def test_download_refuses_other_addresses_without_a_request(self):
        with patch.object(url_utils.requests, "get") as get:
            for url in ("http://127.0.0.1:8069/web/content/1", "file:///etc/passwd"):
                with self.assertRaises(ValueError):
                    url_utils.download_form_file(url, self.env)
        get.assert_not_called()

    def test_download_takes_only_the_file(self):
        with patch.object(url_utils.requests, "get", return_value=_Answer(chunks=(b"for", b"m"))) as get:
            self.assertEqual(url_utils.download_form_file(self.GALLERY_FILE, self.env), b"form")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        for status in (301, 302, 307, 404, 500):
            with patch.object(url_utils.requests, "get", return_value=_Answer(status_code=status)):
                with self.assertRaises(ValueError, msg=status):
                    url_utils.download_form_file(self.GALLERY_FILE, self.env)

    def test_download_stops_on_a_big_file(self):
        chunk = b"x" * (1024 * 1024)
        chunks = [chunk] * (url_utils.FORM_FILE_MAX_SIZE // len(chunk) + 1)
        with patch.object(url_utils.requests, "get", return_value=_Answer(chunks=chunks)):
            with self.assertRaises(ValueError):
                url_utils.download_form_file(self.GALLERY_FILE, self.env)
