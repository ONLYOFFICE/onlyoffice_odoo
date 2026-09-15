# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import ipaddress
import logging
import socket
from urllib.parse import urlparse

from odoo.tools import config
from odoo.tools.misc import str2bool

_logger = logging.getLogger(__name__)

# odoo.conf switch, not a UI checkbox: the admin who sets the Document Server address could flip a checkbox too.
#   [onlyoffice]
#   allow_local_address = True
CONFIG_SECTION = "onlyoffice"
CONFIG_ALLOW_LOCAL_ADDRESS = "allow_local_address"

LOCAL_HOSTNAMES = ("localhost",)

# 100.64.0.0/10 (carrier-grade NAT) is not flagged private by ipaddress on every Python version.
EXTRA_LOCAL_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"),)


def is_local_address_check_disabled():
    """Return True when odoo.conf explicitly allows local Document Server addresses."""
    value = config.misc.get(CONFIG_SECTION, {}).get(CONFIG_ALLOW_LOCAL_ADDRESS)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str2bool(str(value), default=False)


def is_local_ip(ip):
    """Return True for loopback, private, link-local, reserved, multicast and unspecified addresses."""
    if isinstance(ip, str):
        ip = ipaddress.ip_address(ip)
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True
    return any(ip in network for network in EXTRA_LOCAL_NETWORKS if network.version == ip.version)


def is_local_host(host):
    """Return True when the host name or IP literal points to the local or a private network.

    Host names are resolved and every returned address is checked, so a public name that resolves
    to a private address is rejected too. A name that does not resolve is not treated as local:
    the connection check that follows fails on its own and logs the reason.
    """
    if not host:
        return True

    host = host.strip().lower().rstrip(".")
    if host in LOCAL_HOSTNAMES or host.endswith(".localhost"):
        return True

    ip = _parse_ip(host)
    if ip is not None:
        return is_local_ip(ip)

    try:
        address_infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        _logger.warning("is_local_host - cannot resolve host %s: %s", host, e)
        return False

    resolved_ips = (_parse_ip(address_info[4][0]) for address_info in address_infos)
    return any(is_local_ip(ip) for ip in resolved_ips if ip is not None)


def _parse_ip(value):
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def is_local_url(url):
    """Return True when the URL host points to the local or a private network."""
    if not url:
        return True
    return is_local_host(urlparse(url).hostname)
