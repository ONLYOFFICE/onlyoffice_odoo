# -*- coding: utf-8 -*-
{
    'name': "ONLYOFFICE Template",

    'summary': "Edit and collaborate on office files within Odoo Documents.",

    'description': "The ONLYOFFICE connector allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",

    'author': "ONLYOFFICE",
    'website': "https://www.onlyoffice.com",

    'category': 'Productivity',
    'version': '2.0.0',

    'depends': ['base', 'sale', 'onlyoffice_odoo', 'mail'],

    "external_dependencies": {"python": ["pyjwt"]},

    # always loaded
    'data': [
        'security/ir.model.access.csv',
        'views/onlyoffice_menu_views.xml',
        'views/templates_extension.xml',
        'views/sale_order_form_extension.xml',
    ],

    'license': 'LGPL-3',
    'support': 'support@onlyoffice.com',

    'images': [ "static/description/main_screenshot.png", "static/description/icon.png"],

    'installable': True,
    'application': True,

    'assets': {
        'web.assets_backend': [
            'onlyoffice_template/static/src/css/*',
            'onlyoffice_template/static/src/views/**/*',
        ],
    },
}
