# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import logging

from odoo import api, models

logger = logging.getLogger(__name__)

# Any of these changing means the underlying file content changed.
_CONTENT_FIELDS = {"datas", "raw", "db_datas", "store_fname"}


class IrAttachment(models.Model):
    _inherit = "ir.attachment"

    @api.model_create_multi
    def create(self, vals_list):
        attachments = super().create(vals_list)
        self._refresh_template_field_keys(attachments.filtered(lambda a: a.res_model == "onlyoffice.odoo.templates"))
        return attachments

    def write(self, vals):
        to_refresh = self.env["ir.attachment"]
        if _CONTENT_FIELDS.intersection(vals.keys()):
            to_refresh = self.filtered(lambda a: a.res_model == "onlyoffice.odoo.templates")
        res = super().write(vals)
        if to_refresh:
            self._refresh_template_field_keys(to_refresh)
        return res

    def _refresh_template_field_keys(self, attachments):
        """Eagerly (re)compute and cache the OFORM field keys for any ONLYOFFICE
        template whose PDF attachment was just created or had its content
        changed (upload, re-upload, or an ONLYOFFICE editor save).

        This is the single choke point for template PDF content changes, so
        filling a template later only ever needs to read the already-cached
        keys off ``onlyoffice.odoo.templates.field_keys`` instead of paying
        for a synchronous docbuilder round-trip per fill.
        """
        if not attachments:
            return
        templates = self.env["onlyoffice.odoo.templates"]
        for attachment in attachments:
            template = templates.browse(attachment.res_id).exists()
            if template:
                template._update_field_keys(attachment)
