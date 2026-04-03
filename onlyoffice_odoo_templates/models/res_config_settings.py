# Copyright (C) 2026 Ascensio System SIA

from odoo import fields, models

from odoo.addons.onlyoffice_odoo_templates.utils import config_utils


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"
    editable_form_fields = fields.Boolean("Disable form fields after printing PDF form")

    def set_values(self):
        res = super().set_values()
        previous_disable_form_fields = config_utils.get_editable_form_fields(self.env)
        if previous_disable_form_fields != self.editable_form_fields:
            config_utils.set_editable_form_fields(self.env, self.editable_form_fields)
        return res

    def get_values(self):
        res = super().get_values()
        editable_form_fields = config_utils.get_editable_form_fields(self.env)
        res.update(editable_form_fields=editable_form_fields)
        return res
