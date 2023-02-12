#
# (c) Copyright Ascensio System SIA 2023
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

from odoo.addons.onlyoffice_odoo_connector.utils import format_utils

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
