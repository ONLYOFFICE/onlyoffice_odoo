# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

import base64
import json
import logging
import re

import markupsafe
from werkzeug.exceptions import Forbidden

from odoo import _, http
from odoo.exceptions import AccessError
from odoo.http import request

from odoo.addons.onlyoffice_odoo.controllers.controllers import (
    Onlyoffice_Connector,
    onlyoffice_urlopen,
)
from odoo.addons.onlyoffice_odoo.utils import (
    config_utils,
    file_utils,
    jwt_utils,
    url_utils,
)

_logger = logging.getLogger(__name__)

_mobile_regex = (
    r"android|avantgo|playbook|blackberry|blazer|compal|elaine|fennec|hiptop|"
    r"iemobile|ip(hone|od|ad)|iris|kindle|lge |maemo|midp|mmp|opera m(ob|in)i|"
    r"palm( os)?|phone|p(ixi|re)\\/|plucker|pocket|psp|symbian|treo|"
    r"up\\.(browser|link)|vodafone|wap|windows (ce|phone)|xda|xiino"
)


class OnlyofficeDms_Connector(Onlyoffice_Connector):
    """
    HTTP routes for ONLYOFFICE ↔ DMS integration.

    Inherits Onlyoffice_Connector to reuse shared helpers:
    get_user_from_token(), filter_xss(), etc.
    """

    # ----------------------------------------------------------
    # Editor page (rendered in browser)
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/editor/<int:file_id>",
        auth="user",
        type="http",
        website=True,
    )
    def render_dms_editor(self, file_id, mode=None, **kwargs):
        """Render the ONLYOFFICE editor page for a DMS file."""
        dms_file = request.env["dms.file"].browse(file_id)

        if not dms_file.exists():
            return request.not_found()

        # Block if locked by another user (better UX, write will fail anyway)
        if dms_file.is_locked and dms_file.locked_by.id != request.env.user.id:
            raise Forbidden()

        try:
            dms_file.check_access("read")
        except AccessError as err:
            raise Forbidden() from err

        if not file_utils.can_view(dms_file.name):
            return request.not_found()

        oo_role = dms_file.get_oo_role_for_user(request.env.user)
        if oo_role == "none":
            raise Forbidden()

        force_view = mode == "view"
        values = self._prepare_dms_editor_values(dms_file, oo_role, force_view=force_view)
        return request.render("onlyoffice_odoo.onlyoffice_editor", values)

    # ----------------------------------------------------------
    # File content (fetched by ONLYOFFICE Docs server)
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/file/content/<int:file_id>",
        auth="public",
        methods=["GET"],
    )
    def get_dms_file_content(self, file_id, oo_security_token=None, access_token=None, **kwargs):
        """Serve raw file bytes to the ONLYOFFICE Docs server."""
        user = self.get_user_from_token(oo_security_token)
        dms_file = request.env["dms.file"].with_user(user).browse(file_id)

        if not dms_file.exists():
            return request.not_found()

        if access_token and not dms_file.check_access_token(access_token):
            return request.not_found()

        try:
            dms_file.check_access("read")
        except AccessError:
            return request.not_found()

        if jwt_utils.is_jwt_enabled(request.env):
            token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env), "")
            if token.startswith("Bearer "):
                token = token[len("Bearer ") :]
            if not token:
                _logger.warning("DMS content: JWT expected but missing for file %s", file_id)
                raise Exception("Expected JWT from ONLYOFFICE Docs server")
            jwt_utils.decode_token(request.env, token)

        content = dms_file.sudo().content
        if not content:
            return request.not_found()

        binary = base64.b64decode(content)
        return request.make_response(
            binary,
            headers=[
                ("Content-Type", dms_file.mimetype or "application/octet-stream"),
                ("Content-Disposition", f'attachment; filename="{dms_file.name}"'),
                ("Content-Length", len(binary)),
            ],
        )

    # ----------------------------------------------------------
    # Save callback (ONLYOFFICE Docs → Odoo after editing)
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/editor/callback/<int:file_id>",
        auth="public",
        methods=["POST"],
        type="http",
        csrf=False,
    )
    def dms_editor_callback(self, file_id, oo_security_token=None, access_token=None, **kwargs):
        """Receive the edited file from ONLYOFFICE Docs and write it back to DMS."""
        response_json = {"error": 0}

        try:
            body = request.get_json_data()
            user = self.get_user_from_token(oo_security_token)
            dms_file = request.env["dms.file"].with_user(user).browse(file_id)

            if not dms_file.exists():
                raise Exception(f"DMS file not found: {file_id}")

            if access_token and not dms_file.check_access_token(access_token):
                raise Exception(f"Invalid access token for DMS file {file_id}")

            dms_file.check_access("write")

            if jwt_utils.is_jwt_enabled(request.env):
                token = body.get("token") or ""
                if not token:
                    token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env), "")
                    if token.startswith("Bearer "):
                        token = token[len("Bearer ") :]
                if not token:
                    raise Exception("Expected JWT from ONLYOFFICE Docs server")
                body = jwt_utils.decode_token(request.env, token)
                if body.get("payload"):
                    body = body["payload"]

            status = body["status"]
            _logger.info("DMS callback file=%s status=%s", file_id, status)

            if status in (2, 3):  # 2=MustSave, 3=Corrupted (force-save)
                file_url = url_utils.replace_public_url_to_internal(request.env, body.get("url"))
                new_bytes = onlyoffice_urlopen(file_url).read()
                dms_file.with_user(user).write(
                    {
                        "content": base64.encodebytes(new_bytes),
                        "oo_version": dms_file.oo_version + 1,
                    }
                )
                dms_file.sudo().message_post(body=_("File edited by %(user)s", user=user.name))
                _logger.info("DMS file %s saved (oo_version=%s)", file_id, dms_file.oo_version)

        except Exception as ex:
            _logger.error("DMS callback error file=%s: %s", file_id, ex)
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )

    # ----------------------------------------------------------
    # Create a blank document in DMS
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/file/create",
        auth="user",
        methods=["POST"],
        type="json",
    )
    def post_dms_file_create(self, directory_id, supported_format, title, url=None):
        """
        Create a blank ONLYOFFICE document inside a DMS directory.

        supported_format: 'docx' | 'xlsx' | 'pptx' | 'pdf'
        Returns JSON with 'file_id' or 'error'.
        """
        result = {"error": None, "file_id": None}
        try:
            if url:
                import requests as _req

                resp = _req.get(url, stream=True, timeout=30)
                resp.raise_for_status()
                file_data = resp.content
            else:
                file_data = file_utils.get_default_file_template(request.env.user.lang, supported_format)

            dms_file = request.env["dms.file"].create(
                {
                    "name": f"{title}.{supported_format}",
                    "directory_id": int(directory_id),
                    "content": base64.encodebytes(file_data),
                }
            )

            # Bootstrap ONLYOFFICE access: creator gets edit, everyone else none
            request.env["onlyoffice.dms.file.access.user"].create(
                {
                    "file_id": dms_file.id,
                    "user_id": request.env.user.id,
                    "role": "edit",
                }
            )
            result["file_id"] = dms_file.id

        except Exception as ex:
            _logger.exception("Failed to create DMS file: %s", ex)
            result["error"] = _("Failed to create file")

        return json.dumps(result)

    # ----------------------------------------------------------
    # Shared-link editor (portal / public access via access_token)
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/share/<int:file_id>/",
        auth="public",
        type="http",
    )
    def render_dms_shared_editor(self, file_id, access_token=None, **kwargs):
        """
        Render ONLYOFFICE editor for a DMS file accessed via its portal
        access token.  The ONLYOFFICE role comes from
        onlyoffice.dms.file.access.link_access.
        """
        dms_file = request.env["dms.file"].sudo().browse(file_id)

        if not dms_file.exists():
            return request.not_found()

        if not access_token or not dms_file.check_access_token(access_token):
            return request.not_found()

        link_access = dms_file.get_oo_effective_link_access()
        if link_access == "none":
            raise Forbidden()

        if not file_utils.can_view(dms_file.name):
            return request.not_found()

        values = self._prepare_dms_shared_editor_values(dms_file, access_token, link_access)
        return request.render("onlyoffice_odoo.onlyoffice_editor", values)

    # ----------------------------------------------------------
    # Shared-link save callback
    # ----------------------------------------------------------

    @http.route(
        "/onlyoffice/dms/share/callback/<int:file_id>/<oo_security_token>",
        auth="public",
        methods=["POST"],
        type="http",
        csrf=False,
    )
    def dms_share_callback(self, file_id, oo_security_token, **kwargs):
        """Save callback for DMS files accessed via portal access token."""
        response_json = {"error": 0}
        try:
            body = request.get_json_data()
            user = self.get_user_from_token(oo_security_token)

            dms_file = request.env["dms.file"].sudo().browse(file_id)
            if not dms_file.exists():
                raise Exception(f"DMS file not found: {file_id}")

            if dms_file.get_oo_effective_link_access() in ("none", "view"):
                raise Exception(f"No write access via share link for file {file_id}")

            if jwt_utils.is_jwt_enabled(request.env):
                token = body.get("token") or ""
                if not token:
                    token = request.httprequest.headers.get(config_utils.get_jwt_header(request.env), "")
                    if token.startswith("Bearer "):
                        token = token[len("Bearer ") :]
                if not token:
                    raise Exception("Expected JWT from ONLYOFFICE Docs server")
                body = jwt_utils.decode_token(request.env, token)
                if body.get("payload"):
                    body = body["payload"]

            status = body["status"]
            if status in (2, 3):
                file_url = url_utils.replace_public_url_to_internal(request.env, body.get("url"))
                new_bytes = onlyoffice_urlopen(file_url).read()
                dms_file.with_user(user).sudo().write(
                    {
                        "content": base64.encodebytes(new_bytes),
                        "oo_version": dms_file.oo_version + 1,
                    }
                )
                dms_file.sudo().message_post(body=_("File edited by %(user)s", user=user.name))

        except Exception as ex:
            _logger.error("DMS share callback error file=%s: %s", file_id, ex)
            response_json["error"] = 1
            response_json["message"] = http.serialize_exception(ex)

        return request.make_response(
            data=json.dumps(response_json),
            status=500 if response_json["error"] == 1 else 200,
            headers=[("Content-Type", "application/json")],
        )

    # ----------------------------------------------------------
    # Private helpers
    # ----------------------------------------------------------

    def _prepare_dms_editor_values(self, dms_file, oo_role, force_view=False):
        """Build the template context dict for the ONLYOFFICE editor page."""
        filename = self.filter_xss(dms_file.name)
        checksum = dms_file.checksum or str(dms_file.id)
        key = f"dms_{dms_file.id}_{checksum}_{dms_file.oo_version}"

        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        security_token = jwt_utils.encode_payload(
            request.env,
            {"id": request.env.user.id},
            config_utils.get_internal_jwt_secret(request.env),
        )
        if isinstance(security_token, bytes):
            security_token = security_token.decode("utf-8")

        path_part = f"{dms_file.id}" f"?oo_security_token={security_token}" f"&shardkey={key}"

        document_type = file_utils.get_file_type(filename)
        is_mobile = bool(
            re.search(
                _mobile_regex,
                request.httprequest.headers.get("User-Agent", ""),
                re.IGNORECASE,
            )
        )

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "mobile" if is_mobile else "desktop",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": odoo_url + "onlyoffice/dms/file/content/" + path_part,
                "fileType": file_utils.get_file_ext(filename),
                "key": key,
                "permissions": {},
            },
            "editorConfig": {
                "lang": request.env.user.lang,
                "user": {
                    "id": str(request.env.user.id),
                    "name": request.env.user.name,
                },
                "customization": {},
            },
        }

        effective_role = "view" if force_view else oo_role
        root_config = self._apply_oo_role(root_config, effective_role)

        # Only provide a callbackUrl for roles that produce edits
        if effective_role in ("edit", "commenter", "reviewer", "form_filling", "custom_filter"):
            root_config["editorConfig"]["callbackUrl"] = odoo_url + "onlyoffice/dms/editor/callback/" + path_part

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        return {
            "docTitle": filename,
            "docIcon": (f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico"),
            "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
            "editorConfig": markupsafe.Markup(json.dumps(root_config)),
        }

    def _prepare_dms_shared_editor_values(self, dms_file, access_token, role):
        """Build the template context dict for a publicly shared DMS file."""
        filename = self.filter_xss(dms_file.name)
        checksum = dms_file.checksum or str(dms_file.id)
        key = f"dms_{dms_file.id}_{checksum}_{dms_file.oo_version}"

        docserver_url = config_utils.get_doc_server_public_url(request.env)
        odoo_url = config_utils.get_base_or_odoo_url(request.env)

        if isinstance(access_token, bytes):
            access_token = access_token.decode("utf-8")

        document_type = file_utils.get_file_type(filename)
        is_mobile = bool(
            re.search(
                _mobile_regex,
                request.httprequest.headers.get("User-Agent", ""),
                re.IGNORECASE,
            )
        )

        root_config = {
            "width": "100%",
            "height": "100%",
            "type": "mobile" if is_mobile else "desktop",
            "documentType": document_type,
            "document": {
                "title": filename,
                "url": odoo_url + f"my/dms/file/{dms_file.id}/download",
                "fileType": file_utils.get_file_ext(filename),
                "key": key,
                "permissions": {},
            },
            "editorConfig": {
                "mode": "view",
                "lang": request.env.user.lang,
                "user": {
                    "id": str(request.env.user.id),
                    "name": request.env.user.name,
                },
                "customization": {},
            },
        }

        root_config = self._apply_oo_role(root_config, role)

        if role not in ("none", "view"):
            public_user = request.env.ref("base.public_user")
            security_token = jwt_utils.encode_payload(
                request.env,
                {"id": public_user.id},
                config_utils.get_internal_jwt_secret(request.env),
            )
            if isinstance(security_token, bytes):
                security_token = security_token.decode("utf-8")
            root_config["editorConfig"]["callbackUrl"] = (
                odoo_url + f"onlyoffice/dms/share/callback/{dms_file.id}/{security_token}"
            )

        if jwt_utils.is_jwt_enabled(request.env):
            root_config["token"] = jwt_utils.encode_payload(request.env, root_config)

        return {
            "docTitle": filename,
            "docIcon": (f"/onlyoffice_odoo/static/description/editor_icons/{document_type}.ico"),
            "docApiJS": docserver_url + "web-apps/apps/api/documents/api.js",
            "editorConfig": markupsafe.Markup(json.dumps(root_config)),
        }

    @staticmethod
    def _apply_oo_role(root_config, role):
        """Translate an ONLYOFFICE role string into document/editor permissions."""
        if role == "edit":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
        elif role == "commenter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["comment"] = True
        elif role == "reviewer":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["review"] = True
        elif role == "form_filling":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = False
            root_config["document"]["permissions"]["fillForms"] = True
        elif role == "custom_filter":
            root_config["editorConfig"]["mode"] = "edit"
            root_config["document"]["permissions"]["edit"] = True
            root_config["document"]["permissions"]["modifyFilter"] = False
        else:  # "view" or anything unrecognised
            root_config["editorConfig"]["mode"] = "view"
            root_config["document"]["permissions"]["edit"] = False
        return root_config
