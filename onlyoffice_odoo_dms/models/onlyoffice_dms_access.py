# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

from odoo import api, fields, models
from odoo.exceptions import AccessError

_ROLES_ALL = [
    ("none", "None"),
    ("view", "Viewer"),
    ("commenter", "Commenter"),
    ("reviewer", "Reviewer"),
    ("form_filling", "Form Filling"),
    ("custom_filter", "Custom Filter"),
    ("edit", "Editor"),
]

_ROLES_READONLY = [
    ("none", "None"),
    ("view", "Viewer"),
    ("commenter", "Commenter"),
    ("reviewer", "Reviewer"),
]


class DmsAccessGroup(models.Model):
    _inherit = "dms.access.group"

    oo_role = fields.Selection(
        _ROLES_ALL,
        default="none",
        required=True,
        string="ONLYOFFICE Role",
        help=(
            "Default ONLYOFFICE role granted to users in this access group. "
            "'None' means fall back to the next resolution level."
        ),
    )

    @api.model
    def oo_role_dynamic_values(self):
        """Return available ONLYOFFICE roles based on the group's write permission."""
        if self.env.context.get("depending_on"):
            return _ROLES_ALL
        return _ROLES_READONLY

    @api.onchange("perm_write")
    def _onchange_perm_write_oo_role(self):
        """Reset oo_role to a read-compatible value when write access is removed."""
        write_only_roles = {"edit", "form_filling", "custom_filter"}
        for record in self:
            if not record.perm_write and record.oo_role in write_only_roles:
                record.oo_role = "none"


class OnlyofficeDmsFileAccessUser(models.Model):
    """
    Per-user ONLYOFFICE role override for a specific DMS file.

    Takes precedence over dms.file.oo_internal_users.
    Useful for giving a collaborator a role that differs from the file default,
    e.g. restricting a DMS write-capable user to 'commenter' in ONLYOFFICE.
    """

    _name = "onlyoffice.dms.file.access.user"
    _description = "ONLYOFFICE DMS Per-User File Access"

    file_id = fields.Many2one(
        "dms.file",
        required=True,
        ondelete="cascade",
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        ondelete="cascade",
        string="User",
    )
    role = fields.Selection(
        _ROLES_ALL,
        required=True,
        default="view",
        string="ONLYOFFICE Role",
    )

    dms_perm_read = fields.Boolean(
        string="Read",
        compute="_compute_dms_perms",
        help="User has DMS read access to this file.",
    )
    dms_perm_write = fields.Boolean(
        string="Write",
        compute="_compute_dms_perms",
        help="User has DMS write access to this file.",
    )
    dms_perm_unlink = fields.Boolean(
        string="Delete",
        compute="_compute_dms_perms",
        help="User has DMS delete access to this file.",
    )
    oo_dir_role = fields.Selection(
        _ROLES_ALL,
        string="Directory Role",
        compute="_compute_oo_dir_role",
        help="Effective ONLYOFFICE role from directory/group configuration (without per-user override).",
    )
    dms_access_level = fields.Selection(
        [("write", "Write"), ("read", "Read"), ("none", "None")],
        string="DMS Access Level",
        compute="_compute_dms_perms",
        help="Effective DMS access level, used to limit available ONLYOFFICE roles.",
    )

    _sql_constraints = [
        (
            "unique_user_file",
            "UNIQUE(file_id, user_id)",
            "A user can only have one ONLYOFFICE role per DMS file.",
        )
    ]

    @api.depends("file_id", "user_id")
    def _compute_oo_dir_role(self):
        for record in self:
            if not record.file_id or not record.user_id:
                record.oo_dir_role = "none"
            else:
                record.oo_dir_role = record.file_id._get_oo_role_without_override(record.user_id)

    @api.depends("file_id", "user_id")
    def _compute_dms_perms(self):
        for record in self:
            if not record.file_id or not record.user_id:
                record.dms_perm_read = False
                record.dms_perm_write = False
                record.dms_perm_unlink = False
                record.dms_access_level = "none"
                continue
            file_as_user = record.file_id.with_user(record.user_id)
            try:
                file_as_user.check_access("read")
                record.dms_perm_read = True
            except (AccessError, Exception):
                record.dms_perm_read = False
            try:
                file_as_user.check_access("write")
                record.dms_perm_write = True
            except (AccessError, Exception):
                record.dms_perm_write = False
            try:
                file_as_user.check_access("unlink")
                record.dms_perm_unlink = True
            except (AccessError, Exception):
                record.dms_perm_unlink = False
            if record.dms_perm_write:
                record.dms_access_level = "write"
            elif record.dms_perm_read:
                record.dms_access_level = "read"
            else:
                record.dms_access_level = "none"

    @api.model
    def oo_role_dynamic_values(self):
        """Return available ONLYOFFICE roles based on the user's DMS access level."""
        level = self.env.context.get("depending_on")
        if level == "write":
            return _ROLES_ALL
        if level == "read":
            return _ROLES_READONLY
        return [("none", "None")]

