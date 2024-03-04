from odoo.addons.onlyoffice_odoo.utils import jwt_utils
from odoo.exceptions import ValidationError

from urllib.request import urlopen
import json
import os
import re
import requests
import time

def valid_url(url):
    if not url:
        return True
    ip_pattern = "^([0-9]{1,3}\.){3}[0-9]{1,3}$"
    no_protocol_pattern = "^(http|https):\/\/[0-9A-z.]+.[0-9A-z.]+(|\/)$"
    patterns = [
        "^https:\/\/[0-9A-z.]+.[0-9A-z.]+.[a-z]+$",
        "^http:\/\/[0-9A-z.]+.[0-9A-z.]+.[a-z]+$",
        ip_pattern,
        no_protocol_pattern,
    ]
    for pattern in patterns:
        if re.findall(pattern, url):
            return True
    return False

def settings_validation(self):
        base_url = self.env["ir.config_parameter"].get_param("web.base.url")
        public_url = self.doc_server_public_url
        jwt_secret = self.doc_server_jwt_secret
        jwt_header = self.doc_server_jwt_header
        demo = False

        check_mixed_content(base_url, public_url, demo)
        check_doc_serv_url(public_url, demo)
        check_doc_serv_command_service(self.env, public_url, jwt_secret, jwt_header, demo)
        check_doc_serv_convert_service(self.env, public_url, base_url, jwt_secret, jwt_header, demo)

def check_mixed_content(base_url, public_url, demo):
    if (base_url.startswith("https") and not public_url.startswith("https")):
        get_message_error("Mixed Active Content is not allowed. HTTPS address for Document Server is required.", demo)

def check_doc_serv_url(public_url, demo):
    try:
        response = urlopen(os.path.join(public_url, "healthcheck"))
        healthcheck = response.read()

        if not healthcheck:
            get_message_error(os.path.join(public_url, "healthcheck") + " returned false.")

    except:
        get_message_error("ONLYOFFICE cannot be reached", demo)


def check_doc_serv_command_service(env, url, jwt_secret, jwt_header, demo):
    try:
        headers = {"Content-Type": "application/json"}
        body_json = {"c": "version"}

        if jwt_secret != None and jwt_secret != False and jwt_secret != "":
            payload = {"payload": body_json}

            header_token = jwt_utils.encode_payload(env, payload, jwt_secret)
            headers[jwt_header] = "Bearer " + header_token

            token = jwt_utils.encode_payload(env, body_json, jwt_secret)
            body_json["token"] = token

        response = requests.post(
            os.path.join(url, "coauthoring/CommandService.ashx"),
            data=json.dumps(body_json),
            headers=headers,
        )

        if response.json()["error"] == 6:
            get_message_error("Authorization error")

        if response.json()["error"] != 0:
            get_message_error(
                os.path.join(url, "coauthoring/CommandService.ashx")
                + " returned error: "
                + str(response.json()["error"])
            )

    except:
        get_message_error("Error when trying to check CommandService", demo)


def check_doc_serv_convert_service(env, public_url, base_url, jwt_secret, jwt_header, demo):
    file_url = os.path.join(base_url, "onlyoffice/file/content/test.txt")

    result = convert(env, file_url, public_url, jwt_secret, jwt_header)

    if isinstance(result, str):
        return get_message_error(result, demo)


def convert(env, file_url, public_url, jwt_secret, jwt_header):
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
            os.path.join(public_url, "ConvertService.ashx"),
            data = json.dumps(body_json),
            headers = headers
        )

        if response.status_code == 200:
            response_json = response.json()
            if "error" in response_json:
                return get_conversion_error_message(response_json.get("error"))
        else:
            return "Document conversion service returned status ${status_code}"

    except:
        return "Document conversion service cannot be reached"


def get_message_error(message, demo):
    if demo:
        raise ValidationError("Error connecting to demo server (${error})")
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

    except:
        return "Undefined error code"