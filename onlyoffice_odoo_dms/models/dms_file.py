# Copyright (C) 2026 Data Dance s.r.o., Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

import logging

from odoo import api, fields, models
from odoo.exceptions import AccessError

from odoo.addons.onlyoffice_odoo.utils import file_utils

_logger = logging.getLogger(__name__)

_ROLE_SELECTION = [
    ("none", "None"),
    ("view", "Viewer"),
    ("commenter", "Commenter"),
    ("reviewer", "Reviewer"),
    ("edit", "Editor"),
    ("form_filling", "Form Filling"),
    ("custom_filter", "Custom Filter"),
]

_LINK_ROLE_SELECTION = [
    ("none", "None"),
    ("view", "Viewer"),
    ("commenter", "Commenter"),
    ("reviewer", "Reviewer"),
    ("edit", "Editor"),
    ("form_filling", "Form Filling"),
    ("custom_filter", "Custom Filter"),
]


class DmsFile(models.Model):
    _inherit = "dms.file"

    # ----------------------------------------------------------
    # ONLYOFFICE fields
    # ----------------------------------------------------------

    oo_version = fields.Integer(
        string="ONLYOFFICE Version",
        default=0,
        copy=False,
        help=("Incremented each time a file is saved back from ONLYOFFICE. " "Used as part of the document cache key."),
    )
    oo_user_access_ids = fields.One2many(
        "onlyoffice.dms.file.access.user",
        "file_id",
        string="ONLYOFFICE User Roles",
    )
    oo_is_viewable = fields.Boolean(
        compute="_compute_oo_capabilities",
        string="Viewable in ONLYOFFICE",
    )
    oo_is_editable = fields.Boolean(
        compute="_compute_oo_capabilities",
        string="Editable in ONLYOFFICE",
    )
    oo_effective_role = fields.Selection(
        selection=_ROLE_SELECTION,
        string="ONLYOFFICE Role",
        compute="_compute_oo_effective_role",
        help="Effective ONLYOFFICE role for the current user on this file.",
    )

    # ----------------------------------------------------------
    # Computed fields
    # ----------------------------------------------------------

    @api.depends(
        "oo_user_access_ids.user_id",
        "oo_user_access_ids.role",
        "directory_id.complete_group_ids.oo_role",
        "directory_id.complete_group_ids.users",
    )
    @api.depends_context("uid")
    def _compute_oo_effective_role(self):
        for record in self:
            record.oo_effective_role = record.get_oo_role_for_user(self.env.user)

    @api.depends("name")
    def _compute_oo_capabilities(self):
        for record in self:
            name = record.name or ""
            record.oo_is_viewable = bool(name) and file_utils.can_view(name)
            record.oo_is_editable = bool(name) and file_utils.can_edit(name)

    # ----------------------------------------------------------
    # Dynamic dropdown proxy (called by widget from dms.file view context)
    # ----------------------------------------------------------

    @api.model
    def oo_role_dynamic_values(self):
        """Proxy so the widget can call this from the dms.file form view."""
        from .onlyoffice_dms_access import _ROLES_ALL, _ROLES_READONLY, _filter_roles_by_file

        level = self.env.context.get("depending_on")
        if level == "write":
            roles = _ROLES_ALL
        elif level == "read":
            roles = _ROLES_READONLY
        else:
            return [("none", "None")]
        return _filter_roles_by_file(roles, self.env.context.get("file_name"))

    # ----------------------------------------------------------
    # Actions
    # ----------------------------------------------------------

    def action_open_oo_editor(self):
        """Open the file in ONLYOFFICE inside the Odoo shell (embedded iframe)."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "onlyoffice_dms.editor",
            "name": "Edit in ONLYOFFICE",
            "context": {"file_id": self.id, "mode": "edit"},
        }

    def action_open_oo_preview(self):
        """Open the file in ONLYOFFICE (view-only) inside the Odoo shell."""
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "onlyoffice_dms.editor",
            "name": "Preview in ONLYOFFICE",
            "context": {"file_id": self.id, "mode": "view"},
        }

    # ----------------------------------------------------------
    # Role resolution
    # ----------------------------------------------------------

    def get_oo_role_for_user(self, user):
        """
        Return the effective ONLYOFFICE role string for *user* on this file.

        Resolution order:
          1. Per-user override      (onlyoffice.dms.file.access.user)
          2. Access group oo_role   (user is a member of a group with a role set,
                                     inherits via dms.access.group cascade)
          3. DMS permission fallback: write → 'edit', read-only → 'view'
        """
        self.ensure_one()

        # 1. Per-user override
        user_override = (
            self.env["onlyoffice.dms.file.access.user"]
            .sudo()
            .search(
                [("file_id", "=", self.id), ("user_id", "=", user.id)],
                limit=1,
            )
        )
        if user_override:
            return user_override.role

        # 2+3. Access group + DMS fallback (no per-user override)
        return self._get_oo_role_without_override(user)

    def _get_oo_role_without_override(self, user):
        """Role resolution excluding step 1 (per-user override)."""
        self.ensure_one()
        group_role = self._get_oo_role_from_access_groups(user)
        if group_role is not None and group_role != "none":
            return group_role
        if group_role == "none":
            return "none"
        dms_file_as_user = self.with_user(user)
        try:
            dms_file_as_user.check_access("write")
            return "edit"
        except (AccessError, Exception) as err:
            _logger.debug("No DMS write access for user %s on file %s: %s", user.id, self.id, err)
        try:
            dms_file_as_user.check_access("read")
            return "view"
        except (AccessError, Exception):
            return "none"

    def _get_oo_role_from_access_groups(self, user):
        """
        Return the most permissive ONLYOFFICE role set on any access group
        that applies to this file's directory and contains *user*.
        """
        self.ensure_one()
        applicable_groups = self.directory_id.sudo().complete_group_ids
        user_groups = applicable_groups.filtered(lambda g: user in g.users)
        if not user_groups:
            return None

        priority = {
            "none": 0,
            "view": 1,
            "custom_filter": 2,
            "form_filling": 3,
            "commenter": 4,
            "reviewer": 5,
            "edit": 6,
        }
        best = max(user_groups.mapped("oo_role"), key=lambda r: priority.get(r or "none", 0))
        return best or "none"

    def get_oo_effective_link_access(self):
        """
        Return the effective public-link ONLYOFFICE role for this file.

        Delegates to the nearest ancestor directory that has oo_link_access set.
        """
        self.ensure_one()
        if self.directory_id:
            return self.directory_id._get_oo_effective_link_access()
        return "none"
