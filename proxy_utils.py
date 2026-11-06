"""Shared helpers for scraping and checking proxies.

Everything in this module is pure (no network, no filesystem) so it can be
unit tested without any external service.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit

# Matches "1.2.3.4:8080" even when embedded in text such as
# "http://1.2.3.4:8080", "1.2.3.4:8080:United States" or HTML.
IP_PORT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3}):(\d{1,5})(?!\d)")

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")

# Proxy protocol -> URL scheme understood by httpx/httpcore.
# "https" proxies are plain HTTP proxies that support CONNECT, hence "http".
PROXY_SCHEMES = {
    "http": "http",
    "https": "http",
    "socks4": "socks4",
    "socks5": "socks5",
}


def normalize_address(ip: str, port: str | int) -> str | None:
    """Return a canonical ``ip:port`` string, or ``None`` if unusable.

    Only globally routable IPv4 addresses are accepted: private, loopback,
    link-local, reserved, multicast and documentation ranges are rejected so
    they never end up in the published lists.
    """
    try:
        address = ipaddress.IPv4Address(str(ip).strip())
    except ValueError:
        return None
    if (
        not address.is_global
        or address.is_private
        or address.is_multicast
        or address.is_reserved
        or address.is_loopback
        or address.is_link_local
        or address.is_unspecified
    ):
        return None
    try:
        port_number = int(str(port).strip())
    except ValueError:
        return None
    if not 0 < port_number < 65536:
        return None
    return f"{address}:{port_number}"


def parse_entry(entry: str) -> str | None:
    """Normalize one list entry (bare or ``scheme://`` prefixed)."""
    candidate = entry.strip().strip("\"'")
    candidate = _SCHEME_RE.sub("", candidate)
    candidate = candidate.strip("/")
    ip, separator, port = candidate.rpartition(":")
    if not separator:
        return None
    return normalize_address(ip, port)


def parse_ip_port_text(text: str) -> list[str]:
    """Extract every ``ip:port`` pair from a free-form text body."""
    proxies: list[str] = []
    for ip, port in IP_PORT_RE.findall(text):
        normalized = normalize_address(ip, port)
        if normalized:
            proxies.append(normalized)
    return proxies


def sort_key(address: str) -> tuple[int, int]:
    """Deterministic numeric ordering (keeps git diffs stable)."""
    ip, _, port = address.partition(":")
    return int(ipaddress.IPv4Address(ip)), int(port)


def site_url(site: str, proxy_method: str = "http") -> str:
    """Turn ``google.com`` into a URL suitable for the given proxy type."""
    site = site.strip()
    if "://" in site:
        return site
    scheme = "http" if proxy_method == "http" else "https"
    return f"{scheme}://{site}"


def site_slug(url: str) -> str:
    """``https://www.google.com/`` -> ``google`` (used for output filenames)."""
    host = urlsplit(url).hostname or url
    host = host.removeprefix("www.")
    return host.split(".")[0]
