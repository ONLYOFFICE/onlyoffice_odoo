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

    @api.model
    def get_onlyoffice_spreadsheets_to_display(self, domain=None, offset=0, limit=0):
        """Return XLSX documents from the Spreadsheets workspace folder."""
        spreadsheet_folder = self.env.company.documents_spreadsheet_folder_id
        base_domain = [
            ("folder_id", "=", spreadsheet_folder.id if spreadsheet_folder else False),
            ("type", "=", "binary"),
            ("mimetype", "=", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]
        if domain:
            base_domain += domain

        records = self.search(
            base_domain,
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
        """Return count of XLSX documents in the Spreadsheets workspace folder."""
        spreadsheet_folder = self.env.company.documents_spreadsheet_folder_id
        base_domain = [
            ("folder_id", "=", spreadsheet_folder.id if spreadsheet_folder else False),
            ("type", "=", "binary"),
            ("mimetype", "=", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ]
        if domain:
            base_domain += domain
        return self.search_count(base_domain)

    @api.depends("checksum")
    def _compute_thumbnail(self):
        super()._compute_thumbnail()

        for record in self:
            if record.mimetype == "application/pdf":
                record.thumbnail = False
                record.thumbnail_status = False
        return
