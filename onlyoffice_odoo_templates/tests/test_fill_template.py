# Copyright (C) 2026 Ascensio System SIA
import datetime
import json
import re

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_templates.utils import config_utils as templates_config_utils

# Form keys of the template: plain fields of each type handled by get_fields (html is skipped), then related fields.
KEYS = ["name", "email", "is_company", "type", "color", "partner_latitude", "date", "comment"]
KEYS += ["parent_id name", "child_ids name"]
SAVE_FILE = re.compile(r"^\s*builder\.SaveFile\(.*$", re.M)
# A SaveFile call whose only string literals are the format, the file name and the optional print parameters.
SAFE_SAVE_FILE = re.compile(r'^\s*builder\.SaveFile\("pdf",\s+"[^"]*\.pdf"(, "[^"]*")?\);$')


@tagged("post_install", "-at_install")
class TestFillTemplateScript(HttpCase):
    """The docbuilder script that /onlyoffice/template/callback/docbuilder/fill_template serves to the Document Server;
    no Document Server is involved."""

    def setUp(self):
        super().setUp()
        # A preset internal secret keeps get_internal_jwt_secret from generating one and committing the test.
        self.env["ir.config_parameter"].sudo().set_param(config_constants.INTERNAL_JWT_SECRET, "test-internal-secret")
        self.token = jwt_utils.encode_payload(
            self.env, {"id": self.env.ref("base.user_admin").id}, config_utils.get_internal_jwt_secret(self.env)
        )
        self.template = (
            self.env["onlyoffice.odoo.templates"]
            .with_context(skip_field_keys_refresh=True)
            .create({"name": "Partner", "template_model_id": self.env["ir.model"]._get("res.partner").id})
        )
        self.template.field_keys = json.dumps(KEYS)  # normally extracted from the PDF form by docbuilder
        self.company = self.env["res.partner"].create({"name": "Parent Co", "is_company": True})

    def _partner(self, name, **vals):
        return self.env["res.partner"].create({"name": name, **vals})

    def _get(self, records, token):
        record_ids = ",".join(str(record.id) for record in records)
        return self.url_open(
            "/onlyoffice/template/callback/docbuilder/fill_template"
            f"?oo_security_token={token}&record_ids={record_ids}&template_id={self.template.id}"
        )

    def _script(self, records):
        response = self._get(records, self.token)
        self.assertEqual(response.status_code, 200)
        return response.text

    @staticmethod
    def _fields(script):
        return [json.loads(fields) for fields in re.findall(r"var fields = (.*);\n", script)]

    def test_fields_are_formatted_by_type(self):
        partner = self._partner(
            "Jane Doe",
            email="jane@e2e.test",
            color=4,
            partner_latitude=1.5,
            date=datetime.date(2026, 1, 31),
            comment="<p>skipped</p>",
            parent_id=self.company.id,
        )

        partner_fields, company_fields = self._fields(self._script(partner | self.company))

        self.assertEqual(
            partner_fields,
            {
                "name": "Jane Doe",
                "email": "jane@e2e.test",
                "is_company": "false",
                "type": "Contact",
                "color": "4",
                "partner_latitude": "1.5000000",
                "date": "01/31/2026",
                "parent_id": {"name": "Parent Co"},
            },
        )
        self.assertEqual(company_fields["child_ids"], [{"name": "Jane Doe"}])

    def test_one_pdf_is_saved_per_record_with_a_file_system_safe_name(self):
        script = self._script(self._partner("A/B: report?") | self._partner("Second"))

        names = re.findall(r'builder\.SaveFile\("pdf",\s+"([^"]*)\.pdf"', script)
        self.assertEqual(names, ["Partner - A B report", "Partner - Second"])
        self.assertEqual(script.count("builder.OpenFile("), 2)

    def test_record_names_cannot_break_out_of_the_script(self):
        script = self._script(self._partner('Evil"); builder.CloseFile(); //'))

        self.assertRegex(SAVE_FILE.search(script).group(), SAFE_SAVE_FILE)
        self.assertEqual(self._fields(script)[0]["name"], 'Evil"); builder.CloseFile(); //')

    def test_disable_form_fields_setting_saves_the_pdf_for_print(self):
        partner = self._partner("Jane Doe")
        self.assertNotIn("isPrint", self._script(partner))

        templates_config_utils.set_editable_form_fields(self.env, True)
        self.assertIn("isPrint", SAVE_FILE.search(self._script(partner)).group())

    def test_request_without_a_valid_token_gets_no_script(self):
        self.assertEqual(self._get(self.company, "").status_code, 404)

        forged = jwt_utils.encode_payload(self.env, {"id": self.env.ref("base.user_admin").id}, "another-secret")
        response = self._get(self.company, forged)
        self.assertNotEqual(response.status_code, 200)
        self.assertNotIn("builder.", response.text)
