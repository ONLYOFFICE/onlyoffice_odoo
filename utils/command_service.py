#
# (c) Copyright Ascensio System SIA 2023
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import requests

from odoo.addons.onlyoffice_odoo_connector.utils import config_utils
from odoo.addons.onlyoffice_odoo_connector.utils import jwt_utils

_logger = logging.getLogger(__name__)

def get_command_service_url(env):
    return config_utils.get_doc_server_public_url(env) + "coauthoring/CommandService.ashx"

def get_version(env):
    return send_command_request(env, { "c": "version" })
    
def send_command_request(env, data):
    headers = None

    if jwt_utils.is_jwt_enabled(env):
        secret = config_utils.get_jwt_secret(env)
        data["token"] = jwt_utils.encode_payload(env, data, secret)
        headers = {}
        headers[config_utils.get_jwt_header(env)] = jwt_utils.encode_payload(env, { "payload": data }, secret)

    try:
        url = get_command_service_url(env)
    except Exception as ex:
        _logger.warning(f"Unexpected error while doing request to commandService: {ex}, {type(ex)}")
        return None

    return requests.post(url, json = data, headers = headers, timeout = 10)