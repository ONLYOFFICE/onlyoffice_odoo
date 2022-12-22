# -*- coding: utf-8 -*-

import threading
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")

    def set_values(self):
        res = super().set_values()
        self.env["ir.config_parameter"].set_param("onlyoffice_connector.doc_server_public_url", self.doc_server_public_url)
        self.env["ir.config_parameter"].set_param("onlyoffice_connector.doc_server_jwt_secret", self.doc_server_jwt_secret)
        return res

    def get_values(self):
        res = super().get_values()
        doc_server_public_url = self.env["ir.config_parameter"].sudo().get_param("onlyoffice_connector.doc_server_public_url")
        doc_server_jwt_secret = self.env["ir.config_parameter"].sudo().get_param("onlyoffice_connector.doc_server_jwt_secret")
        res.update(
            doc_server_public_url=str(doc_server_public_url),
            doc_server_jwt_secret=str(doc_server_jwt_secret),
        )
        return res

        # we can validate settings here
