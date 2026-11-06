"""Offline country/ASN lookup using the free iptoasn.com dataset.

The dataset is a gzipped TSV with one line per IPv4 range::

    start_u32  end_u32  asn  country  as_name

It is used to enrich published proxies with ``country`` and ``asn`` without
calling an external API for every address. See https://iptoasn.com for the
data source and terms.
"""

from __future__ import annotations

import bisect
import gzip
import ipaddress
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import IO

import httpx

DOWNLOAD_URL = "https://iptoasn.com/data/ip2asn-v4-u32.tsv.gz"
DEFAULT_CACHE = Path(__file__).with_name(".cache") / "ip2asn-v4-u32.tsv.gz"


class Ip2Asn:
    """Sorted IPv4 range table with a binary-search lookup."""

    def __init__(
        self,
        starts: list[int],
        ends: list[int],
        countries: list[str | None],
        asns: list[str | None],
        names: list[str | None],
        updated_at: str | None = None,
    ) -> None:
        self.starts = starts
        self.ends = ends
        self.countries = countries
        self.asns = asns
        self.names = names
        self.updated_at = updated_at

    def lookup(self, address: str) -> tuple[str | None, str | None, str | None]:
        """Return ``(country, asn, as_name)`` for an IPv4 address."""
        try:
            value = int(ipaddress.IPv4Address(address))
        except ValueError:
            return None, None, None
        index = bisect.bisect_right(self.starts, value) - 1
        if index < 0 or value > self.ends[index]:
            return None, None, None
        return self.countries[index], self.asns[index], self.names[index]


def _clean_country(value: str) -> str | None:
    value = value.strip()
    return None if value in ("", "None", "-") else value


def _clean_asn(value: str) -> str | None:
    value = value.strip()
    if value in ("", "0", "None", "-"):
        return None
    return value if value.upper().startswith("AS") else f"AS{value}"


def parse_tsv(lines: Iterable[str], updated_at: str | None = None) -> Ip2Asn:
    rows: list[tuple[int, int, str | None, str | None, str | None]] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        country = _clean_country(parts[3])
        asn = _clean_asn(parts[2])
        name = None if asn is None else parts[4].strip() or None
        rows.append((start, end, country, asn, name))
    rows.sort(key=lambda row: row[0])
    return Ip2Asn(
        starts=[row[0] for row in rows],
        ends=[row[1] for row in rows],
        countries=[row[2] for row in rows],
        asns=[row[3] for row in rows],
        names=[row[4] for row in rows],
        updated_at=updated_at,
    )


def _open_dataset(path: Path) -> IO[str]:
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def download_dataset(
    destination: Path = DEFAULT_CACHE,
    url: str = DOWNLOAD_URL,
    timeout: float = 120.0,
) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with httpx.stream("GET", url, follow_redirects=True, timeout=timeout) as response:
        response.raise_for_status()
        with temporary.open("wb") as handle:
            for chunk in response.iter_bytes():
                handle.write(chunk)
    os.replace(temporary, destination)
    return destination


def load_dataset(path: Path = DEFAULT_CACHE, refresh: bool = False) -> Ip2Asn:
    """Load the local dataset, downloading it first when needed."""
    path = Path(path)
    if refresh or not path.exists():
        download_dataset(path)
    updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(path.stat().st_mtime))
    with _open_dataset(path) as handle:
        return parse_tsv(handle, updated_at=updated_at)
