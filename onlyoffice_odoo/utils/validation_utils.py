import json
import os
import re
import time
from urllib.request import urlopen

import requests

from odoo.exceptions import ValidationError

from odoo.addons.onlyoffice_odoo.utils import jwt_utils


def valid_url(url):
    if not url:
        return True
    # pylint: disable=anomalous-backslash-in-string
    pattern = "^(https?:\/\/)?[\w-]{1,32}(\.[\w-]{1,32})*[\/\w-]*(:[\d]{1,5}\/?)?$"
    # pylint: enable=anomalous-backslash-in-string
    if re.findall(pattern, url):
        return True
    return False


def settings_validation(self):
    base_url = self.doc_server_odoo_url
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
            import ssl

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
    body_json = {
        "key": int(time.time()),
        "url": file_url,
        "filetype": "txt",
        "outputtype": "txt",
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    if bool(jwt_secret):
        payload = {"payload": body_json}
        header_token = jwt_utils.encode_payload(env, payload, jwt_secret)
        headers[jwt_header] = "Bearer " + header_token
        token = jwt_utils.encode_payload(env, body_json, jwt_secret)
        body_json["token"] = token

    try:
        response = requests.post(
            os.path.join(url, "ConvertService.ashx"),
            verify=not disable_certificate,
            timeout=60,
            data=json.dumps(body_json),
            headers=headers,
        )

        if response.status_code == 200:
            response_json = response.json()
            if "error" in response_json:
                return get_conversion_error_message(response_json.get("error"))
        else:
            return f"Document conversion service returned status {response.status_code}"

    except Exception:
        return "Document conversion service cannot be reached"


def get_message_error(message, demo):
    if demo:
        raise ValidationError(f"Error connecting to demo server: {message}")
    else:
        raise ValidationError(message)


def get_conversion_error_message(errorCode):
    errorDictionary = {
        -1: "Unknown error",
        -2: "Conversion timeout error",
        -3: "Conversion error",
        -4: "Error while downloading the document file to be converted",
        -5: "Incorrect password",
        -6: "Error while accessing the conversion result database",
        -7: "Input error",
        -8: "Invalid token",
    }

    try:
        return errorDictionary[errorCode]

    except Exception:
        return "Undefined error code"
