# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import file_utils, format_utils


@tagged("post_install", "-at_install")
class TestFileUtils(TransactionCase):
    """Tests for file_utils module тАФ file type detection, view/edit permissions."""

    # -- Extension extraction --

    def test_get_file_ext_simple(self):
        """Extract extension from a simple filename."""
        self.assertEqual(file_utils.get_file_ext("report.docx"), "docx")

    def test_get_file_ext_multiple_dots(self):
        """Extract extension when filename contains multiple dots."""
        self.assertEqual(file_utils.get_file_ext("my.report.v2.xlsx"), "xlsx")

    def test_get_file_ext_uppercase(self):
        """Extension is returned in lowercase regardless of original case."""
        self.assertEqual(file_utils.get_file_ext("REPORT.DOCX"), "docx")

    # -- File type detection --

    def test_get_file_type_word(self):
        """DOCX files are detected as 'word' document type."""
        self.assertEqual(file_utils.get_file_type("letter.docx"), "word")

    def test_get_file_type_cell(self):
        """XLSX files are detected as 'cell' (spreadsheet) type."""
        self.assertEqual(file_utils.get_file_type("budget.xlsx"), "cell")

    def test_get_file_type_slide(self):
        """PPTX files are detected as 'slide' (presentation) type."""
        self.assertEqual(file_utils.get_file_type("slides.pptx"), "slide")

    def test_get_file_type_unknown(self):
        """Truly unknown extensions (not in format list) return None."""
        self.assertIsNone(file_utils.get_file_type("archive.xyz123"))

    # -- View permission --

    def test_can_view_docx(self):
        """DOCX files can be viewed."""
        self.assertTrue(file_utils.can_view("file.docx"))

    def test_can_view_xlsx(self):
        """XLSX files can be viewed."""
        self.assertTrue(file_utils.can_view("file.xlsx"))

    def test_can_view_pptx(self):
        """PPTX files can be viewed."""
        self.assertTrue(file_utils.can_view("file.pptx"))

    def test_can_view_pdf(self):
        """PDF files can be viewed."""
        self.assertTrue(file_utils.can_view("file.pdf"))

    def test_can_view_unsupported(self):
        """Unsupported extensions cannot be viewed."""
        self.assertFalse(file_utils.can_view("file.zip"))
        self.assertFalse(file_utils.can_view("file.exe"))

    def test_can_view_empty_string(self):
        """Empty filename cannot be viewed."""
        self.assertFalse(file_utils.can_view(""))

    # -- Edit permission --

    def test_can_edit_docx(self):
        """DOCX files can be edited."""
        self.assertTrue(file_utils.can_edit("file.docx"))

    def test_can_edit_xlsx(self):
        """XLSX files can be edited."""
        self.assertTrue(file_utils.can_edit("file.xlsx"))

    def test_can_edit_pptx(self):
        """PPTX files can be edited."""
        self.assertTrue(file_utils.can_edit("file.pptx"))

    def test_can_edit_pdf(self):
        """PDF files can be edited (ONLYOFFICE Docs supports PDF editing)."""
        self.assertTrue(file_utils.can_edit("file.pdf"))

    def test_can_edit_unsupported(self):
        """Unsupported extensions cannot be edited."""
        self.assertFalse(file_utils.can_edit("file.zip"))

    def test_can_edit_empty_string(self):
        """Empty filename cannot be edited."""
        self.assertFalse(file_utils.can_edit(""))

    # -- Form filling --

    def test_can_fill_form_pdf(self):
        """PDF files support form filling."""
        self.assertTrue(file_utils.can_fill_form("file.pdf"))

    def test_can_fill_form_docx(self):
        """DOCX files do not support form filling."""
        self.assertFalse(file_utils.can_fill_form("file.docx"))

    # -- MIME type lookup --

    def test_get_mime_by_ext_docx(self):
        """DOCX returns correct MIME type."""
        self.assertEqual(
            file_utils.get_mime_by_ext("docx"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

    def test_get_mime_by_ext_xlsx(self):
        """XLSX returns correct MIME type."""
        self.assertEqual(
            file_utils.get_mime_by_ext("xlsx"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def test_get_mime_by_ext_pptx(self):
        """PPTX returns correct MIME type."""
        self.assertEqual(
            file_utils.get_mime_by_ext("pptx"),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )

    def test_get_mime_by_ext_pdf(self):
        """PDF returns correct MIME type."""
        self.assertEqual(file_utils.get_mime_by_ext("pdf"), "application/pdf")

    def test_get_mime_by_ext_unknown(self):
        """Unknown extension returns None."""
        self.assertIsNone(file_utils.get_mime_by_ext("zip"))

    # -- File name helpers --

    def test_get_file_name_without_ext(self):
        """Return filename without extension."""
        self.assertEqual(file_utils.get_file_name_without_ext("report.docx"), "report")

    def test_get_file_name_without_ext_multiple_dots(self):
        """Return filename preserving internal dots."""
        self.assertEqual(file_utils.get_file_name_without_ext("my.report.v2.xlsx"), "my.report.v2")

    # -- Format utils integration --

    def test_formats_loaded(self):
        """Supported formats list is not empty after module load."""
        self.assertTrue(len(format_utils.get_supported_formats()) > 0)

    # -- Default file templates --

    def test_get_default_file_template_docx(self):
        """Default DOCX template can be loaded for English locale."""
        content = file_utils.get_default_file_template("en_US", "docx")
        self.assertIsInstance(content, bytes)
        self.assertTrue(len(content) > 0)

    def test_get_default_file_template_xlsx(self):
        """Default XLSX template can be loaded for English locale."""
        content = file_utils.get_default_file_template("en_US", "xlsx")
        self.assertIsInstance(content, bytes)
        self.assertTrue(len(content) > 0)

    def test_get_default_file_template_pptx(self):
        """Default PPTX template can be loaded for English locale."""
        content = file_utils.get_default_file_template("en_US", "pptx")
        self.assertIsInstance(content, bytes)
        self.assertTrue(len(content) > 0)

    def test_get_default_file_template_fallback_locale(self):
        """Unknown locale falls back to default template."""
        content = file_utils.get_default_file_template("xx_XX", "docx")
        self.assertIsInstance(content, bytes)
        self.assertTrue(len(content) > 0)

    # -- format_utils.Format defaults --

    def test_format_defaults_to_empty_lists_when_optional_args_omitted(self):
        """Format can be constructed with only name and type; optional fields default to empty lists."""
        fmt = format_utils.Format("test", "word")
        self.assertEqual(fmt.actions, [])
        self.assertEqual(fmt.convert, [])
        self.assertEqual(fmt.mime, [])
