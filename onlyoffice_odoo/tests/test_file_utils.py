# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import file_utils, format_utils

OFFICE_MIMES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}


@tagged("post_install", "-at_install")
class TestFileUtils(TransactionCase):
    """Tests for file_utils — file type detection, view/edit permissions, blank templates."""

    def test_get_file_ext_is_the_lowercase_last_suffix(self):
        self.assertEqual(file_utils.get_file_ext("report.docx"), "docx")
        self.assertEqual(file_utils.get_file_ext("my.report.v2.XLSX"), "xlsx")

    def test_get_file_name_without_ext_keeps_inner_dots(self):
        self.assertEqual(file_utils.get_file_name_without_ext("my.report.v2.xlsx"), "my.report.v2")

    def test_get_file_type_by_extension(self):
        for name, file_type in {"a.docx": "word", "a.xlsx": "cell", "a.pptx": "slide", "a.xyz123": None}.items():
            with self.subTest(name=name):
                self.assertEqual(file_utils.get_file_type(name), file_type)

    def test_office_formats_can_be_viewed_and_edited(self):
        for ext in OFFICE_MIMES:
            with self.subTest(ext=ext):
                self.assertTrue(file_utils.can_view(f"file.{ext}"))
                self.assertTrue(file_utils.can_edit(f"file.{ext}"))

    def test_unsupported_or_empty_names_cannot_be_viewed_or_edited(self):
        for name in ("file.zip", "file.exe", ""):
            with self.subTest(name=name):
                self.assertFalse(file_utils.can_view(name))
                self.assertFalse(file_utils.can_edit(name))

    def test_only_pdf_supports_form_filling(self):
        self.assertTrue(file_utils.can_fill_form("file.pdf"))
        self.assertFalse(file_utils.can_fill_form("file.docx"))

    def test_get_mime_by_ext(self):
        for ext, mime in {**OFFICE_MIMES, "zip": None}.items():
            with self.subTest(ext=ext):
                self.assertEqual(file_utils.get_mime_by_ext(ext), mime)

    def test_default_file_templates_exist_with_locale_fallback(self):
        for lang, ext in (("en_US", "docx"), ("en_US", "xlsx"), ("en_US", "pptx"), ("xx_XX", "docx")):
            with self.subTest(lang=lang, ext=ext):
                self.assertTrue(file_utils.get_default_file_template(lang, ext))

    def test_supported_formats_are_loaded(self):
        self.assertTrue(format_utils.get_supported_formats())

    def test_format_optional_lists_default_to_empty(self):
        fmt = format_utils.Format("test", "word")
        self.assertEqual((fmt.actions, fmt.convert, fmt.mime), ([], [], []))
