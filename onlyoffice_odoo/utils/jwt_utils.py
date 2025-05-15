#
# (c) Copyright Ascensio System SIA 2024
#

import datetime

import jwt

from odoo.addons.onlyoffice_odoo.utils import config_utils


def is_jwt_enabled(env):
    return bool(config_utils.get_jwt_secret(env))


def encode_payload(env, payload, secret=None):
    if secret is None:
        secret = config_utils.get_jwt_secret(env)
    now = datetime.datetime.utcnow()
    exp = now + datetime.timedelta(hours=24)
    payload["iat"] = int(now.timestamp())
    payload["exp"] = int(exp.timestamp())
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(env, token, secret=None):
    if secret is None:
        secret = config_utils.get_jwt_secret(env)
    return jwt.decode(token, secret, algorithms=["HS256"])
