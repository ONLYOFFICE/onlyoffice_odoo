from odoo import _, fields, models, api

class OnlyofficeOdooDocumentsTemplate(models.Model):
    _name = "onlyoffice.template"

    name = fields.Char('Name')

    @api.model
    def get_parameter(self):
        a = self.env["ir.attachment"].fields_get()
        return "test"
