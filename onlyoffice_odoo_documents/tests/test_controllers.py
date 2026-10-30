# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

from .common import INTERNAL_SECRET, XLSX_MIMETYPE, DocumentsCase, blank, xlsx_with_metadata

CONTROLLERS = "odoo.addons.onlyoffice_odoo_documents.controllers.controllers"
URLOPEN = "odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_urlopen"


@tagged("post_install", "-at_install")
class TestDocumentEditor(DocumentsCase, HttpCase):
    """Opening a Documents file: the editor config, the ONLYOFFICE roles and the editor page."""

    def _config(self, login, **params):
        self.authenticate(login, login)
        return self._rpc("/onlyoffice/editor/get_config", **params)

    def _editor(self, login, document):
        """editorConfig.mode and document.permissions the user gets for ``document``, or the error."""
        body = self._config(login, document_id=document.id)
        if "error" in body:
            return body["error"]["data"]["name"]
        config = body["result"]["editorConfig"]
        return config["editorConfig"]["mode"], config["document"]["permissions"]

    def test_config_carries_the_document_and_a_token_for_the_formulas(self):
        document = self._document()

        config = self._config("oo_doc_owner", document_id=document.id)["result"]

        self.assertEqual(config["document_id"], document.id)
        payload = jwt_utils.decode_token(self.env, config["jwt_token"], INTERNAL_SECRET)
        self.assertEqual((payload["uid"], payload["document_id"]), (self.owner.id, document.id))
        editor = config["editorConfig"]["editorConfig"]
        self.assertEqual(editor["mode"], "edit")
        self.assertIn(f"/onlyoffice/editor/callback/{document.attachment_id.id}?", editor["callbackUrl"])
        self.assertNotIn("has_odoo_formulas", config)

    def test_config_of_an_xlsx_with_odoo_formulas(self):
        metadata = {"lists": {}, "globalFilters": [{"label": "Region", "defaultValue": "EU"}]}
        document = self._document("Sales.xlsx", content=xlsx_with_metadata(metadata), mimetype=XLSX_MIMETYPE)

        config = self._config("oo_doc_owner", attachment_id=document.attachment_id.id)["result"]

        self.assertTrue(config["has_odoo_formulas"])
        self.assertEqual(json.loads(config["filter_values_json"]), {"Region": "EU"})
        self.env.invalidate_all()
        self.assertEqual(json.loads(document.onlyoffice_spreadsheet_metadata), metadata, "restored from the file")

    def test_roles_of_a_colleague(self):
        expected = {
            # No ONLYOFFICE role: the standard Documents right decides.
            (): ("edit", {"edit": True}),
            (("internal_users", "view"),): ("view", {"edit": False}),
            (("internal_users", "commenter"),): ("edit", {"edit": False, "comment": True}),
            (("internal_users", "reviewer"), ("colleague", "edit")): ("edit", {"edit": True}),
            (("colleague", "reviewer"),): ("edit", {"edit": False, "review": True}),
            (("internal_users", "none"),): "odoo.exceptions.AccessError",
            (("internal_users", "edit"), ("colleague", "none")): "odoo.exceptions.AccessError",
        }
        for roles, result in expected.items():
            with self.subTest(roles=roles):
                document = self._document()
                self._roles(document, **dict(roles))
                self.assertEqual(self._editor("oo_doc_colleague", document), result)

    def test_custom_filter_role_keeps_the_filters_of_others(self):
        document = self._document("Sheet.xlsx")
        self._roles(document, colleague="custom_filter")
        self.assertEqual(self._editor("oo_doc_colleague", document), ("edit", {"edit": True, "modifyFilter": False}))

    def test_owner_edits_whatever_the_roles(self):
        document = self._document()
        self._roles(document, internal_users="none", owner="view")
        self.assertEqual(self._editor("oo_doc_owner", document), ("edit", {"edit": True}))

    def test_previous_versions_open_read_only(self):
        document = self._document()
        previous = (
            self.env["ir.attachment"]
            .with_context(no_document=True)
            .create({"name": "Report (1).docx", "raw": b"v1", "res_model": "documents.document", "res_id": document.id})
        )

        config = self._config("oo_doc_owner", attachment_id=previous.id)["result"]["editorConfig"]

        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertFalse(config["document"]["permissions"]["edit"])

    # -- GET /onlyoffice/editor/document/<id> --

    def test_editor_page_of_a_document(self):
        document = self._document()
        self.authenticate("oo_doc_owner", "oo_doc_owner")

        response = self.url_open(f"/onlyoffice/editor/document/{document.id}")

        self.assertEqual(response.status_code, 200)
        config = self._editor_config(response.text)
        self.assertEqual(config["document"]["title"], "Report.docx")
        self.assertEqual(config["editorConfig"]["mode"], "edit")

    def test_editor_page_is_forbidden_without_access_or_when_locked(self):
        private = self._document(folder_id=False)
        locked = self._document()
        locked.sudo().lock_uid = self.owner
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")
        for document in (private, locked):
            with self.subTest(document=document.name):
                response = self.url_open(f"/onlyoffice/editor/document/{document.id}", allow_redirects=False)
                self.assertEqual(response.status_code, 403)

    def test_editor_page_is_forbidden_to_visitors(self):
        response = self.url_open(f"/onlyoffice/editor/document/{self._document().id}", allow_redirects=False)
        self.assertEqual(response.status_code, 403)


