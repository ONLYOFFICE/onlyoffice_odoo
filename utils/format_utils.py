#
# (c) Copyright Ascensio System SIA 2023
#
# This program is a free software product. You can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License (AGPL)
# version 3 as published by the Free Software Foundation. In accordance with
# Section 7(a) of the GNU AGPL its Section 15 shall be amended to the effect
# that Ascensio System SIA expressly excludes the warranty of non-infringement
# of any third-party rights.
#
# This program is distributed WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR  PURPOSE. For
# details, see the GNU AGPL at: http://www.gnu.org/licenses/agpl-3.0.html
#
# You can contact Ascensio System SIA at 20A-12 Ernesta Birznieka-Upisha
# street, Riga, Latvia, EU, LV-1050.
#
# The  interactive user interfaces in modified source and object code versions
# of the Program must display Appropriate Legal Notices, as required under
# Section 5 of the GNU AGPL version 3.
#
# Pursuant to Section 7(b) of the License you must retain the original Product
# logo when distributing the program. Pursuant to Section 7(e) we decline to
# grant you any rights under trademark law for use of our trademarks.
#
# All the Product's GUI elements, including illustrations and icon sets, as
# well as technical writing content are licensed under the terms of the
# Creative Commons Attribution-ShareAlike 4.0 International. See the License
# terms at http://creativecommons.org/licenses/by-sa/4.0/legalcode
#


class Format:
    def __init__(self, name, type, edit=False, fill_form=False, convert_to=[]):
        self.name = name
        self.type = type
        self.edit = edit
        self.fill_form = fill_form
        self.convert_to = convert_to


def get_supported_formats():
    return [
        Format("djvu", "word"),
        Format("doc", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("docm", "word", convert_to=["docx", "docxf", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format(
            "docx",
            "word",
            True,
            convert_to=["docxf", "oform", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"],
        ),
        Format(
            "docxf",
            "word",
            True,
            convert_to=["docx", "oform", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"],
        ),
        Format("dot", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("dotm", "word", convert_to=["docx", "docxf", "docm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("dotx", "word", convert_to=["docx", "docxf", "docm", "dotm", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("epub", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("fb2", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("fodt", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("html", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("mht", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("odt", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("ott", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "pdf", "pdfa", "rtf", "txt"]),
        Format("oxps", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("pdf", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdfa", "rtf", "txt"]),
        Format("rtf", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "txt"]),
        Format("txt", "word"),
        Format("xps", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("xml", "word", convert_to=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("oform", "word", fill_form=True),
        Format("csv", "cell"),
        Format("fods", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("ods", "cell", convert_to=["xlsx", "csv", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("ots", "cell", convert_to=["xlsx", "csv", "ods", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xls", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlsb", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlsm", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xltm", "xltx"]),
        Format("xlsx", "cell", True, convert_to=["csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlt", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xltm", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltx"]),
        Format("xltx", "cell", convert_to=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm"]),
        Format("fodp", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("odp", "slide", convert_to=["pptx", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("otp", "slide", convert_to=["pptx", "odp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("pot", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("potm", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potx", "pptm"]),
        Format("potx", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "pptm"]),
        Format("pps", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppsm", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppsx", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppt", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("pptm", "slide", convert_to=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx"]),
        Format("pptx", "slide", True, convert_to=["odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
    ]
