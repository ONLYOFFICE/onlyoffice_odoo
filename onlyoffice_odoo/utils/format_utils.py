# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
import os

import markupsafe


def to_script_json(data):
    # Escape "<" so "</script>" in user data can't close the surrounding <script> tag (XSS).
    return markupsafe.Markup(json.dumps(data).replace("<", "\\u003c"))


class Format:
    def __init__(self, name, fmt_type, actions=None, convert=None, mime=None):
        if actions is None:
            actions = []
        if convert is None:
            convert = []
        if mime is None:
            mime = []
        self.name = name
        self.type = fmt_type
        self.actions = actions
        self.convert = convert
        self.mime = mime


def get_supported_formats():
    file_path = os.path.join(
        os.path.dirname(__file__), "..", "static", "assets", "document_formats", "onlyoffice-docs-formats.json"
    )

    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    formats = []
    for item in data:
        n = item["name"]
        t = item["type"]
        a = item.get("actions", [])
        c = item.get("convert", [])
        m = item.get("mime", [])

        formats.append(Format(n, t, a, c, m))

    return formats
