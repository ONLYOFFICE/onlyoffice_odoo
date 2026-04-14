# Copyright (C) 2026 Ascensio System SIA

import datetime

import jwt

from odoo.addons.onlyoffice_odoo.utils import config_utils


def is_jwt_enabled(env):
    return bool(config_utils.get_jwt_secret(env))


def encode_payload(env, payload, secret=None):
    if secret is None:
        secret = config_utils.get_jwt_secret(env)
    now = datetime.datetime.now(datetime.timezone.utc)
    exp = now + datetime.timedelta(hours=24)
    payload["iat"] = int(now.timestamp())
    payload["exp"] = int(exp.timestamp())
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(env, token, secret=None):
    if secret is None:
        secret = config_utils.get_jwt_secret(env)
    return jwt.decode(token, secret, algorithms=["HS256"])
