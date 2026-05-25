# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

from odoo import api, fields, models

from .dms_file import _LINK_ROLE_SELECTION
from .onlyoffice_dms_access import _ROLES_ALL, _ROLES_READONLY


class DmsDirectory(models.Model):
    _inherit = "dms.directory"

    oo_link_access = fields.Selection(
        selection=_LINK_ROLE_SELECTION,
        string="Public Link",
        default="none",
        help=(
            "Default ONLYOFFICE role for portal/public token access to files "
            "in this directory. 'None' inherits from the parent directory."
        ),
    )

    @api.model
    def oo_role_dynamic_values(self):
        """Proxy so the widget can call this method from the dms.directory form view."""
        if self.env.context.get("depending_on"):
            return _ROLES_ALL
        return _ROLES_READONLY

    def _get_oo_effective_link_access(self):
        """
        Walk up the directory tree and return the nearest non-'none'
        oo_link_access value.
        """
        self.ensure_one()
        record = self.sudo()
        while record:
            if record.oo_link_access and record.oo_link_access != "none":
                return record.oo_link_access
            record = record.parent_id
        return "none"
