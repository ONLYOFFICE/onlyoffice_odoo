# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import ipaddress
import json
import os
import re
import ssl
from urllib.parse import urlparse
from urllib.request import urlopen

import requests

from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo.utils import config_utils, conversion_utils, jwt_utils


def valid_url(url):
    """True for an empty address, or an http(s) one as the settings save it (without a scheme it gets http://).

    A host name, an IPv4 or an IPv6 address, an optional port and path; no login, query or fragment.
    """
    url = (url or "").strip()
    if not url:
        return True
    if re.match(r"[a-z][a-z0-9+.-]*://", url, re.IGNORECASE) and not re.match(r"https?://", url, re.IGNORECASE):
        return False
    url = config_utils.fix_proto(url)
    try:
        parsed = urlparse(url)
        _port = parsed.port  # raises ValueError for a port that is not a number in range
    except ValueError:
        return False
    host = parsed.hostname or ""
    return (
        parsed.scheme in ("http", "https")
        and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
        and (_valid_ipv6(host) if ":" in host else bool(re.fullmatch(r"[\w-]{1,63}(\.[\w-]{1,63})*", host)))
        and not re.search(r"\s", url)
    )


def _valid_ipv6(host):
    """True for an IPv6 address (in brackets in a URL, without them in its host name)."""
    try:
        ipaddress.IPv6Address(host)
    except ValueError:
        return False
    return True


def settings_validation(self):
    # The addresses as they are saved (scheme and final slash added), so the check reaches what is saved.
    base_url = config_utils.fix_url(self.doc_server_odoo_url) or config_utils.get_base_or_odoo_url(self.env)
    public_url = config_utils.fix_url(self.doc_server_public_url or "http://documentserver/")
    inner_url = config_utils.fix_url(self.doc_server_inner_url)
    jwt_secret = self.doc_server_jwt_secret
    # An empty header is saved as the default one: check with it.
    jwt_header = self.doc_server_jwt_header or "Authorization"
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
            get_message_error(url + " returned false.", demo)

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
