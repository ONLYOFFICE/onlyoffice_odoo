# pylint: disable=pointless-statement
{
    "name": "ONLYOFFICE Documents",
    "summary": "Edit and collaborate on office files within Odoo Documents.",
    "description": "The ONLYOFFICE app allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",  # noqa: E501
    "author": "ONLYOFFICE",
    "website": "https://github.com/ONLYOFFICE/onlyoffice_odoo",
    "category": "Productivity",
    "version": "5.2.1",
    "depends": ["onlyoffice_odoo", "documents"],
    # always loaded
    "data": [
        "security/ir.model.access.csv",
        "views/onlyoffice_templates_share.xml",
    ],
    "license": "LGPL-3",
    "support": "support@onlyoffice.com",
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
            "onlyoffice_odoo_documents/static/src/models/*.js",
            "onlyoffice_odoo_documents/static/src/components/*/*.xml",
            "onlyoffice_odoo_documents/static/src/documents_view/**/*",
            "onlyoffice_odoo_documents/static/src/onlyoffice_create_template/**/*",
            "onlyoffice_odoo_documents/static/src/css/*",
        ],
    },
}
