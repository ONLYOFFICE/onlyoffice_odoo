# -*- coding: utf-8 -*-
{
    'name': "ONLYOFFICE",

    'summary': "Edit and collaborate on office files within Odoo Documents.",

    'description': "The ONLYOFFICE connector allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",

    'author': "ONLYOFFICE",
    'website': "https://www.onlyoffice.com",

    'category': 'Productivity',
    'version': '2.0.0',

    'depends': ['base', 'mail'],

    "external_dependencies": {"python": ["pyjwt"]},

    # always loaded
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],

    'license': 'LGPL-3',
    'support': 'support@onlyoffice.com',

    'images': [ "static/description/main_screenshot.png", "static/description/document.png", "static/description/sales_section.png", "static/description/discuss_section.png", "static/description/settings.png" ],

    'installable': True,
    'application': True,

    'assets': {
        'mail.assets_messaging': [
            'onlyoffice_odoo/static/src/models/*.js',
        ],
        'web.assets_backend': [
            'onlyoffice_odoo/static/src/components/*/*.xml',
        ],
    },
}
