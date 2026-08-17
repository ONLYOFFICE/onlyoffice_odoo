# Copyright (C) 2026 Ascensio System SIA
import base64
import json
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_templates.controllers.controllers import OnlyofficeTemplate_Connector


@tagged("post_install", "-at_install")
class TestOnlyofficeTemplateControllers(TransactionCase):
    """Tests for _get_cached_keys, which caches PDF form field keys by attachment checksum."""

    def setUp(self):
        super().setUp()
        model = self.env["ir.model"].search([("model", "=", "res.partner")], limit=1)
        self.template = self.env["onlyoffice.odoo.templates"].create(
            {
                "name": "Test template",
                "template_model_id": model.id,
            }
        )
        self.controller = OnlyofficeTemplate_Connector()

    # -- Caching --

    def test_keys_are_computed_then_cached(self):
        """First call computes keys via get_keys; second call hits the cache."""
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a", "b"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "b"])
            self.assertEqual(mock_get_keys.call_count, 1)

            cached = json.loads(self.template.field_keys)
            self.assertEqual(cached["keys"], ["a", "b"])
            self.assertEqual(cached["checksum"], self.template.attachment_id.checksum)

            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "b"])
            self.assertEqual(mock_get_keys.call_count, 1)

    def test_cache_invalidated_when_pdf_changes(self):
        """Changing the template PDF changes its checksum and forces a recompute."""
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a"]) as mock_get_keys:
            self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(mock_get_keys.call_count, 1)

        self.template.attachment_id.write({"datas": base64.b64encode(b"%PDF-1.4 different contents")})

        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a", "c"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "c"])
            self.assertEqual(mock_get_keys.call_count, 1)
            self.assertEqual(json.loads(self.template.field_keys)["keys"], ["a", "c"])

    def test_corrupt_cache_is_recomputed(self):
        """A non-JSON cache value is ignored and recomputed instead of raising."""
        self.template.sudo().write({"field_keys": "not-json"})
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["x"])
            self.assertEqual(mock_get_keys.call_count, 1)
