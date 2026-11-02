# Copyright (C) 2026 Ascensio System SIA
import base64
import json
from contextlib import contextmanager
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_templates.controllers.controllers import OnlyofficeTemplate_Connector
from odoo.addons.onlyoffice_odoo_templates.models.onlyoffice_odoo_templates import OnlyOfficeTemplate


@tagged("post_install", "-at_install")
class TestFieldKeysCache(TransactionCase):
    """The PDF form field keys are cached on ``field_keys`` whenever the template's PDF attachment is created or
    changed (``ir.attachment`` create/write overrides, run in ``cr.postcommit``); ``_get_cached_keys`` reads that
    cache and falls back to ``get_keys`` only when it is empty or corrupt."""

    def setUp(self):
        super().setUp()
        self.model = self.env["ir.model"].search([("model", "=", "res.partner")], limit=1)
        self.controller = OnlyofficeTemplate_Connector()

    @contextmanager
    def _pdf(self, is_pdf_form, keys):
        """Patches the PDF form detection and the key extraction, then runs the postcommit refresh.

        A non-form PDF is converted through the Document Server and committed in create(); both are mocked, so the
        postcommit queue that normally runs on commit is run by hand.
        """
        with (
            patch("odoo.addons.onlyoffice_odoo_templates.utils.pdf_utils.is_pdf_form", return_value=is_pdf_form),
            patch.object(OnlyOfficeTemplate, "_convert_to_form", return_value={}),
            patch.object(OnlyOfficeTemplate, "_fetch_field_keys", return_value=keys) as fetch_keys,
            patch.object(self.env.cr, "commit"),
        ):
            yield fetch_keys
            self.env.cr.postcommit.run()

    def _create_template(self, is_pdf_form=True, keys=()):
        with self._pdf(is_pdf_form, list(keys)) as fetch_keys:
            template = self.env["onlyoffice.odoo.templates"].create(
                {"name": "Test template", "template_model_id": self.model.id, "file": base64.b64encode(b"%PDF-1.4")}
            )
        return template, fetch_keys

    def test_keys_are_cached_on_create(self):
        template, fetch_keys = self._create_template(keys=["a", "b"])
        fetch_keys.assert_called_once()
        self.assertEqual(json.loads(template.field_keys), ["a", "b"])

    def test_non_form_pdf_has_no_cached_keys(self):
        template, fetch_keys = self._create_template(is_pdf_form=False)
        fetch_keys.assert_not_called()
        self.assertFalse(template.field_keys)

    def test_keys_are_refreshed_when_attachment_content_changes(self):
        template, _fetch_keys = self._create_template(keys=["a"])
        with self._pdf(True, ["a", "c"]) as fetch_keys:
            template.attachment_id.write({"datas": base64.b64encode(b"%PDF-1.4 different contents")})
        fetch_keys.assert_called_once()
        self.assertEqual(json.loads(template.field_keys), ["a", "c"])

    def test_get_cached_keys_reads_cache_without_recomputing(self):
        template, _fetch_keys = self._create_template(keys=["a", "b"])
        with patch.object(OnlyofficeTemplate_Connector, "get_keys") as get_keys:
            self.assertEqual(self.controller._get_cached_keys(template, "token"), ["a", "b"])
        get_keys.assert_not_called()

    def test_get_cached_keys_falls_back_to_get_keys_when_empty(self):
        template, _fetch_keys = self._create_template(is_pdf_form=False)
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as get_keys:
            self.assertEqual(self.controller._get_cached_keys(template, "token"), ["x"])
        get_keys.assert_called_once()
        self.assertEqual(json.loads(template.field_keys), ["x"])

    def test_corrupt_cache_is_recomputed(self):
        template, _fetch_keys = self._create_template(keys=["a"])
        template.sudo().write({"field_keys": "not-json"})
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as get_keys:
            self.assertEqual(self.controller._get_cached_keys(template, "token"), ["x"])
        get_keys.assert_called_once()
