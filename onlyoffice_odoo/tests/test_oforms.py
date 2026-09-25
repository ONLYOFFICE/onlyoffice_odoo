# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from unittest.mock import MagicMock, patch

import requests

from odoo.tests import tagged
from odoo.tests.common import HttpCase

REQUESTS_GET = "odoo.addons.onlyoffice_odoo.controllers.main.requests.get"


@tagged("post_install", "-at_install")
class TestOformsProxy(HttpCase):
    """The /onlyoffice/oforms* routes behind the form gallery: they map the public forms API; the API is mocked."""

    def setUp(self):
        super().setUp()
        self.env["res.users"].create({"name": "OO Gallery", "login": "_oo_gallery", "password": "_oo_gallery_pass"})
        self.authenticate("_oo_gallery", "_oo_gallery_pass")

    def _call(self, route, api_response=None, side_effect=None, **params):
        api = MagicMock()
        api.json.return_value = api_response
        with patch(REQUESTS_GET, return_value=api, side_effect=side_effect) as get:
            body = {"jsonrpc": "2.0", "method": "call", "params": params}
            response = self.url_open(route, data=json.dumps(body), headers={"Content-Type": "application/json"})
        return response.json(), get

    def test_category_types_take_the_localized_name(self):
        localized = {"data": [{"attributes": {"locale": "de", "name": "Formulare"}}]}
        api = {
            "data": [
                {"id": 1, "attributes": {"categoryId": 7, "categoryTitle": "categorie", "name": "Forms"}},
                {"id": 2, "attributes": {"categoryTitle": "type", "name": "Letters", "localizations": localized}},
            ]
        }
        data, _get = self._call("/onlyoffice/oforms/category-types", api, locale="de")
        self.assertEqual(
            data["result"]["data"],
            [
                {"id": 1, "categoryId": 7, "name": "Forms", "type": "categorie"},
                {"id": 2, "categoryId": None, "name": "Formulare", "type": "type"},
            ],
        )

    def test_subcategories_of_an_unknown_type_are_empty_without_calling_the_api(self):
        data, get = self._call("/onlyoffice/oforms/subcategories", {}, category_type="unknown")
        self.assertEqual(data["result"], {"data": []})
        get.assert_not_called()

    def test_subcategories_are_mapped_to_their_endpoint(self):
        api = {"data": [{"id": 5, "attributes": {"categorie": "HR"}}]}
        data, get = self._call("/onlyoffice/oforms/subcategories", api, category_type="categorie")
        self.assertEqual(data["result"]["data"], [{"id": 5, "name": "HR", "category_type": "categories"}])
        self.assertTrue(get.call_args.args[0].endswith("/categories"))

    def test_forms_request_maps_the_gallery_filters(self):
        params = {"filters[categories][$eq]": 5, "type": "pdf", "filters[name_form][$containsi]": "lease"}
        _data, get = self._call("/onlyoffice/oforms", {"data": []}, params=params)
        api_params = get.call_args.kwargs["params"]
        self.assertEqual(api_params["filters[categories][id][$eq]"], 5)
        self.assertEqual(api_params["filters[form_exts][ext][$eq]"], "pdf")
        self.assertEqual(api_params["filters[name_form][$containsi]"], "lease")

    def test_api_failure_is_reported_to_the_gallery(self):
        data, _get = self._call("/onlyoffice/oforms/locales", side_effect=requests.exceptions.ConnectionError("down"))
        self.assertIn("Failed to connect to Forms API", data["error"]["data"]["message"])
