# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2023
#

from odoo import api, fields, models

from odoo.addons.onlyoffice_odoo.utils import config_utils
from odoo.addons.onlyoffice_odoo.utils import validation_utils

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")

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
        config_utils.set_jwt_secret(self.env, self.doc_server_jwt_secret)
        config_utils.set_jwt_header(self.env, self.doc_server_jwt_header)

    def set_values(self):
        res = super().set_values()
        validation_utils.settings_validation(self)
        self.save_config_values()

        return res

    def get_values(self):
        res = super().get_values()

        doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        doc_server_jwt_secret = config_utils.get_jwt_secret(self.env)
        doc_server_jwt_header = config_utils.get_jwt_header(self.env)

        res.update(
            doc_server_public_url=doc_server_public_url,
            doc_server_jwt_secret=doc_server_jwt_secret,
            doc_server_jwt_header=doc_server_jwt_header,
        )

        return res

