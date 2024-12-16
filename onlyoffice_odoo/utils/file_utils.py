#
# (c) Copyright Ascensio System SIA 2024
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
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            return supported_format.type

    return None


def can_view(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            return True

    return False


def can_edit(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            return supported_format.edit

    return False


def can_fill_form(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            return supported_format.fillForm

    return False


def get_mime_by_ext(ext):
    if ext == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == "xlsx":
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if ext == "pptx":
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    if ext == "pdf":
        return "application/pdf"

    return None


def get_default_file_template(lang, ext):
    locale_path = {
        "az": "az-Latn-AZ",
        "bg": "bg-BG",
        "cs": "cs-CZ",
        "de": "de-DE",
        "default": "default",
        "el": "el-GR",
        "en-gb": "en-GB",
        "en": "en-US",
        "es": "es-ES",
        "eu_ES": "eu-ES",
        "fi": "fi-FI",
        "fr": "fr-FR",
        "gl": "gl-ES",
        "he": "he-IL",
        "it": "it-IT",
        "ja": "ja-JP",
        "ko": "ko-KR",
        "lv": "lv-LV",
        "nb_NO": "nb-NO",
        "nl": "nl-NL",
        "pl": "pl-PL",
        "pt-br": "pt-BR",
        "pt": "pt-PT",
        "ru": "ru-RU",
        "sk": "sk-SK",
        "sv": "sv-SE",
        "tr_TR": "tr-TR",
        "uk": "uk-UA",
        "vi": "vi-VN",
        "zh-CN": "zh-CN",
        "zh_TW": "zh-TW",
    }

    lang = lang.replace("_", "-")

    locale = locale_path.get(lang)
    if locale is None:
        lang = lang.split("-")[0]
        locale = locale_path.get(lang)
        if locale is None:
            locale = locale_path.get("default")

    file = open(
        os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "..",
            "static",
            "assets",
            "document_templates",
            locale,
            "new." + ext,
        ),
        "rb",
    )

    try:
        file_data = file.read()
        return file_data
    finally:
        file.close()
