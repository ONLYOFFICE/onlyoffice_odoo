# Copyright (C) 2026 Ascensio System SIA

import base64
import json
import logging
import os
from pathlib import Path

from odoo import api, fields, models
from odoo.modules import get_module_path
from odoo.tools import file_open

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
        template_model = self.env["onlyoffice.odoo.templates"]

        for template_path in selected_templates:
            try:
                model_name, filename = template_path.split("/")
            except ValueError:
                _logger.error("Invalid template path %s", template_path)
                continue

            try:
                content = self.get_template_content(template_path)

                model = self.env["ir.model"].search([("model", "=", model_name)], limit=1)
                if not model:
                    continue

                template_model.with_context(skip_field_keys_refresh=True).create(
                    {
                        "name": os.path.splitext(filename)[0],
                        "template_model_id": model.id,
                        "file": base64.b64encode(content),
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
        templates_dir = Path(self._get_templates_dir()).resolve()

        # resolve() + relative_to() rejects "..", absolute paths and symlinks
        # that escape templates_dir in one go, no manual string checks needed.
        try:
            relative_path = (templates_dir / template_path).resolve().relative_to(templates_dir)
        except ValueError as e:
            raise ValueError("Invalid template path") from e

        # Use Odoo's file_open() for the actual read: extra safety check + extension filter.
        relative_name = f"{self._module}/data/templates/{relative_path.as_posix()}"
        with file_open(relative_name, "rb", filter_ext=(".pdf",)) as f:
            return f.read()
