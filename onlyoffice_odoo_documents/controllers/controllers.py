# Copyright (C) 2026 Ascensio System SIA
import base64
import json
import logging
import os
import re
from mimetypes import guess_type
from urllib.request import urlopen

import requests
from werkzeug.exceptions import Forbidden

from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request
from odoo.tools.json import scriptsafe
from odoo.tools.translate import _

from odoo.addons.documents.controllers.documents import ShareRoute
from odoo.addons.onlyoffice_odoo.controllers.main import OnlyofficeConnector, onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import (
    config_utils,
    conversion_utils,
    file_utils,
    format_utils,
    jwt_utils,
    url_utils,
)

_logger = logging.getLogger(__name__)
_mobile_regex = r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"  # noqa: E501


def _get_document_share_role(document):
    """Resolve the effective ONLYOFFICE sharing role of the current user on a document.

    Mirrors the resolution order used by OnlyofficeConnector.get_documents_permissions
    so conversion access matches editor/view access.
    """
    if document.owner_id.id == request.env.user.id:
        return "editor"

    access_user = request.env["onlyoffice.odoo.documents.access.user"].search(
        [("document_id", "=", document.id), ("user_id", "=", request.env.user.id)], limit=1
    )
    if access_user:
        return access_user.role

    access = request.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)], limit=1)
    if access:
        return access.internal_users

    return "viewer"  # default role for internal users, consistent with get_documents_permissions


def _validate_document_for_convert(document, save_to_documents):
    """Validate access rights for converting a document, returning an error message or None."""
    try:
        document.check_access_rule("read")
    except AccessError:
        return _("You do not have access to this document")

    if document.is_locked and document.lock_uid.id != request.env.user.id:
        return _("This document is locked by another user")

    if _get_document_share_role(document) == "none":
        return _("You do not have access to this document")

    if save_to_documents and not document.folder_id.has_write_access:
        return _("You do not have permission to create documents in this workspace")

    return None


