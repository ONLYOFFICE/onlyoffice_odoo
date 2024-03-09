# -*- coding: utf-8 -*-

#
# (c) Copyright Ascensio System SIA 2023
#

from odoo import http
from odoo.http import request
from odoo.tools.translate import _
from odoo.addons.onlyoffice_odoo.utils import file_utils
import base64
import requests
import base64
from urllib.request import urlopen

class OnlyofficeTemplate_Connector(http.Controller):
    @http.route("/onlyoffice/template/file/create", auth="user", methods=["POST"], type="json")
    def template_create(self):
        file_data = file_utils.get_default_file_template(request.env.user.lang, "docx")
        mimetype = file_utils.get_mime_by_ext("docx")

        attachment = request.env['onlyoffice.template'].create({
            "name": "new_template.docxf",
            "file": base64.encodebytes(file_data),
            "mimetype": mimetype
        })
        
        return {
            "file_id": attachment.attachment_id.id
        }
    
    @http.route("/onlyoffice/upload_file_from_url", auth="user", methods=["POST"], type="json")
    def post_file_create(self, url, title):
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()

            if response.status_code != 200:
                raise Exception("HTTP error", response.status_code)
            if 'Content-Length' not in response.headers:
                raise Exception("Empty file")
            if not response.headers['Content-Type']:
                raise Exception("Unknown content type")

            filename = title
            data = urlopen(url).read()


            attachment = request.env['onlyoffice.template'].create({
                "name": filename,
                "file": base64.encodebytes(data),
                "mimetype": response.headers['Content-Type'],
            })
            
            return {'ids': attachment.id}

        except Exception as e:
            raise Exception("error", str(e))