# -*- coding: utf-8 -*-
{
    'name': "onlyoffice_odoo_connector",

    'summary': """
        Short (1 phrase/line) summary of the module's purpose, used as
        subtitle on modules listing or apps.openerp.com""",

    'description': """
        Long description of module's purpose
    """,

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

    'assets': {
        'mail.assets_messaging': [
            'onlyoffice_odoo_connector/static/src/models/*.js',
        ],
        'web.assets_backend': [
            'onlyoffice_odoo_connector/static/src/components/*/*.xml',
        ],
    },
}
