# Copyright (C) 2026 Data Dance s.r.o.
# License LGPL-3.0 or later (https://www.gnuorg/licenses/agpl.html).

from odoo import fields, models


class OnlyOfficeTemplate(models.Model):
    _inherit = "onlyoffice.odoo.templates"

    report_id = fields.Many2one("ir.actions.report", string="Related Report", copy=False)

    def create_action(self):
        for template in self:
            if not template.report_id:
                report = self.env["ir.actions.report"].create(
                    {
                        "name": f"{template.name} Print (ONLYOFFICE)",
                        "report_type": "onlyoffice-pdf",
                        "report_name": template.name,
                        "onlyoffice_template_id": template.id,
                        "model": template.template_model_id.model,
                        "binding_model_id": template.template_model_id.id,
                    }
                )
                template.report_id = report.id

    def unlink_action(self):
        for template in self:
            if template.report_id:
                template.report_id.unlink()

    def associated_report(self):
        self.ensure_one()
        if self.report_id:
            return {
                "name": "Associated Report",
                "type": "ir.actions.act_window",
                "res_model": "ir.actions.report",
                "res_id": self.report_id.id,
                "view_mode": "form",
            }
        else:
            return {
                "type": "ir.actions.act_window_close",
            }
