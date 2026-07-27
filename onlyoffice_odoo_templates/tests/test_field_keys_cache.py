# Copyright (C) 2026 Ascensio System SIA
import base64
import json
from unittest.mock import patch

from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo_templates.controllers.controllers import OnlyofficeTemplate_Connector


class TestFieldKeysCache(TransactionCase):
    """The PDF Form field keys depend only on the template PDF, so they are cached
    on the template (keyed by attachment checksum) to avoid an extra synchronous
    docbuilder round-trip on every fill. See ``_get_cached_keys``.
    """

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

    def test_keys_are_computed_then_cached(self):
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a", "b"]) as mock_get_keys:
            # First call: cache empty -> compute via get_keys and store.
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "b"])
            self.assertEqual(mock_get_keys.call_count, 1)

            cached = json.loads(self.template.field_keys)
            self.assertEqual(cached["keys"], ["a", "b"])
            self.assertEqual(cached["checksum"], self.template.attachment_id.checksum)

            # Second call: same PDF -> cache hit, get_keys not called again.
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "b"])
            self.assertEqual(mock_get_keys.call_count, 1)

    def test_cache_invalidated_when_pdf_changes(self):
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a"]) as mock_get_keys:
            self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(mock_get_keys.call_count, 1)

        # Changing the underlying PDF changes the attachment checksum, which must
        # invalidate the cache and trigger a recompute.
        self.template.attachment_id.write({"datas": base64.b64encode(b"%PDF-1.4 different contents")})

        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["a", "c"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["a", "c"])
            self.assertEqual(mock_get_keys.call_count, 1)
            self.assertEqual(json.loads(self.template.field_keys)["keys"], ["a", "c"])

    def test_corrupt_cache_is_recomputed(self):
        # A non-JSON value must not break filling; it should just recompute.
        self.template.sudo().write({"field_keys": "not-json"})
        with patch.object(OnlyofficeTemplate_Connector, "get_keys", return_value=["x"]) as mock_get_keys:
            keys = self.controller._get_cached_keys(self.template, "token")
            self.assertEqual(keys, ["x"])
            self.assertEqual(mock_get_keys.call_count, 1)
