# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import html
import io
import json
from unittest.mock import patch
from urllib.parse import unquote

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase
from odoo.tools.pdf import PdfFileReader

from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils

from .common import TemplatesCase, ds_response, plain_pdf

REQUEST = "odoo.addons.onlyoffice_odoo_templates.models.ir_actions_report.onlyoffice_request"
DOCBUILDER = "http://documentserver/docbuilder"


GENERATED = plain_pdf("generated")


def pages(pdf):
    return len(PdfFileReader(io.BytesIO(pdf)).pages)


class ReportCase(TemplatesCase):
    """A template of res.partner with its ``onlyoffice-pdf`` report; the docbuilder service is mocked."""

    def setUp(self):
        super().setUp()
        self.template = self._template()
        self.template.create_action()
        self.report = self.template.report_id
        self.ann, self.bob = self.env["res.partner"].create([{"name": "Ann"}, {"name": "Bob"}])

    def _document_server(self, docbuilder=None, download=None):
        """Answers each docbuilder call with one generated PDF; returns the patch and the list of calls."""
        calls = []

        def onlyoffice_request(url, method, opts=None, env=None):
            calls.append({"url": url, "method": method, "opts": opts})
            if url == DOCBUILDER:
                return docbuilder or ds_response({"end": True, "urls": {"Partner Card.pdf": "http://ds/out.pdf"}})
            return download or ds_response(content=GENERATED)

        return patch(REQUEST, side_effect=onlyoffice_request), calls


@tagged("post_install", "-at_install")
class TestOnlyofficePdfReport(ReportCase, TransactionCase):
    """ir.actions.report of type onlyoffice-pdf: one docbuilder fill per record, PDFs merged like a QWeb report."""

    def _render(self, records):
        return self.report.with_context(report_pdf_no_attachment=True)._render_onlyoffice_pdf(
            self.report.report_name, res_ids=records.ids
        )

    def test_report_of_a_template_is_bound_to_its_model(self):
        self.assertEqual(
            (self.report.report_type, self.report.model, self.report.binding_model_id, self.report.report_name),
            ("onlyoffice-pdf", "res.partner", self.partner_model, "Partner Card"),
        )
        self.template.create_action()
        self.assertEqual(self.template.report_id, self.report, "a second call keeps the report")

    def test_one_record_is_filled_and_downloaded(self):
        mock, calls = self._document_server()
        with mock:
            pdf, report_type = self._render(self.ann)

        self.assertEqual((pdf, report_type), (GENERATED, "onlyoffice-pdf"))
        docbuilder, download = calls
        self.assertEqual(docbuilder["url"], DOCBUILDER)
        url = docbuilder["opts"]["json"]["url"]
        self.assertIn(f"&record_ids={self.ann.id}&template_id={self.template.id}", url)
        self.assertEqual(download["url"], "http://ds/out.pdf")

    def test_several_records_are_merged_into_one_pdf(self):
        mock, calls = self._document_server()
        with mock:
            pdf, _report_type = self._render(self.ann | self.bob)

        self.assertEqual(len([call for call in calls if call["url"] == DOCBUILDER]), 2, "one fill per record")
        self.assertEqual(pages(pdf), 2)

    def test_docbuilder_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        mock, calls = self._document_server()
        with mock:
            self._render(self.ann)

        opts = calls[0]["opts"]
        self.assertEqual(
            jwt_utils.decode_token(self.env, opts["json"]["token"], "ds-secret")["url"], opts["json"]["url"]
        )
        self.assertTrue(opts["headers"][config_utils.get_jwt_header(self.env)].startswith("Bearer "))

    def test_saved_report_is_reused_without_the_document_server(self):
        self.report.write({"attachment": "'Card %s.pdf' % object.name", "attachment_use": True})
        mock, calls = self._document_server()
        with mock:
            self.report._render_onlyoffice_pdf(self.report.report_name, res_ids=self.ann.ids)
        attachment = self.env["ir.attachment"].search([("res_model", "=", "res.partner"), ("res_id", "=", self.ann.id)])
        self.assertEqual((attachment.name, attachment.raw), ("Card Ann.pdf", GENERATED))

        with mock:
            pdf, _report_type = self.report._render_onlyoffice_pdf(self.report.report_name, res_ids=self.ann.ids)
        self.assertEqual(pdf, GENERATED)
        self.assertEqual(len(calls), 2, "the second print reads the saved PDF")

    def test_record_that_cannot_be_generated_fails_the_print(self):
        cases = {
            "Document generation error.": (ds_response({"error": -3}), None),
            "returned no document": (ds_response({"urls": {}}), None),
            "failed with HTTP 500": (None, ds_response(status_code=500)),
        }
        for message, (docbuilder, download) in cases.items():
            with self.subTest(message=message):
                mock, _calls = self._document_server(docbuilder, download)
                with mock, self.assertRaises(UserError) as error:
                    self._render(self.ann | self.bob)
                self.assertIn("Ann", str(error.exception))
                self.assertIn(message, str(error.exception))

    def test_template_sets_the_model_and_name_of_a_new_report(self):
        report = self.env["ir.actions.report"].new({"report_type": "onlyoffice-pdf"})
        report.onlyoffice_template_id = self.template
        report.onchange_onlyoffice_template_id()
        self.assertEqual((report.model, report.report_name), ("res.partner", "Partner Card"))

    def test_docbuilder_error_messages(self):
        error = self.env["ir.actions.report"].get_docbuilder_error
        self.assertEqual(error(-8), "Invalid token.")
        self.assertEqual(error(-99), "Error code not recognized.")

    def test_unlink_action_removes_the_report(self):
        self.template.unlink_action()
        self.assertFalse(self.report.exists())
        self.assertFalse(self.template.report_id)

    def test_associated_report_opens_the_report_form(self):
        action = self.template.associated_report()
        self.assertEqual((action["res_model"], action["res_id"]), ("ir.actions.report", self.report.id))
        self.template.unlink_action()
        self.assertEqual(self.template.associated_report(), {"type": "ir.actions.act_window_close"})


@tagged("post_install", "-at_install")
class TestReportRoutes(ReportCase, HttpCase):
    """The web client's report routes for the onlyoffice-pdf converter (report_controller.py)."""

    def setUp(self):
        super().setUp()
        self.authenticate("oo_tpl_user", "oo_tpl_user")

    def _download(self, url):
        with patch("odoo.http.Request.validate_csrf", return_value=True):
            return self.url_open("/report/download", data={"data": json.dumps([url, "onlyoffice-pdf"])})

    def test_report_route_answers_the_pdf(self):
        mock, _calls = self._document_server()
        with mock:
            response = self.url_open(f"/report/onlyoffice-pdf/{self.report.report_name}/{self.ann.id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")
        self.assertEqual(response.content, GENERATED)

    def test_print_menu_downloads_the_pdf_under_the_report_name(self):
        mock, _calls = self._document_server()
        with mock:
            response = self._download(f"/report/onlyoffice-pdf/{self.report.report_name}/{self.ann.id},{self.bob.id}")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Partner Card Print (ONLYOFFICE).pdf", unquote(response.headers["Content-Disposition"]))
        self.assertEqual(pages(response.content), 2)

    def test_print_menu_reports_a_failure_as_a_server_error(self):
        mock, _calls = self._document_server(docbuilder=ds_response({"error": -4}))
        with mock:
            response = self._download(f"/report/onlyoffice-pdf/{self.report.report_name}/{self.ann.id}")

        error = json.loads(html.unescape(response.text))
        self.assertEqual(error["message"], "Odoo Server Error")
        self.assertIn("Error while downloading the document file to be generated.", error["data"]["message"])
