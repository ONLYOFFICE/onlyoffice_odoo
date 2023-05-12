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

from odoo.addons.onlyoffice_odoo.utils import format_utils

locale_path = {
    "az": "az-Latn-AZ",
    "bg": "bg-BG",
    "cs": "cs-CZ",
    "de": "de-DE",
    "el": "el-GR",
    "en-gb": "en-GB",
    "en": "en-US",
    "es": "es-ES",
    "fr": "fr-FR",
    "it": "it-IT",
    "ja": "ja-JP",
    "ko": "ko-KR",
    "lv": "lv-LV",
    "nl": "nl-NL",
    "pl": "pl-PL",
    "pt-br": "pt-BR",
    "pt": "pt-PT",
    "ru": "ru-RU",
    "sk": "sk-SK",
    "sv": "sv-SE",
    "uk": "uk-UA",
    "vi": "vi-VN",
    "zh": "zh-CN",
}


def get_file_title_without_ext(name):
    ind = name.rfind(".")
    return name[:ind]


def get_file_name_without_ext(name):
    ind = name.rfind(".")
    return name[:ind]


def get_file_ext(name):
    return name[name.rfind(".") + 1 :].lower()


def get_file_type(context):
    for format in format_utils.get_supported_formats():
        if format.name == get_file_ext(context):
            return format.type

    return None


def can_view(context):
    for format in format_utils.get_supported_formats():
        if format.name == get_file_ext(context):
            return True

    return False


def can_edit(context):
    for format in format_utils.get_supported_formats():
        if format.name == get_file_ext(context):
            return format.edit

    return False


def can_fill_form(context):
    for format in format_utils.get_supported_formats():
        if format.name == get_file_ext(context):
            return format.fillForm

    return False


def get_default_ext_by_type(str):
    if str == "word":
        return "docx"
    if str == "cell":
        return "xlsx"
    if str == "slide":
        return "pptx"
    if str == "form":
        return "docxf"

    return None


def get_default_name_by_type(str):
    if str == "word":
        return "Document"
    if str == "cell":
        return "Spreadsheet"
    if str == "slide":
        return "Presentation"
    if str == "form":
        return "Form template"

    return None
