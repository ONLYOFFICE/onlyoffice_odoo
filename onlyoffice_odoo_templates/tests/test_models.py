# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json
import os
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_templates.models.onlyoffice_odoo_templates import OnlyOfficeTemplate
from odoo.addons.onlyoffice_odoo_templates.utils import config_utils as templates_config_utils

from .common import INTERNAL_SECRET, PLAIN_PDF, TemplatesCase, bundled_pdf, ds_response

REQUEST = "odoo.addons.onlyoffice_odoo_templates.models.onlyoffice_odoo_templates.onlyoffice_request"


@tagged("post_install", "-at_install")
class TestDemoTemplates(TransactionCase):
    """onlyoffice.odoo.demo.templates: the PDFs bundled per model, exported from Settings. Needs `hr` installed
    (preinstall of the templates job in test.yml)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.hr_model = cls.env["ir.model"]._get("hr.employee")
        assert cls.hr_model, "the templates tests need the hr module (preinstall: hr in .github/workflows/test.yml)"
        cls.demo = cls.env["onlyoffice.odoo.demo.templates"].create({})
        cls.hr_files = sorted(os.listdir(os.path.join(cls.demo._get_templates_dir(), "hr.employee")))

    def test_structure_lists_the_files_of_installed_models_only(self):
        structure = self.demo.get_template_data()["structure"]

        self.assertEqual(sorted(file["name"] for file in structure["hr.employee"]["files"]), self.hr_files)
        self.assertEqual(structure["hr.employee"]["name"], self.hr_model.name)
        for model in structure:
            with self.subTest(model=model):
                self.assertTrue(self.env["ir.model"]._get(model))

    def test_install_creates_a_template_per_bundled_file_of_installed_models(self):
        Template = self.env["onlyoffice.odoo.templates"]
        before = Template.search([])

        with patch.object(OnlyOfficeTemplate, "_update_field_keys"):
            Template._create_demo_data()

        created = Template.search([]) - before
        self.assertEqual(sorted(created.mapped("name")), sorted(os.path.splitext(name)[0] for name in self.hr_files))
        self.assertEqual(set(created.mapped("template_model_model")), {"hr.employee"})

    def test_export_creates_the_selected_templates_with_their_pdf(self):
        self.demo.selected_templates = json.dumps(["hr.employee/Employee.pdf", "no-slash", "x.model/Missing.pdf"])
        before = self.env["onlyoffice.odoo.templates"].search([])

        self.demo.action_save()

        created = self.env["onlyoffice.odoo.templates"].search([]) - before
        self.assertEqual((created.name, created.template_model_id), ("Employee", self.hr_model))
        self.assertEqual(created.attachment_id.raw, bundled_pdf("hr.employee/Employee.pdf"))

    def test_export_without_a_selection_creates_nothing(self):
        before = self.env["onlyoffice.odoo.templates"].search_count([])
        self.demo.selected_templates = "[]"
        self.assertIsNone(self.demo.action_save())
        self.assertEqual(self.env["onlyoffice.odoo.templates"].search_count([]), before)

    def test_only_files_of_the_templates_directory_can_be_read(self):
        self.assertEqual(self.demo.get_template_content("hr.employee/Employee.pdf"), bundled_pdf())
        outside = (
            "../../../onlyoffice_odoo/static/assets/document_templates/en-US/new.pdf",
            "/etc/passwd",
            "hr.employee/../../../__manifest__.py",
        )
        for path in outside:
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.demo.get_template_content(path)


@tagged("post_install", "-at_install")
class TestTemplateCreation(TemplatesCase, TransactionCase):
    """onlyoffice.odoo.templates.create: blank, uploaded, from the form gallery, and plain PDFs converted to forms."""

    def setUp(self):
        super().setUp()
        # A non-form PDF is converted and committed in create(); the commits are disabled.
        commit = patch.object(self.env.cr, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        refresh = patch.object(OnlyOfficeTemplate, "_update_field_keys")
        refresh.start()
        self.addCleanup(refresh.stop)
        self.Template = self.env["onlyoffice.odoo.templates"]

    def _create(self, name="Partner Card", **vals):
        return self.Template.create({"name": name, "template_model_id": self.partner_model.id, **vals})

    def _exists(self, name):
        return bool(self.Template.search([("name", "=", name)]))

    def test_template_without_a_file_is_a_blank_pdf_form(self):
        template = self._create()

        attachment = template.attachment_id
        self.assertEqual((attachment.name, attachment.mimetype), ("Partner Card.pdf", "application/pdf"))
        self.assertEqual(attachment.raw, file_utils.get_default_file_template(self.env.user.lang, "pdf"))
        self.assertEqual((attachment.res_model, attachment.res_id), ("onlyoffice.odoo.templates", template.id))
        self.assertEqual((template.template_model_model, template.template_model_name), ("res.partner", "Contact"))

    def test_uploaded_pdf_form_is_kept_as_is(self):
        with patch(REQUEST) as request:
            template = self._create(file=base64.b64encode(bundled_pdf()))
        self.assertEqual(template.attachment_id.raw, bundled_pdf())
        request.assert_not_called()

    def test_invalid_file_is_refused(self):
        with self.assertRaises(UserError):
            self._create(file="abc")

    def test_form_of_the_gallery_is_downloaded(self):
        with patch(REQUEST, return_value=ds_response(content=bundled_pdf())) as request:
            template = self.Template.with_context(url="https://forms.example/lease.pdf").create(
                {"name": "Lease", "template_model_id": self.partner_model.id}
            )
        self.assertEqual(request.call_args.kwargs["url"], "https://forms.example/lease.pdf")
        self.assertEqual(template.attachment_id.raw, bundled_pdf())

    def test_failed_gallery_download_is_reported(self):
        with patch(REQUEST, side_effect=Exception("timeout")), self.assertRaises(UserError):
            self.Template.with_context(url="https://forms.example/lease.pdf").create(
                {"name": "Lease", "template_model_id": self.partner_model.id}
            )

    def test_plain_pdf_is_converted_into_a_form(self):
        converted = {"endConvert": True, "fileUrl": "http://ds/form.pdf"}
        with (
            patch.object(OnlyOfficeTemplate, "_convert_to_form", return_value=converted) as convert,
            patch(REQUEST, return_value=ds_response(content=b"%PDF converted form")) as request,
        ):
            template = self._create(file=base64.b64encode(PLAIN_PDF))

        self.assertEqual(convert.call_args.args[-1], template.attachment_id)
        self.assertEqual(request.call_args.kwargs["url"], "http://ds/form.pdf")
        self.assertEqual(template.attachment_id.raw, b"%PDF converted form")

    def test_failed_conversion_leaves_no_template(self):
        cases = {
            "Conversion error": ({"error": -3, "message": "Conversion error"}, None),
            "Failed to download converted PDF form": ({"fileUrl": "http://ds/form.pdf"}, Exception("gone")),
        }
        for message, (converted, download_error) in cases.items():
            with (
                self.subTest(message=message),
                patch.object(OnlyOfficeTemplate, "_convert_to_form", return_value=converted),
                patch(REQUEST, side_effect=download_error),
                self.assertRaises(UserError) as error,
            ):
                self._create(name=f"Failed {message}", file=base64.b64encode(PLAIN_PDF))
            self.assertEqual(str(error.exception), message)
            self.assertFalse(self._exists(f"Failed {message}"))


@tagged("post_install", "-at_install")
class TestTemplateFile(TemplatesCase, TransactionCase):
    """Conversion request of a plain PDF, a new file uploaded on an existing template, the name of its PDF."""

    def setUp(self):
        super().setUp()
        commit = patch.object(self.env.cr, "commit")
        commit.start()
        self.addCleanup(commit.stop)
        self.template = self._template()

    def test_conversion_request_asks_the_document_server_for_a_form(self):
        config_utils.set_doc_server_public_url(self.env, "http://documentserver/")
        converted = ds_response({"endConvert": True, "fileUrl": "http://ds/form.pdf"})
        with patch(REQUEST, return_value=converted) as request:
            result = self.template._convert_to_form(self.template.attachment_id)

        self.assertEqual(result["fileUrl"], "http://ds/form.pdf")
        self.assertIn("http://documentserver/converter", request.call_args.kwargs["url"])
        body = json.loads(request.call_args.kwargs["opts"]["data"])
        self.assertEqual((body["filetype"], body["outputtype"], body["pdf"]), ("pdf", "pdf", {"form": True}))
        source = f"/onlyoffice/template/download/{self.template.attachment_id.id}?oo_security_token="
        self.assertIn(source, body["url"])
        token = body["url"].split("oo_security_token=")[1]
        self.assertEqual(jwt_utils.decode_token(self.env, token, INTERNAL_SECRET)["id"], self.env.uid)

    def test_conversion_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        with patch(REQUEST, return_value=ds_response({"fileUrl": "u"})) as request:
            self.template._convert_to_form(self.template.attachment_id)
        body = json.loads(request.call_args.kwargs["opts"]["data"])
        self.assertEqual(jwt_utils.decode_token(self.env, body["token"], "ds-secret")["outputtype"], "pdf")

    def test_unreachable_converter_is_an_error_result(self):
        with patch(REQUEST, side_effect=Exception("refused")):
            result = self.template._convert_to_form(self.template.attachment_id)
        self.assertEqual(result, {"error": 1, "message": "Document conversion service cannot be reached"})

    def test_new_pdf_form_replaces_the_file(self):
        form = bundled_pdf("hr.employee/Certificate.pdf")
        self.template.file = base64.b64encode(form)

        self.template._onchange_file()

        self.assertEqual(self.template.attachment_id.raw, form)
        self.assertFalse(self.template.file)

    def test_new_plain_pdf_is_converted(self):
        self.template.file = base64.b64encode(PLAIN_PDF)
        with (
            patch.object(OnlyOfficeTemplate, "_convert_to_form", return_value={"fileUrl": "http://ds/form.pdf"}),
            patch(REQUEST, return_value=ds_response(content=b"%PDF converted")),
        ):
            self.template._onchange_file()
        self.assertEqual(self.template.attachment_id.raw, b"%PDF converted")

    def test_failed_conversion_restores_the_previous_file(self):
        self.template.file = base64.b64encode(PLAIN_PDF)
        with (
            patch.object(OnlyOfficeTemplate, "_convert_to_form", return_value={"error": -4, "message": "Download"}),
            self.assertRaises(UserError),
        ):
            self.template._onchange_file()
        self.assertEqual(self.template.attachment_id.raw, bundled_pdf())

    def test_renaming_renames_the_pdf(self):
        self.template.name = "Contact Card"
        self.template._onchange_name()
        self.assertEqual(self.template.attachment_id.name, "Contact Card.pdf")

    def test_conversion_error_messages(self):
        message = self.template._get_conversion_error_message
        self.assertEqual(message(-5), "Incorrect password")
        self.assertEqual(message(-99), "Undefined error code")


@tagged("post_install", "-at_install")
class TestTemplateModel(TemplatesCase, TransactionCase):
    """The model of a template: the field tree of the editor panel, the model link after a module reinstall."""

    def test_field_tree_of_a_model(self):
        fields = {
            field["id"]: field for field in self.env["onlyoffice.odoo.templates"].get_fields_for_model("res.partner")
        }

        self.assertEqual(fields["name"]["field_type"], "char")
        self.assertFalse(fields["name"]["children"])
        self.assertNotIn("comment", fields, "html fields cannot be filled into a form")
        parent = fields["parent_id"]
        self.assertTrue(parent["children"])
        self.assertEqual(parent["params"], {"model": "res.partner", "prefix": "parent_id", "name": parent["string"]})
        self.assertEqual(parent["value"], "parent_id/id")
        labels = [field["string"].lower() for field in fields.values()]
        self.assertEqual(labels, sorted(labels))

    def test_nested_field_tree_and_exclusions(self):
        get_fields = self.env["onlyoffice.odoo.templates"].get_fields_for_model
        nested = get_fields("res.partner", prefix="parent_id", parent_name="Related Company", exclude=["email"])

        names = {field["id"]: field["string"] for field in nested}
        self.assertEqual(names["parent_id/name"], "Related Company/Name")
        self.assertNotIn("parent_id/email", names)
        deep = get_fields("res.partner", prefix="a/b/c")
        self.assertFalse(any(field["children"] for field in deep), "no relations below the fourth level")
        self.assertEqual(get_fields("no.such.model"), [])

    def test_model_link_is_restored_by_model_name(self):
        template = self._template()
        users_model = self.env["ir.model"]._get("res.users")
        template.template_model_id = users_model

        self.env["onlyoffice.odoo.templates"].update_relationship(template.id, "res.partner")
        self.assertEqual(template.template_model_id, self.partner_model)

        self.env["onlyoffice.odoo.templates"].update_relationship(template.id, "no.such.model")
        self.assertEqual(template.template_model_id, self.partner_model, "an unknown model changes nothing")

    def test_editor_action_carries_the_template(self):
        template = self._template()
        action = template.open_template_editor()
        self.assertEqual(action["tag"], "onlyoffice_template_editor")
        self.assertEqual(
            action["params"],
            {"attachment_id": template.attachment_id.id, "id": template.id, "template_model_model": "res.partner"},
        )


@tagged("post_install", "-at_install")
class TestDisableFormFieldsSetting(TransactionCase):
    """Settings: "Disable form fields after printing PDF form"."""

    def test_setting_is_saved_and_read_back(self):
        config_utils.set_demo(self.env, True)  # the demo server skips the Document Server checks of set_values
        settings = self.env["res.config.settings"].create({})
        self.assertFalse(settings.editable_form_fields)

        settings.editable_form_fields = True
        settings.set_values()

        self.assertTrue(templates_config_utils.get_editable_form_fields(self.env))
        self.assertTrue(self.env["res.config.settings"].create({}).editable_form_fields)
