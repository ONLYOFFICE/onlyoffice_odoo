# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2024
#

import logging
import json

from odoo import http
from odoo.http import request
from odoo.tools.translate import _

from werkzeug.exceptions import Forbidden
from odoo.exceptions import AccessError

from odoo.addons.onlyoffice_odoo.utils import file_utils
from odoo.addons.onlyoffice_odoo.controllers.controllers import Onlyoffice_Connector

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

class OnlyofficeDocuments_Inherited_Connector(Onlyoffice_Connector):
    @http.route("/onlyoffice/editor/document/<int:document_id>", auth="public", type="http", website=True)
    def render_document_editor(self, document_id, access_token=None):
        return request.render("onlyoffice_odoo.onlyoffice_editor", self.prepare_document_editor(document_id, access_token))
    
    def prepare_document_editor(self, document_id, access_token):
        document = request.env['documents.document'].browse(int(document_id))
        try:
            document.check_access_rule("read")
        except AccessError:
            _logger.error("User has no read access rights to open this document")
            raise Forbidden()
        
        attachment = self.get_attachment(document.attachment_id.id)
        if not attachment:
            _logger.error("Current document has no attachments")
            raise Forbidden()
        
        try:
            document.check_access_rule("write")
            return self.prepare_editor_values(attachment, access_token, True)
        except AccessError:
            _logger.debug("Current user has no write access")
            return self.prepare_editor_values(attachment, access_token, False)