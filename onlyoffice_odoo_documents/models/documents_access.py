# Copyright (C) 2026 Ascensio System SIA

from odoo import models


class DocumentsAccess(models.Model):
    _inherit = "documents.access"

    def unlink(self):
        """A member removed in Odoo (by the autovacuum of expired invitations too) loses their ONLYOFFICE role."""
        documents = self.sudo().document_id
        result = super().unlink()
        self.env["onlyoffice.odoo.documents"]._forget_former_members(documents)
        return result
