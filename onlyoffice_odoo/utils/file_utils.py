#
# (c) Copyright Ascensio System SIA 2023
#

import os

from odoo.addons.onlyoffice_odoo.utils import format_utils


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

def get_mime_by_ext(str):
    if str == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if str == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if str == "pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"

    return None

def get_default_file_template(lang, ext):
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

    lang = lang.replace("_", "-")

    locale = locale_path.get(lang)
    if locale is None:
        lang = lang.split("-")[0]
        locale = locale_path.get(lang)
        if locale is None:
            locale = locale_path.get("en")

    file = open(os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "static", "assets", "document_templates", locale, "new." + ext), "rb")

    try:
        file_data = file.read()
        return file_data
    finally:
        file.close()