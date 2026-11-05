# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import functools
import hashlib
import os

from odoo.tools import file_open

from odoo.addons.onlyoffice_odoo.utils import format_utils

_CUSTOM_FUNCTIONS_PATH = "onlyoffice_odoo/static/src/js/odoo_custom_functions_init.js"


@functools.cache
def get_custom_functions_url():
    """URL of the ODOO functions of the editor with a hash of the file.

    The file is served raw with a long browser cache: a new version must have a new URL, or browsers keep the old one.
    """
    with file_open(_CUSTOM_FUNCTIONS_PATH, "rb") as f:
        digest = hashlib.sha1(f.read()).hexdigest()[:12]
    return f"/{_CUSTOM_FUNCTIONS_PATH}?v={digest}"


def get_file_title_without_ext(name):
    ind = name.rfind(".")
    # A name without extension is the title itself.
    return name[:ind] if ind != -1 else name


def get_file_name_without_ext(name):
    ind = name.rfind(".")
    return name[:ind] if ind != -1 else name


def get_file_ext(name):
    # A name without extension has none (not the whole name).
    ind = name.rfind(".")
    return name[ind + 1 :].lower() if ind != -1 else ""


def get_ext_by_mime(mimetype):
    """The extension of a supported format of that type, for a file whose name has no extension."""
    for supported_format in format_utils.get_supported_formats():
        if mimetype and mimetype in supported_format.mime:
            return supported_format.name
    return ""


def get_file_type(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            return supported_format.type

    return None


def can_view(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            if "view" in supported_format.actions:
                return True

    return False


def can_edit(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            if "edit" in supported_format.actions:
                return True

    return False


def can_fill_form(context):
    for supported_format in format_utils.get_supported_formats():
        if supported_format.name == get_file_ext(context):
            if "fill" in supported_format.actions:
                return True

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
        "eu": "eu-ES",
        "fi": "fi-FI",
        "fr": "fr-FR",
        "gl": "gl-ES",
        "he": "he-IL",
        "it": "it-IT",
        "ja": "ja-JP",
        "ko": "ko-KR",
        "lv": "lv-LV",
        "nb": "nb-NO",
        "nl": "nl-NL",
        "pl": "pl-PL",
        "pt-br": "pt-BR",
        "pt": "pt-PT",
        "ru": "ru-RU",
        "sk": "sk-SK",
        "sv": "sv-SE",
        "tr": "tr-TR",
        "uk": "uk-UA",
        "vi": "vi-VN",
        "zh-CN": "zh-CN",
        "zh-TW": "zh-TW",
        "ca": "ca-ES",
        "da": "da-DK",
        "hu": "hu-HU",
        "id": "id-ID",
        "ro": "ro-RO",
    }

    lang = lang.replace("_", "-")

    locale = locale_path.get(lang)
    if locale is None:
        lang = lang.split("-")[0]
        locale = locale_path.get(lang)
        if locale is None:
            locale = locale_path.get("default")

    with open(
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
    ) as file:
        return file.read()
