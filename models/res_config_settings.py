# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2023
#
# This program is a free software product. You can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License (AGPL)
# version 3 as published by the Free Software Foundation. In accordance with
# Section 7(a) of the GNU AGPL its Section 15 shall be amended to the effect
# that Ascensio System SIA expressly excludes the warranty of non-infringement
# of any third-party rights.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR  PURPOSE. For
# details, see the GNU AGPL at: http://www.gnu.org/licenses/agpl-3.0.html
#
# You can contact Ascensio System SIA at 20A-12 Ernesta Birznieka-Upisha
# street, Riga, Latvia, EU, LV-1050.
#
# The  interactive user interfaces in modified source and object code versions
# of the Program must display Appropriate Legal Notices, as required under
# Section 5 of the GNU AGPL version 3.
#
# Pursuant to Section 7(b) of the License you must retain the original Product
# logo when distributing the program. Pursuant to Section 7(e) we decline to
# grant you any rights under trademark law for use of our trademarks.
#
# All the Product's GUI elements, including illustrations and icon sets, as
# well as technical writing content are licensed under the terms of the
# Creative Commons Attribution-ShareAlike 4.0 International. See the License
# terms at http://creativecommons.org/licenses/by-sa/4.0/legalcode
#

from odoo import fields, models, _

from odoo.addons.onlyoffice_odoo.utils import config_utils

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    doc_server_public_url = fields.Char("Document Server URL")
    doc_server_jwt_secret = fields.Char("Document Server JWT Secret")
    doc_server_jwt_header = fields.Char("Document Server JWT Header")

    internal_jwt_secret = fields.Char("Internal JWT Secret")

    def set_values(self):
        res = super().set_values()

        config_utils.set_doc_server_public_url(self.env, self.doc_server_public_url)
        config_utils.set_jwt_secret(self.env, self.doc_server_jwt_secret)
        config_utils.set_jwt_header(self.env, self.doc_server_jwt_header)

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

        # we can validate settings here