@tagged("post_install", "-at_install")
class TestDocumentSave(DocumentsCase, HttpCase):
    """The base save callback for a Documents file: a new version, the previous one kept and renamed."""

    def _save(self, document, user, content):
        downloaded = MagicMock()
        downloaded.read.return_value = content
        token = self._internal_token({"id": user.id})
        with patch(URLOPEN, return_value=downloaded):
            return self.url_open(
                f"/onlyoffice/editor/callback/{document.attachment_id.id}?oo_security_token={token}",
                data=json.dumps({"status": 2, "url": "http://documentserver/cache/files/out.docx"}),
                headers={"Content-Type": "application/json"},
            )

    def test_each_save_keeps_the_previous_version(self):
        document = self._document()
        attachment = document.attachment_id
        original = attachment.raw

        self.assertEqual(self._save(document, self.owner, b"version 2").json(), {"error": 0})
        self.assertEqual(self._save(document, self.owner, b"version 3").json(), {"error": 0})

        self.env.invalidate_all()
        self.assertEqual(document.attachment_id, attachment)
        self.assertEqual(attachment.raw, b"version 3")
        self.assertEqual(attachment.oo_attachment_version, 3)
        previous = {a.name: a.raw for a in document.previous_attachment_ids}
        self.assertEqual(previous, {"Report (1).docx": original, "Report (2).docx": b"version 2"})
        self.assertIn("Document edited by OO Owner", document.message_ids.mapped("body")[0])

    def test_save_by_a_viewer_is_rejected(self):
        document = self._document()
        document.action_update_access_rights(access_internal="view")

        response = self._save(document, self.colleague, b"overwritten")

        self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
        self.env.invalidate_all()
        self.assertEqual(document.attachment_id.raw, blank("docx"))


