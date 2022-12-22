# -*- coding: utf-8 -*-
import json
import logging
import markupsafe

from odoo import http
from odoo.http import request
from odoo.tools import replace_exceptions

from odoo.addons.onlyoffice_odoo_connector.utils import file_utils

from urllib.request import urlopen

_logger = logging.getLogger(__name__)


class Onlyoffice_Connector(http.Controller):
    @http.route("/onlyoffice/file/content/<int:attachment_id>", auth="public")
    def get_file_content(self, attachment_id, access_token=None):

        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return request.not_found()

        # check if we can impersonate user and check access via internal method
        # attachment.validate_access(access_token)

        stream = request.env["ir.binary"]._get_stream_from(attachment, "datas", None, "name", None)

        send_file_kwargs = {"as_attachment": True, "max_age": None}

        return stream.get_response(**send_file_kwargs)

    @http.route("/onlyoffice/editor/<int:attachment_id>", auth="public", type="http", website=True)
    def render_editor(self, attachment_id, access_token=None):
        attachment = self.get_attachment(attachment_id)
        if not attachment:
            return request.not_found()

        attachment.validate_access(access_token)

        return request.render("onlyoffice_odoo_connector.onlyoffice_editor", self.prepare_editor_values(attachment, access_token))

    @http.route("/onlyoffice/editor/callback/<int:attachment_id>", auth="public", methods=["POST"], type="http", csrf=False)
    def editor_callback(self, attachment_id, access_token=None):

        response_json = {"error": 0}

        try:
            body = request.get_json_data()

            attachment = self.get_attachment(attachment_id)
            if not attachment:
                raise Exception("attachment not found")

            # impersonate
            # attachment.validate_access(access_token)

            # jwt

            status = body["status"]

            if (status == 2) | (status == 3):  # mustsave, corrupted
                file_url = body.get("url")
                attachment.write({"raw": urlopen(file_url).read()})

        except Exception as ex:
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )

    def prepare_editor_values(self, attachment, access_token):
        data = attachment.read(["id", "checksum", "public", "name", "access_token"])[0]

        docserver_url = request.env["ir.config_parameter"].sudo().get_param("onlyoffice_connector.doc_server_public_url")
        odoo_url = request.env["ir.config_parameter"].sudo().get_param("web.base.url")

        filename = data["name"]

        editor_config = {
            "width": "100%",
            "height": "100%",
            "type": "desktop",
            "documentType": file_utils.getFileType(filename),
            "document": {
                "title": filename,
                "url": odoo_url + "/onlyoffice/file/content/" + str(data["id"]) + ("?access_token=" + access_token if access_token else ""),
                "fileType": file_utils.getFileExt(filename),
                "key": data["checksum"],
                "permissions": {"edit": True},
            },
            "editorConfig": {
                "callbackUrl": odoo_url + "/onlyoffice/editor/callback/" + str(data["id"]) + ("?access_token=" + access_token if access_token else ""),
                "mode": "edit",
                "lang": request.env.user.lang,
                "user": {"id": request.env.user.id, "name": request.env.user.name},
                "customization": {},
            },
        }

        return {"docTitle": filename, "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js", "editorConfig": markupsafe.Markup(json.dumps(editor_config))}

    def get_attachment(self, attachment_id):

        # remove sudo
        IrAttachment = request.env["ir.attachment"].sudo()
        try:
            return IrAttachment.browse([attachment_id]).exists().ensure_one()
        except Exception:
            return None


# save https://github.com/odoo/odoo/blob/04a70e99e15b23b78d4ada5c34c4cbc7e77c0770/addons/web/controllers/binary.py#L166

#     @http.route('/my_module/my_module/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('my_module.listing', {
#             'root': '/my_module/my_module',
#             'objects': http.request.env['my_module.my_module'].search([]),
#         })

#     @http.route('/my_module/my_module/objects/<model("my_module.my_module"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('my_module.object', {
#             'object': obj
#         })
