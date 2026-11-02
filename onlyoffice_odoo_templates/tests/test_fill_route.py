# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import io
import zipfile
from unittest.mock import patch
from urllib.parse import quote

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user

from odoo.addons.onlyoffice_odoo.tests.common import known_bug
from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils

from .common import TemplatesCase, bundled_pdf, ds_response

REQUEST = "odoo.addons.onlyoffice_odoo_templates.controllers.controllers.onlyoffice_request"
DOCBUILDER = "http://documentserver/docbuilder"


@tagged("post_install", "-at_install")
class TestFillRoute(TemplatesCase, HttpCase):
    """GET /onlyoffice/template/fill: the print dialog's download; the docbuilder service is mocked."""

    def setUp(self):
        super().setUp()
        self.template = self._template()
        self.ann, self.bob = self.env["res.partner"].create([{"name": "Ann"}, {"name": "Bob"}])
        self.authenticate("oo_tpl_user", "oo_tpl_user")

    def _fill(self, records, files, docbuilder=None):
        """Prints ``records``; the docbuilder answers with ``files`` {name: content, or the HTTP status of a failed
        download}. Returns the response and the calls to the Document Server."""
        urls = {name: f"http://documentserver/cache/out{index}.pdf" for index, name in enumerate(files)}
        downloads = {url: files[name] for name, url in urls.items()}
        calls = []

        def onlyoffice_request(url, method, opts=None, env=None):
            calls.append({"url": url, "method": method, "opts": opts})
            if url == DOCBUILDER:
                return docbuilder or ds_response({"end": True, "urls": urls})
            result = downloads[url]
            return ds_response(status_code=result) if isinstance(result, int) else ds_response(content=result)

        record_ids = ",".join(str(record.id) for record in records)
        with patch(REQUEST, side_effect=onlyoffice_request):
            response = self.url_open(
                f"/onlyoffice/template/fill?template_id={self.template.id}&record_ids={record_ids}"
            )
        return response, calls

    def test_one_record_downloads_its_pdf(self):
        response, calls = self._fill(self.ann, {"Partner Card - Ann.pdf": b"%PDF ann"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"%PDF ann")
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertEqual(response.headers["Content-Disposition"], 'attachment; filename="Partner Card - Ann.pdf"')
        docbuilder = calls[0]
        self.assertEqual((docbuilder["url"], docbuilder["method"]), (DOCBUILDER, "post"))
        payload = docbuilder["opts"]["json"]
        self.assertFalse(payload["async"])
        self.assertIn("/onlyoffice/template/callback/docbuilder/fill_template?oo_security_token=", payload["url"])
        self.assertIn(f"&record_ids={self.ann.id}&template_id={self.template.id}", payload["url"])
        self.assertNotIn("token", payload)
        self.assertNotIn("headers", docbuilder["opts"])

    def test_several_records_download_a_zip_of_their_pdfs(self):
        files = {"Partner Card - Ann.pdf": b"%PDF ann", "Partner Card - Bob.pdf": b"%PDF bob"}
        response, calls = self._fill(self.ann | self.bob, files)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/zip")
        self.assertRegex(response.headers["Content-Disposition"], r'filename="onlyoffice-templates-[\d_]+\.zip"')
        self.assertEqual(int(response.headers["Content-Length"]), len(response.content))
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            self.assertEqual({name: archive.read(name) for name in archive.namelist()}, files)
        self.assertIn(f"&record_ids={self.ann.id},{self.bob.id}&", calls[0]["opts"]["json"]["url"])

    def test_docbuilder_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")

        _response, calls = self._fill(self.ann, {"a.pdf": b"%PDF"})

        opts = calls[0]["opts"]
        payload = jwt_utils.decode_token(self.env, opts["json"]["token"], "ds-secret")
        self.assertEqual(payload["url"], opts["json"]["url"])
        self.assertTrue(opts["headers"][config_utils.get_jwt_header(self.env)].startswith("Bearer "))

    def test_failures_answer_not_found(self):
        cases = {
            "docbuilder error": (self.ann, {"a.pdf": b"%PDF"}, ds_response({"error": -8})),
            "no document generated": (self.ann, {}, None),
            "download failed": (self.ann, {"a.pdf": 500}, None),
            "one download of the ZIP failed": (self.ann | self.bob, {"a.pdf": b"%PDF", "b.pdf": 502}, None),
        }
        for case, (records, files, docbuilder) in cases.items():
            with self.subTest(case=case):
                response, _calls = self._fill(records, files, docbuilder)
                self.assertEqual(response.status_code, 404)

    @known_bug("a non-ASCII file name is reduced to '.pdf' in Content-Disposition")
    def test_non_ascii_file_name_is_kept(self):
        response, _calls = self._fill(self.ann, {"Карточка - Анна.pdf": b"%PDF"})
        self.assertIn(f"filename*=UTF-8''{quote('Карточка - Анна.pdf')}", response.headers["Content-Disposition"])

    def test_visitor_is_sent_to_the_login(self):
        self.authenticate(None, None)
        response = self.url_open(
            f"/onlyoffice/template/fill?template_id={self.template.id}&record_ids={self.ann.id}", allow_redirects=False
        )
        self.assertIn(response.status_code, (302, 303))
        self.assertIn("/web/login", response.headers["Location"])


@tagged("post_install", "-at_install")
class TestDocbuilderFileRoutes(TemplatesCase, HttpCase):
    """Public routes the Document Server calls back: the template file and the script that reads its field keys."""

    def setUp(self):
        super().setUp()
        self.template = self._template()
        self.attachment = self.template.attachment_id
        self.odoo_url = config_utils.get_base_or_odoo_url(self.env)

    def _download(self, token):
        return self.url_open(f"/onlyoffice/template/download/{self.attachment.id}?oo_security_token={token}")

    def test_template_file_is_served_to_its_token(self):
        response = self._download(self._token(self.admin))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, bundled_pdf())
        self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_template_file_needs_a_valid_token_of_a_user_who_can_read_it(self):
        stranger = new_test_user(self.env, login="oo_tpl_stranger", groups="base.group_user")
        forged = jwt_utils.encode_payload(self.env, {"id": self.admin.id}, "another-secret")
        for case, token in {"no token": "", "forged": forged, "no templates group": self._token(stranger)}.items():
            with self.subTest(case=case):
                response = self._download(token)
                self.assertNotEqual(response.status_code, 200)
                self.assertNotIn(b"%PDF", response.content)

    def test_keys_script_opens_the_template_and_saves_its_keys(self):
        token = self._token(self.admin)
        response = self.url_open(
            f"/onlyoffice/template/callback/docbuilder/get_keys?attachment_id={self.attachment.id}"
            f"&oo_security_token={token}"
        )

        self.assertEqual(response.status_code, 200)
        url = f"{self.odoo_url}onlyoffice/template/download/{self.attachment.id}?oo_security_token={token}"
        self.assertIn(f'builder.OpenFile("{url}");', response.text)
        self.assertIn('builder.SaveFile("txt", "keys.txt");', response.text)

    def test_fill_script_for_an_unknown_template_or_record_set_is_not_found(self):
        token = self._token(self.admin)
        for case, query in {
            "unknown template": f"template_id=999999999&record_ids=1&oo_security_token={token}",
            "no records": f"template_id={self.template.id}&record_ids=&oo_security_token={token}",
        }.items():
            with self.subTest(case=case):
                response = self.url_open(f"/onlyoffice/template/callback/docbuilder/fill_template?{query}")
                self.assertEqual(response.status_code, 404)
                self.assertNotIn("builder.", response.text)

    def test_keys_script_needs_a_token(self):
        response = self.url_open(
            f"/onlyoffice/template/callback/docbuilder/get_keys?attachment_id={self.attachment.id}&oo_security_token="
        )
        self.assertEqual(response.status_code, 404)
