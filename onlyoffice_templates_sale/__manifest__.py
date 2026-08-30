# Copyright 2024 Open2Bizz <info@open2bizz.nl>
# License LGPL-3

{
    'name': 'OnlyOffice Templates Sale/CRM',
    'summary': 'OnlyOffice Templates Sale/CRM',
    'version': '1.0.1',
    'category': 'Productivity',
    'website': 'https://www.open2bizz.nl/',
    'author': 'Open2Bizz',
    'license': 'LGPL-3',
    'installable': True,
    'depends': [
        'onlyoffice_templates',
        'sale',
        'crm',
    ],
    'data': [
        'views/actions.xml',
    ]
}
