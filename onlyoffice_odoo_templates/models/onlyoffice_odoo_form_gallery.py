import logging

import requests

from odoo import models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class OnlyOfficeFormGallery(models.Model):
    _name = "onlyoffice.odoo.form.gallery"
    _description = "ONLYOFFICE Form Gallery"

    def get_template_content(self, form_path):
        try:
            response = requests.get(form_path, stream=True, timeout=10)
            response.raise_for_status()

            return response.content

        except requests.RequestException as e:
            _logger.error("Failed to download file from URL %s: %s", form_path, str(e))
            raise UserError(f"Could not download file from URL: {form_path}. Error: {str(e)}") from e
