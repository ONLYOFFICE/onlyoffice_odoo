# Copyright 2024 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

{
    'name': 'OnlyOffice Templates',
    'summary': 'OnlyOffice Templates',
    'version': '1.0.1',
    'category': 'Productivity',
    'website': 'https://www.open2bizz.nl/',
    'author': 'Open2Bizz',
    'license': 'LGPL-3',
    'installable': True,
    'depends': [
        'base',
        'onlyoffice_odoo',
    ],
    'data': [
        'security/ir_model_access.xml',
        'views/actions.xml',
        'views/ir_attachment.xml',
        'wizard/attachment_from_template.xml'
    ]
}
