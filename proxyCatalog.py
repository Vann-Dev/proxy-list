#!/usr/bin/env python3
"""Combine checked proxy results into one catalog and a stats file.

Reads the ``proxies.json`` files written by ``proxyChecker.py --json-out``,
enriches every address with offline country/ASN data and writes:

  proxies/proxies.json  - one entry per unique proxy with protocols and latency
  proxies/stats.json    - per-protocol, per-site and per-country counts
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from proxy_anonymity import ANONYMOUS, ELITE, TRANSPARENT, UNKNOWN, weakest
from proxy_geo import DEFAULT_CACHE, Ip2Asn, load_dataset
from proxy_utils import normalize_address, sort_key

SCHEMA_VERSION = 1


@dataclass
class Entry:
    address: str
    protocols: set[str] = field(default_factory=set)
    sites: dict[str, int] = field(default_factory=dict)  # slug -> latency in ms
    country: str | None = None
    asn: str | None = None
    as_name: str | None = None
    anonymity: str | None = None


def discover_results(proxies_dir: Path) -> list[Path]:
    return sorted(proxies_dir.glob("*-tested/proxies.json"))


def merge_results(paths: list[Path]) -> tuple[dict[str, Entry], dict[str, dict]]:
    entries: dict[str, Entry] = {}
    summaries: dict[str, dict] = {}
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"Skipping {path}: {exc}", file=sys.stderr)
            continue
        protocol = payload.get("protocol") or path.parent.name.removesuffix("-tested")
        summaries[protocol] = {
            "generated_at": payload.get("generated_at"),
            "tested": payload.get("input_count"),
            "sites": {site.get("name"): site.get("alive", 0) for site in payload.get("sites", [])},
        }
        for item in payload.get("proxies", []):
            address = item.get("address")
            if not address:
                continue
            ip, _, port = address.partition(":")
            if normalize_address(ip, port) is None:
                continue
            entry = entries.get(address)
            if entry is None:
                entry = entries[address] = Entry(address=address)
            entry.protocols.add(protocol)
            reported_anonymity = item.get("anonymity")
            if reported_anonymity:
                # Different protocols can expose different amounts of information;
                # publish the least private result across all of them.
                entry.anonymity = weakest([entry.anonymity, reported_anonymity])
            for slug, latency in item.get("sites", {}).items():
                value = int(latency)
                entry.sites[slug] = min(value, entry.sites.get(slug, value))
    return entries, summaries


def build_catalog(
    entries: dict[str, Entry],
    summaries: dict[str, dict],
    geo: Ip2Asn | None,
    generated_at: str | None = None,
) -> tuple[dict, dict]:
    generated_at = generated_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    proxies = []
    for address in sorted(entries, key=sort_key):
        entry = entries[address]
        ip, _, port = address.partition(":")
        if geo is not None:
            entry.country, entry.asn, entry.as_name = geo.lookup(ip)
        proxies.append(
            {
                "address": address,
                "ip": ip,
                "port": int(port),
                "protocols": sorted(entry.protocols),
                "country": entry.country,
                "asn": entry.asn,
                "as_name": entry.as_name,
                "anonymity": entry.anonymity,
                "sites": dict(sorted(entry.sites.items())),
            }
        )

    catalog = {
        "schema": SCHEMA_VERSION,
        "generated_at": generated_at,
        "geo": (
            {"source": "iptoasn.com", "updated_at": geo.updated_at}
            if geo is not None
            else None
        ),
        "count": len(proxies),
        "proxies": proxies,
    }

    protocol_stats: dict[str, dict] = {}
    site_protocols: dict[str, dict[str, int]] = {}
    for protocol, summary in summaries.items():
        alive = sum(1 for entry in entries.values() if protocol in entry.protocols)
        protocol_stats[protocol] = {
            "tested": summary.get("tested"),
            "alive": alive,
            "checked_at": summary.get("generated_at"),
            "sites": dict(sorted(summary.get("sites", {}).items())),
        }
        for slug, count in summary.get("sites", {}).items():
            site_protocols.setdefault(slug, {})[protocol] = count

    sites = {
        slug: {"total": sum(by_protocol.values()), "by_protocol": dict(sorted(by_protocol.items()))}
        for slug, by_protocol in sorted(site_protocols.items())
    }
    countries = Counter(entry.country for entry in entries.values() if entry.country)
    anonymities = Counter(entry.anonymity for entry in entries.values() if entry.anonymity)
    anonymity_stats = {
        name: anonymities[name]
        for name in (TRANSPARENT, ANONYMOUS, ELITE, UNKNOWN)
        if anonymities[name]
    }

    stats = {
        "schema": SCHEMA_VERSION,
        "generated_at": generated_at,
        "total_proxies": len(proxies),
        "protocols": protocol_stats,
        "sites": sites,
        "countries": dict(sorted(countries.items(), key=lambda item: (-item[1], item[0]))),
        "anonymity": anonymity_stats or None,
    }
    return catalog, stats


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build proxies.json and stats.json from checked results.")
    parser.add_argument("--proxies-dir", default="proxies", help="Directory containing *-tested/proxies.json")
    parser.add_argument("--output", default="proxies/proxies.json", help="Combined catalog output")
    parser.add_argument("--stats", default="proxies/stats.json", help="Stats output")
    parser.add_argument("--geo-cache", default=str(DEFAULT_CACHE), help="ip2asn dataset cache")
    parser.add_argument("--no-geo", action="store_true", help="Skip country/ASN enrichment")
    parser.add_argument("--refresh-geo", action="store_true", help="Re-download the ip2asn dataset")
    args = parser.parse_args()

    proxies_dir = Path(args.proxies_dir)
    paths = discover_results(proxies_dir)
    if not paths:
        print(f"No checked results found under {proxies_dir}/*-tested/proxies.json", file=sys.stderr)
        return 1

    entries, summaries = merge_results(paths)
    if not entries:
        print("Checked results contained no working proxies", file=sys.stderr)
        return 2

    geo = None
    if not args.no_geo:
        print("Loading country/ASN database...")
        geo = load_dataset(Path(args.geo_cache), refresh=args.refresh_geo)

    catalog, stats = build_catalog(entries, summaries, geo)
    write_json(Path(args.output), catalog)
    write_json(Path(args.stats), stats)
    print(
        f"Wrote {catalog['count']} unique proxies to {args.output} "
        f"and stats to {args.stats} ({len(summaries)} protocol result file(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
