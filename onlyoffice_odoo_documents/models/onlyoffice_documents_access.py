from odoo import fields, models


class OnlyofficeDocumentsAccessUser(models.Model):
    _name = "onlyoffice.documents.access"
    _description = "Document Access Rights"

    document_id = fields.Many2one("documents.document", string="Document", ondelete="cascade")
    folder_id = fields.Many2one("documents.folder", string="Folder", ondelete="cascade")
    internal_access = fields.Selection(
        [
            ("none", "None"),
            ("viewer", "Viewer"),
            ("comment", "Comment"),
            ("reviewer", "Reviewer"),
            ("editor", "Editor"),
            ("form filling", "Form Filling"),
        ],
        default="viewer",
    )
    link_access = fields.Selection(
        [
            ("none", "None"),
            ("viewer", "Viewer"),
            ("comment", "Comment"),
            ("reviewer", "Reviewer"),
            ("editor", "Editor"),
            ("form filling", "Form Filling"),
        ],
        default="viewer",
    )

    _sql_constraints = [
        (
            "document_or_folder",
            "CHECK(document_id IS NOT NULL OR folder_id IS NOT NULL)",
            "Access rights must be assigned to either a document or a folder.",
        ),
    ]
