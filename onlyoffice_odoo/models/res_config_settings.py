# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2023
#

from odoo import fields, models, _

from odoo.addons.onlyoffice_odoo.utils import config_utils

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")
    doc_server_demo = fields.Boolean("Connect to demo ONLYOFFICE Docs server")

    internal_jwt_secret = fields.Char("Internal JWT Secret")

    def set_values(self):
        res = super().set_values()

        config_utils.set_doc_server_public_url(self.env, self.doc_server_public_url)
        config_utils.set_jwt_secret(self.env, self.doc_server_jwt_secret)
        config_utils.set_jwt_header(self.env, self.doc_server_jwt_header)
        config_utils.set_demo(self.env, self.doc_server_demo)
        
        return res

    def get_values(self):
        res = super().get_values()

        doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        doc_server_jwt_secret = config_utils.get_jwt_secret(self.env)
        doc_server_jwt_header = config_utils.get_jwt_header(self.env)
        doc_server_demo = config_utils.get_demo(self.env)

        res.update(
            doc_server_public_url=doc_server_public_url,
            doc_server_jwt_secret=doc_server_jwt_secret,
            doc_server_jwt_header=doc_server_jwt_header,
            doc_server_demo=doc_server_demo
        )

        return res

        # we can validate settings here
