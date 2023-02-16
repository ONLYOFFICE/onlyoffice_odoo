# -*- coding: utf-8 -*-
{
    'name': "onlyoffice_odoo_connector",

    'summary': "Edit and collaborate on office files within Odoo Documents.",

    'description': "The ONLYOFFICE connector allows users to edit and collaborate on office files within Odoo Documents using ONLYOFFICE Docs. You can work with text documents, spreadsheets, and presentations, co-author documents in real time using two co-editing modes (Fast and Strict), Track Changes, comments, and built-in chat.",

    'author': "ONLYOFFICE",
    'website': "https://onlyoffice.com",

    # Categories can be used to filter modules in modules listing
    # Check https://github.com/odoo/odoo/blob/16.0/odoo/addons/base/data/ir_module_category_data.xml
    # for the full list
    'category': 'Productivity',
    'version': '0.1',

    'depends': ['base'],

    "external_dependencies": {"python": ["pyjwt"]},

    # always loaded
    'data': [
        'views/templates.xml',
        'views/res_config_settings_views.xml',
    ],

    'license': 'AGPL-3',

    'installable': True,
    'application': True,

    'assets': {
        'mail.assets_messaging': [
            'onlyoffice_odoo_connector/static/src/models/*.js',
        ],
        'web.assets_backend': [
            'onlyoffice_odoo_connector/static/src/components/*/*.xml',
        ],
    },
}
