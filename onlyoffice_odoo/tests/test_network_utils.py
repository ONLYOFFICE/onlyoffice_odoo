# Copyright (C) 2026 Ascensio System SIA
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl-3.0-standalone.html).

import socket
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.onlyoffice_odoo.utils import network_utils

GETADDRINFO = "odoo.addons.onlyoffice_odoo.utils.network_utils.socket.getaddrinfo"


def _addrinfo(*addresses):
    """Build a socket.getaddrinfo-like result for the given IP literals."""
    result = []
    for address in addresses:
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        sockaddr = (address, 0, 0, 0) if family == socket.AF_INET6 else (address, 0)
        result.append((family, socket.SOCK_STREAM, 6, "", sockaddr))
    return result


@tagged("post_install", "-at_install")
class TestNetworkUtils(TransactionCase):
    """Tests for network_utils module — local address detection and the odoo.conf switch."""

    # -- is_local_ip --

    def test_is_local_ip_loopback(self):
        """IPv4 and IPv6 loopback addresses are local."""
        self.assertTrue(network_utils.is_local_ip("127.0.0.1"))
        self.assertTrue(network_utils.is_local_ip("127.10.20.30"))
        self.assertTrue(network_utils.is_local_ip("::1"))

    def test_is_local_ip_private_ranges(self):
        """RFC 1918 and RFC 4193 private ranges are local."""
        self.assertTrue(network_utils.is_local_ip("10.0.0.5"))
        self.assertTrue(network_utils.is_local_ip("172.16.0.1"))
        self.assertTrue(network_utils.is_local_ip("172.31.255.254"))
        self.assertTrue(network_utils.is_local_ip("192.168.1.100"))
        self.assertTrue(network_utils.is_local_ip("fd12:3456:789a::1"))

    def test_is_local_ip_link_local_and_metadata(self):
        """Link-local ranges, including the cloud metadata address, are local."""
        self.assertTrue(network_utils.is_local_ip("169.254.169.254"))
        self.assertTrue(network_utils.is_local_ip("fe80::1"))

    def test_is_local_ip_unspecified_and_shared(self):
        """Unspecified addresses and the carrier-grade NAT range are local."""
        self.assertTrue(network_utils.is_local_ip("0.0.0.0"))
        self.assertTrue(network_utils.is_local_ip("::"))
        self.assertTrue(network_utils.is_local_ip("100.64.0.1"))

    def test_is_local_ip_ipv4_mapped_ipv6(self):
        """An IPv4-mapped IPv6 address is checked by its embedded IPv4 address."""
        self.assertTrue(network_utils.is_local_ip("::ffff:127.0.0.1"))
        self.assertTrue(network_utils.is_local_ip("::ffff:192.168.0.1"))
        self.assertFalse(network_utils.is_local_ip("::ffff:93.184.216.34"))

    def test_is_local_ip_public(self):
        """Public IPv4 and IPv6 addresses are not local."""
        self.assertFalse(network_utils.is_local_ip("93.184.216.34"))
        self.assertFalse(network_utils.is_local_ip("8.8.8.8"))
        self.assertFalse(network_utils.is_local_ip("2606:4700:4700::1111"))

    # -- is_local_host --

    def test_is_local_host_localhost_names(self):
        """'localhost' and names under .localhost are local without DNS resolution."""
        with patch(GETADDRINFO) as mock_resolve:
            self.assertTrue(network_utils.is_local_host("localhost"))
            self.assertTrue(network_utils.is_local_host("LOCALHOST"))
            self.assertTrue(network_utils.is_local_host("docs.localhost"))
            self.assertTrue(network_utils.is_local_host("localhost."))
            mock_resolve.assert_not_called()

    def test_is_local_host_empty(self):
        """An empty host cannot be checked and is treated as local."""
        self.assertTrue(network_utils.is_local_host(""))
        self.assertTrue(network_utils.is_local_host(None))

    def test_is_local_host_ip_literal_skips_dns(self):
        """IP literals are checked directly, without DNS resolution."""
        with patch(GETADDRINFO) as mock_resolve:
            self.assertTrue(network_utils.is_local_host("192.168.1.100"))
            self.assertFalse(network_utils.is_local_host("93.184.216.34"))
            mock_resolve.assert_not_called()

    def test_is_local_host_name_resolving_to_private_address(self):
        """A host name that resolves to a private address (Docker service name) is local."""
        with patch(GETADDRINFO, return_value=_addrinfo("172.18.0.2")):
            self.assertTrue(network_utils.is_local_host("documentserver"))

    def test_is_local_host_name_resolving_to_public_address(self):
        """A host name that resolves only to public addresses is not local."""
        with patch(GETADDRINFO, return_value=_addrinfo("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946")):
            self.assertFalse(network_utils.is_local_host("docs.example.com"))

    def test_is_local_host_name_with_mixed_addresses(self):
        """A host name is local when any of its resolved addresses is local (DNS rebinding guard)."""
        with patch(GETADDRINFO, return_value=_addrinfo("93.184.216.34", "10.0.0.7")):
            self.assertTrue(network_utils.is_local_host("docs.example.com"))

    def test_is_local_host_unresolvable_name(self):
        """A host name that does not resolve is not treated as local; the connection check reports it."""
        with (
            patch(GETADDRINFO, side_effect=socket.gaierror("Name or service not known")),
            self.assertLogs(network_utils._logger, level="WARNING") as logs,
        ):
            self.assertFalse(network_utils.is_local_host("no-such-host.invalid"))
        self.assertIn("cannot resolve host", logs.output[0])

    # -- is_local_url --

    def test_is_local_url_uses_host_only(self):
        """Only the URL host is checked; port, path and userinfo are ignored."""
        with patch(GETADDRINFO) as mock_resolve:
            self.assertTrue(network_utils.is_local_url("http://127.0.0.1:8080/"))
            self.assertTrue(network_utils.is_local_url("https://user:pass@[::1]:443/docs/"))
            self.assertFalse(network_utils.is_local_url("https://93.184.216.34/onlyoffice/"))
            mock_resolve.assert_not_called()

    def test_is_local_url_empty_or_without_host(self):
        """Empty URLs and URLs without a host are treated as local."""
        self.assertTrue(network_utils.is_local_url(""))
        self.assertTrue(network_utils.is_local_url(None))
        self.assertTrue(network_utils.is_local_url("http:///path"))

    def test_is_local_url_resolves_host_name(self):
        """A URL with a host name is resolved and checked."""
        with patch(GETADDRINFO, return_value=_addrinfo("172.18.0.2")):
            self.assertTrue(network_utils.is_local_url("http://documentserver/"))
        with patch(GETADDRINFO, return_value=_addrinfo("93.184.216.34")):
            self.assertFalse(network_utils.is_local_url("https://docs.example.com/"))

    # -- is_local_address_check_disabled --

    def test_check_enabled_by_default(self):
        """Without an [onlyoffice] section in odoo.conf the local address ban is active."""
        with patch.dict(network_utils.config.misc, {}, clear=True):
            self.assertFalse(network_utils.is_local_address_check_disabled())

    def test_check_disabled_by_bool_value(self):
        """Odoo parses 'True'/'true' in odoo.conf to a bool; the bool turns the ban off."""
        with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": True}}):
            self.assertTrue(network_utils.is_local_address_check_disabled())
        with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": False}}):
            self.assertFalse(network_utils.is_local_address_check_disabled())

    def test_check_disabled_by_string_values(self):
        """String values like '1', 'yes' or 'on' are accepted as truthy; unknown strings keep the ban."""
        for value in ("1", "yes", "on", "TRUE"):
            with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": value}}):
                self.assertTrue(network_utils.is_local_address_check_disabled(), value)
        for value in ("0", "no", "off", "maybe", ""):
            with patch.dict(network_utils.config.misc, {"onlyoffice": {"allow_local_address": value}}):
                self.assertFalse(network_utils.is_local_address_check_disabled(), value)

    def test_check_ignores_other_sections(self):
        """The switch is read only from the [onlyoffice] section."""
        with patch.dict(network_utils.config.misc, {"options": {"allow_local_address": True}}, clear=True):
            self.assertFalse(network_utils.is_local_address_check_disabled())
