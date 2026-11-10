# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import io
import json
import os
from email.message import Message
from unittest.mock import MagicMock, patch
from urllib import request as urllib_request
from urllib.error import URLError
from urllib.response import addinfourl

from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase, new_test_user

from odoo.addons.onlyoffice_odoo.controllers.main import (
    OnlyofficeConnector,
    _http_urlopen,
    onlyoffice_urlopen,
)
from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils

from .common import INTERNAL_SECRET, OnlyofficeCase

URLOPEN = "odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_urlopen"
DS_SECRET = "ds-secret"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@tagged("post_install", "-at_install")
class ConnectorCase(OnlyofficeCase, HttpCase):
    """An attachment and two internal users: ``editor`` can write everything, ``reader`` sees only its own files."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.editor = new_test_user(cls.env, login="oo_base_editor", groups="base.group_user,base.group_system")
        cls.reader = new_test_user(cls.env, login="oo_base_reader", groups="base.group_user")

    def setUp(self):
        super().setUp()
        self.attachment = self._attachment("test_document.docx")
        self.odoo_url = config_utils.get_base_or_odoo_url(self.env)

    def _attachment(self, name, **vals):
        return self.env["ir.attachment"].create({"name": name, "raw": b"content", **vals})

    def _private_attachment(self):
        """An attachment of a record the reader cannot read (system parameters are for administrators only)."""
        parameter = self.env["ir.config_parameter"].search([], limit=1)
        return self._attachment("private.docx", res_model="ir.config_parameter", res_id=parameter.id)

    def _get_config(self, attachment_id, **params):
        return self._rpc("/onlyoffice/editor/get_config", attachment_id=attachment_id, **params)


@tagged("post_install", "-at_install")
class TestEditorConfig(ConnectorCase):
    """POST /onlyoffice/editor/get_config and GET /onlyoffice/editor/<id>: the config passed to DocsAPI.DocEditor."""

    def test_config_requires_a_session(self):
        self.assertIn("error", self._get_config(self.attachment.id))

    def test_config_of_an_editable_file(self):
        self.authenticate("oo_base_editor", "oo_base_editor")

        config = self._get_config(self.attachment.id)["result"]["editorConfig"]

        attachment = self.attachment
        key = f"{attachment.id}{attachment.checksum}"
        self.assertEqual(config["documentType"], "word")
        self.assertEqual(config["document"]["title"], "test_document.docx")
        self.assertEqual((config["document"]["fileType"], config["document"]["key"]), ("docx", key))
        file_url = f"{self.odoo_url}onlyoffice/file/content/{attachment.id}?oo_security_token="
        self.assertTrue(config["document"]["url"].startswith(file_url))
        self.assertTrue(config["document"]["url"].endswith(f"&shardkey={key}"))
        token = config["document"]["url"].split("oo_security_token=")[1].split("&")[0]
        self.assertEqual(jwt_utils.decode_token(self.env, token, INTERNAL_SECRET)["id"], self.editor.id)
        editor = config["editorConfig"]
        self.assertEqual((editor["mode"], config["document"]["permissions"]), ("edit", {"edit": True}))
        self.assertTrue(editor["callbackUrl"].startswith(f"{self.odoo_url}onlyoffice/editor/callback/{attachment.id}?"))
        self.assertEqual(editor["user"], {"id": str(self.editor.id), "name": self.editor.name})
        self.assertNotIn("token", config)

    def test_config_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, DS_SECRET)
        self.authenticate("oo_base_editor", "oo_base_editor")

        config = self._get_config(self.attachment.id)["result"]["editorConfig"]

        signed = jwt_utils.decode_token(self.env, config.pop("token"), DS_SECRET)
        self.assertEqual(signed["document"], config["document"])
        self.assertEqual(signed["editorConfig"], config["editorConfig"])

    def test_view_only_formats_open_without_callback(self):
        self.authenticate("oo_base_editor", "oo_base_editor")
        config = self._get_config(self._attachment("notes.rtf").id)["result"]["editorConfig"]
        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertNotIn("callbackUrl", config["editorConfig"])

    def test_editor_opens_a_file_of_a_read_only_record_for_viewing(self):
        # The user can read the company (and its attachments) but not write it: no edit mode, no callback.
        attachment = self._attachment("company.docx", res_model="res.company", res_id=self.env.company.id)
        self.authenticate("oo_base_reader", "oo_base_reader")

        config = self._get_config(attachment.id)["result"]["editorConfig"]
        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertNotIn("callbackUrl", config["editorConfig"])
        page = self.url_open(f"/onlyoffice/editor/{attachment.id}").text
        self.assertNotIn("/onlyoffice/editor/callback/", page)

    def test_missing_attachment_and_unsupported_format(self):
        gone = self._attachment("gone.docx")
        gone_id = gone.id
        gone.unlink()
        self.authenticate("oo_base_editor", "oo_base_editor")
        # get_config returns request.not_found() from a JSON route, which arrives as a "404 ..." string result.
        self.assertTrue(self._get_config(gone_id)["result"].startswith("404"))
        self.assertIn("error", self._get_config(self._attachment("archive.zip").id))

    def test_editor_page_passes_the_config_and_loads_the_document_server_api(self):
        self.authenticate("oo_base_editor", "oo_base_editor")

        response = self.url_open(f"/onlyoffice/editor/{self.attachment.id}")

        self.assertEqual(response.status_code, 200)
        config = self._editor_config(response.text)
        self.assertEqual((config["document"]["title"], config["editorConfig"]["mode"]), ("test_document.docx", "edit"))
        self.assertEqual(config["type"], "desktop")
        api = f"{config_utils.get_doc_server_public_url(self.env)}web-apps/apps/api/documents/api.js?shardkey="
        self.assertIn(api, response.text)

    def test_editor_page_on_a_phone_uses_the_mobile_editor(self):
        self.authenticate("oo_base_editor", "oo_base_editor")
        response = self.url_open(
            f"/onlyoffice/editor/{self.attachment.id}", headers={"User-Agent": "Mozilla/5.0 (iPhone) Mobile Safari"}
        )
        self.assertEqual(self._editor_config(response.text)["type"], "mobile")

    def test_editor_page_is_forbidden_to_visitors_and_other_users(self):
        private = self._private_attachment()
        self.authenticate("oo_base_reader", "oo_base_reader")
        self.assertEqual(self.url_open(f"/onlyoffice/editor/{private.id}", allow_redirects=False).status_code, 403)
        self.authenticate(None, None)
        response = self.url_open(f"/onlyoffice/editor/{self.attachment.id}", allow_redirects=False)
        self.assertEqual(response.status_code, 403)

    def test_access_token_opens_a_shared_attachment(self):
        private = self._private_attachment()
        access_token = private.generate_access_token()[0]
        self.authenticate("oo_base_reader", "oo_base_reader")

        response = self.url_open(f"/onlyoffice/editor/{private.id}?access_token={access_token}")

        self.assertEqual(response.status_code, 200)
        config = self._editor_config(response.text)
        self.assertIn(f"&access_token={access_token}", config["document"]["url"])
        # The token only lets the user read the file.
        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertNotIn("callbackUrl", config["editorConfig"])

    def test_wrong_access_token_is_refused(self):
        private = self._private_attachment()
        private.generate_access_token()
        self.authenticate("oo_base_reader", "oo_base_reader")
        response = self.url_open(f"/onlyoffice/editor/{private.id}?access_token=wrong", allow_redirects=False)
        self.assertEqual(response.status_code, 403)

    def test_file_name_is_cleaned_of_markup(self):
        connector = OnlyofficeConnector()
        self.assertEqual(connector.filter_xss("My Report 2024-Q1.docx"), "My Report 2024-Q1.docx")
        self.assertEqual(connector.filter_xss("<script>alert('x')</script>a.docx"), "scriptalertxscripta.docx")


@tagged("post_install", "-at_install")
class TestFileContent(ConnectorCase):
    """GET /onlyoffice/file/content/<id>: the Document Server downloads the file as the user of the token."""

    def _content(self, attachment, user=None, headers=None, **params):
        query = {"oo_security_token": self._internal_token({"id": (user or self.editor).id}), **params}
        url = f"/onlyoffice/file/content/{attachment.id}?" + "&".join(f"{k}={v}" for k, v in query.items())
        return self.url_open(url, headers=headers, allow_redirects=False)

    def test_file_is_served_to_the_token_user(self):
        response = self._content(self.attachment)
        self.assertEqual((response.status_code, response.content), (200, b"content"))

    def test_file_needs_a_valid_token_of_a_user_who_can_read_it(self):
        forged = jwt_utils.encode_payload(self.env, {"id": self.editor.id}, "another-secret")
        cases = {
            "no token": self.url_open(f"/onlyoffice/file/content/{self.attachment.id}", allow_redirects=False),
            "forged token": self.url_open(
                f"/onlyoffice/file/content/{self.attachment.id}?oo_security_token={forged}", allow_redirects=False
            ),
            "user without access": self._content(self._private_attachment(), user=self.reader),
        }
        for case, response in cases.items():
            with self.subTest(case=case):
                self.assertNotEqual(response.status_code, 200)
                self.assertNotEqual(response.content, b"content")

    def test_document_server_must_sign_the_request_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, DS_SECRET)
        signed = jwt_utils.encode_payload(self.env, {"url": "any"}, DS_SECRET)
        forged = jwt_utils.encode_payload(self.env, {"url": "any"}, "another-secret")

        self.assertEqual(self._content(self.attachment).status_code, 403)
        self.assertEqual(
            self._content(self.attachment, headers={"Authorization": f"Bearer {signed}"}).content, b"content"
        )
        self.assertNotEqual(
            self._content(self.attachment, headers={"Authorization": f"Bearer {forged}"}).status_code, 200
        )

    def test_access_token_lets_the_document_server_download_a_shared_attachment(self):
        private = self._private_attachment()
        access_token = private.generate_access_token()[0]
        response = self._content(private, user=self.reader, access_token=access_token)
        self.assertEqual((response.status_code, response.content), (200, b"content"))

    def test_connection_check_file_is_public(self):
        response = self.url_open("/onlyoffice/file/content/test.txt")
        self.assertEqual((response.status_code, response.text), (200, "test"))


@tagged("post_install", "-at_install")
class TestEditorCallback(ConnectorCase):
    """POST /onlyoffice/editor/callback/<id>: the Document Server reports a saved file; its download is mocked."""

    def _callback(self, body, token=None, headers=None, saved=b"edited content"):
        downloaded = MagicMock()
        downloaded.read.return_value = saved
        token = token if token is not None else self._internal_token({"id": self.editor.id})
        with patch(URLOPEN, return_value=downloaded) as urlopen:
            response = self.url_open(
                f"/onlyoffice/editor/callback/{self.attachment.id}?oo_security_token={token}",
                data=json.dumps(body),
                headers={"Content-Type": "application/json", **(headers or {})},
            )
        return response, urlopen

    def _raw(self):
        self.env.invalidate_all()
        return self.attachment.raw.content

    def test_ready_and_corrupted_files_are_saved(self):
        for status in (2, 3):
            with self.subTest(status=status):
                response, urlopen = self._callback(
                    {"status": status, "url": "http://documentserver/cache/out.docx"}, saved=f"v{status}".encode()
                )
                self.assertEqual((response.status_code, response.json()), (200, {"error": 0}))
                self.assertEqual(self._raw(), f"v{status}".encode())
                self.assertEqual(urlopen.call_args.args[0], "http://documentserver/cache/out.docx")
                self.assertEqual(self.attachment.mimetype, DOCX_MIME)

    def test_other_statuses_change_nothing(self):
        for status in (1, 4, 6, 7):
            with self.subTest(status=status):
                response, urlopen = self._callback({"status": status})
                self.assertEqual(response.json(), {"error": 0})
                urlopen.assert_not_called()
                self.assertEqual(self._raw(), b"content")

    def test_saved_file_is_downloaded_from_the_inner_address(self):
        config_utils.set_doc_server_public_url(self.env, "https://docs.example.com/")
        config_utils.set_doc_server_inner_url(self.env, "http://documentserver/")

        _response, urlopen = self._callback({"status": 2, "url": "https://docs.example.com/cache/out.docx"})

        self.assertEqual(urlopen.call_args.args[0], "http://documentserver/cache/out.docx")

    def test_callback_needs_a_valid_security_token(self):
        forged = jwt_utils.encode_payload(self.env, {"id": self.editor.id}, "another-secret")
        for case, token in {"no token": "", "forged": forged}.items():
            with self.subTest(case=case):
                response, _urlopen = self._callback({"status": 2, "url": "http://ds/out.docx"}, token=token)
                self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
                self.assertEqual(self._raw(), b"content")

    def test_access_token_does_not_let_a_user_save_a_file_they_cannot_write(self):
        private = self._private_attachment()
        access_token = private.generate_access_token()[0]
        token = self._internal_token({"id": self.reader.id})
        with patch(URLOPEN) as urlopen:
            response = self.url_open(
                f"/onlyoffice/editor/callback/{private.id}?oo_security_token={token}&access_token={access_token}",
                data=json.dumps({"status": 2, "url": "http://documentserver/cache/out.docx"}),
                headers={"Content-Type": "application/json"},
            )

        self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
        urlopen.assert_not_called()
        self.env.invalidate_all()
        self.assertEqual(private.raw.content, b"content")

    def test_signed_body_or_header_is_accepted_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, DS_SECRET)
        body = {"status": 2, "url": "http://documentserver/cache/out.docx"}
        in_body = {"token": jwt_utils.encode_payload(self.env, body, DS_SECRET)}
        in_header = {"Authorization": "Bearer " + jwt_utils.encode_payload(self.env, {"payload": body}, DS_SECRET)}

        for case, (sent, headers) in {"body": (in_body, None), "header": ({}, in_header)}.items():
            with self.subTest(case=case):
                response, _urlopen = self._callback(sent, headers=headers, saved=case.encode())
                self.assertEqual(response.json(), {"error": 0})
                self.assertEqual(self._raw(), case.encode())

    def test_unsigned_or_forged_callback_is_rejected_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, DS_SECRET)
        body = {"status": 2, "url": "http://documentserver/cache/out.docx"}
        forged = {"token": jwt_utils.encode_payload(self.env, body, "another-secret")}
        for case, sent in {"unsigned": body, "forged": forged}.items():
            with self.subTest(case=case):
                response, urlopen = self._callback(sent)
                self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
                urlopen.assert_not_called()

    def test_user_without_write_access_cannot_save(self):
        private = self._private_attachment()
        token = self._internal_token({"id": self.reader.id})
        downloaded = MagicMock()
        downloaded.read.return_value = b"overwritten"
        with patch(URLOPEN, return_value=downloaded):
            response = self.url_open(
                f"/onlyoffice/editor/callback/{private.id}?oo_security_token={token}",
                data=json.dumps({"status": 2, "url": "http://ds/out.docx"}),
                headers={"Content-Type": "application/json"},
            )
        self.assertEqual(response.json()["error"], 1)
        self.env.invalidate_all()
        self.assertEqual(private.raw.content, b"content")


@tagged("post_install", "-at_install")
class TestPreview(ConnectorCase):
    """GET /onlyoffice/preview: a read-only viewer of any file URL (form gallery, template print dialog)."""

    def _config(self, url, title="Form.pdf"):
        response = self.url_open(f"/onlyoffice/preview?url={url}&title={title}")
        self.assertEqual(response.status_code, 200)
        return self._editor_config(response.text)

    def test_visitor_is_sent_to_the_login(self):
        response = self.url_open(
            "/onlyoffice/preview?url=https://docs.example.com/a.pdf&title=a.pdf", allow_redirects=False
        )
        self.assertIn(response.status_code, (302, 303))

    def test_external_file_opens_read_only(self):
        self.authenticate("oo_base_reader", "oo_base_reader")

        config = self._config("https://forms.example/lease.pdf")

        self.assertEqual(config["type"], "embedded")
        self.assertEqual(config["document"]["url"], "https://forms.example/lease.pdf")
        self.assertEqual((config["document"]["title"], config["document"]["fileType"]), ("Form.pdf", "pdf"))
        self.assertEqual((config["editorConfig"]["mode"], config["document"]["permissions"]), ("view", {"edit": False}))

    def test_file_of_this_odoo_gets_the_user_token(self):
        self.authenticate("oo_base_reader", "oo_base_reader")

        url = self._config(f"/onlyoffice/file/content/{self.attachment.id}")["document"]["url"]

        prefix = f"{self.odoo_url}onlyoffice/file/content/{self.attachment.id}?oo_security_token="
        self.assertTrue(url.startswith(prefix))
        self.assertEqual(jwt_utils.decode_token(self.env, url[len(prefix) :], INTERNAL_SECRET)["id"], self.reader.id)


@tagged("post_install", "-at_install")
class TestOnlyofficeUrlopen(TransactionCase):
    """Downloads of Document Server files: HTTP only, redirects included, through the proxy of the environment."""

    @staticmethod
    def _answer(url, code, body=b"", location=None):
        headers = Message()
        if location:
            headers["Location"] = location
        answer = addinfourl(io.BytesIO(body), headers, url, code)
        answer.msg = "Found" if location else "OK"
        return answer

    def test_redirect_only_to_http(self):
        url = "http://documentserver/cache/file.docx"
        # urllib itself follows a redirect to "ftp://" and refuses one to "file://".
        for location, error in (("ftp://attacker.com/file.docx", ValueError), ("file:///etc/passwd", URLError)):
            with patch.object(
                urllib_request.HTTPHandler, "http_open", return_value=self._answer(url, 302, location=location)
            ):
                with self.assertRaises(error, msg=location):
                    onlyoffice_urlopen(url, env=self.env)
        other = "http://documentserver/cache/other.docx"
        answers = [self._answer(url, 302, location=other), self._answer(other, 200, b"file")]
        with patch.object(urllib_request.HTTPHandler, "http_open", side_effect=answers) as http_open:
            self.assertEqual(onlyoffice_urlopen(url, env=self.env).read(), b"file")
        self.assertEqual(http_open.call_args.args[0].full_url, other)

    def test_refuses_not_http_addresses(self):
        for url in ("file:///etc/passwd", "ftp://attacker.com/file.docx"):
            with self.assertRaises(ValueError, msg=url):
                onlyoffice_urlopen(url, env=self.env)
        # The opener itself has no handlers of other schemes, also with proxies of them in the environment (the proxy
        # answers, so an address sent to it would open).
        proxies = {"ftp_proxy": "http://proxy.example:3128", "all_proxy": "http://proxy.example:3128"}
        proxy_answer = self._answer("http://proxy.example:3128/", 200, b"secret")
        with (
            patch.dict(os.environ, proxies),
            patch.object(urllib_request.HTTPHandler, "http_open", return_value=proxy_answer),
        ):
            for url in ("file:///etc/passwd", "ftp://attacker.com/file.docx", "data:text/plain,secret"):
                with self.assertRaises(URLError, msg=url):
                    _http_urlopen(url, timeout=5)

    def test_uses_the_proxy_of_the_environment(self):
        proxy = {"http_proxy": "http://proxy.example:3128", "no_proxy": "", "NO_PROXY": ""}
        with (
            patch.dict(os.environ, proxy),
            patch.object(urllib_request.HTTPHandler, "http_open", side_effect=URLError("stop")) as http_open,
        ):
            with self.assertRaises(URLError):
                onlyoffice_urlopen("http://documentserver.example/cache/file.docx", env=self.env)
        self.assertEqual(http_open.call_args.args[0].host, "proxy.example:3128")
