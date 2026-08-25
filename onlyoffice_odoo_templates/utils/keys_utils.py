# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

import codecs
import json
import logging

from odoo.addons.onlyoffice_odoo.controllers.main import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, jwt_utils, url_utils

logger = logging.getLogger(__name__)


def fetch_field_keys(env, attachment_id, oo_security_token):
    """Ask the docbuilder service for the OFORM field keys of an attachment.

    Shared by the eager cache population (``onlyoffice.odoo.templates``
    model, triggered on template create/upload/edit) and the lazy fallback
    (``OnlyofficeTemplate_Connector._get_cached_keys``) so there is a single
    place that knows how to talk to docbuilder for this.
    """
    docserver_url = config_utils.get_doc_server_public_url(env)
    docserver_url = url_utils.replace_public_url_to_internal(env, docserver_url)
    docbuilder_url = f"{docserver_url}docbuilder"
    jwt_header = config_utils.get_jwt_header(env)
    jwt_secret = config_utils.get_jwt_secret(env)
    odoo_url = config_utils.get_base_or_odoo_url(env)

    docbuilder_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    docbuilder_callback_url = (
        f"{odoo_url}onlyoffice/template/callback/docbuilder/get_keys"
        f"?attachment_id={attachment_id}&oo_security_token={oo_security_token}"
    )
    docbuilder_payload = {"async": False, "url": docbuilder_callback_url}

    opts = {"json": docbuilder_payload}
    if jwt_secret:
        docbuilder_payload["token"] = jwt_utils.encode_payload(env, docbuilder_payload, jwt_secret)
        docbuilder_headers[jwt_header] = "Bearer " + jwt_utils.encode_payload(
            env, {"payload": docbuilder_payload}, jwt_secret
        )
        opts["headers"] = docbuilder_headers

    docbuilder_response = onlyoffice_request(url=docbuilder_url, method="post", opts=opts)
    docbuilder_json = docbuilder_response.json()
    if docbuilder_json.get("error"):
        raise Exception(f"docbuilder error while fetching field keys: {docbuilder_json.get('error')}")

    urls = docbuilder_json.get("urls")
    keys_url = urls.get("keys.txt")
    keys_response = onlyoffice_request(url=keys_url, method="get")
    response_content = codecs.decode(keys_response.content, "utf-8-sig")

    return json.loads(response_content)