class OnlyofficeDocuments_Connector(http.Controller):
    @http.route("/onlyoffice/documents/file/create", auth="user", methods=["POST"], type="json")
    def post_file_create(self, folder_id, supported_format, title, url=None):
        result = {"error": None, "file_id": None, "document_id": None}

        try:
            _logger.info(f"Getting new file template {request.env.user.lang} {supported_format}")

            if url:
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                file_data = response.content
            else:
                file_data = file_utils.get_default_file_template(request.env.user.lang, supported_format)

            data = {
                "name": title + "." + supported_format,
                "mimetype": file_utils.get_mime_by_ext(supported_format),
                "raw": file_data,
                "folder_id": int(folder_id),
            }

            document = request.env["documents.document"].create(data)
            request.env["onlyoffice.odoo.documents.access"].create(
                {
                    "document_id": document.id,
                    "internal_users": "none",
                    "link_access": "viewer",
                }
            )
            request.env["onlyoffice.odoo.documents.access.user"].create(
                {
                    "document_id": document.id,
                    "user_id": request.env.user.id,
                    "role": "editor",
                }
            )
            result["file_id"] = document.attachment_id.id
            result["document_id"] = document.id

        except Exception as ex:
            _logger.exception(f"Failed to create document {ex!s}")
            result["error"] = _("Failed to create document")

        return json.dumps(result)

    @http.route("/onlyoffice/documents/file/convert", auth="user", methods=["POST"], type="json")
    def post_file_convert(self, document_id, target_format, save_to_documents=False):
        result = {"error": None}

        try:
            document = request.env["documents.document"].browse(int(document_id)).exists()
            if not document:
                result["error"] = _("Document not found")
                return json.dumps(result)

            access_error = _validate_document_for_convert(document, save_to_documents)
            if access_error:
                result["error"] = access_error
                return json.dumps(result)

            attachment = document.attachment_id
            if not attachment:
                result["error"] = _("Document has no attachment")
                return json.dumps(result)

            source_ext = file_utils.get_file_ext(attachment.name)
            target_format = (target_format or "").lower()

            allowed_formats = []
            for supported_format in format_utils.get_supported_formats():
                if supported_format.name == source_ext:
                    allowed_formats = supported_format.convert
                    break

            if target_format not in allowed_formats:
                result["error"] = _("Unsupported target format")
                return json.dumps(result)

            jwt_header = config_utils.get_jwt_header(request.env)
            jwt_secret = config_utils.get_jwt_secret(request.env)
            internal_jwt_secret = config_utils.get_internal_jwt_secret(request.env)
            docserver_url = config_utils.get_doc_server_public_url(request.env)
            docserver_url = url_utils.replace_public_url_to_internal(request.env, docserver_url)
            odoo_url = config_utils.get_base_or_odoo_url(request.env)

            oo_security_token = jwt_utils.encode_payload(request.env, {"id": request.env.user.id}, internal_jwt_secret)
            oo_security_token = (
                oo_security_token.decode("utf-8") if isinstance(oo_security_token, bytes) else oo_security_token
            )

            source_url = f"{odoo_url}onlyoffice/file/content/{attachment.id}?oo_security_token={oo_security_token}"
            region = conversion_utils.get_region(request.env.user.lang)
            body_json = conversion_utils.build_conversion_body(
                source_url, source_ext, target_format, extra_options={"async": False}, region=region
            )
            conversion_url = os.path.join(docserver_url, "converter", f"?shardkey={body_json['key']}")
            body_json, headers = conversion_utils.sign_conversion_request(
                request.env, body_json, jwt_secret, jwt_header
            )

            response = onlyoffice_request(
                url=conversion_url,
                method="post",
                opts={"data": json.dumps(body_json), "headers": headers},
            )
            conversion_result = conversion_utils.parse_conversion_response(response)

            if "error" in conversion_result:
                _logger.error("Document conversion failed: %s", conversion_result.get("error"))
                result["error"] = conversion_result.get("message") or _("Document conversion failed")
                return json.dumps(result)

            file_url = conversion_result.get("fileUrl")
            if not file_url:
                result["error"] = _("Conversion service did not return a file")
                return json.dumps(result)

            file_response = onlyoffice_request(url=file_url, method="get")
            converted_data = file_response.content

            title = file_utils.get_file_title_without_ext(attachment.name)
            new_name = f"{title}.{target_format}"

            if save_to_documents:
                new_document = request.env["documents.document"].create(
                    {
                        "name": new_name,
                        "raw": converted_data,
                        "mimetype": file_utils.get_mime_by_ext(target_format)
                        or (guess_type(new_name)[0] or "application/octet-stream"),
                        "folder_id": document.folder_id.id,
                    }
                )

                result["saved"] = True
                result["document_id"] = new_document.id
            else:
                result["saved"] = False
                result["filename"] = new_name
                result["data"] = base64.b64encode(converted_data).decode("utf-8")

        except Exception as ex:
            _logger.exception(f"Failed to convert document {ex!s}")
            result["error"] = _("Failed to convert document")

        return json.dumps(result)


