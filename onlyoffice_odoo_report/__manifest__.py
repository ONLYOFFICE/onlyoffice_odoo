{
    "name": "ONLYOFFICE reports",
    "version": "19.0.1.0.0",
    "category": "Productivity",
    "author": "Data Dance s.r.o.",
    "website": "https://github.com/ONLYOFFICE/onlyoffice_odoo",
    "description": """
        Adds support to render reports using ONLYOFFICE Docs backend.
    """,
    "depends": ["onlyoffice_odoo_templates"],
    "data": [
        "views/ir_actions_report_views.xml",
        "views/onlyoffice_odoo_templates_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "onlyoffice_odoo_report/static/src/js/report/action_manager_report.esm.js",
        ],
    },
    "auto_install": False,
    "license": "LGPL-3",
}
