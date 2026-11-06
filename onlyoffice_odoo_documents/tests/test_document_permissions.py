import base64

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user
from odoo.tools import mute_logger


@tagged("-at_install", "post_install")
class TestDocumentPermissions(TransactionCase):
    def setUp(self):
        super().setUp()
        groups = "base.group_user,documents.group_documents_user"
        self.creator = new_test_user(
            self.env,
            login="onlyoffice_creator",
            email="onlyoffice_creator@example.com",
            groups=groups,
        )
        self.editor = new_test_user(
            self.env,
            login="onlyoffice_editor",
            email="onlyoffice_editor@example.com",
            groups=groups,
        )
        self.reader = new_test_user(
            self.env,
            login="onlyoffice_reader",
            email="onlyoffice_reader@example.com",
            groups=groups,
        )
        self.outsider = new_test_user(
            self.env,
            login="onlyoffice_outsider",
            email="onlyoffice_outsider@example.com",
            groups=groups,
        )
        documents = self.env["documents.document"].with_context(tracking_disable=True)
        self.source_folder = (
            documents.with_user(self.creator)
            .create(
                {
                    "name": "ONLYOFFICE shared source",
                    "type": "folder",
                    "access_internal": "none",
                    "access_via_link": "none",
                    "access_ids": [
                        Command.create({"partner_id": self.editor.partner_id.id, "role": "edit"}),
                        Command.create({"partner_id": self.reader.partner_id.id, "role": "view"}),
                    ],
                }
            )
            .with_env(self.env)
        )
        self.destination_folder = (
            documents.with_user(self.editor)
            .create(
                {
                    "name": "ONLYOFFICE editor destination",
                    "type": "folder",
                    "access_internal": "view",
                    "access_via_link": "view",
                    "access_ids": [
                        Command.create({"partner_id": self.reader.partner_id.id, "role": "edit"}),
                    ],
                }
            )
            .with_env(self.env)
        )
        self.document = (
            documents.with_user(self.creator)
            .create(
                {
                    "name": "onlyoffice-permissions.txt",
                    "type": "binary",
                    "datas": base64.b64encode(b"Synthetic ONLYOFFICE permission regression fixture."),
                    "mimetype": "text/plain",
                    "folder_id": self.source_folder.id,
                }
            )
            .with_env(self.env)
        )
        self.sharing = self.env["onlyoffice.odoo.documents"]
        self.access_model = self.env["onlyoffice.odoo.documents.access"]
        self.user_access_model = self.env["onlyoffice.odoo.documents.access.user"]
        self.access_settings = self.access_model.create(
            {
                "document_id": self.document.id,
                "internal_users": "none",
                "link_access": "none",
            }
        )
        self.user_access_settings = self.user_access_model.create(
            [
                {"document_id": self.document.id, "user_id": self.creator.partner_id.id, "role": "edit"},
                {"document_id": self.document.id, "user_id": self.reader.partner_id.id, "role": "view"},
            ]
        )

    def _sharing_values(self):
        return {
            "document_id": self.document.id,
            "internal_users": "commenter",
            "link_access": "reviewer",
            "users_to_remove": [self.creator.partner_id.id],
            "user_accesses": [
                {"user_id": self.reader.partner_id.id, "role": "reviewer"},
                {"user_id": self.outsider.partner_id.id, "role": "commenter"},
            ],
        }

    def _onlyoffice_settings_snapshot(self):
        domain = [("document_id", "=", self.document.id)]
        return {
            "document": self.access_model.search(domain, order="id").read(
                ["internal_users", "link_access", "write_uid", "write_date"], load=False
            ),
            "users": self.user_access_model.search(domain, order="id").read(
                ["user_id", "role", "write_uid", "write_date"], load=False
            ),
        }

    def test_non_creator_editor_can_move_document_and_sync_permissions(self):
        # Arrange
        document_as_editor = self.document.with_user(self.editor)
        self.assertFalse(
            document_as_editor.env.su,
            "Moving another user's document must exercise the editor's rights, not superuser mode.",
        )
        for group in ("base.group_system", "documents.group_documents_manager", "documents.group_documents_system"):
            self.assertFalse(
                self.editor.has_group(group),
                f"The non-creator move must succeed without membership in {group}.",
            )
        self.assertRecordValues(
            self.document,
            [{"create_uid": self.creator.id, "owner_id": self.creator.id, "folder_id": self.source_folder.id}],
        )
        self.assertEqual(
            self.destination_folder.owner_id,
            self.editor,
            "The editor moving another user's document must own the destination folder.",
        )
        for record in (self.source_folder, self.document, self.destination_folder):
            record.with_user(self.editor).check_access("write")
        self.assertTrue(
            document_as_editor.user_can_move,
            "An editor of both the source and document must be allowed to move the other user's document.",
        )

        # Act
        result = document_as_editor.write({"folder_id": self.destination_folder.id})

        # Assert
        self.assertTrue(result, "Moving another user's document as an authorized editor must succeed.")
        self.assertRecordValues(
            self.document,
            [
                {
                    "folder_id": self.destination_folder.id,
                    "owner_id": self.creator.id,
                    "create_uid": self.creator.id,
                    "access_internal": "view",
                    "access_via_link": "view",
                }
            ],
        )
        access = self.access_model.search([("document_id", "=", self.document.id)])
        self.assertEqual(
            access,
            self.access_settings,
            "Moving the document must update its existing ONLYOFFICE settings without creating a duplicate.",
        )
        self.assertRecordValues(access, [{"internal_users": "view", "link_access": "view"}])
        reader_access = self.document.access_ids.filtered(lambda access: access.partner_id == self.reader.partner_id)
        self.assertRecordValues(reader_access, [{"role": "edit"}])
        onlyoffice_reader_access = self.user_access_model.search(
            [("document_id", "=", self.document.id), ("user_id", "=", self.reader.partner_id.id)]
        )
        self.assertRecordValues(onlyoffice_reader_access, [{"role": "edit"}])

    def test_current_owner_different_from_creator_can_save_sharing(self):
        # Arrange
        self.document.with_user(self.creator).write({"owner_id": self.editor.id})
        self.assertRecordValues(self.document, [{"create_uid": self.creator.id, "owner_id": self.editor.id}])
        self.document.with_user(self.editor).check_access("write")
        values = self._sharing_values()

        # Act
        result = self.sharing.with_user(self.editor).advanced_share_save(values)

        # Assert
        self.assertTrue(result, "The current owner must be able to save sharing settings for another user's creation.")
        access = self.access_model.search([("document_id", "=", self.document.id)])
        self.assertEqual(
            access,
            self.access_settings,
            "Saving sharing as the current owner must reuse existing settings.",
        )
        self.assertRecordValues(access, [{"internal_users": "commenter", "link_access": "reviewer"}])
        user_accesses = self.user_access_model.search([("document_id", "=", self.document.id)]).sorted(
            lambda access: access.user_id.id
        )
        self.assertRecordValues(
            user_accesses,
            [
                {"user_id": self.reader.partner_id.id, "role": "reviewer"},
                {"user_id": self.outsider.partner_id.id, "role": "commenter"},
            ],
        )

    def test_non_creator_editor_can_create_sharing_settings(self):
        # Arrange
        self.access_settings.unlink()
        self.user_access_settings.unlink()
        self.document.with_user(self.editor).check_access("write")
        values = self._sharing_values()

        # Act
        result = self.sharing.with_user(self.editor).advanced_share_save(values)

        # Assert
        self.assertTrue(result, "A non-owner editor must be able to create missing ONLYOFFICE sharing settings.")
        access = self.access_model.search([("document_id", "=", self.document.id)])
        self.assertRecordValues(access, [{"internal_users": "commenter", "link_access": "reviewer"}])
        user_accesses = self.user_access_model.search([("document_id", "=", self.document.id)]).sorted(
            lambda access: access.user_id.id
        )
        self.assertRecordValues(
            user_accesses,
            [
                {"user_id": self.reader.partner_id.id, "role": "reviewer"},
                {"user_id": self.outsider.partner_id.id, "role": "commenter"},
            ],
        )

    @mute_logger("odoo.addons.base.models.ir_rule")
    def test_read_only_user_cannot_update_sharing_settings(self):
        # Arrange
        document_as_reader = self.document.with_user(self.reader)
        document_as_reader.check_access("read")
        self.assertFalse(
            document_as_reader.has_access("write"),
            "The read-only sharing scenario must not grant the reader native document write access.",
        )
        values = self._sharing_values()
        before = self._onlyoffice_settings_snapshot()

        # Act
        with self.assertRaises(AccessError, msg="A read-only user saving document sharing settings must be denied."):
            try:
                self.sharing.with_user(self.reader).advanced_share_save(values)
            finally:
                # Assert before assertRaises rolls back, so partial writes cannot be hidden by its savepoint.
                self.assertEqual(
                    self._onlyoffice_settings_snapshot(),
                    before,
                    "Denied read-only sharing must not update, create, or delete any ONLYOFFICE access settings.",
                )

    @mute_logger("odoo.addons.base.models.ir_rule")
    def test_read_only_user_cannot_create_sharing_settings(self):
        # Arrange
        self.access_settings.unlink()
        self.user_access_settings.unlink()
        document_as_reader = self.document.with_user(self.reader)
        document_as_reader.check_access("read")
        self.assertFalse(
            document_as_reader.has_access("write"),
            "The read-only user must remain unable to write the document when ONLYOFFICE settings are absent.",
        )
        values = self._sharing_values()

        # Act
        with self.assertRaises(AccessError, msg="A read-only user creating document sharing settings must be denied."):
            try:
                self.sharing.with_user(self.reader).advanced_share_save(values)
            finally:
                # Assert
                self.assertEqual(
                    self._onlyoffice_settings_snapshot(),
                    {"document": [], "users": []},
                    "Denied read-only sharing must not create document-level or per-user ONLYOFFICE settings.",
                )

    @mute_logger("odoo.addons.base.models.ir_rule")
    def test_original_creator_without_write_access_cannot_save_sharing(self):
        # Arrange
        self.document.with_user(self.creator).write({"owner_id": self.editor.id})
        self.document.action_update_access_rights(partners={self.creator.partner_id.id: ("view", False)})
        self.assertRecordValues(self.document, [{"create_uid": self.creator.id, "owner_id": self.editor.id}])
        document_as_creator = self.document.with_user(self.creator)
        document_as_creator.check_access("read")
        self.assertFalse(
            document_as_creator.has_access("write"),
            "The original creator must have lost native write access before attempting to save sharing.",
        )
        values = self._sharing_values()
        before = self._onlyoffice_settings_snapshot()

        # Act
        with self.assertRaises(AccessError, msg="The original creator without write access must not save sharing."):
            try:
                self.sharing.with_user(self.creator).advanced_share_save(values)
            finally:
                # Assert
                self.assertEqual(
                    self._onlyoffice_settings_snapshot(),
                    before,
                    "A denied original creator must not change ONLYOFFICE settings despite still being create_uid.",
                )

    @mute_logger("odoo.addons.base.models.ir_rule")
    def test_inaccessible_document_cannot_be_shared(self):
        # Arrange
        document_as_outsider = self.document.with_user(self.outsider)
        self.assertFalse(
            document_as_outsider.has_access("read"),
            "The inaccessible-document scenario must not give the outsider native read access.",
        )
        self.assertFalse(
            document_as_outsider.has_access("write"),
            "The inaccessible-document scenario must not give the outsider native write access.",
        )
        values = self._sharing_values()
        before = self._onlyoffice_settings_snapshot()

        # Act
        with self.assertRaises(AccessError, msg="Sharing an inaccessible document by its ID must be denied."):
            try:
                self.sharing.with_user(self.outsider).advanced_share_save(values)
            finally:
                # Assert
                self.assertEqual(
                    self._onlyoffice_settings_snapshot(),
                    before,
                    "Sharing an inaccessible document must not grant access or change existing ONLYOFFICE settings.",
                )

    def test_missing_document_id_cannot_save_sharing(self):
        for document_id in (None, False):
            with self.subTest(document_id=document_id):
                # Arrange
                values = self._sharing_values()
                if document_id is None:
                    values.pop("document_id")
                else:
                    values["document_id"] = document_id
                before = self._onlyoffice_settings_snapshot()

                # Act
                with self.assertRaises(AccessError, msg="Saving sharing without a selected document must be denied."):
                    try:
                        self.sharing.with_user(self.editor).advanced_share_save(values)
                    finally:
                        # Assert
                        self.assertEqual(
                            self._onlyoffice_settings_snapshot(),
                            before,
                            "Missing document_id validation must reject sharing without changing ONLYOFFICE settings.",
                        )

    @mute_logger("odoo.addons.base.models.ir_rule")
    def test_editor_cannot_move_document_into_read_only_destination(self):
        # Arrange
        read_only_destination = (
            self.env["documents.document"]
            .with_user(self.creator)
            .create(
                {
                    "name": "ONLYOFFICE read-only destination",
                    "type": "folder",
                    "access_internal": "view",
                    "access_via_link": "none",
                }
            )
        )
        self.document.with_user(self.editor).check_access("write")
        self.source_folder.with_user(self.editor).check_access("write")
        read_only_destination.with_user(self.editor).check_access("read")
        self.assertFalse(
            read_only_destination.with_user(self.editor).has_access("write"),
            "The move destination must be readable but not writable by the otherwise authorized editor.",
        )
        before = self._onlyoffice_settings_snapshot()

        # Act
        with self.assertRaises(
            AccessError,
            msg="A document editor moving into a read-only destination must be denied.",
        ):
            try:
                self.document.with_user(self.editor).write({"folder_id": read_only_destination.id})
            finally:
                # Assert
                self.assertRecordValues(self.document, [{"folder_id": self.source_folder.id}])
                self.assertEqual(
                    self._onlyoffice_settings_snapshot(),
                    before,
                    "A move denied by destination permissions must leave ONLYOFFICE settings unchanged.",
                )

    def test_user_can_downgrade_own_access_through_native_sharing(self):
        # Arrange
        self.document.with_user(self.creator).write({"owner_id": self.editor.id})
        document_as_creator = self.document.with_user(self.creator)
        document_as_creator.check_access("write")

        # Act
        result = document_as_creator.action_update_access_rights(partners={self.creator.partner_id.id: ("view", False)})

        # Assert
        self.assertEqual(
            result,
            ["view"],
            "A native sharing operation authorized before self-demotion must complete with read-only access.",
        )
        self.assertFalse(
            document_as_creator.has_access("write"),
            "Self-demotion must remove native write access without preventing ONLYOFFICE synchronization.",
        )
        access = self.user_access_model.search(
            [("document_id", "=", self.document.id), ("user_id", "=", self.creator.partner_id.id)]
        )
        self.assertRecordValues(access, [{"role": "view"}])

    def test_user_can_remove_own_access_through_native_sharing(self):
        # Arrange
        self.document.with_user(self.creator).write({"owner_id": self.editor.id})
        document_as_creator = self.document.with_user(self.creator)
        document_as_creator.check_access("write")

        # Act
        result = document_as_creator.action_update_access_rights(partners={self.creator.partner_id.id: (False, False)})

        # Assert
        self.assertEqual(
            result,
            ["none"],
            "A native sharing operation authorized before self-removal must complete without document access.",
        )
        self.assertFalse(
            document_as_creator.has_access("read"),
            "Self-removal must revoke native document access without preventing ONLYOFFICE synchronization.",
        )
        self.assertFalse(
            self.user_access_model.search(
                [("document_id", "=", self.document.id), ("user_id", "=", self.creator.partner_id.id)]
            ),
            "Successful native self-removal must also remove the caller's ONLYOFFICE membership.",
        )
