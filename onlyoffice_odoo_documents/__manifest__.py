# Copyright (C) 2026 Ascensio System SIA
# pylint: disable=pointless-statement
{
    "name": "ONLYOFFICE Documents",
    "summary": "Edit and collaborate on office files within Odoo Documents.",
    "description": "The ONLYOFFICE app allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",  # noqa: E501
    "author": "ONLYOFFICE",
    "website": "https://www.onlyoffice.com/office-for-odoo?utm_source=odoo_market",
    "category": "Productivity",
    "version": "18.0.5.3.1",
    "license": "LGPL-3",
    "support": "support@onlyoffice.com",
    "depends": ["onlyoffice_odoo", "documents"],
    "data": [
        "security/ir.model.access.csv",
        "views/onlyoffice_templates_share.xml",
    ],
    "images": [
        "static/description/main_screenshot.png",
        "static/description/editors.png",
        "static/description/edit_files.png",
        "static/description/create_files.png",
    ],
    "installable": True,
    "application": True,
    "assets": {
        "web.assets_backend": [
            "onlyoffice_odoo_documents/static/src/js/desktop_mode_init.js",
            "onlyoffice_odoo_documents/static/src/js/desktop_restriction.js",
            "onlyoffice_odoo_documents/static/src/js/desktop_auth.js",
            "onlyoffice_odoo_documents/static/src/models/*.js",
            "onlyoffice_odoo_documents/static/src/components/*/*.xml",
            "onlyoffice_odoo_documents/static/src/documents_view/**/*",
            "onlyoffice_odoo_documents/static/src/onlyoffice_create_template/**/*",
            "onlyoffice_odoo_documents/static/src/css/desktop_restriction.css",
            "onlyoffice_odoo_documents/static/src/css/*.css",
        ],
    },
}
