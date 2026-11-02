# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
import zipfile
from contextlib import contextmanager
from io import BytesIO
from unittest.mock import patch

from odoo.tests.common import new_test_user
from odoo.tools import file_open

from odoo.addons.onlyoffice_odoo.tests.common import INTERNAL_SECRET, OnlyofficeCase  # noqa: F401

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def blank(ext):
    """Blank office file shipped with onlyoffice_odoo (docx, xlsx, pptx, pdf)."""
    with file_open(f"onlyoffice_odoo/static/assets/document_templates/en-US/new.{ext}", "rb") as f:
        return f.read()


def make_xlsx(sheets, shared_strings=True):
    """Minimal XLSX: {sheet name: [text of A1, A2, ...]}; only the parts read by this module are written."""
    workbook_sheets, rels, strings = [], [], []
    files = {}
    for index, (name, column) in enumerate(sheets.items(), start=1):
        workbook_sheets.append(f'<sheet name="{name}" sheetId="{index}" r:id="rId{index}"/>')
        rels.append(f'<Relationship Id="rId{index}" Target="worksheets/sheet{index}.xml"/>')
        cells = []
        for row, text in enumerate(column, start=1):
            if shared_strings:
                strings.append(text)
                cells.append(f'<c r="A{row}" t="s"><v>{len(strings) - 1}</v></c>')
            else:
                cells.append(f'<c r="A{row}" t="inlineStr"><is><t>{text}</t></is></c>')
        sheet_data = f"<sheetData>{''.join(cells)}</sheetData>"
        files[f"xl/worksheets/sheet{index}.xml"] = f'<worksheet xmlns="{_MAIN_NS}">{sheet_data}</worksheet>'
    files["[Content_Types].xml"] = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
    files["xl/workbook.xml"] = (
        f'<workbook xmlns="{_MAIN_NS}" xmlns:r="{_REL_NS}"><sheets>{"".join(workbook_sheets)}</sheets></workbook>'
    )
    files["xl/_rels/workbook.xml.rels"] = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(rels)}</Relationships>"
    )
    if strings:
        items = "".join(f"<si><t>{text}</t></si>" for text in strings)
        files["xl/sharedStrings.xml"] = f'<sst xmlns="{_MAIN_NS}">{items}</sst>'

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buffer.getvalue()


def xlsx_with_metadata(metadata, chunk=40):
    """XLSX with the hidden `_OdooMetadata` sheet: the metadata JSON split over column A, like the docbuilder does."""
    text = json.dumps(metadata)
    return make_xlsx({"Sheet1": ["data"], "_OdooMetadata": [text[i : i + chunk] for i in range(0, len(text), chunk)]})


class FakeRequest:
    """Stands in for ``odoo.http.request`` where the spreadsheet code only needs ``request.env``."""

    def __init__(self, env):
        self.env = env

    def update_env(self, user=None, context=None):
        self.env = self.env(user=user, context=context)


@contextmanager
def fake_request(env):
    """Runs the spreadsheet formula / docbuilder helpers outside an HTTP request."""
    fake = FakeRequest(env)
    with (
        patch("odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_formulas.request", fake),
        patch("odoo.addons.onlyoffice_odoo_documents.controllers.spreadsheet_docbuilder.request", fake),
    ):
        yield fake


class DocumentsCase(OnlyofficeCase):
    """Shared fixture: a folder editable by internal users, its owner and a colleague, both Documents users
    (OnlyofficeCase: no Document Server JWT, a preset internal secret)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        groups = "base.group_user,documents.group_documents_user"
        cls.owner = new_test_user(cls.env, login="oo_doc_owner", groups=groups, name="OO Owner")
        cls.colleague = new_test_user(cls.env, login="oo_doc_colleague", groups=groups, name="OO Colleague")
        cls.folder = cls.env["documents.document"].create(
            {
                "name": "OO Folder",
                "type": "folder",
                "access_internal": "edit",
                "owner_id": cls.env.ref("base.user_root").id,
            }
        )

    def _document(self, name="Report.docx", user=None, content=None, **vals):
        """A binary document created by ``user`` (the owner by default) in the shared folder."""
        values = {"name": name, "raw": content or blank(name.rsplit(".", 1)[-1]), "folder_id": self.folder.id}
        return self.env["documents.document"].with_user(user or self.owner).create({**values, **vals})

    def _roles(self, document, internal_users=None, link_access=None, **user_roles):
        """ONLYOFFICE roles of ``document``: the defaults row and per-user rows keyed by the test user attribute."""
        if internal_users or link_access:
            self.env["onlyoffice.odoo.documents.access"].create(
                {
                    "document_id": document.id,
                    "internal_users": internal_users or "none",
                    "link_access": link_access or "none",
                }
            )
        for user, role in user_roles.items():
            self.env["onlyoffice.odoo.documents.access.user"].create(
                {"document_id": document.id, "user_id": getattr(self, user).partner_id.id, "role": role}
            )
