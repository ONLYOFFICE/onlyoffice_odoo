# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user

from .common import TemplatesCase, bundled_pdf


@tagged("post_install", "-at_install")
class TestTemplateContentRoute(HttpCase):
    """GET /onlyoffice/template/template_content/<model>_<file>: the bundled PDFs, for the preview in Settings."""

    def _get(self, path):
        return self.url_open(f"/onlyoffice/template/template_content/{path}")

    def test_bundled_template_is_served(self):
        response = self._get("hr.employee_Employee.pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, bundled_pdf("hr.employee/Employee.pdf"))
        self.assertEqual(response.headers["Content-Type"], "application/pdf")

    def test_missing_files_and_paths_out_of_the_templates_directory_are_not_found(self):
        # "_" stands for "/" in the route; the traversal guard itself is tested in test_models.py.
        for path in ("hr.employee_Missing.pdf", ".._hr.employee_Employee.pdf"):
            with self.subTest(path=path):
                response = self._get(path)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(b"%PDF", response.content)


@tagged("post_install", "-at_install")
class TestTemplateEditorRoute(TemplatesCase, HttpCase):
    """POST /onlyoffice/template/editor: only a template administrator edits; a template user only views."""

    def setUp(self):
        super().setUp()
        self.template = self._template()

    def _config(self, login):
        self.authenticate(login, login)
        return self._rpc("/onlyoffice/template/editor", attachment_id=self.template.attachment_id.id)

    def test_administrator_edits_the_template(self):
        config = self._config("oo_tpl_admin")["result"]["editorConfig"]

        self.assertEqual(config["editorConfig"]["mode"], "edit")
        self.assertIn(
            f"/onlyoffice/editor/callback/{self.template.attachment_id.id}?", config["editorConfig"]["callbackUrl"]
        )
        self.assertEqual(config["document"]["title"], "Partner Card.pdf")

    def test_user_only_views_the_template(self):
        config = self._config("oo_tpl_user")["result"]["editorConfig"]

        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertNotIn("callbackUrl", config["editorConfig"])

    def test_user_without_templates_group_gets_no_editor(self):
        new_test_user(self.env, login="oo_tpl_stranger", groups="base.group_user")
        self.assertIn("error", self._config("oo_tpl_stranger"))


@tagged("post_install", "-at_install")
class TestDocumentsRoutesWithoutDocuments(TemplatesCase, HttpCase):
    """Routes of "Save to Documents" when the Documents app is not installed (with it: e2e/tests/templates.spec.ts)."""

    def setUp(self):
        super().setUp()
        if "documents.document" in self.env:
            self.skipTest("the Documents app is installed in this database")
        self.authenticate("oo_tpl_user", "oo_tpl_user")

    def test_print_dialog_hides_save_to_documents(self):
        self.assertIs(self._rpc("/onlyoffice/template/documents/check")["result"], False)

    def test_no_folders_are_offered(self):
        self.assertEqual(self._rpc("/onlyoffice/template/documents/folders")["result"], [])

    def test_saving_reports_the_missing_app(self):
        template = self._template()
        partner = self.env["res.partner"].create({"name": "Ann"})

        body = self._rpc(
            "/onlyoffice/template/documents/save", template_id=template.id, record_ids=[partner.id], folder_id=1
        )

        self.assertEqual(body["error"]["data"]["message"], "Documents module is not installed")
