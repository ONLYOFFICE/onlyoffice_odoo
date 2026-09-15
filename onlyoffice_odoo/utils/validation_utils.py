# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import json
import logging
import os
import re
import ssl
from urllib.request import urlopen

import requests

from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo.utils import config_utils, conversion_utils, jwt_utils, network_utils

_logger = logging.getLogger(__name__)

# Client-facing message for all request checks below; real details go to the server log only.
REQUEST_ERROR_MESSAGE = "Connection check failed. See the server log for details."

LOCAL_ADDRESS_ERROR_MESSAGE = (
    "Local and private addresses are not allowed. "
    "To allow them, set allow_local_address = True in the [onlyoffice] section of the Odoo config file."
)

# ONLYOFFICE Document Server CommandService error codes ("c": "version" request).
COMMAND_SERVICE_ERROR_CODES = {
    1: "Document key is missing or no document with such key could be found",
    2: "Callback url not correct",
    3: "Internal server error",
    4: "No changes were applied to the document before the forcesave command was received",
    5: "Command not correct",
    6: "Invalid token",
}


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

    check_local_address(url, demo)
    check_mixed_content(base_url, url, demo)
    check_api_js(url, demo, disable_certificate)
    check_doc_serv_healthcheck(url, demo, disable_certificate)
    check_doc_serv_command_service(self.env, url, jwt_secret, jwt_header, disable_certificate, demo)
    check_doc_serv_convert_service(self.env, url, base_url, jwt_secret, jwt_header, disable_certificate, demo)


def check_local_address(url, demo):
    # Runs first: rejecting here leaks nothing about the network.
    if network_utils.is_local_address_check_disabled():
        _logger.info("check_local_address - local address ban is disabled in the Odoo configuration file")
        return

    if network_utils.is_local_url(config_utils.fix_url(url)):
        _logger.warning("check_local_address - local address rejected for ONLYOFFICE Docs: %s", url)
        get_message_error(LOCAL_ADDRESS_ERROR_MESSAGE, demo)


def check_mixed_content(base_url, url, demo):
    if base_url.startswith("https") and not url.startswith("https"):
        get_message_error(
            "Mixed Active Content is not allowed. HTTPS address for ONLYOFFICE Document Server is required.", demo
        )


def check_api_js(url, demo, disable_certificate):
    api_js_url = os.path.join(url, "web-apps/apps/api/documents/api.js")

    try:
        context = None
        if disable_certificate and api_js_url.startswith("https://"):
            context = ssl._create_unverified_context()
        status = urlopen(api_js_url, timeout=30, context=context).status
    except Exception as e:
        _logger.warning("check_api_js - cannot reach %s: %r", api_js_url, e)
        status = None

    if status != 200:
        get_message_error("The API JavaScript file cannot be reached.", demo)


def check_doc_serv_healthcheck(url, demo, disable_certificate):
    url = os.path.join(url, "healthcheck")

    try:
        context = None
        if disable_certificate and url.startswith("https://"):
            context = ssl._create_unverified_context()

        healthcheck = urlopen(url, timeout=30, context=context).read()

        if not healthcheck:
            _logger.error("check_doc_serv_healthcheck - %s returned false", url)
            get_request_error("Document Server return bad healthcheck status.", demo)

    except ValidationError:
        raise
    except Exception as e:
        _logger.error("check_doc_serv_healthcheck - cannot reach %s: %r", url, e)
        get_request_error("Document Server cannot be reached.", demo)


def check_doc_serv_command_service(env, url, jwt_secret, jwt_header, disable_certificate, demo):
    url = os.path.join(url, "coauthoring/CommandService.ashx")

    try:
        headers = {"Content-Type": "application/json"}
        body_json = {"c": "version"}

        if jwt_secret:
            payload = {"payload": body_json}

            header_token = jwt_utils.encode_payload(env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + header_token

            token = jwt_utils.encode_payload(env, body_json, jwt_secret)
            body_json["token"] = token

        response = requests.post(
            url,
            verify=not disable_certificate,
            timeout=60,
            data=json.dumps(body_json),
            headers=headers,
        )

        error = response.json()["error"]

        if error != 0:
            message = COMMAND_SERVICE_ERROR_CODES.get(error, "Undefined error code")
            get_request_error(f"Error when trying to check CommandService({message}).", demo)

    except ValidationError:
        raise
    except Exception as e:
        _logger.error("check_doc_serv_command_service - request failed at %s: %r", url, e)
        get_request_error("Error when trying to check CommandService(Connection error).", demo)


def check_doc_serv_convert_service(env, url, base_url, jwt_secret, jwt_header, disable_certificate, demo):
    file_url = os.path.join(base_url, "onlyoffice/file/content/test.txt")

    result = convert(env, file_url, url, jwt_secret, jwt_header, disable_certificate)

    if isinstance(result, str):
        return get_request_error(f"Error when trying to check ConvertService({result}).", demo)


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
    except Exception as e:
        _logger.error("convert - conversion service request failed at %s: %r", url, e)
        return "Connection error"

    result = conversion_utils.parse_conversion_response(response)
    if "error" in result:
        return result["message"]
    return None


def get_request_error(message, demo):
    # Logs full details; the client only sees REQUEST_ERROR_MESSAGE.
    _logger.error("settings_validation - %s", message)
    get_message_error(REQUEST_ERROR_MESSAGE, demo)


def get_message_error(message, demo):
    if demo:
        raise ValidationError(f"Demo server error: {message}")
    else:
        raise ValidationError(message)
