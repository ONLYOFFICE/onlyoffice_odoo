# Copyright (C) 2026 Ascensio System SIA

from odoo import api, fields, models


class Document(models.Model):
    _inherit = "documents.document"

    onlyoffice_spreadsheet_source_id = fields.Many2one(
        "documents.document",
        string="Spreadsheet Source",
        help="Reference to the original Odoo spreadsheet if this is an XLSX copy",
        ondelete="set null",
    )

    onlyoffice_spreadsheet_metadata = fields.Text(
        string="Spreadsheet Metadata",
        help="JSON metadata from original spreadsheet (lists, pivots, filters) for XLSX copies",
    )

    def _get_onlyoffice_spreadsheets_domain(self, domain=None):
        """Build the base domain matching any XLSX document, regardless of folder."""
        base_domain = [
            ("type", "=", "binary"),
            ("mimetype", "=", XLSX_MIMETYPE),
        ]
        if domain:
            base_domain += domain
        return base_domain

    @api.model
    def get_onlyoffice_spreadsheets_to_display(self, domain=None, offset=0, limit=0):
        """Return XLSX documents available for the ONLYOFFICE insert-sheet tab."""
        records = self.search(
            self._get_onlyoffice_spreadsheets_domain(domain),
            offset=offset,
            limit=limit or None,
            order="write_date desc, id desc",
        )
        return [
            {
                "id": rec.id,
                "name": rec.name,
                "thumbnail": rec.thumbnail or False,
            }
            for rec in records
        ]

    @api.model
    def get_onlyoffice_spreadsheets_count(self, domain=None):
        """Return count of XLSX documents available for the ONLYOFFICE insert-sheet tab."""
        return self.search_count(self._get_onlyoffice_spreadsheets_domain(domain))

    @api.depends("checksum")
    def _compute_thumbnail(self):
        super()._compute_thumbnail()

        for record in self:
            if record.mimetype == "application/pdf":
                record.thumbnail = False
                record.thumbnail_status = False
