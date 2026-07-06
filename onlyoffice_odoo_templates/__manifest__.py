# Copyright (C) 2026 Ascensio System SIA
# pylint: disable=pointless-statement
{
    "name": "ONLYOFFICE Templates",
    "summary": "Automate form creation with inserting fields from Odoo in templates.",
    "description": "Work with fillable templates in Odoo using ONLYOFFICE. Create templates based on the data and fields available in Odoo, fill them out and print with several clicks.",  # noqa: E501
    "author": "ONLYOFFICE, Data Dance s.r.o.",
    "website": "https://www.onlyoffice.com/office-for-odoo?utm_source=odoo_market",
    "category": "Productivity",
    "version": "4.4.2",
    "license": "LGPL-3",
    "support": "support@onlyoffice.com",
    "depends": ["base", "onlyoffice_odoo", "web"],
    "external_dependencies": {"python": ["pyjwt"]},
    "data": [
        "security/onlyoffice_templates_security.xml",
        "security/ir.model.access.csv",
        "views/onlyoffice_menu_views.xml",
        "views/res_config_settings_views.xml",
        "views/ir_actions_report_views.xml",
    ],
    "demo": ["data/templates_data.xml"],
    "images": [
        "static/description/main_screenshot.png",
        "static/description/create_templates.png",
        "static/description/edit_templates.png",
        "static/description/access_rights.png",
        "static/description/work_with_templates.png",
    ],
    "installable": True,
    "application": True,
    "assets": {
        "web.assets_backend": [
            "onlyoffice_odoo_templates/static/src/css/*",
            "onlyoffice_odoo_templates/static/src/views/**/*",
            "onlyoffice_odoo_templates/static/src/js/report/action_manager_report.esm.js",
        ],
    },
}
