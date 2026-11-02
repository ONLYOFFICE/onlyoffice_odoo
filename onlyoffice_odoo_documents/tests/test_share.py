# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
from unittest.mock import MagicMock, patch

from odoo.tests import tagged
from odoo.tests.common import HttpCase

from odoo.addons.onlyoffice_odoo.utils import config_utils

from .common import DocumentsCase, blank

URLOPEN = "odoo.addons.onlyoffice_odoo_documents.controllers.controllers.urlopen"


@tagged("post_install", "-at_install")
class TestShareLink(DocumentsCase, HttpCase):
    """Documents shared by link: the portal page button, the share editor and its own save callback."""

    def setUp(self):
        super().setUp()
        self.public_user = self.env.ref("base.public_user")
        self.shared = self._document(access_via_link="view")

    def _shared_folder(self):
        return self.env["documents.document"].create(
            {"name": "OO Shared", "type": "folder", "access_internal": "edit", "access_via_link": "view"}
        )

    def _raw(self, document):
        self.env.invalidate_all()
        return document.attachment_id.raw

    def _open(self, document, folder=None):
        query = f"?folder_token={folder.access_token}" if folder else ""
        return self.url_open(f"/onlyoffice/documents/share/{document.access_token}/{query}", allow_redirects=False)

    def _config(self, document, folder=None):
        response = self._open(document, folder)
        self.assertEqual(response.status_code, 200)
        return self._editor_config(response.text)

    def _save(self, document, user, status=2):
        downloaded = MagicMock()
        downloaded.read.return_value = b"edited through the link"
        token = self._internal_token({"id": user.id})
        with patch(URLOPEN, return_value=downloaded):
            return self.url_open(
                f"/onlyoffice/documents/share/callback/{document.access_token}/{token}",
                data=json.dumps({"status": status, "url": "http://documentserver/cache/files/out.docx"}),
                headers={"Content-Type": "application/json"},
            )

    # -- Portal pages (/documents/<access_token>) --

    def test_portal_page_offers_onlyoffice_for_office_files(self):
        response = self.url_open(f"/documents/{self.shared.access_token}")
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'href="/onlyoffice/documents/share/{self.shared.access_token}"', response.text)

        archive = self._document("Backup.zip", content=b"PK\x05\x06" + b"\0" * 18, access_via_link="view")
        response = self.url_open(f"/documents/{archive.access_token}")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Open in ONLYOFFICE", response.text)

    def test_portal_page_of_a_shared_folder(self):
        folder = self._shared_folder()
        child = self._document(folder_id=folder.id, access_via_link="view")

        response = self.url_open(f"/documents/{folder.access_token}")

        self.assertEqual(response.status_code, 200)
        link = f"/onlyoffice/documents/share/{child.access_token}?folder_token={folder.access_token}"
        self.assertIn(link.replace("&", "&amp;"), response.text)

    # -- GET /onlyoffice/documents/share/<access_token>/ --

    def test_visitor_views_a_document_shared_by_link(self):
        config = self._config(self.shared)

        self.assertEqual(config["editorConfig"]["mode"], "view")
        self.assertNotIn("callbackUrl", config["editorConfig"])
        self.assertTrue(config["document"]["url"].endswith(f"/documents/content/{self.shared.access_token}"))

    def test_link_role_decides_what_the_visitor_can_do(self):
        expected = {
            "commenter": ("edit", {"edit": False, "comment": True}),
            "form_filling": ("edit", {"edit": False, "fillForms": True}),
            "edit": ("edit", {"edit": True}),
        }
        for role, (mode, permissions) in expected.items():
            with self.subTest(role=role):
                document = self._document(access_via_link="view")
                self._roles(document, link_access=role)
                config = self._config(document)
                self.assertEqual(
                    (config["editorConfig"]["mode"], config["document"]["permissions"]), (mode, permissions)
                )
                callback = config["editorConfig"]["callbackUrl"]
                self.assertIn(f"/onlyoffice/documents/share/callback/{document.access_token}/", callback)

    def test_logged_in_user_gets_their_own_role(self):
        self._roles(self.shared, link_access="view", colleague="reviewer")
        self.authenticate("oo_doc_colleague", "oo_doc_colleague")

        config = self._config(self.shared)

        self.assertEqual(config["document"]["permissions"], {"edit": False, "review": True})
        self.assertEqual(config["editorConfig"]["user"]["id"], str(self.colleague.id))

    def test_blocked_links_are_not_found(self):
        blocked = self._document(access_via_link="view")
        self._roles(blocked, link_access="none")
        not_shared = self._document()
        for document in (blocked, not_shared):
            with self.subTest(document=document.access_via_link):
                self.assertEqual(self._open(document).status_code, 404)

    def test_document_opened_from_its_shared_folder(self):
        folder = self._shared_folder()
        child = self._document(folder_id=folder.id, access_via_link="view")
        self._roles(folder, link_access="edit")

        config = self._config(child, folder)

        self.assertEqual(config["editorConfig"]["mode"], "edit")
        self.assertTrue(config["editorConfig"]["callbackUrl"].endswith(f"?folder_token={folder.access_token}"))
        self.assertEqual(self._open(self.shared, folder).status_code, 404, "not a child of that folder")

    # -- POST /onlyoffice/documents/share/callback/<access_token>/<oo_security_token> --

    def test_visitor_with_an_edit_link_saves(self):
        self._roles(self.shared, link_access="edit")

        response = self._save(self.shared, self.public_user)

        self.assertEqual(response.json(), {"error": 0})
        self.assertEqual(self._raw(self.shared), b"edited through the link")

    def test_user_with_an_edit_role_saves_through_a_view_link(self):
        self._roles(self.shared, link_access="view", colleague="edit")
        self.assertEqual(self._save(self.shared, self.colleague).json(), {"error": 0})
        self.assertEqual(self._raw(self.shared), b"edited through the link")

    def test_view_link_cannot_save(self):
        self._roles(self.shared, link_access="view", owner="edit")

        response = self._save(self.shared, self.colleague)

        self.assertEqual((response.status_code, response.json()["error"]), (500, 1))
        self.assertEqual(self._raw(self.shared), blank("docx"))

    def test_callback_needs_the_document_server_token_when_jwt_is_enabled(self):
        self._roles(self.shared, link_access="edit")
        config_utils.set_jwt_secret(self.env, "ds-secret")

        response = self._save(self.shared, self.public_user)

        self.assertEqual(response.json()["error"], 1)
        self.assertEqual(self._raw(self.shared), blank("docx"))

    def test_status_without_a_file_changes_nothing(self):
        self._roles(self.shared, link_access="edit")
        self.assertEqual(self._save(self.shared, self.public_user, status=1).json(), {"error": 0})
        self.assertEqual(self._raw(self.shared), blank("docx"))

    # -- ONLYOFFICE Desktop Editors --

    def test_desktop_editors_land_in_documents(self):
        self.authenticate("oo_doc_owner", "oo_doc_owner")
        response = self.url_open("/Products/Files", allow_redirects=False)
        self.assertIn(response.status_code, (302, 303))
        self.assertTrue(response.headers["Location"].endswith("/odoo/action-documents.document_action"))
