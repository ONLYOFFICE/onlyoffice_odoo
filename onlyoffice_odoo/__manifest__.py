# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).
# pylint: disable=pointless-statement
{
    "name": "ONLYOFFICE",
    "summary": "Edit and collaborate on office files within Odoo Documents.",
    "description": "The ONLYOFFICE app allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",  # noqa: E501
    "author": "ONLYOFFICE",
    "website": "https://www.onlyoffice.com/office-for-odoo?utm_source=odoo_market",
    "category": "Productivity",
    "version": "19.0.6.4.0",
    "license": "LGPL-3",
    "development_status": "Production/Stable",
    "maintainers": ["ONLYOFFICE"],
    "support": "support@onlyoffice.com",
    "depends": ["base", "mail"],
    "external_dependencies": {"python": ["pyjwt"]},
    "data": [
        "security/ir.model.access.csv",
        "views/templates.xml",
        "views/res_config_settings_views.xml",
    ],
    "images": [
        "static/description/main_screenshot.png",
        "static/description/document.png",
        "static/description/sales_section.png",
        "static/description/discuss_section.png",
        "static/description/settings.png",
    ],
    "installable": True,
    "application": True,
    "assets": {
        "web.assets_backend": [
            "onlyoffice_odoo/static/src/actions/*",
            "onlyoffice_odoo/static/src/components/*/*.xml",
            "onlyoffice_odoo/static/src/models/*.js",
            "onlyoffice_odoo/static/src/views/**/*",
            "onlyoffice_odoo/static/src/css/*",
        ],
    },
}
