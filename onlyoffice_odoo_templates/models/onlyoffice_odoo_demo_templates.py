import base64
import json
import logging
import os

from odoo import api, fields, models
from odoo.modules import get_module_path

_logger = logging.getLogger(__name__)


class OnlyOfficeDemoTemplate(models.Model):
    _name = "onlyoffice.odoo.demo.templates"
    _description = "ONLYOFFICE Demo Templates"

    selected_templates = fields.Text(string="Selected Templates")

    def _get_template_structure(self):
        templates_dir = self._get_templates_dir()
        structure = {}

        for root, _dirs, files in os.walk(templates_dir):
            if files:
                model = os.path.basename(root)

                model_exists = bool(self.env["ir.model"].search([("model", "=", model)], limit=1))
                if not model_exists:
                    continue

                name = self._get_model_name(model)

                rel_path = os.path.relpath(root, templates_dir)

                structure[model] = {
                    "model": model,
                    "name": name,
                    "files": [
                        {
                            "name": f,
                            "path": os.path.join(rel_path, f) if rel_path != "." else f,
                        }
                        for f in files
                    ],
                }

        return structure

    def _get_model_name(self, model_name):
        model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
        return model.name if model else model_name

    def _get_templates_dir(self):
        module_path = get_module_path(self._module)
        return os.path.join(module_path, "data", "templates")

    @api.model
    def get_template_data(self):
        structure = self._get_template_structure()
        selected = json.loads(self.selected_templates or "[]")

        return {"structure": structure, "selected": selected}

    def action_save(self):
        selected_templates = json.loads(self.selected_templates or "[]")
        if len(selected_templates) == 0:
            return
        templates_dir = self._get_templates_dir()
        template_model = self.env["onlyoffice.odoo.templates"]

        for template_path in selected_templates:
            model_name, filename = template_path.split("/")
            full_path = os.path.join(templates_dir, template_path)

            try:
                with open(full_path, "rb") as f:
                    template_data = base64.b64encode(f.read())

                model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
                if not model:
                    continue

                template_model.create(
                    {
                        "name": os.path.splitext(filename)[0],
                        "template_model_id": model.id,
                        "file": template_data,
                        "mimetype": "application/pdf",
                    }
                )

            except Exception as e:
                _logger.error("Failed to process template %s: %s", template_path, str(e))
                continue

        return {
            "type": "ir.actions.client",
            "tag": "soft_reload",
        }

    def get_template_content(self, template_path):
        templates_dir = self._get_templates_dir()
        file_path = os.path.join(templates_dir, template_path)

        with open(file_path, "rb") as f:
            return f.read()
