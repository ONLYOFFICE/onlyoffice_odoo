# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import base64
import io

from reportlab.pdfgen import canvas

from odoo.tests.common import new_test_user
from odoo.tools import file_open

from odoo.addons.onlyoffice_odoo.tests.common import INTERNAL_SECRET, OnlyofficeCase, ds_response  # noqa: F401

ADMIN_GROUPS = "base.group_user,onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_admin"
USER_GROUPS = "base.group_user,onlyoffice_odoo_templates.group_onlyoffice_odoo_templates_user"
# A PDF without the ONLYOFFICE form signature: saving it as a template converts it through the Document Server.
PLAIN_PDF = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"


def bundled_pdf(path="hr.employee/Employee.pdf"):
    """A PDF form shipped with the module (data/templates/<model>/<name>.pdf)."""
    with file_open(f"onlyoffice_odoo_templates/data/templates/{path}", "rb") as f:
        return f.read()


def plain_pdf(text):
    """A one-page PDF made by reportlab: the kind of file Odoo's PDF merge reads."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


class TemplatesCase(OnlyofficeCase):
    """Shared fixture: a template administrator and a template user (OnlyofficeCase: no Document Server JWT, a preset
    internal secret)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin = new_test_user(cls.env, login="oo_tpl_admin", groups=ADMIN_GROUPS, name="OO Template Admin")
        cls.user = new_test_user(cls.env, login="oo_tpl_user", groups=USER_GROUPS, name="OO Template User")
        cls.partner_model = cls.env["ir.model"]._get("res.partner")

    def _template(self, name="Partner Card", model=None, content=None):
        """A template of a PDF form (the bundled Employee form by default); field keys are not fetched."""
        return (
            self.env["onlyoffice.odoo.templates"]
            .with_context(skip_field_keys_refresh=True)
            .create(
                {
                    "name": name,
                    "template_model_id": (model or self.partner_model).id,
                    "file": base64.b64encode(content or bundled_pdf()),
                }
            )
        )

    def _token(self, user):
        """oo_security_token of ``user``, as the Document Server gets it in the docbuilder callback URLs."""
        return self._internal_token({"id": user.id})
