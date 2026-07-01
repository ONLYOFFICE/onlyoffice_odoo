# pylint: disable=pointless-statement
{
    "name": "ONLYOFFICE DMS",
    "summary": "Edit and preview DMS files with ONLYOFFICE Docs.",
    "description": (
        "Integrates ONLYOFFICE Docs with the OCA DMS module. "
        "Allows viewing and editing DMS files (docx, xlsx, pptx, pdf) "
        "directly in Odoo using the ONLYOFFICE editor, with fine-grained "
        "per-file and per-user role control on top of DMS permissions."
    ),
    "author": "Data Dance s.r.o., ONLYOFFICE, Odoo Community Association (OCA)",
    "website": "https://www.onlyoffice.com/office-for-odoo?utm_source=odoo_market",
    "category": "Document Management",
    "version": "1.0.3",
    "license": "LGPL-3",
    "support": "support@onlyoffice.com",
    "depends": ["onlyoffice_odoo", "dms"],
    "data": [
        "security/ir.model.access.csv",
        "views/onlyoffice_dms_access_views.xml",
        "views/dms_directory_views.xml",
        "views/dms_file_views.xml",
    ],
    "images": [
        "static/description/main_screenshot.png",
        "static/description/01_creating_files.png",
        "static/description/02_new_onlyoffice_document.png",
        "static/description/03_file_editing.png",
        "static/description/04_edit_in_onlyoffice.png",
        "static/description/05_preview_in_onlyoffice.png",
        "static/description/06_onlyoffice_access.png",
        "static/description/07_directory_level_access.png",
    ],
    "assets": {
        "web.assets_backend": [
            "onlyoffice_odoo_dms/static/src/css/dms_editor_action.css",
            "onlyoffice_odoo_dms/static/src/js/oo_role_select.js",
            "onlyoffice_odoo_dms/static/src/js/dms_editor_action.js",
            "onlyoffice_odoo_dms/static/src/xml/dms_editor_action.xml",
            # JS must load after DMS views register their button templates
            (
                "after",
                "dms/static/src/js/views/file_list_view.esm.js",
                "onlyoffice_odoo_dms/static/src/js/dms_file_onlyoffice.js",
            ),
            # XML must load after DMS button templates are defined
            (
                "after",
                "dms/static/src/js/views/file_list_renderer.xml",
                "onlyoffice_odoo_dms/static/src/xml/dms_file_onlyoffice.xml",
            ),
        ],
    },
    "installable": True,
    "application": False,
}
