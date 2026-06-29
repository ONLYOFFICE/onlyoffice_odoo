# Copyright (C) 2026 Ascensio System SIA

import io
import zipfile

# Inner files that identify an OOXML container produced by Word/Excel/PowerPoint.
_OOXML_MARKERS = (
    ("word/document.xml", "docx"),
    ("xl/workbook.xml", "xlsx"),
    ("ppt/presentation.xml", "pptx"),
)


def get_source_format(data):
    """Detect the real format of an uploaded template from its bytes.

    Returns one of ``"pdf"``, ``"docx"``, ``"xlsx"``, ``"pptx"`` or ``None`` when
    the format is not recognised. The upload widget gives us no filename, so the
    type has to be sniffed from the magic bytes.
    """
    if not data:
        return None

    # Regular PDF ("%PDF-") or the ONLYOFFICE form PDF marker.
    if data[:4] == b"%PDF" or data[:6] == b"%\xcd\xca\xd2\xa9\x0d":
        return "pdf"

    # OOXML files are ZIP containers starting with the local file header "PK\x03\x04".
    if data[:4] == b"PK\x03\x04":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())
        except Exception:
            return None
        for marker, ext in _OOXML_MARKERS:
            if marker in names:
                return ext

    return None


def is_pdf_form(text):
    if not text:
        return False

    index_first = text.find(b"%\xcd\xca\xd2\xa9\x0d")
    if index_first == -1:
        return False

    p_first = text[index_first + 6 :]

    if not p_first.startswith(b"1 0 obj\x0a<<\x0a"):
        return False

    p_first = p_first[11:]

    signature = b"ONLYOFFICEFORM"
    index_stream = p_first.find(b"stream\x0d\x0a")
    index_meta = p_first.find(signature)

    if index_stream == -1 or index_meta == -1 or index_stream < index_meta:
        return False

    p_meta = p_first[index_meta:]
    p_meta = p_meta[len(signature) + 3 :]

    index_meta_last = p_meta.find(b" ")
    if index_meta_last == -1:
        return False

    p_meta = p_meta[index_meta_last + 1 :]

    index_meta_last = p_meta.find(b" ")
    if index_meta_last == -1:
        return False

    return True
