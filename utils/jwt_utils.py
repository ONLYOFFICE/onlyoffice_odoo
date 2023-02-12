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

import jwt

from odoo.addons.onlyoffice_odoo_connector.utils import config_utils

def is_jwt_enabled(env):
    return bool(config_utils.get_jwt_secret(env))

def encode_payload(env, payload, secret = None):
    if (secret is None):
        secret = config_utils.get_jwt_secret(env)
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_token(env, token, secret = None):
    if (secret is None):
        secret = config_utils.get_jwt_secret(env)
    return jwt.decode(token, secret, algorithms=['HS256'])