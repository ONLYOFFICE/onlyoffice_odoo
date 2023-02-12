# -*- coding: utf-8 -*-

import threading
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo_connector.utils import config_constants
from odoo.addons.onlyoffice_odoo_connector.utils import config_utils

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")

    internal_jwt_secret = fields.Char("Internal JWT Secret")

    def set_values(self):
        res = super().set_values()
        self.env["ir.config_parameter"].set_param(config_utils.fix_url(config_constants.DOC_SERVER_PUBLIC_URL, self.doc_server_public_url))
        self.env["ir.config_parameter"].set_param(config_constants.DOC_SERVER_JWT_SECRET, self.doc_server_jwt_secret)
        self.env["ir.config_parameter"].set_param(config_constants.DOC_SERVER_JWT_HEADER, self.doc_server_jwt_header)
        return res

    def get_values(self):
        res = super().get_values()
        doc_server_public_url = config_utils.get_doc_server_public_url(self.env)
        doc_server_jwt_secret = config_utils.get_jwt_secret(self.env)
        doc_server_jwt_header = config_utils.get_jwt_header(self.env)
        res.update(
            doc_server_public_url=str(doc_server_public_url),
            doc_server_jwt_secret=str(doc_server_jwt_secret),
            doc_server_jwt_header=str(doc_server_jwt_header),
        )
        return res

        # we can validate settings here
