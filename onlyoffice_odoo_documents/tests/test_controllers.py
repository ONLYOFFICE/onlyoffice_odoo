# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase, new_test_user

from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

from .common import INTERNAL_SECRET, XLSX_MIMETYPE, DocumentsCase, blank, xlsx_with_metadata

CONTROLLERS = "odoo.addons.onlyoffice_odoo_documents.controllers.controllers"
URLOPEN = "odoo.addons.onlyoffice_odoo.controllers.main.onlyoffice_urlopen"
FORM_GET = "odoo.addons.onlyoffice_odoo.utils.url_utils.requests.get"
FORM_FILE = "https://static-oforms.onlyoffice.com/uploads/lease.pdf"


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
        }
        for roles, result in expected.items():
            with self.subTest(roles=roles):
                document = self._document()
                self._roles(document, **dict(roles))
                self.assertEqual(self._editor("oo_doc_colleague", document), result)

    def _read_only_document(self):
        """A document of the shared folder that internal users may only read (a new one takes the folder access)."""
        document = self._document()
        document.action_update_access_rights(access_internal="view")
        return document

    def test_roles_of_a_colleague_who_can_only_read(self):
        """Edit needs the right to write in Odoo; commenting roles save with the right to read, signed by JWT."""
        config_utils.set_jwt_secret(self.env, "ds-secret")
        expected = {
            (): ("view", {"edit": False}),
            (("internal_users", "custom_filter"),): ("view", {"edit": False}),
            (("colleague", "commenter"),): ("edit", {"edit": False, "comment": True}),
            (("internal_users", "reviewer"),): ("edit", {"edit": False, "review": True}),
        }
        for roles, result in expected.items():
            with self.subTest(roles=roles):
                document = self._read_only_document()
                self._roles(document, **dict(roles))
                self.assertEqual(self._editor("oo_doc_colleague", document), result)
                config = self._config("oo_doc_colleague", document_id=document.id)["result"]["editorConfig"]
                self.assertEqual("callbackUrl" in config["editorConfig"], result[0] == "edit")

    def test_commenting_roles_only_view_without_jwt_when_the_user_cannot_write(self):
        document = self._read_only_document()
        self._roles(document, colleague="commenter")
        self.assertEqual(self._editor("oo_doc_colleague", document), ("view", {"edit": False}))

    def test_an_invitation_of_odoo_comes_before_the_role_of_internal_users(self):
        document = self._read_only_document()
        document.with_user(self.owner).action_update_access_rights(
            access_internal="commenter", partners={self.colleague.partner_id.id: ("edit", None)}
        )
        self.assertEqual(self._editor("oo_doc_colleague", document), ("edit", {"edit": True}))

    def _group(self, name):
        return self.env["res.group.functional"].create({"name": name, "user_ids": [(6, 0, self.colleague.ids)]})

    def test_the_widest_role_of_the_groups_of_a_colleague(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        cases = {
            "view and edit": (["view", "edit"], ("edit", {"edit": True})),
            "view and commenter": (["view", "commenter"], ("edit", {"edit": False, "comment": True})),
            "view only": (["view"], ("view", {"edit": False})),
        }
        for case, (roles, result) in cases.items():
            with self.subTest(case=case):
                document = self._read_only_document()
                groups = {self._group(f"OO {case} {i}").id: (role, None) for i, role in enumerate(roles)}
                document.with_user(self.owner).action_update_access_rights(groups=groups)
                self.assertEqual(self._editor("oo_doc_colleague", document), result)

    def test_the_role_of_a_colleague_comes_before_that_of_their_groups(self):
        document = self._read_only_document()
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("commenter", None)},
            groups={self._group("OO Editors").id: ("edit", None)},
        )
        self.assertEqual(self._editor("oo_doc_colleague", document), ("edit", {"edit": False, "comment": True}))

    def test_an_expired_or_turned_off_group_gives_no_role(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        expired, viewers = self._group("OO Expired"), self._group("OO Viewers")
        document = self._read_only_document()
        document.with_user(self.owner).action_update_access_rights(
            groups={expired.id: ("commenter", None), viewers.id: ("view", None)}
        )
        document.access_ids.filtered(lambda a: a.group_id == expired).sudo().expiration_date = "2020-01-01 00:00:00"
        self.assertEqual(self._editor("oo_doc_colleague", document), ("view", {"edit": False}))

        # A role of Odoo in a group row ("none", written by older versions) is not used: Odoo decides.
        AccessGroup = self.env["onlyoffice.odoo.documents.access.group"]
        AccessGroup.search([("document_id", "=", document.id)]).unlink()
        AccessGroup.create({"document_id": document.id, "group_id": viewers.id, "role": "none"})
        self.assertEqual(self._editor("oo_doc_colleague", document), ("view", {"edit": False}))

    def test_an_expired_invitation_gives_no_role(self):
        config_utils.set_jwt_secret(self.env, "ds-secret")
        document = self._read_only_document()
        document.with_user(self.owner).action_update_access_rights(
            partners={self.colleague.partner_id.id: ("commenter", None)}
        )
        invitation = document.access_ids.filtered(lambda a: a.partner_id == self.colleague.partner_id)
        invitation.sudo().expiration_date = "2020-01-01 00:00:00"
        self.assertEqual(self._editor("oo_doc_colleague", document), ("view", {"edit": False}))

    def test_a_document_shared_by_link_opens_with_the_rights_of_the_link(self):
        """A colleague who followed the link of Odoo gets its rights in ONLYOFFICE too."""
        document = self._document()
        document.action_update_access_rights(access_internal="none", access_via_link="edit")
        self.env["documents.access"].create(
            {"document_id": document.id, "partner_id": self.colleague.partner_id.id, "last_access_date": "2026-01-01"}
        )
        self.assertEqual(self._editor("oo_doc_colleague", document), ("edit", {"edit": True}))

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

    def test_the_editor_shows_the_name_of_the_document(self):
        # Renamed in Odoo, a document keeps the former name on its attachment.
        document = self._document()
        document.name = "Q3 Report.docx"

        config = self._config("oo_doc_owner", document_id=document.id)["result"]
        page = self.url_open(f"/onlyoffice/editor/document/{document.id}")

        self.assertEqual(config["editorConfig"]["document"]["title"], "Q3 Report.docx")
        self.assertEqual(config["docTitle"], "Q3 Report.docx")
        self.assertEqual(self._editor_config(page.text)["document"]["title"], "Q3 Report.docx")
        self.assertEqual(config["editorConfig"]["document"]["fileType"], "docx")

    def test_a_shortcut_opens_the_document_it_points_to(self):
        document = self._document()
        shortcut = self._document(shortcut_document_id=document.id, raw=False)

        config = self._config("oo_doc_owner", document_id=shortcut.id)["result"]
        page = self.url_open(f"/onlyoffice/editor/document/{shortcut.id}")

        self.assertEqual(config["document_id"], document.id)
        self.assertIn(
            f"/onlyoffice/editor/callback/{document.attachment_id.id}?",
            config["editorConfig"]["editorConfig"]["callbackUrl"],
        )
        self.assertEqual(page.status_code, 200)
        self.assertIn(
            f"/onlyoffice/file/content/{document.attachment_id.id}?", self._editor_config(page.text)["document"]["url"]
        )

    def test_a_shortcut_to_a_document_the_user_cannot_read_does_not_open(self):
        private = self._document(folder_id=False, access_internal="none")
        shortcut = self._document(shortcut_document_id=private.id, raw=False, user=self.owner)
        shortcut.sudo().owner_id = self.colleague
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")

        response = self.url_open(f"/onlyoffice/editor/document/{shortcut.id}", allow_redirects=False)

        self.assertEqual(response.status_code, 403)

    # -- GET /onlyoffice/editor/document/<id> --

    def test_editor_page_of_a_document(self):
        document = self._document()
        self.authenticate("oo_doc_owner", "oo_doc_owner")

        response = self.url_open(f"/onlyoffice/editor/document/{document.id}")

        self.assertEqual(response.status_code, 200)
        config = self._editor_config(response.text)
        self.assertEqual(config["document"]["title"], "Report.docx")
        self.assertEqual(config["editorConfig"]["mode"], "edit")

    def test_editor_page_does_not_run_the_text_of_a_file(self):
        # The labels of the filters come from the metadata sheet of the file, written by whoever uploads it.
        label = "</script><script>window.injected=1</script>"
        metadata = {"lists": {}, "globalFilters": [{"label": label, "defaultValue": "<b>EU</b>"}]}
        document = self._document("Sales.xlsx", content=xlsx_with_metadata(metadata), mimetype=XLSX_MIMETYPE)
        self.authenticate("oo_doc_owner", "oo_doc_owner")

        page = self.url_open(f"/onlyoffice/editor/document/{document.id}").text

        self.assertNotIn("<script>window.injected", page)
        self.assertNotIn("</script><script>", page)
        self.assertIn("window.odooFilterValues = ", page)

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
    """The base save callback for a Documents file: a new version, the previous one kept in its history."""

    def _save(self, document, user, content, jwt_secret=None):
        downloaded = MagicMock()
        downloaded.read.return_value = content
        token = self._internal_token({"id": user.id})
        body = {"status": 2, "url": "http://documentserver/cache/files/out.docx"}
        if jwt_secret:
            config_utils.set_jwt_secret(self.env, jwt_secret)
            body = {"token": jwt_utils.encode_payload(self.env, body, jwt_secret)}
        with patch(URLOPEN, return_value=downloaded):
            return self.url_open(
                f"/onlyoffice/editor/callback/{document.attachment_id.id}?oo_security_token={token}",
                data=json.dumps(body),
                headers={"Content-Type": "application/json"},
            )

    def test_a_save_keeps_the_name_the_document_got_in_odoo(self):
        document = self._document()
        document.name = "Q3 Report.docx"

        self.assertEqual(self._save(document, self.owner, b"edited").json(), {"error": 0})

        self.env.invalidate_all()
        self.assertEqual((document.name, document.raw.content), ("Q3 Report.docx", b"edited"))

    def test_each_save_keeps_the_previous_version(self):
        document = self._document()
        attachment = document.attachment_id
        original = attachment.raw.content

        self.assertEqual(self._save(document, self.owner, b"version 2").json(), {"error": 0})
        self.assertEqual(self._save(document, self.owner, b"version 3").json(), {"error": 0})

        self.env.invalidate_all()
        self.assertEqual(document.attachment_id, attachment)
        self.assertEqual(attachment.raw.content, b"version 3")
        # Documents copies the replaced file into the history under its name; nothing is renamed or numbered.
        previous = document.previous_attachment_ids
        self.assertEqual(sorted(previous.mapped(lambda a: a.raw.content)), sorted([original, b"version 2"]))
        self.assertEqual(set(previous.mapped("name")), {"Report.docx"})
        self.assertIn("Document edited by OO Owner", document.message_ids.mapped("body")[0])

    def test_a_commenter_who_can_only_read_saves_when_jwt_signs_the_save(self):
        document = self._document()
        document.action_update_access_rights(access_internal="view")
        self._roles(document, colleague="commenter")

        response = self._save(document, self.colleague, b"commented", jwt_secret="ds-secret")

        self.assertEqual(response.json(), {"error": 0})
        self.env.invalidate_all()
        self.assertEqual(document.attachment_id.raw.content, b"commented")
        self.assertEqual(document.write_uid, self.colleague, "the user stays the author")
        self.assertIn("Document edited by OO Colleague", document.message_ids.mapped("body")[0])

    def test_a_save_without_the_right_to_write_is_rejected(self):
        """Without JWT a save cannot be trusted; edit needs the right to write whatever signs it."""
        cases = {"commenter without jwt": ("commenter", None), "custom filter with jwt": ("custom_filter", "ds-secret")}
        for case, (role, jwt_secret) in cases.items():
            with self.subTest(case=case):
                document = self._document()
                document.action_update_access_rights(access_internal="view")
                self._roles(document, internal_users=role)

                response = self._save(document, self.colleague, b"overwritten", jwt_secret=jwt_secret)

                self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
                self.env.invalidate_all()
                self.assertEqual(document.attachment_id.raw.content, blank("docx"))

    def test_save_by_a_viewer_is_rejected(self):
        document = self._document()
        document.action_update_access_rights(access_internal="view")

        response = self._save(document, self.colleague, b"overwritten")

        self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
        self.env.invalidate_all()
        self.assertEqual(document.attachment_id.raw.content, blank("docx"))


@tagged("post_install", "-at_install")
class TestCreateAndConvert(DocumentsCase, HttpCase):
    """The "Create with ONLYOFFICE" and "Convert with ONLYOFFICE" dialogs."""

    def setUp(self):
        super().setUp()
        self.authenticate("oo_doc_owner", "oo_doc_owner")

    def _create(self, **params):
        return json.loads(self._rpc("/onlyoffice/documents/file/create", **params)["result"])

    def _convert(self, document, target_format="pdf", save_to_documents=True, responses=None, **params):
        converted = MagicMock(status_code=200)
        converted.json.return_value = {"endConvert": True, "fileUrl": "http://documentserver/out.pdf", "percent": 100}
        responses = responses or [converted, MagicMock(content=b"%PDF-1.7 converted")]
        with patch(f"{CONTROLLERS}.onlyoffice_request", side_effect=responses) as request:
            body = self._rpc(
                "/onlyoffice/documents/file/convert",
                document_id=document.id,
                target_format=target_format,
                save_to_documents=save_to_documents,
                **params,
            )
        return json.loads(body["result"]), request

    def _spreadsheet(self):
        return (
            self.env["documents.document"]
            .with_user(self.owner)
            .create(
                {
                    "name": "Sales",
                    "handler": "spreadsheet",
                    "mimetype": "application/o-spreadsheet",
                    "spreadsheet_data": json.dumps({"sheets": [{"id": "s1", "name": "Sheet1"}]}),
                    "folder_id": self.folder.id,
                }
            )
        )

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
        self.assertEqual(document.raw.content, file_utils.get_default_file_template("en_US", "docx"))
        self.assertEqual(document.mimetype, file_utils.get_mime_by_ext("docx"))
        # No ONLYOFFICE roles: the rights of Odoo decide.
        self.assertFalse(self.env["onlyoffice.odoo.documents.access"].search([("document_id", "=", document.id)]))
        self.assertFalse(self.env["onlyoffice.odoo.documents.access.user"].search([("document_id", "=", document.id)]))

    def test_a_colleague_who_can_edit_works_on_a_created_document(self):
        result = self._create(folder_id=self.folder.id, supported_format="docx", title="Plan")
        document = self.env["documents.document"].browse(result["document_id"])
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")

        config = self._rpc("/onlyoffice/editor/get_config", document_id=document.id)["result"]["editorConfig"]

        self.assertEqual(config["editorConfig"]["mode"], "edit")
        self.assertIn("callbackUrl", config["editorConfig"])
        self.assertTrue(self._convert(document)[0]["saved"])

    def test_create_in_my_drive(self):
        result = self._create(folder_id="MY", supported_format="xlsx", title="Budget")
        document = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual((document.folder_id.id, document.owner_id), (False, self.owner))

    def test_create_from_a_gallery_form(self):
        form = MagicMock(status_code=200)
        form.__enter__.return_value = form
        form.iter_content.return_value = [b"%PDF-1.7 form"]
        with patch(FORM_GET, return_value=form) as get:
            result = self._create(folder_id=self.folder.id, supported_format="pdf", title="Lease", url=FORM_FILE)
        self.assertEqual(get.call_args.args[0], FORM_FILE)
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).raw.content, b"%PDF-1.7 form")

    def test_create_takes_only_forms_of_the_gallery_and_known_formats(self):
        cases = {
            "an internal address": {"supported_format": "pdf", "url": "http://localhost:8069/web/content/1/x.pdf"},
            "another format": {"supported_format": "txt"},
            "a format other than the file": {"supported_format": "docx", "url": FORM_FILE},
        }
        for case, params in cases.items():
            with self.subTest(case=case), patch(FORM_GET) as get:
                result = self._create(folder_id=self.folder.id, title="Intruder", **params)
                self.assertEqual(result["error"], "Failed to create document")
                get.assert_not_called()
        self.assertFalse(self.env["documents.document"].search([("name", "like", "Intruder")]))

    def test_portal_user_cannot_create(self):
        new_test_user(self.env, login="oo_doc_portal", groups="base.group_portal")
        self.authenticate("oo_doc_portal", "oo_doc_portal")
        with patch(FORM_GET) as get:
            result = self._create(folder_id=self.folder.id, supported_format="pdf", title="Portal", url=FORM_FILE)
        self.assertEqual(result["error"], "Failed to create document")
        get.assert_not_called()

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
        self.assertEqual(converted.raw.content, b"%PDF-1.7 converted")
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

    def test_an_odoo_spreadsheet_is_converted_from_its_export(self):
        spreadsheet = self._spreadsheet()
        export = blank("xlsx")
        xlsx_base64 = base64.b64encode(export).decode()

        result, request = self._convert(spreadsheet, target_format="xlsx", xlsx_base64=xlsx_base64)

        request.assert_not_called()
        converted = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual(
            (converted.name, converted.raw.content, converted.folder_id), ("Sales.xlsx", export, self.folder)
        )
        # A file, not another Odoo Spreadsheet.
        self.assertEqual((converted.handler, converted.mimetype), (False, XLSX_MIMETYPE))
        self.assertFalse(converted.spreadsheet_revision_ids)

        result, request = self._convert(spreadsheet, xlsx_base64=xlsx_base64)

        self.assertTrue(result["saved"])
        body = json.loads(request.call_args_list[0].kwargs["opts"]["data"])
        self.assertEqual((body["filetype"], body["outputtype"]), ("xlsx", "pdf"))
        # The Document Server takes the export once, from the cache of the Document Builder files.
        token = body["url"].split("/onlyoffice/documents/docbuilder_file/")[1]
        self.assertEqual(self.url_open(f"/onlyoffice/documents/docbuilder_file/{token}").status_code, 404)
        pdf = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual((pdf.name, pdf.handler, pdf.mimetype), ("Sales.pdf", False, "application/pdf"))

    def test_an_odoo_spreadsheet_needs_its_export(self):
        result, request = self._convert(self._spreadsheet())
        self.assertEqual(result["error"], "Native spreadsheet export is required for conversion")
        request.assert_not_called()

    def test_a_file_without_extension_takes_the_format_of_its_type(self):
        document = self._document("Contract", content=blank("docx"), mimetype=file_utils.get_mime_by_ext("docx"))

        result, request = self._convert(document)

        body = json.loads(request.call_args_list[0].kwargs["opts"]["data"])
        self.assertEqual((body["filetype"], body["outputtype"]), ("docx", "pdf"))
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).name, "Contract.pdf")

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

    def test_convert_needs_the_right_to_read_and_ignores_locks(self):
        private = self._document(folder_id=False)
        read_only = self._document()
        read_only.action_update_access_rights(access_internal="view")
        locked = self._document()
        locked.sudo().lock_uid = self.owner
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")

        for document in (private,):
            with self.subTest(document=document.id):
                result, request = self._convert(document)
                self.assertEqual(result["error"], "You do not have access to this document")
                request.assert_not_called()
        for document in (read_only, locked):
            with self.subTest(document=document.id):
                self.assertFalse(self._convert(document, save_to_documents=False)[0]["error"])

    def test_a_converted_copy_has_the_name_of_the_document(self):
        document = self._document()
        document.name = "Q3 Report.docx"
        result, _request = self._convert(document)
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).name, "Q3 Report.pdf")
        # A name without the extension keeps all of it.
        document.name = "Q3 Report v1.2"
        result, _request = self._convert(document)
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).name, "Q3 Report v1.2.pdf")

    def test_a_shortcut_converts_the_document_it_points_to(self):
        document = self._document()
        shortcut = self._document(shortcut_document_id=document.id, raw=False)

        result, request = self._convert(shortcut)

        self.assertFalse(result["error"])
        self.assertIn(f"/onlyoffice/file/content/{document.attachment_id.id}?", str(request.call_args_list[0]))
        self.assertEqual(self.env["documents.document"].browse(result["document_id"]).name, "Report.pdf")

    def test_converted_copy_goes_where_duplicate_puts_it(self):
        """Next to the source when the user may create there, otherwise in their own drive."""
        Document = self.env["documents.document"]
        new_test_user(self.env, login="oo_doc_manager", groups="base.group_user,documents.group_documents_manager")
        read_only = Document.create({"name": "OO Read-only", "type": "folder", "access_internal": "view"})
        odoobot = self.env.ref("base.user_root")
        # Odoo 19 creates a document of an archived owner (OdooBot) without owner: the company root.
        company_root = {"folder_id": False, "owner_id": odoobot.id, "access_internal": "view"}
        no_owner = self.env["res.users"]
        cases = [
            ("own drive", "oo_doc_owner", self._document(folder_id=False), self.owner),
            (
                "read-only folder",
                "oo_doc_colleague",
                self._document(user=odoobot, folder_id=read_only.id),
                self.colleague,
            ),
            ("company root, manager", "oo_doc_manager", self._document(user=odoobot, **company_root), no_owner),
            ("company root, user", "oo_doc_colleague", self._document(user=odoobot, **company_root), self.colleague),
        ]
        for case, login, document, owner in cases:
            with self.subTest(case=case):
                self.authenticate(login, login)
                result, _request = self._convert(document)
                self.assertTrue(result.get("saved"), result)
                converted = Document.browse(result["document_id"])
                self.assertEqual((converted.folder_id, converted.owner_id), (Document, owner))
                self.assertEqual((converted.name, converted.raw.content), ("Report.pdf", b"%PDF-1.7 converted"))
                self.assertEqual(converted.mimetype, "application/pdf")

    def test_converted_copy_gets_the_access_of_the_source(self):
        contact = self.env["res.partner"].create({"name": "OO Contact", "email": "oo.contact@example.com"})
        document = self._document()
        document.action_update_access_rights(access_internal="view", partners={contact.id: ("view", None)})
        document.sudo().lock_uid = self.owner

        result, _request = self._convert(document)

        converted = self.env["documents.document"].browse(result["document_id"])
        self.assertEqual(converted.folder_id, self.folder)
        self.assertEqual(converted.access_internal, "view", "not the edit of the folder")
        self.assertIn(contact, converted.access_ids.partner_id)
        self.assertFalse(converted.lock_uid)