class OnlyofficeDocuments_Inherited_Connector(OnlyofficeConnector):
    @http.route(
        ["/onlyoffice/documents/share/<int:share_id>/<access_token>/<int:document_id>"], type="http", auth="public"
    )
    def render_shared_document_editor(self, document_id=None, access_token=None, share_id=None):
        try:
            document = None
            if share_id:
                share = request.env["documents.share"].sudo().browse(int(share_id))
                document = share._get_documents_and_check_access(access_token, [int(document_id)], operation="read")
            if not document or not document.exists():
                raise request.not_found()

            values = self.prepare_share_editor(document, access_token, share_id)
            values["editorConfig"] = scriptsafe.dumps(values["editorConfig"])
            try:
                session_info = request.env["ir.http"].get_frontend_session_info()
            except Exception:
                session_info = {}
            values["session_info"] = scriptsafe.dumps(session_info)
            return request.render("onlyoffice_odoo.onlyoffice_editor", values)

        except Exception as ex:
            _logger.error("Failed to open shared document: %s", ex)

        return request.not_found()

    @http.route("/onlyoffice/editor/document/<int:document_id>", auth="public", type="http", website=True)
    def render_document_editor(self, document_id, access_token=None):
        values = self.prepare_document_editor(document_id, access_token)
        values["editorConfig"] = scriptsafe.dumps(values["editorConfig"])
        values["session_info"] = scriptsafe.dumps(values["session_info"])
        return request.render("onlyoffice_odoo.onlyoffice_editor", values)

    def prepare_document_editor(self, document_id, access_token):
        document = request.env["documents.document"].browse(int(document_id))
        if document.is_locked and document.lock_uid.id != request.env.user.id:
            _logger.error("Document is locked by another user")
            raise Forbidden()
        try:
            document.check_access_rule("read")
        except AccessError:
            _logger.error("User has no read access rights to open this document")
            raise Forbidden()  # noqa: B904

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

    def prepare_share_editor(self, document, access_token, share_id):
        role = "viewer"
        access = (
            request.env["onlyoffice.odoo.documents.access"].sudo().search([("document_id", "=", document.id)], limit=1)
        )
        if access:
            if access.link_access != "none":
                role = access.link_access
            else:
                role = None

        public_user = request.env.ref("base.public_user")
        current_user = request.env.user
        if current_user and current_user.id != public_user.id:
            access_user = (
                request.env["onlyoffice.odoo.documents.access.user"]
                .sudo()
                .search([("document_id", "=", document.id), ("user_id", "=", current_user.id)], limit=1)
            )
            if access_user and access_user.role != "none":
                role = access_user.role

        if not role:
            raise AccessError(_("User has no read access rights to open this document"))

        attachment = self.get_attachment(document.attachment_id.id)
        data = attachment.sudo().read(["id", "checksum", "public", "name", "access_token"])[0]
        key = str(data["id"]) + str(data["checksum"])
        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        filename = self.filter_xss(data["name"])
        access_token = access_token.decode("utf-8") if isinstance(access_token, bytes) else access_token
        document_type = file_utils.get_file_type(filename)
        is_mobile = bool(re.search(_mobile_regex, request.httprequest.headers.get("User-Agent"), re.IGNORECASE))

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "mobile" if is_mobile else "desktop",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": odoo_url + "document/download/" + str(share_id) + "/" + access_token + "/" + str(document.id),
                "fileType": file_utils.get_file_ext(filename),
                "key": key,
                "permissions": {"edit": False},
            },
            "editorConfig": {
                "mode": "view",
                "lang": request.env.user.lang,
                "user": {"id": str(request.env.user.id), "name": request.env.user.name},
                "customization": {},
            },
        }

        if not role or role == "viewer":
            root_config["editorConfig"]["mode"] = "view"
            root_config["document"]["permissions"]["edit"] = False
        elif role == "commenter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["comment"] = True
        elif role == "reviewer":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["review"] = True
        elif role == "editor":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
        elif role == "form_filling":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["fillForms"] = True
        elif role == "custom_filter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
            root_config["document"]["permissions"]["modifyFilter"] = False

        if role and role != "viewer":
            token_user = current_user if current_user and current_user.id != public_user.id else public_user
            security_token = jwt_utils.encode_payload(
                request.env, {"id": token_user.id}, config_utils.get_internal_jwt_secret(request.env)
            )
            security_token = security_token.decode("utf-8") if isinstance(security_token, bytes) else security_token
            root_config["editorConfig"]["callbackUrl"] = (
                odoo_url
                + "onlyoffice/documents/share/callback/"
                + str(share_id)
                + "/"
                + access_token
                + "/"
                + str(document.id)
                + "/"
                + security_token
            )

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        return {
            "docTitle": filename,
            "docIcon": f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico",
            "docApiJS": f"{docserver_url}web-apps/apps/api/documents/api.js?shardkey={key}",
            "editorConfig": root_config,
        }

    @http.route(
        "/onlyoffice/documents/share/callback/<int:share_id>/<access_token>/<int:document_id>/<oo_security_token>",
        auth="public",
        methods=["POST"],
        type="http",
        csrf=False,
    )
    def share_callback(self, share_id, access_token, document_id, oo_security_token):
        response_json = {"error": 0}

        try:
            body = request.get_json_data()
            user = self.get_user_from_token(oo_security_token)
            share = request.env["documents.share"].sudo().browse(int(share_id))
            document = share._get_documents_and_check_access(access_token, [int(document_id)], operation="read")

            access = (
                request.env["onlyoffice.odoo.documents.access"]
                .sudo()
                .search([("document_id", "=", document.id)], limit=1)
            )
            can_write = False
            if access:
                if access.link_access in ("editor", "custom_filter"):
                    can_write = True

            if not can_write and user:
                access_user = (
                    request.env["onlyoffice.odoo.documents.access.user"]
                    .sudo()
                    .search([("document_id", "=", document.id), ("user_id", "=", user.id)], limit=1)
                )
                if access_user and access_user.role in ("editor", "custom_filter"):
                    can_write = True

            if not can_write:
                raise Exception("No access rights to overwrite this document for access via share link")

            attachment = request.env["ir.attachment"].sudo().browse([document.attachment_id.id]).exists().ensure_one()

            if jwt_utils.is_jwt_enabled(request.env):
                token = body.get("token")

                if not token:
                    token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env))
                    if token:
                        token = token[len("Bearer ") :]

                if not token:
                    raise Exception("expected JWT")

                body = jwt_utils.decode_token(request.env, token)
                if body.get("payload"):
                    body = body["payload"]

            status = body["status"]

            if (status == 2) | (status == 3):  # mustsave, corrupted
                file_url = url_utils.replace_public_url_to_internal(request.env, body.get("url"))
                datas = base64.encodebytes(urlopen(file_url, timeout=120).read())
                document = request.env["documents.document"].sudo().browse(int(attachment.res_id))
                document.with_user(user).sudo().write(
                    {
                        "name": attachment.name,
                        "datas": datas,
                        "mimetype": guess_type(file_url)[0],
                    }
                )

        except Exception as ex:
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )


