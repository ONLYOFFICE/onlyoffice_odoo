# -*- coding: utf-8 -*-
{
    'name': "ONLYOFFICE Documents",

    'summary': "Edit and collaborate on office files within Odoo Documents.",

    'description': "The ONLYOFFICE connector allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",

    'author': "ONLYOFFICE",
    'website': "https://www.onlyoffice.com",

    'category': 'Productivity',
    'version': '2.0.1',

    'depends': ['onlyoffice_odoo', 'documents'],

    # always loaded
    'data': [
    ],

    'license': 'LGPL-3',
    'support': 'support@onlyoffice.com',

    'images': [ "static/description/main_screenshot.png", "static/description/editors.png", "static/description/edit_files.png", "static/description/create_files.png" ],

    'installable': True,
    'application': True,

    'assets': {
        'mail.assets_messaging': [
            'onlyoffice_odoo_documents/static/src/models/*.js',
        ],
        'web.assets_backend': [
            'onlyoffice_odoo_documents/static/src/components/*/*.xml',
            'onlyoffice_odoo_documents/static/src/documents_view/**/*',
            'onlyoffice_odoo_documents/static/src/onlyoffice_create_template/**/*',
        ],
    },
}
