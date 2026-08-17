# Copyright (C) 2026 Ascensio System SIA
import base64
import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# `hr` ships a bundled default template for hr.employee.
MODEL_NAME = "hr.employee"


class OnlyofficeTemplatesModelTestCase(TransactionCase):
    """Shared setup for tests that need the hr.employee bundled template."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ir_model = cls.env["ir.model"].search([("model", "=", MODEL_NAME)], limit=1)
        if not cls.ir_model:
            return

        cls.demo_record = cls.env[MODEL_NAME].search([], limit=1)
        if not cls.demo_record:
            cls.demo_record = cls.env[MODEL_NAME].create({"name": "ONLYOFFICE Test Employee"})

    def setUp(self):
        super().setUp()
        if not self.ir_model:
            self.skipTest(f"Model {MODEL_NAME} is not installed in this test environment")

    def _create_template_from_first_bundled_file(self):
        demo = self.env["onlyoffice.odoo.demo.templates"].create({})
        data = demo.get_template_data()
        template_path = data["structure"][MODEL_NAME]["files"][0]["path"]
        selected_path = f"{MODEL_NAME}/{template_path}"

        demo.selected_templates = json.dumps([selected_path])
        demo.action_save()

        return (
            self.env["onlyoffice.odoo.templates"].search([("template_model_model", "=", MODEL_NAME)], limit=1),
            selected_path,
            demo,
        )


@tagged("post_install", "-at_install")
class TestOnlyofficeOdooDemoTemplates(OnlyofficeTemplatesModelTestCase):
    """Tests for onlyoffice.odoo.demo.templates — get_template_data and action_save."""

    # -- get_template_data --

    def test_default_template_visible_in_structure(self):
        """A bundled template shows up in the picker once its module is installed."""
        demo = self.env["onlyoffice.odoo.demo.templates"].create({})
        data = demo.get_template_data()

        self.assertIn(MODEL_NAME, data["structure"])
        files = data["structure"][MODEL_NAME]["files"]
        self.assertTrue(files, f"Expected at least one bundled PDF template for {MODEL_NAME}")
        self.assertEqual(data["structure"][MODEL_NAME]["model"], MODEL_NAME)

    def test_structure_excludes_uninstalled_models(self):
        """Bundled templates for uninstalled models are not exposed to the picker."""
        demo = self.env["onlyoffice.odoo.demo.templates"].create({})
        data = demo.get_template_data()

        for model_name in data["structure"]:
            self.assertTrue(
                self.env["ir.model"].search([("model", "=", model_name)], limit=1),
                f"{model_name} appears in the picker but has no matching ir.model",
            )

    # -- action_save --

    def test_action_save_creates_template_with_attachment(self):
        """Saving a selected template creates a template record with the exact PDF bytes."""
        template, selected_path, demo = self._create_template_from_first_bundled_file()

        self.assertTrue(template, "Template record was not created by action_save")
        self.assertTrue(template.attachment_id)
        self.assertEqual(template.template_model_id, self.ir_model)

        expected_bytes = demo.get_template_content(selected_path)
        self.assertEqual(base64.b64decode(template.attachment_id.datas), expected_bytes)

    def test_action_save_without_selection_is_noop(self):
        """Saving with an empty selection creates no template."""
        demo = self.env["onlyoffice.odoo.demo.templates"].create({})
        demo.selected_templates = json.dumps([])

        before = self.env["onlyoffice.odoo.templates"].search_count([])
        demo.action_save()
        after = self.env["onlyoffice.odoo.templates"].search_count([])

        self.assertEqual(before, after)


@tagged("post_install", "-at_install")
class TestOnlyofficeOdooTemplates(OnlyofficeTemplatesModelTestCase):
    """Tests for onlyoffice.odoo.templates — create_action, unlink_action and printing."""

    # -- create_action / unlink_action --

    def test_create_action_binds_onlyoffice_report(self):
        """create_action creates a bound onlyoffice-pdf report."""
        template, _selected_path, _demo = self._create_template_from_first_bundled_file()
        template.create_action()

        self.assertTrue(template.report_id)
        self.assertEqual(template.report_id.report_type, "onlyoffice-pdf")
        self.assertEqual(template.report_id.model, MODEL_NAME)
        self.assertEqual(template.report_id.onlyoffice_template_id, template)

    def test_unlink_action_removes_report(self):
        """unlink_action removes the bound report and clears the link."""
        template, _selected_path, _demo = self._create_template_from_first_bundled_file()
        template.create_action()
        report = template.report_id

        template.unlink_action()

        self.assertFalse(template.report_id)
        self.assertFalse(report.exists())

    # -- Printing (IrActionsReport._render_onlyoffice_pdf, mocked) --

    def test_print_demo_record_returns_generated_pdf(self):
        """Printing returns the PDF bytes produced by fill_template."""
        template, _selected_path, _demo = self._create_template_from_first_bundled_file()
        template.create_action()
        report = template.report_id

        fake_pdf = b"%PDF-1.4 fake generated content%%EOF"
        fake_response = MagicMock(status_code=200, content=fake_pdf)

        with (
            patch(
                "odoo.addons.onlyoffice_odoo_templates.models.ir_actions_report.IrActionsReport.fill_template",
                return_value={self.demo_record.id: "http://fake-docserver/result.pdf"},
            ) as mock_fill,
            patch(
                "odoo.addons.onlyoffice_odoo_templates.models.ir_actions_report.onlyoffice_request",
                return_value=fake_response,
            ) as mock_request,
        ):
            pdf_content, report_type = report.with_context(report_pdf_no_attachment=True)._render_onlyoffice_pdf(
                report.report_name, res_ids=[self.demo_record.id]
            )

        self.assertEqual(report_type, "onlyoffice-pdf")
        self.assertEqual(pdf_content, fake_pdf)
        mock_fill.assert_called_once()
        mock_request.assert_called_once()

    def test_print_reports_docbuilder_error_without_crashing(self):
        """A failed fill_template skips the record's stream instead of crashing."""
        template, _selected_path, _demo = self._create_template_from_first_bundled_file()
        template.create_action()
        report = template.report_id

        with patch(
            "odoo.addons.onlyoffice_odoo_templates.models.ir_actions_report.IrActionsReport.fill_template",
            side_effect=Exception("Document conversion service cannot be reached"),
        ):
            streams = report.with_context(report_pdf_no_attachment=True)._render_onlyoffice_pdf_prepare_streams(
                report.report_name, data={}, res_ids=[self.demo_record.id]
            )

        self.assertIsNone(streams[self.demo_record.id]["stream"])
