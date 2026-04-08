# Copyright (C) 2026 Ascensio System SIA

from odoo.addons.onlyoffice_odoo_templates.utils import config_constants


def set_editable_form_fields(env, value):
    env["ir.config_parameter"].sudo().set_param(config_constants.EDITABLE_FORM_FIELDS, value)
    return


def get_editable_form_fields(env):
    return env["ir.config_parameter"].sudo().get_param(config_constants.EDITABLE_FORM_FIELDS)