class OnlyOfficeShareRoute(ShareRoute):
    @http.route(["/document/share/<int:share_id>/<token>"], type="http", auth="public", website=True)
    def share_portal(self, share_id=None, token=None, **kwargs):
        response = super(OnlyOfficeShareRoute, self).share_portal(share_id, token, **kwargs)  # noqa: UP008

        if not hasattr(response, "qcontext"):
            return response

        share = http.request.env["documents.share"].sudo().browse(share_id)
        qcontext = response.qcontext

        if share.type == "domain":
            data = []
            for document in qcontext["document_ids"]:
                data.append({"document": document, "onlyoffice_supported": file_utils.can_view(document.name)})
            qcontext["onlyoffice_supported"] = data

        elif response.qcontext.get("is_files_shared"):
            document = qcontext.get("document_ids") and qcontext["document_ids"][0] or None

            if document and len(qcontext["document_ids"]) == 1:
                can_view = file_utils.can_view(document.name)
                if can_view:
                    qcontext["onlyoffice_supported"] = True

        return response

    @http.route(["/Products/Files/", "/Products/Files"], auth="user", methods=["GET"], type="http")
    def desktop_editor_redirect(self, **kwargs):
        return request.redirect("/web#action=documents.document_action&menu_id=documents.menu_root")
