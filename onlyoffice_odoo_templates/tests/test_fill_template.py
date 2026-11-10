# Copyright (C) 2026 Ascensio System SIA
import datetime
import io
import json
import re
import zipfile
from unittest.mock import MagicMock, patch

from odoo.fields import Float
from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils, jwt_utils
from odoo.addons.onlyoffice_odoo_templates.utils import config_utils as templates_config_utils

# Form keys of the template: plain fields of each type handled by get_fields (html is skipped), then related fields.
KEYS = ["name", "email", "is_company", "type", "color", "partner_latitude", "activity_date_deadline", "comment"]
KEYS += ["parent_id name", "child_ids name"]
SAVE_FILE = re.compile(r"^\s*builder\.SaveFile\(.*$", re.M)
# A SaveFile call whose only string literals are the format, the file name and the optional print parameters.
SAFE_SAVE_FILE = re.compile(r'^\s*builder\.SaveFile\("pdf",\s+"[^"]*\.pdf"(, "[^"]*")?\);$')
CONTROLLERS = "odoo.addons.onlyoffice_odoo_templates.controllers.controllers"


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
            comment="<p>skipped</p>",
            parent_id=self.company.id,
        )
        # res.partner has no plain date field in 18.0 (date was removed); this one comes from the next activity.
        partner.activity_schedule("mail.mail_activity_data_todo", date_deadline=datetime.date(2026, 1, 31))

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
                "activity_date_deadline": "01/31/2026",
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

    def test_records_with_one_name_get_a_file_each(self):
        first, second = self._partner("Twin"), self._partner("Twin")

        names = re.findall(r'builder\.SaveFile\("pdf",\s+"([^"]*)\.pdf"', self._script(first | second))
        self.assertEqual(names, ["Partner - Twin", f"Partner - Twin ({second.id})"])

    def test_selection_shows_the_label_of_a_selection_method(self):
        # res.partner.lang: its selection is a method (the installed languages), not a list.
        self.template.field_keys = json.dumps(["lang", "type"])
        partner = self._partner("Jane Doe", lang="en_US", type="invoice")

        self.assertEqual(self._fields(self._script(partner))[0], {"lang": "English (US)", "type": "Invoice Address"})

    def test_float_without_digits_or_with_the_full_precision(self):
        rate_template = (
            self.env["onlyoffice.odoo.templates"]
            .with_context(skip_field_keys_refresh=True)
            .create({"name": "Rate", "template_model_id": self.env["ir.model"]._get("res.currency.rate").id})
        )
        rate_template.field_keys = json.dumps(["rate"])
        self.template = rate_template
        # res.currency.rate.rate has digits=0: the full precision, as the shortest text of the float (no binary
        # noise such as 100.004999999999995, no exponent such as 1e-05).
        for day, value, printed in (
            (1, 1.2345678, "1.2345678"),
            (2, 100.005, "100.005"),
            (3, 0.00001, "0.00001"),
            (4, 1234567.891, "1234567.891"),
            (5, 2.0, "2"),
        ):
            with self.subTest(value=value):
                rate = self.env["res.currency.rate"].create(
                    {"name": f"2001-01-0{day}", "rate": value, "currency_id": self.env.ref("base.EUR").id}
                )
                self.assertEqual(self._fields(self._script(rate))[0], {"rate": printed})

        self.template = self.env["onlyoffice.odoo.templates"].search([("name", "=", "Partner")], limit=1)
        self.template.field_keys = json.dumps(["partner_latitude"])
        partner = self._partner("Jane Doe", partner_latitude=1.5)
        original = Float.get_digits

        def without_digits(field, env):
            return None if field.name == "partner_latitude" else original(field, env)

        with patch.object(Float, "get_digits", without_digits):
            self.assertEqual(self._fields(self._script(partner))[0], {"partner_latitude": "1.50"})

    def test_zip_downloads_files_whose_name_has_a_hash(self):
        self.authenticate("admin", "admin")
        files = {
            "Partner - A#1.pdf": "http://docserver/cache/Partner - A#1.pdf",
            "Partner - B.pdf": "http://docserver/cache/b.pdf",
        }
        requested = []

        def download(url, method, env, **kwargs):
            requested.append(url)
            return MagicMock(status_code=200 if "#" not in url else 404, content=b"%PDF-1.7")

        with (
            patch(f"{CONTROLLERS}.OnlyofficeTemplate_Connector.fill_template", return_value=files),
            patch(f"{CONTROLLERS}.onlyoffice_request", side_effect=download),
        ):
            response = self.url_open(
                f"/onlyoffice/template/fill?template_id={self.template.id}&record_ids={self.company.id}"
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("%23", requested[0])
        self.assertEqual(sorted(zipfile.ZipFile(io.BytesIO(response.content)).namelist()), sorted(files))
