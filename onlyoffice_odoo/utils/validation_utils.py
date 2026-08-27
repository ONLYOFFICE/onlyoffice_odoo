# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
import os
import re
import ssl
from urllib.request import urlopen

import requests

from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo.utils import config_utils, conversion_utils, jwt_utils


def valid_url(url):
    if not url:
        return True
    pattern = r"^(https?://)?[\w-]{1,32}(\.[\w-]{1,32})*[/\w-]*(:[\d]{1,5}/?)?$"
    if re.findall(pattern, url):
        return True
    return False


def settings_validation(self):
    base_url = self.doc_server_odoo_url or config_utils.get_base_or_odoo_url(self.env)
    public_url = self.doc_server_public_url
    inner_url = self.doc_server_inner_url
    jwt_secret = self.doc_server_jwt_secret
    jwt_header = self.doc_server_jwt_header
    disable_certificate = self.doc_server_disable_certificate
    demo = self.doc_server_demo

    url = public_url
    if inner_url and inner_url != public_url:
        url = inner_url

    check_mixed_content(base_url, url, demo)
    check_doc_serv_url(url, demo, disable_certificate)
    check_doc_serv_command_service(self.env, url, jwt_secret, jwt_header, disable_certificate, demo)
    check_doc_serv_convert_service(self.env, url, base_url, jwt_secret, jwt_header, disable_certificate, demo)


def check_mixed_content(base_url, url, demo):
    if base_url.startswith("https") and not url.startswith("https"):
        get_message_error("Mixed Active Content is not allowed. HTTPS address for Document Server is required.", demo)


def check_doc_serv_url(url, demo, disable_certificate):
    try:
        url = os.path.join(url, "healthcheck")

        context = None
        if disable_certificate and url.startswith("https://"):
            context = ssl._create_unverified_context()

        response = urlopen(url, timeout=30, context=context)

        healthcheck = response.read()

        if not healthcheck:
            get_message_error(os.path.join(url, "healthcheck") + " returned false.", demo)

    except ValidationError as e:
        get_message_error(str(e), demo)
    except Exception:
        get_message_error("ONLYOFFICE cannot be reached", demo)


def check_doc_serv_command_service(env, url, jwt_secret, jwt_header, disable_certificate, demo):
    try:
        headers = {"Content-Type": "application/json"}
        body_json = {"c": "version"}

        if jwt_secret is not None and jwt_secret is not False and jwt_secret != "":
            payload = {"payload": body_json}

            header_token = jwt_utils.encode_payload(env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + header_token

            token = jwt_utils.encode_payload(env, body_json, jwt_secret)
            body_json["token"] = token

        response = requests.post(
            os.path.join(url, "coauthoring/CommandService.ashx"),
            verify=not disable_certificate,
            timeout=60,
            data=json.dumps(body_json),
            headers=headers,
        )

        if response.json()["error"] == 6:
            get_message_error("Authorization error", demo)

        if response.json()["error"] != 0:
            get_message_error(
                os.path.join(url, "coauthoring/CommandService.ashx")
                + " returned error: "
                + str(response.json()["error"]),
                demo,
            )

    except ValidationError as e:
        get_message_error(str(e), demo)
    except Exception:
        get_message_error("Error when trying to check CommandService", demo)


def check_doc_serv_convert_service(env, url, base_url, jwt_secret, jwt_header, disable_certificate, demo):
    file_url = os.path.join(base_url, "onlyoffice/file/content/test.txt")

    result = convert(env, file_url, url, jwt_secret, jwt_header, disable_certificate)

    if isinstance(result, str):
        return get_message_error(result, demo)


def convert(env, file_url, url, jwt_secret, jwt_header, disable_certificate):
    body_json = conversion_utils.build_conversion_body(file_url, "txt", "txt")
    body_json, headers = conversion_utils.sign_conversion_request(env, body_json, jwt_secret, jwt_header)

    try:
        response = requests.post(
            os.path.join(url, "converter", f"?shardkey={body_json['key']}"),
            verify=not disable_certificate,
            timeout=60,
            data=json.dumps(body_json),
            headers=headers,
        )
    except Exception:
        return "Document conversion service cannot be reached"

    result = conversion_utils.parse_conversion_response(response)
    if "error" in result:
        return result["message"]
    return None


def get_message_error(message, demo):
    if demo:
        raise ValidationError(f"Error connecting to demo server: {message}")
    else:
        raise ValidationError(message)
