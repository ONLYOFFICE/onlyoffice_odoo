#
# (c) Copyright Ascensio System SIA 2024
#

import json
import os


class Format:
    def __init__(self, name, type, actions=None, convert=None, mime=None):
        if actions is None:
            actions = []
        if convert is None:
            convert = []
        if mime is None:
            mime = []
        self.name = name
        self.type = type
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