@tagged("post_install", "-at_install")
class TestCreateAndConvert(DocumentsCase, HttpCase):
    """The "Create with ONLYOFFICE" and "Convert with ONLYOFFICE" dialogs."""

    def setUp(self):
        super().setUp()
        self.authenticate("oo_doc_owner", "oo_doc_owner")

    def _create(self, **params):
        return json.loads(self._rpc("/onlyoffice/documents/file/create", **params)["result"])

    def _convert(self, document, target_format="pdf", save_to_documents=True, responses=None):
        converted = MagicMock(status_code=200)
        converted.json.return_value = {"endConvert": True, "fileUrl": "http://documentserver/out.pdf", "percent": 100}
        responses = responses or [converted, MagicMock(content=b"%PDF-1.7 converted")]
        with patch(f"{CONTROLLERS}.onlyoffice_request", side_effect=responses) as request:
            body = self._rpc(
                "/onlyoffice/documents/file/convert",
                document_id=document.id,
                target_format=target_format,
                save_to_documents=save_to_documents,
            )
        return json.loads(body["result"]), request

    # -- POST /onlyoffice/documents/folders --

    def test_folders_where_the_user_can_create(self):
        Document = self.env["documents.document"]
        sub = Document.create({"name": "Sub", "type": "folder", "folder_id": self.folder.id})
        read_only = Document.create({"name": "OO Read-only", "type": "folder", "access_internal": "view"})

        folders = self._rpc("/onlyoffice/documents/folders")["result"]

        self.assertIn({"display_name": "OO Folder", "id": self.folder.id}, folders)
        self.assertIn({"display_name": "OO Folder/Sub", "id": sub.id}, folders)
        self.assertNotIn(read_only.id, [folder["id"] for folder in folders])
        self.assertEqual(folders, sorted(folders, key=lambda folder: folder["display_name"]))

    # -- POST /onlyoffice/documents/file/create --

    def test_create_a_blank_document_in_a_folder(self):
        result = self._create(folder_id=self.folder.id, supported_format="docx", title="Plan")

        self.assertFalse(result["error"])
        document = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual((document.name, document.folder_id, document.owner_id), ("Plan.docx", self.folder, self.owner))
        self.assertEqual(document.attachment_id.id, result["file_id"])
        self.assertEqual(document.raw, file_utils.get_default_file_template("en_US", "docx"))
        self.assertEqual(document.mimetype, file_utils.get_mime_by_ext("docx"))
        # Only the creator gets an ONLYOFFICE role on a new document.
        access = self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)])
        self.assertEqual((access.internal_users, access.link_access), ("none", "none"))
        user_access = self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)])
        self.assertEqual((user_access.user_id, user_access.role), (self.owner.partner_id, "edit"))

    def test_create_in_my_drive(self):
        result = self._create(folder_id="MY", supported_format="xlsx", title="Budget")
        document = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual((document.folder_id.id, document.owner_id), (False, self.owner))

    def test_create_from_a_gallery_form(self):
        form = MagicMock(content=b"%PDF-1.7 form")
        with patch(f"{CONTROLLERS}.requests.get", return_value=form) as get:
            result = self._create(
                folder_id=self.folder.id, supported_format="pdf", title="Lease", url="https://forms.example/lease.pdf"
            )
        get.assert_called_once()
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).raw, b"%PDF-1.7 form")

    def test_create_in_a_read_only_folder_creates_nothing(self):
        read_only = self.env["documents.document"].create(
            {"name": "OO Read-only", "type": "folder", "access_internal": "view"}
        )

        result = self._create(folder_id=read_only.id, supported_format="docx", title="Intruder")

        self.assertEqual(result["error"], "Failed to create document")
        self.assertFalse(self.env["documents.document"].search([("name", "=", "Intruder.docx")]))

    # -- POST /onlyoffice/documents/file/convert --

    def test_convert_and_save_next_to_the_source(self):
        document = self._document()

        result, request = self._convert(document)

        self.assertTrue(result["saved"])
        converted = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual((converted.name, converted.folder_id), ("Report.pdf", self.folder))
        self.assertEqual(converted.raw, b"%PDF-1.7 converted")
        converter, download = request.call_args_list
        self.assertIn("/converter", converter.kwargs["url"])
        body = json.loads(converter.kwargs["opts"]["data"])
        self.assertEqual((body["filetype"], body["outputtype"], body["async"]), ("docx", "pdf", False))
        self.assertIn(f"/onlyoffice/file/content/{document.attachment_id.id}?oo_security_token=", body["url"])
        self.assertEqual(download.kwargs["url"], "http://documentserver/out.pdf")

    def test_convert_and_download(self):
        result, _request = self._convert(self._document(), target_format="odt", save_to_documents=False)
        self.assertEqual((result["saved"], result["filename"]), (False, "Report.odt"))
        self.assertTrue(result["data"])

    def test_converter_request_is_signed_when_jwt_is_enabled(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        _result, request = self._convert(self._document())
        body = json.loads(request.call_args_list[0].kwargs["opts"]["data"])
        self.assertEqual(jwt_utils.decode_token(self.env, body["token"], "ds-secret")["outputtype"], "pdf")

    def test_convert_errors(self):
        failed = MagicMock(status_code=200)
        failed.json.return_value = {"error": -4}
        self.assertEqual(self._convert(self._document(), target_format="exe")[0]["error"], "Unsupported target format")
        self.assertEqual(
            self._convert(self._document(), responses=[failed])[0]["error"],
            "Error while downloading the document file to be converted",
        )
        self.assertEqual(
            self._convert(self.env["documents.document"].browse(999_999_999))[0]["error"], "Document not found"
        )

    def test_convert_needs_access(self):
        no_role = self._document()
        self._roles(no_role, internal_users="edit", colleague="none")
        locked = self._document()
        locked.sudo().lock_uid = self.owner
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")

        result, request = self._convert(no_role)
        self.assertEqual(result["error"], "You do not have access to this document")
        self.assertEqual(self._convert(locked)[0]["error"], "This document is locked by another user")
        request.assert_not_called()
