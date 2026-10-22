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

    def test_categories_keep_only_subcategories_with_forms(self):
        def subcategory(document_id, name, count):
            return {"id": 1, "documentId": document_id, "name": name, "oforms": {"count": count}}

        api = {
            "data": [
                {
                    "key": "business",
                    "name": "Geschäftlich",
                    "parent_categories": [
                        {
                            "documentId": "c1",
                            "name": "Integrations",
                            "subcategories": [subcategory("s1", "Odoo", 24), subcategory("s2", "Empty", 0)],
                        },
                        {"documentId": "c2", "name": "Empty group", "subcategories": [subcategory("s3", "Empty", 0)]},
                    ],
                },
                {"key": "personal", "name": "Privat", "parent_categories": []},
            ]
        }
        data, get = self._call("/onlyoffice/oforms/categories", api, ext="docx", locale="de")
        self.assertEqual(
            data["result"]["data"],
            [
                {
                    "key": "business",
                    "name": "Geschäftlich",
                    "categories": [
                        {"id": "c1", "name": "Integrations", "subcategories": [{"id": "s1", "name": "Odoo"}]}
                    ],
                }
            ],
        )
        self.assertTrue(get.call_args.args[0].endswith("/purposes"))
        api_params = get.call_args.kwargs["params"]
        self.assertEqual(api_params["locale"], "de")
        ext_filter = (
            "populate[parent_categories][populate][subcategories][populate][oforms][filters][form_exts][ext][$eq]"
        )
        self.assertEqual(api_params[ext_filter], "docx")

    def test_forms_request_maps_the_gallery_filters(self):
        params = {"ext": "docx", "search": "lease", "subcategory": "s1", "purpose": "business", "page": 2}
        _data, get = self._call("/onlyoffice/oforms", {"data": []}, **params)
        self.assertTrue(get.call_args.args[0].endswith("/oforms"))
        api_params = get.call_args.kwargs["params"]
        self.assertEqual(api_params["filters[form_exts][ext][$eq]"], "docx")
        self.assertEqual(api_params["populate[file_oform][filters][url][$endsWith]"], ".docx")
        self.assertEqual(api_params["filters[name_form][$containsi]"], "lease")
        self.assertEqual(api_params["filters[subcategories][documentId][$eq]"], "s1")
        self.assertEqual(api_params["filters[subcategories][parent_categories][purpose][key][$eq]"], "business")
        self.assertEqual(api_params["pagination[page]"], 2)

    def test_forms_request_without_filters(self):
        _data, get = self._call("/onlyoffice/oforms", {"data": []})
        api_params = get.call_args.kwargs["params"]
        self.assertEqual(api_params["filters[form_exts][ext][$eq]"], "pdf")
        self.assertEqual(api_params["locale"], "en")
        self.assertFalse([key for key in api_params if "name_form][$containsi" in key or "subcategories" in key])

    def test_api_failure_is_reported_to_the_gallery(self):
        data, _get = self._call("/onlyoffice/oforms/locales", side_effect=requests.exceptions.ConnectionError("down"))
        self.assertIn("Failed to connect to Forms API", data["error"]["data"]["message"])
