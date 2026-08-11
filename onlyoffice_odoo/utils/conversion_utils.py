# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import time

from odoo.tools.translate import _

from odoo.addons.onlyoffice_odoo.utils import jwt_utils

_CONVERSION_ERROR_CODES = {
    -1: "Unknown error",
    -2: "Conversion timeout error",
    -3: "Conversion error",
    -4: "Error while downloading the document file to be converted",
    -5: "Incorrect password",
    -6: "Error while accessing the conversion result database",
    -7: "Input error",
    -8: "Invalid token",
}


def get_conversion_error_message(error_code):
    return _(_CONVERSION_ERROR_CODES.get(error_code, "Undefined error code"))


def build_conversion_body(source_url, source_ext, target_ext, extra_options=None):
    """Build the JSON body for a request to the ONLYOFFICE Document Server converter API."""
    body_json = {
        "key": int(time.time()),
        "url": source_url,
        "filetype": source_ext,
        "outputtype": target_ext,
    }
    if extra_options:
        body_json.update(extra_options)
    return body_json


def sign_conversion_request(env, body_json, jwt_secret, jwt_header):
    """Sign a conversion request body with JWT, if a secret is configured.

    Returns a (body_json, headers) tuple. body_json is mutated in place with a
    "token" field when signing is enabled.
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if jwt_secret:
        payload = {"payload": body_json}
        token = jwt_utils.encode_payload(env, payload, jwt_secret)
        headers[jwt_header] = "Bearer " + token
        body_json["token"] = jwt_utils.encode_payload(env, body_json, jwt_secret)
    return body_json, headers


def parse_conversion_response(response):
    """Parse a converter API HTTP response into a normalized result dict.

    Returns the decoded response JSON on success (contains "fileUrl", etc.),
    or {"error": <code>, "message": <str>} on failure.
    """
    if response.status_code != 200:
        return {
            "error": response.status_code,
            "message": _("Document conversion service returned status %s") % response.status_code,
        }

    response_json = response.json()
    if "error" in response_json:
        return {
            "error": response_json.get("error"),
            "message": get_conversion_error_message(response_json.get("error")),
        }

    return response_json
