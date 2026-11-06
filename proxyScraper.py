#!/usr/bin/env python3
"""Scrape public proxy lists from several sources.

Each source declares the output category it feeds (``http``, ``https``,
``socks4`` or ``socks5``) and how its response is parsed. Results are
validated, de-duplicated, sorted and written atomically so a failed scrape
never truncates a previously good list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from proxy_utils import normalize_address, parse_ip_port_text, sort_key

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 30.0
DEFAULT_RETRIES = 1
DEFAULT_CONCURRENCY = 16
# Refuse to overwrite a list with something suspiciously small (scrape outage).
MIN_PROXIES = 10


@dataclass(frozen=True)
class Source:
    name: str
    url: str
    category: str
    parser: str = "text"


# ---------------------------------------------------------------------------
# Sources
#
# Kept in one place so it is easy to add or retire a source. GitHub raw lists
# are generally the freshest; the legacy HTML/API endpoints are kept as extra
# coverage but are no longer the only providers.
# ---------------------------------------------------------------------------

SOURCES: tuple[Source, ...] = (
    # --- HTTP -------------------------------------------------------------
    Source("thespeedx-http", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt", "http"),
    Source("monosans-http", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt", "http"),
    Source("proxifly-http", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt", "http"),
    Source("proxyscrape-http", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=http&proxy_format=ipport&format=text&timeout=10000", "http"),
    Source("shiftytr-http", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt", "http"),
    Source("clarketm-http", "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt", "http"),
    Source("mmpx12-http", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt", "http"),
    Source("vakhov-http", "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt", "http"),
    Source("sunny9577-http", "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt", "http"),
    Source("aliilapro-http", "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt", "http"),
    Source("zloi-http", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt", "http"),
    Source("spysme-http", "https://spys.me/proxy.txt", "http"),
    Source("free-proxy-list-http", "https://free-proxy-list.net", "http", parser="html_table"),
    Source("us-proxy-http", "https://www.us-proxy.org", "http", parser="html_table"),
    Source("geonode-http", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=http", "http", parser="geonode"),
    # --- HTTPS ------------------------------------------------------------
    Source("proxifly-https", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/https/data.txt", "https"),
    Source("proxyscrape-https", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=https&proxy_format=ipport&format=text&timeout=10000", "https"),
    Source("shiftytr-https", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/https.txt", "https"),
    Source("roosterkid-https", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt", "https"),
    Source("sslproxies-https", "https://www.sslproxies.org", "https", parser="html_table"),
    Source("free-proxy-list-https", "https://free-proxy-list.net", "https", parser="html_table"),
    Source("geonode-https", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=https", "https", parser="geonode"),
    # --- SOCKS4 -----------------------------------------------------------
    Source("thespeedx-socks4", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt", "socks4"),
    Source("monosans-socks4", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt", "socks4"),
    Source("proxifly-socks4", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks4/data.txt", "socks4"),
    Source("shiftytr-socks4", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt", "socks4"),
    Source("roosterkid-socks4", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS4_RAW.txt", "socks4"),
    Source("aliilapro-socks4", "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt", "socks4"),
    Source("zloi-socks4", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks4.txt", "socks4"),
    Source("proxyscrape-socks4", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks4&proxy_format=ipport&format=text&timeout=10000", "socks4"),
    Source("geonode-socks4", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks4", "socks4", parser="geonode"),
    # --- SOCKS5 -----------------------------------------------------------
    Source("thespeedx-socks5", "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt", "socks5"),
    Source("monosans-socks5", "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt", "socks5"),
    Source("proxifly-socks5", "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/socks5/data.txt", "socks5"),
    Source("shiftytr-socks5", "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt", "socks5"),
    Source("mmpx12-socks5", "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt", "socks5"),
    Source("hookzof-socks5", "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt", "socks5"),
    Source("aliilapro-socks5", "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt", "socks5"),
    Source("zloi-socks5", "https://raw.githubusercontent.com/zloi-user/hideip.me/main/socks5.txt", "socks5"),
    Source("vakhov-socks5", "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt", "socks5"),
    Source("roosterkid-socks5", "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt", "socks5"),
    Source("proxyscrape-socks5", "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&protocol=socks5&proxy_format=ipport&format=text&timeout=10000", "socks5"),
    Source("geonode-socks5", "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks5", "socks5", parser="geonode"),
)


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def parse_geonode(body: str) -> list[str]:
    """Geonode returns JSON with separate ``ip``/``port`` fields."""
    proxies: list[str] = []
    payload = json.loads(body)
    for item in payload.get("data", []):
        normalized = normalize_address(item.get("ip", ""), item.get("port", ""))
        if normalized:
            proxies.append(normalized)
    return proxies


def parse_html_table(body: str, category: str) -> list[str]:
    """Parse the free-proxy-list family of tables.

    For the ``https`` category only rows whose ``Https`` column says ``yes``
    are kept.
    """
    soup = BeautifulSoup(body, "html.parser")
    table = soup.find("table", id="proxylisttable")
    if table is None:
        table = soup.find("table", class_="table-striped")
    if table is None:
        return []

    headers = [cell.get_text(strip=True).lower() for cell in table.find_all("th")]
    https_column = headers.index("https") if "https" in headers else None

    proxies: list[str] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        if (
            category == "https"
            and https_column is not None
            and len(cells) > https_column
            and cells[https_column].get_text(strip=True).lower() != "yes"
        ):
            continue
        normalized = normalize_address(cells[0].get_text(strip=True), cells[1].get_text(strip=True))
        if normalized:
            proxies.append(normalized)
    return proxies


def parse_source_body(source: Source, body: str) -> list[str]:
    if source.parser == "geonode":
        return parse_geonode(body)
    if source.parser == "html_table":
        return parse_html_table(body, source.category)
    return parse_ip_port_text(body)


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------


def verbose_print(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


async def fetch_source(
    client: httpx.AsyncClient,
    source: Source,
    timeout: float,
    retries: int,
    semaphore: asyncio.Semaphore,
) -> tuple[Source, list[str], str | None]:
    error: str | None = None
    for attempt in range(retries + 1):
        try:
            async with semaphore:
                response = await client.get(source.url, timeout=timeout)
            response.raise_for_status()
            return source, parse_source_body(source, response.text), None
        except Exception as exc:  # noqa: BLE001 - report and continue with others
            error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                await asyncio.sleep(1 + attempt)
    return source, [], error


def write_atomic(path: Path, proxies: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(proxies) + ("\n" if proxies else ""), encoding="utf-8")
    os.replace(temporary, path)


async def scrape(
    method: str,
    output: str,
    verbose: bool,
    timeout: float,
    retries: int,
    concurrency: int,
    report: str | None,
) -> int:
    categories = ["socks4", "socks5"] if method == "socks" else [method]
    selected = [source for source in SOURCES if source.category in categories]
    if not selected:
        raise ValueError(f"Unsupported proxy type: {method}")

    started = time.time()
    print(f"Scraping {len(selected)} sources for {', '.join(categories)}...")

    semaphore = asyncio.Semaphore(concurrency)
    client = httpx.AsyncClient(
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
        limits=httpx.Limits(max_connections=concurrency),
    )
    try:
        results = await asyncio.gather(
            *(fetch_source(client, source, timeout, retries, semaphore) for source in selected)
        )
    finally:
        await client.aclose()

    collected: list[str] = []
    report_sources: list[dict[str, object]] = []
    failures = 0
    for source, proxies, error in results:
        collected.extend(proxies)
        if error:
            failures += 1
            print(f"  [FAIL] {source.name}: {error}", file=sys.stderr)
        verbose_print(verbose, f"  {source.name}: {len(proxies)} proxies")
        report_sources.append(
            {"name": source.name, "url": source.url, "category": source.category, "count": len(proxies), "error": error}
        )

    unique = sorted(set(collected), key=sort_key)

    if len(unique) < MIN_PROXIES:
        print(
            f"Only {len(unique)} proxies collected (minimum {MIN_PROXIES}); "
            f"keeping the existing {output} untouched.",
            file=sys.stderr,
        )
        return 2

    destination = Path(output)
    write_atomic(destination, unique)

    duration = round(time.time() - started, 1)
    print(f"Wrote {len(unique)} unique proxies to {destination} in {duration}s ({failures} source(s) failed)")

    if report:
        report_path = Path(report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(
                {
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "method": method,
                    "output": str(destination),
                    "total_unique": len(unique),
                    "duration_seconds": duration,
                    "sources": report_sources,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scrape public proxy lists and save one ip:port per line."
    )
    parser.add_argument(
        "-p",
        "--proxy",
        required=True,
        choices=["http", "https", "socks", "socks4", "socks5"],
        help="Proxy type to scrape (socks = socks4 + socks5)",
    )
    parser.add_argument("-o", "--output", default="output.txt", help="Output .txt file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show per-source details")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Request timeout in seconds")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per source")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Parallel source fetches")
    parser.add_argument("--report", help="Write a JSON report of each source to this path")
    args = parser.parse_args()

    return asyncio.run(
        scrape(
            method=args.proxy,
            output=args.output,
            verbose=args.verbose,
            timeout=args.timeout,
            retries=args.retries,
            concurrency=args.concurrency,
            report=args.report,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
