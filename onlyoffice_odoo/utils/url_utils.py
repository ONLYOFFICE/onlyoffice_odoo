# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import logging
from urllib.parse import unquote, urlparse

import requests

from odoo.addons.onlyoffice_odoo.utils import config_constants, config_utils

_logger = logging.getLogger(__name__)


def replace_public_url_to_internal(env, url):
    public_url = config_utils.get_doc_server_public_url(env)
    inner_url = config_utils.get_doc_server_inner_url(env)
    if inner_url and inner_url != public_url:
        _logger.info("Replace public url %s to internal url %s", public_url, inner_url)
        url = url.replace(public_url, inner_url)
    return url


# The host the files of the ONLYOFFICE form gallery are served from.
FORM_FILES_HOSTS = ("static-oforms.onlyoffice.com",)
# The largest form file taken from the gallery.
FORM_FILE_MAX_SIZE = 50 * 1024 * 1024


def check_download_url(url):
    """Refuse a URL that is not an HTTP one: a file of the Document Server is never at "file://" or "ftp://"."""
    if urlparse(str(url or "")).scheme not in ("http", "https"):
        raise ValueError(f"Not an HTTP address: {url!r}")
    return url


def _origin(parsed):
    """Scheme, host and port of a parsed URL, the default port of the scheme when none is given.

    Raises ValueError for an address with a user (``host@attacker.com`` goes to ``attacker.com``) or a wrong port.
    """
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("An address with a user")
    return parsed.scheme, (parsed.hostname or "").lower(), parsed.port or {"http": 80, "https": 443}.get(parsed.scheme)


def is_form_file_url(url, env=None):
    """Whether ``url`` is a file of the ONLYOFFICE form gallery: an https address of its file host, or an address in
    the folder of an own mirror of the gallery set by an administrator (system parameter
    ``onlyoffice_connector.form_files_url``).

    Addresses are compared by their parts, not as text: ``https://forms.company.com.attacker.com/`` or
    ``https://forms.company.com@attacker.com/`` is not the mirror ``https://forms.company.com``.
    """
    try:
        parsed = urlparse(str(url or ""))
        origin = _origin(parsed)
    except ValueError:
        return False
    scheme, host, port = origin
    if scheme == "https" and host in FORM_FILES_HOSTS and port == 443:
        return True
    mirror = env and env["ir.config_parameter"].sudo().get_str(config_constants.FORM_FILES_URL, False)
    if not mirror:
        return False
    try:
        mirror_parsed = urlparse(mirror)
        mirror_origin = _origin(mirror_parsed)
    except ValueError:
        return False
    if mirror_origin[0] not in ("http", "https") or not mirror_origin[1] or origin != mirror_origin:
        return False
    # The path of the mirror is a folder: "/forms" does not take "/forms-evil", nor "/forms/../admin" in any form a
    # server reads as going up ("..;", a backslash).
    path = unquote(parsed.path)
    folder = mirror_parsed.path.rstrip("/") + "/"
    return path.startswith(folder) and not any(part.startswith("..") or "\\" in part for part in path.split("/"))


def download_form_file(url, env=None):
    """The content of a file of the ONLYOFFICE form gallery. Raises ValueError for any other address, an answer that
    is not the file, or a big file.

    The address comes from the browser: without this check the server would download any address for the user,
    an internal one included.
    """
    if not is_form_file_url(url, env):
        raise ValueError(f"Not a file of the form gallery: {url!r}")
    with requests.get(url, stream=True, timeout=30, allow_redirects=False) as response:
        # A redirect is not followed (it would leave the checked address), so it is not the file either.
        if response.status_code != 200:
            raise ValueError(f"Unexpected answer {response.status_code} from {url!r}")
        content = bytearray()
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            content.extend(chunk)
            if len(content) > FORM_FILE_MAX_SIZE:
                raise ValueError("The form file is too big")
    return bytes(content)
