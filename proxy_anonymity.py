#!/usr/bin/env python3
"""Classify how much a working proxy hides the client from the target site.

A proxy is asked to load an echo endpoint that returns the request headers it
received. The result is one of:

  transparent - the target can see your real IP (leaked through a header)
  anonymous   - the proxy reveals itself, but not your IP
  elite       - neither the proxy nor your IP is visible
  unknown     - the echo request failed or the payload was unusable

The classification is a heuristic: only headers are inspected, so a proxy that
leaks the client IP in some other way is still reported as anonymous.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

DEFAULT_ECHO_URLS = (
    "https://httpbin.org/headers",
    "https://httpbingo.org/headers",
)

TRANSPARENT = "transparent"
ANONYMOUS = "anonymous"
ELITE = "elite"
UNKNOWN = "unknown"

RANK = {TRANSPARENT: 0, ANONYMOUS: 1, ELITE: 2}

# Headers that show the request went through a proxy (or forward the client IP).
PROXY_HEADERS = frozenset(
    {
        "client-ip",
        "forwarded",
        "proxy-connection",
        "via",
        "x-bluecoat-via",
        "x-cache",
        "x-cache-info",
        "x-client-ip",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "x-originating-ip",
        "x-proxy-id",
        "x-real-ip",
        "x-remote-addr",
        "x-remote-ip",
        "x-via",
    }
)

_SPLIT = re.compile(r"[\s,;=]+")


def echo_headers(payload: object) -> dict[str, str]:
    """Return the headers of an httpbin/httpbingo-style echo payload."""
    if not isinstance(payload, dict):
        return {}
    headers = payload.get("headers")
    if not isinstance(headers, dict):
        return {}
    return {str(name): str(value) for name, value in headers.items() if value is not None}


def echo_ip(payload: object) -> str | None:
    """Return the origin IP from an httpbin/httpbingo-style /ip payload."""
    if not isinstance(payload, dict):
        return None
    for key in ("origin", "ip"):
        value = payload.get(key)
        if isinstance(value, str):
            first = value.split(",")[0].strip()
            if first:
                return first
    return None


def ip_url(echo_url: str) -> str:
    """Derive the /ip endpoint from an echo endpoint on the same host."""
    parts = urlsplit(echo_url)
    return urlunsplit((parts.scheme, parts.netloc, "/ip", "", ""))


def parse_echo_urls(value: str | None) -> list[str]:
    """Return the configured comma-separated endpoints, or the defaults."""
    if value:
        urls = [part.strip() for part in value.split(",") if part.strip()]
        if urls:
            return urls
    return list(DEFAULT_ECHO_URLS)


def _contains_ip(value: str, ip: str) -> bool:
    return ip in _SPLIT.split(value)


def classify(headers: dict[str, str], client_ip: str | None = None) -> str:
    """Classify a proxy from the headers the echo endpoint received."""
    lowered = {str(name).lower(): str(value) for name, value in headers.items()}
    revealing = {name: value for name, value in lowered.items() if name in PROXY_HEADERS}
    if not revealing:
        return ELITE
    if client_ip and any(_contains_ip(value, client_ip) for value in revealing.values()):
        return TRANSPARENT
    return ANONYMOUS


def weakest(values) -> str:
    """Combine per-protocol classifications, keeping the least private one."""
    known = [value for value in values if value in RANK]
    if not known:
        return UNKNOWN
    return min(known, key=RANK.__getitem__)
