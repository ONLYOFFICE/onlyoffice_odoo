#
# (c) Copyright Ascensio System SIA 2022
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


class Format:
    def __init__(self, name, type, edit=False, fillForm=False, convertTo=[]):
        self.name = name
        self.type = type
        self.edit = edit
        self.fillForm = fillForm
        self.convertTo = convertTo


def getSupportedFormats():
    return [
        Format("djvu", "word"),
        Format("doc", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("docm", "word", convertTo=["docx", "docxf", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format(
            "docx",
            "word",
            True,
            convertTo=["docxf", "oform", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"],
        ),
        Format(
            "docxf",
            "word",
            True,
            convertTo=["docx", "oform", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"],
        ),
        Format("dot", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("dotm", "word", convertTo=["docx", "docxf", "docm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("dotx", "word", convertTo=["docx", "docxf", "docm", "dotm", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("epub", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("fb2", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("fodt", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("html", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("mht", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("odt", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("ott", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "pdf", "pdfa", "rtf", "txt"]),
        Format("oxps", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("pdf", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdfa", "rtf", "txt"]),
        Format("rtf", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "txt"]),
        Format("txt", "word"),
        Format("xps", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("xml", "word", convertTo=["docx", "docxf", "docm", "dotm", "dotx", "epub", "fb2", "html", "odt", "ott", "pdf", "pdfa", "rtf", "txt"]),
        Format("oform", "word", fillForm=True),
        Format("csv", "cell"),
        Format("fods", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("ods", "cell", convertTo=["xlsx", "csv", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("ots", "cell", convertTo=["xlsx", "csv", "ods", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xls", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlsb", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlsm", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xltm", "xltx"]),
        Format("xlsx", "cell", True, convertTo=["csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xlt", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm", "xltx"]),
        Format("xltm", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltx"]),
        Format("xltx", "cell", convertTo=["xlsx", "csv", "ods", "ots", "pdf", "pdfa", "xlsm", "xltm"]),
        Format("fodp", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("odp", "slide", convertTo=["pptx", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("otp", "slide", convertTo=["pptx", "odp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("pot", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("potm", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potx", "pptm"]),
        Format("potx", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "pptm"]),
        Format("pps", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppsm", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppsx", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("ppt", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
        Format("pptm", "slide", convertTo=["pptx", "odp", "otp", "pdf", "pdfa", "potm", "potx"]),
        Format("pptx", "slide", True, convertTo=["odp", "otp", "pdf", "pdfa", "potm", "potx", "pptm"]),
    ]
