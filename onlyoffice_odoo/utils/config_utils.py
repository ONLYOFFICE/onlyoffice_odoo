# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import re
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
        env["ir.config_parameter"].sudo().set_param(config_constants.INTERNAL_JWT_SECRET, secret)
        # Save the new secret to the database right now, before anything else can fail.
        # Odoo wraps each request in a transaction that can be rolled back on error,
        # which would delete the secret we just created. By committing here we make sure
        # the secret survives even if the rest of the request fails later.
        env.cr.commit()

    return secret


# The public demo server: the settings show its address, secret and header while the demo is on.
DEMO_PUBLIC_URL = "https://onlinedocs.docs.onlyoffice.com/"
DEMO_JWT_HEADER = "AuthorizationJWT"
DEMO_JWT_SECRET = "sn2puSUF7muF5Jas"


def _get_flag(env, key):
    """A flag as set_param stores it ("True", or no parameter), as a boolean: the settings compare it with a box."""
    return str(env["ir.config_parameter"].sudo().get_param(key) or "").lower() in ("true", "1")


def get_demo(env):
    return _get_flag(env, config_constants.DOC_SERVER_DEMO)


def get_demo_date(env):
    return env["ir.config_parameter"].sudo().get_param(config_constants.DOC_SERVER_DEMO_DATE)


def get_same_tab(env):
    return _get_flag(env, config_constants.SAME_TAB)


def get_certificate_verify_disabled(env):
    return _get_flag(env, config_constants.DOC_SERVER_DISABLE_CERTIFICATE)


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
        set_doc_server_public_url(env, DEMO_PUBLIC_URL)
        set_doc_server_odoo_url(env, "")
        set_doc_server_inner_url(env, "")
        set_jwt_header(env, DEMO_JWT_HEADER)
        set_jwt_secret(env, DEMO_JWT_SECRET)
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


def set_same_tab(env, param):
    env["ir.config_parameter"].sudo().set_param(config_constants.SAME_TAB, param)


def set_certificate_verify_disabled(env, param):
    env["ir.config_parameter"].sudo().set_param(config_constants.DOC_SERVER_DISABLE_CERTIFICATE, param)


def fix_url(url):
    if url:
        return fix_end_slash(fix_proto(url))


def fix_proto(url):
    # "httpdocs.example.com" has no scheme although it starts with "http".
    return url if re.match(r"https?://", url, re.IGNORECASE) else ("http://" + url)


def fix_end_slash(url):
    return url if url.endswith("/") else (url + "/")
