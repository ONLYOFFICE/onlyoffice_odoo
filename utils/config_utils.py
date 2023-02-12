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

import uuid

from odoo.addons.onlyoffice_odoo_connector.utils import config_constants

def get_odoo_url(env):
    url = env["ir.config_parameter"].sudo().get_param("web.base.url")
    return fix_url(url)

def get_doc_server_public_url(env):
    url = env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_PUBLIC_URL)
    if not url:
        url = "http://documentserver/"
    return fix_url(url)

def get_jwt_header(env):
    header = env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_JWT_HEADER)
    if not header:
        header = "Authorization"
    return header

def get_jwt_secret(env):
    return env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_JWT_SECRET)

def get_internal_jwt_secret(env):
    secret = env["ir.config_parameter"].sudo().get_param(config_constants.INTERNAL_JWT_SECRET)
    if not secret:
        secret = uuid.uuid4().hex
        env["ir.config_parameter"].set_param(config_constants.INTERNAL_JWT_SECRET, secret)

    return secret

def set_doc_server_public_url(env, url):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_PUBLIC_URL, fix_url(url))

def set_jwt_header(env, header):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_HEADER, header)

def set_jwt_secret(env, secret):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_SECRET, secret)

def fix_url(url):
    return fix_end_slash(fix_proto(url))

def fix_proto(url):
    return url if url.startswith("http") else ("http://" + url)

def fix_end_slash(url):
    return url if url.endswith("/") else (url + "/")