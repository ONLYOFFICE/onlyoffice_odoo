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
import uuid

def is_jwt_enabled(env):
    return bool(get_jwt_secret(env))

def encode_payload(env, payload, secret):
    if (secret is None):
        secret = get_jwt_secret(env)
    return jwt.encode(payload, secret, algorithm="HS256").decode("utf-8")

def decode_token(env, token, secret):
    if (secret is None):
        secret = get_jwt_secret(env)
    return jwt.decode(token, get_jwt_secret(env), algorithms=['HS256'])

def get_jwt_secret(env):
    return env["ir.config_parameter"].sudo().get_param("onlyoffice_connector.doc_server_jwt_secret")

def get_internal_jwt_secret(env):
    secret = env["ir.config_parameter"].sudo().get_param("onlyoffice_connector.internal_jwt_secret")
    if not secret:
        secret = uuid.uuid4().hex
        env["ir.config_parameter"].set_param("onlyoffice_connector.internal_jwt_secret", secret)

    return secret