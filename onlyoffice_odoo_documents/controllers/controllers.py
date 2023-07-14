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

import logging
import json

from odoo import http
from odoo.http import request
from odoo.tools.translate import _

from odoo.addons.onlyoffice_odoo.utils import file_utils

_logger = logging.getLogger(__name__)

class OnlyofficeDocuments_Connector(http.Controller):
    @http.route("/onlyoffice/documents/file/create", auth="user", methods=["POST"], type="json")
    def post_file_create(self, folder_id, format, title):
        result = {"error": None, "file_id": None}

        try:
            _logger.info("Getting new file template %s %s" % (request.env.user.lang, format))
            file_data = file_utils.get_default_file_template(request.env.user.lang, format)

            data = {
                'name': title + "." + format,
                'mimetype': file_utils.get_mime_by_ext(format),
                'raw': file_data,
                'folder_id': int(folder_id)
            }

            document = request.env["documents.document"].create(data)
            result["file_id"] = document.attachment_id.id
            
        except Exception as ex:
            _logger.exception("Failed to create document %s" % str(ex))
            result["error"] = _("Failed to create document")

        return json.dumps(result)