#
# (c) Copyright Ascensio System SIA 2024
#

import uuid
from datetime import date

from odoo.addons.onlyoffice_odoo.utils import config_constants

def get_base_or_odoo_url(env):
    url = env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_ODOO_URL)
    return fix_url(url or env["ir.config_parameter"].sudo().get_param("web.base.url"))

def get_doc_server_public_url(env):
    url = env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_PUBLIC_URL)
    if not url:
        url = "http://documentserver/"
    return fix_url(url)

def get_doc_server_inner_url(env):
    url = env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_INNER_URL)
    return fix_url(url or get_doc_server_public_url(env))

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

def get_demo(env):
    return env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_DEMO)

def get_demo_date(env):
    return env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_DEMO_DATE)

def set_doc_server_public_url(env, url):
    if not url:
        url = "http://documentserver/"
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_PUBLIC_URL, fix_url(url))

def set_doc_server_odoo_url(env, url):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_ODOO_URL, fix_url(url))

def set_doc_server_inner_url(env, url):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_INNER_URL, fix_url(url))

def set_jwt_header(env, header):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_HEADER, header)

def set_jwt_secret(env, secret):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_JWT_SECRET, secret)

def set_demo(env, param):
    demo = get_demo(env)
    demo_date = get_demo_date(env)
    if not demo_date:
        set_demo_date(env)
    if param:
        set_doc_server_public_url(env, "https://onlinedocs.onlyoffice.com/")
        set_doc_server_odoo_url(env, "")
        set_doc_server_inner_url(env, "")
        set_jwt_header(env, "AuthorizationJWT")
        set_jwt_secret(env, "sn2puSUF7muF5Jas")
    elif demo and not param:
        set_doc_server_public_url(env, "http://documentserver/")
        set_doc_server_odoo_url(env, "")
        set_doc_server_inner_url(env, "")
        set_jwt_header(env, "Authorization")
        set_jwt_secret(env, "")
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_DEMO, param)

def set_demo_date(env):
    demo_date = date.today()
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_DEMO_DATE, demo_date)

def fix_url(url):
    if url:
        return fix_end_slash(fix_proto(url))

def fix_proto(url):
    return url if url.startswith("http") else ("http://" + url)

def fix_end_slash(url):
    return url if url.endswith("/") else (url + "/")