# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2024
#

from odoo import api, fields, models

from odoo.addons.onlyoffice_odoo.utils import config_utils
from odoo.addons.onlyoffice_odoo.utils import validation_utils

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server Public URL")
    doc_server_odoo_url = fields.Char("Odoo URL")
    doc_server_inner_url = fields.Char("Document Server Inner URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")
    doc_server_demo = fields.Boolean("Connect to demo ONLYOFFICE Docs server")

    internal_jwt_secret = fields.Char("Internal JWT Secret")

    @api.onchange("doc_server_public_url")
    def onchange_doc_server_public_url(self):
        if self.doc_server_public_url and not validation_utils.valid_url(self.doc_server_public_url):
            return {
                "warning": {
                    "title": "Warning",
                    "message": "Incorrect Document Server URL"
                }
            }

    @api.model
    def save_config_values(self):
        if validation_utils.valid_url(self.doc_server_public_url):
            config_utils.set_doc_server_public_url(self.env, self.doc_server_public_url)
        if validation_utils.valid_url(self.doc_server_odoo_url):
            config_utils.set_doc_server_odoo_url(self.env, self.doc_server_odoo_url)
        if validation_utils.valid_url(self.doc_server_inner_url):
            config_utils.set_doc_server_inner_url(self.env, self.doc_server_inner_url)
        config_utils.set_jwt_secret(self.env, self.doc_server_jwt_secret)
        config_utils.set_jwt_header(self.env, self.doc_server_jwt_header)
        config_utils.set_demo(self.env, self.doc_server_demo)
        
    def set_values(self):
        res = super().set_values()
        сurrent_demo_state = config_utils.get_demo(self.env)
        if not сurrent_demo_state and not self.doc_server_demo:
            validation_utils.settings_validation(self)
        self.save_config_values()

        return res

    def get_values(self):
        res = super().get_values()

        doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        doc_server_odoo_url = config_utils.get_base_or_odoo_url(self.env)
        doc_server_inner_url = config_utils.get_doc_server_inner_url(self.env)
        doc_server_jwt_secret = config_utils.get_jwt_secret(self.env)
        doc_server_jwt_header = config_utils.get_jwt_header(self.env)
        doc_server_demo = config_utils.get_demo(self.env)

        res.update(
            doc_server_public_url=doc_server_public_url,
            doc_server_odoo_url=doc_server_odoo_url,
            doc_server_inner_url=doc_server_inner_url,
            doc_server_jwt_secret=doc_server_jwt_secret,
            doc_server_jwt_header=doc_server_jwt_header,
            doc_server_demo=doc_server_demo
        )

        return res

