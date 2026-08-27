# Copyright (C) 2026 Ascensio System SIA
import base64
import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_templates.controllers.controllers import OnlyofficeTemplate_Connector
from odoo.addons.onlyoffice_odoo_templates.models.onlyoffice_odoo_templates import OnlyOfficeTemplate


class TestFieldKeysCache(TransactionCase):
    """The PDF Form field keys depend only on the template PDF, not on the
    records being filled. They are eagerly (re)computed and cached on
    ``field_keys`` whenever the template's PDF attachment is created or its
    content changes -- see the ``ir.attachment`` create/write overrides in
    ``onlyoffice_odoo_templates.models.ir_attachment``, which call
    ``OnlyOfficeTemplate._update_field_keys``. This avoids an extra
    synchronous docbuilder round-trip on every fill; ``_get_cached_keys``
    just reads whatever is cached, falling back to an on-demand
    ``get_keys`` call only if the cache is empty or corrupt.
    """

    def setUp(self):
        super().setUp()
        self.model = self.env["ir.model"].search([("model", "=", "res.partner")], limit=1)
        self.controller = OnlyofficeTemplate_Connector()

    def _create_template(self, is_pdf_form=True, fetch_keys_return=None):
        with (
            patch(
                "odoo.addons.onlyoffice_odoo_templates.utils.pdf_utils.is_pdf_form",
                return_value=is_pdf_form,
            ),
            patch.object(
                OnlyOfficeTemplate,
                "_fetch_field_keys",
                return_value=fetch_keys_return or [],
            ) as mock_fetch,
        ):
            template = self.env["onlyoffice.odoo.templates"].create(
                {
                    "name": "Test template",
                    "template_model_id": self.model.id,
                    "file": base64.b64encode(b"%PDF-1.4 fake content"),
                }
            )
        return template, mock_fetch

    def test_keys_are_cached_eagerly_on_create(self):
        # A new PDF-form upload must have its keys extracted and cached
        # immediately, without waiting for a fill.
        template, mock_fetch = self._create_template(is_pdf_form=True, fetch_keys_return=["a", "b"])
        mock_fetch.assert_called_once()
        self.assertEqual(json.loads(template.field_keys), ["a", "b"])

    def test_non_form_pdf_has_no_cached_keys(self):
        # Non-form PDFs have no fillable fields, so keys must not be
        # searched for and the cache stays empty.
        template, mock_fetch = self._create_template(is_pdf_form=False)
        mock_fetch.assert_not_called()
        self.assertFalse(template.field_keys)

    def test_keys_are_refreshed_when_attachment_content_changes(self):
        template, _mock_fetch = self._create_template(is_pdf_form=True, fetch_keys_return=["a"])
        self.assertEqual(json.loads(template.field_keys), ["a"])

        # Re-uploading a new PDF form (e.g. re-upload, conversion, editor
        # save) must recompute and re-cache the keys automatically, via the
        # ir.attachment write override.
        with (
            patch(
                "odoo.addons.onlyoffice_odoo_templates.utils.pdf_utils.is_pdf_form",
                return_value=True,
            ),
            patch.object(OnlyOfficeTemplate, "_fetch_field_keys", return_value=["a", "c"]) as mock_fetch,
        ):
            template.attachment_id.write({"datas": base64.b64encode(b"%PDF-1.4 different contents")})

        mock_fetch.assert_called_once()
        self.assertEqual(json.loads(template.field_keys), ["a", "c"])

    def test_get_cached_keys_reads_cache_without_recomputing(self):
        template, _mock_fetch = self._create_template(is_pdf_form=True, fetch_keys_return=["a", "b"])

        with patch.object(OnlyofficeTemplate_Connector, "get_keys") as mock_get_keys:
            keys = self.controller._get_cached_keys(template, "token")
            self.assertEqual(keys, ["a", "b"])
            mock_get_keys.assert_not_called()

    def test_get_cached_keys_falls_back_to_get_keys_when_empty(self):
        template, _mock_fetch = self._create_template(is_pdf_form=False)
        self.assertFalse(template.field_keys)

        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(template, "token")
            self.assertEqual(keys, ["x"])
            mock_get_keys.assert_called_once()
            self.assertEqual(json.loads(template.field_keys), ["x"])

    def test_corrupt_cache_is_recomputed(self):
        # A non-JSON value must not break filling; it should just recompute.
        template, _mock_fetch = self._create_template(is_pdf_form=True, fetch_keys_return=["a"])
        template.sudo().write({"field_keys": "not-json"})
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(template, "token")
            self.assertEqual(keys, ["x"])
            mock_get_keys.assert_called_once()
