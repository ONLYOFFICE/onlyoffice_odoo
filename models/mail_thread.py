# -*- coding: utf-8 -*-

from odoo import models, _

from odoo.addons.onlyoffice_odoo_connector.utils import format_utils
from odoo.addons.onlyoffice_odoo_connector.utils import file_utils

class MailThread(models.AbstractModel):
    _inherit = "mail.thread"

    def _get_mail_thread_data(self, request_list):
        res = super()._get_mail_thread_data(request_list)

        format_dict = { format.name : format.to_dict() for format in format_utils.get_supported_formats() }

        if "attachments" in request_list and res["attachments"]:
            for attachment in res["attachments"]:
                ext = file_utils.get_file_ext(attachment["filename"])
                if ext in format_dict:
                    attachment["onlyofficeFormat"] = format_dict[ext]

        return res

