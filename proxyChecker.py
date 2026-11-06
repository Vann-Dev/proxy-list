#!/usr/bin/env python3
"""Check proxies against one or more sites and keep the ones that work.

A proxy is checked once per site, in the same session, so a single proxy that
works for several domains is only discovered once. Checks run concurrently
with a bounded semaphore instead of one thread per proxy.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import socket
import ssl
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from proxy_utils import PROXY_SCHEMES, parse_entry, site_slug, site_url, sort_key

USER_AGENTS_PATH = Path(__file__).with_name("user_agents.txt")
FALLBACK_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 10.0
DEFAULT_CONCURRENCY = 200
DEFAULT_RETRIES = 1
# Never replace existing results with an empty list because of an outage.
MIN_INPUT_FOR_GUARD = 10

# Errors that mean the proxy itself is unusable; no point trying other sites.
FATAL_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ProxyError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def load_user_agents() -> list[str]:
    try:
        agents = [line.strip() for line in USER_AGENTS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        agents = []
    return agents or [FALLBACK_USER_AGENT]


@dataclass
class ProxyResult:
    proxy: str
    alive: dict[str, float] = field(default_factory=dict)  # site url -> latency
    errors: dict[str, str] = field(default_factory=dict)
    checked: int = 0


def verbose_print(verbose: bool, message: str) -> None:
    if verbose:
        print(message)


async def try_site(
    client: httpx.AsyncClient,
    url: str,
    timeout: float,
    retries: int,
) -> tuple[bool, float, str | None, bool]:
    """Return (ok, latency, error, fatal)."""
    error: str | None = None
    fatal = False
    started = time.perf_counter()
    for attempt in range(retries + 1):
        started = time.perf_counter()
        try:
            response = await client.get(url, timeout=timeout)
            latency = time.perf_counter() - started
            if response.status_code < 400:
                return True, latency, None, False
            # The proxy works, the site just answered with an error status.
            return False, latency, f"HTTP {response.status_code}", False
        except Exception as exc:  # noqa: BLE001 - classified below
            latency = time.perf_counter() - started
            error = f"{type(exc).__name__}: {exc}"
            fatal = isinstance(exc, FATAL_ERRORS)
            if attempt < retries:
                await asyncio.sleep(0.25 * (attempt + 1))
    return False, 0.0, error, fatal


SOCKS4_CONNECT = 1
SOCKS4_GRANTED = 90


def socks4_connect_request(ip: str, port: int) -> bytes:
    """Build a SOCKS4 CONNECT request for an already-resolved IPv4 address."""
    return struct.pack("!BBH", 4, SOCKS4_CONNECT, port) + socket.inet_aton(ip) + b"\x00"


def parse_status_line(line: bytes) -> int:
    """Return the status code of an HTTP/1.x status line, or 0 if malformed."""
    parts = line.split()
    if len(parts) < 2 or not parts[0].startswith(b"HTTP/"):
        return 0
    try:
        return int(parts[1])
    except ValueError:
        return 0


async def socks4_request(
    proxy: str,
    url: str,
    timeout: float,
    user_agent: str,
    verify: bool,
) -> tuple[bool, float, str | None]:
    """HTTP(S) GET through a SOCKS4 proxy using only the standard library.

    httpcore (and therefore httpx) only supports SOCKS5, so SOCKS4 gets a
    minimal implementation here. The target hostname is resolved locally
    because SOCKS4 has no remote-DNS extension.
    """
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"invalid site URL: {url}")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"

    proxy_host, separator, proxy_port = proxy.rpartition(":")
    if not separator or not proxy_host:
        raise ValueError(f"invalid proxy address: {proxy}")

    loop = asyncio.get_running_loop()
    addresses = await loop.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
    target_ip = addresses[0][4][0]

    started = time.perf_counter()
    reader, writer = await asyncio.open_connection(proxy_host, int(proxy_port))
    try:
        writer.write(socks4_connect_request(target_ip, port))
        await writer.drain()
        reply = await reader.readexactly(8)
        if reply[0] != 0 or reply[1] != SOCKS4_GRANTED:
            raise ConnectionError(f"SOCKS4 proxy rejected the connection (code {reply[1]})")

        if parsed.scheme == "https":
            context = ssl.create_default_context()
            if not verify:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            await writer.start_tls(context, server_hostname=host)

        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"User-Agent: {user_agent}\r\n"
            "Accept: */*\r\n"
            "Connection: close\r\n\r\n"
        )
        writer.write(request.encode("ascii", "ignore"))
        await writer.drain()
        status_code = parse_status_line(await reader.readline())
        latency = time.perf_counter() - started
        if status_code == 0:
            raise ConnectionError("SOCKS4 tunnel returned an invalid HTTP response")
        if status_code < 400:
            return True, latency, None
        return False, latency, f"HTTP {status_code}"
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001, S110 - connection may already be broken
            pass


async def try_site_socks4(
    proxy: str,
    url: str,
    timeout: float,
    retries: int,
    user_agent: str,
    verify: bool,
) -> tuple[bool, float, str | None, bool]:
    """Return (ok, latency, error, fatal) for one site over SOCKS4."""
    error: str | None = None
    fatal = False
    for attempt in range(retries + 1):
        try:
            ok, latency, error = await asyncio.wait_for(
                socks4_request(proxy, url, timeout, user_agent, verify), timeout=timeout
            )
            return ok, latency, error, False
        except TimeoutError:
            error = f"timeout after {timeout:.0f}s"
            fatal = True
        except Exception as exc:  # noqa: BLE001 - classified as fatal below
            error = f"{type(exc).__name__}: {exc}"
            fatal = True
        if attempt < retries:
            await asyncio.sleep(0.25 * (attempt + 1))
    return False, 0.0, error, fatal


def record_result(
    result: ProxyResult,
    sites: list[str],
    index: int,
    ok: bool,
    latency: float,
    error: str | None,
    fatal: bool,
    short_circuit: bool,
) -> bool:
    """Record one site result; return True when the remaining sites are skipped."""
    url = sites[index]
    result.checked += 1
    if ok:
        result.alive[url] = latency
        return False
    result.errors[url] = error or "unknown error"
    if fatal and short_circuit:
        for skipped in sites[index + 1 :]:
            result.errors[skipped] = "skipped after fatal proxy error"
            result.checked += 1
        return True
    return False


async def check_proxy(
    proxy: str,
    method: str,
    sites: list[str],
    semaphore: asyncio.Semaphore,
    timeout: float,
    retries: int,
    user_agents: list[str],
    random_user_agent: bool,
    verify: bool,
    short_circuit: bool,
) -> ProxyResult:
    result = ProxyResult(proxy=proxy)
    user_agent = random.choice(user_agents) if random_user_agent else user_agents[0]
    scheme = PROXY_SCHEMES[method]

    async with semaphore:
        if method == "socks4":
            for index, url in enumerate(sites):
                hard_timeout = timeout * (retries + 1) * 2 + 3
                try:
                    ok, latency, error, fatal = await asyncio.wait_for(
                        try_site_socks4(proxy, url, timeout, retries, user_agent, verify),
                        timeout=hard_timeout,
                    )
                except TimeoutError:
                    ok, latency, error, fatal = False, 0.0, f"timeout after {hard_timeout:.0f}s", True
                if record_result(result, sites, index, ok, latency, error, fatal, short_circuit):
                    break
            return result

        try:
            client = httpx.AsyncClient(
                proxy=f"{scheme}://{proxy}",
                timeout=httpx.Timeout(timeout, connect=min(timeout, 10.0)),
                verify=verify,
                follow_redirects=True,
                headers={"User-Agent": user_agent},
                limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            )
        except Exception as exc:  # noqa: BLE001 - e.g. missing socks extra
            result.errors = {url: f"{type(exc).__name__}: {exc}" for url in sites}
            return result

        async with client:
            for index, url in enumerate(sites):
                # httpcore's SOCKS handshake does not always honour the httpx
                # timeout, so enforce a hard deadline per site as well.
                hard_timeout = timeout * (retries + 1) * 2 + 3
                try:
                    ok, latency, error, fatal = await asyncio.wait_for(
                        try_site(client, url, timeout, retries), timeout=hard_timeout
                    )
                except TimeoutError:
                    ok, latency, error, fatal = False, 0.0, f"timeout after {hard_timeout:.0f}s", True
                if record_result(result, sites, index, ok, latency, error, fatal, short_circuit):
                    break
    return result


def load_proxies(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    seen: set[str] = set()
    proxies: list[str] = []
    for line in lines:
        address = parse_entry(line)
        if address and address not in seen:
            seen.add(address)
            proxies.append(address)
    return proxies


def write_lines(path: Path, addresses: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text("\n".join(addresses) + ("\n" if addresses else ""), encoding="utf-8")
    temporary.replace(path)


def unique_slugs(urls: list[str]) -> dict[str, str]:
    slugs: dict[str, str] = {}
    used: set[str] = set()
    for url in urls:
        slug = site_slug(url)
        if slug in used:
            slug = url.split("://", 1)[-1].split("/", 1)[0].replace(".", "_")
        used.add(slug)
        slugs[url] = slug
    return slugs


def write_results(
    results: list[ProxyResult],
    sites: list[str],
    slugs: dict[str, str],
    output: str | None,
    output_dir: str | None,
) -> None:
    for url in sites:
        alive = sorted(
            ((result.proxy, result.alive[url]) for result in results if url in result.alive),
            key=lambda item: (item[1], sort_key(item[0])),
        )
        addresses = [address for address, _ in alive]
        if output_dir:
            write_lines(Path(output_dir) / f"{slugs[url]}.txt", addresses)
        elif output:
            write_lines(Path(output), addresses)
        print(f"  {url}: {len(addresses)} working proxies")


def write_json_results(
    path: str,
    method: str,
    input_path: str,
    input_count: int,
    results: list[ProxyResult],
    sites: list[str],
    slugs: dict[str, str],
    timeout: float,
    duration: float,
) -> None:
    """Write per-proxy results consumed by proxyCatalog.py."""
    proxies = []
    for result in sorted(results, key=lambda item: sort_key(item.proxy)):
        if not result.alive:
            continue
        ip, _, port = result.proxy.partition(":")
        proxies.append(
            {
                "address": result.proxy,
                "ip": ip,
                "port": int(port),
                "sites": {slugs[url]: round(latency * 1000) for url, latency in result.alive.items()},
            }
        )
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol": method,
        "input": input_path,
        "input_count": input_count,
        "timeout_seconds": timeout,
        "duration_seconds": round(duration, 1),
        "sites": [
            {
                "name": slugs[url],
                "url": url,
                "alive": sum(1 for result in results if url in result.alive),
            }
            for url in sites
        ],
        "count": len(proxies),
        "proxies": proxies,
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)


def write_report(
    path: str,
    method: str,
    input_path: str,
    input_count: int,
    results: list[ProxyResult],
    sites: list[str],
    slugs: dict[str, str],
    timeout: float,
    concurrency: int,
    duration: float,
) -> None:
    site_reports = []
    for url in sites:
        latencies = sorted(result.alive[url] for result in results if url in result.alive)
        site_reports.append(
            {
                "name": slugs[url],
                "url": url,
                "alive": len(latencies),
                "latency_ms": {
                    "min": round(latencies[0] * 1000, 1) if latencies else None,
                    "avg": round(sum(latencies) / len(latencies) * 1000, 1) if latencies else None,
                },
            }
        )
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "method": method,
        "input": input_path,
        "input_count": input_count,
        "checked": sum(result.checked for result in results),
        "timeout_seconds": timeout,
        "concurrency": concurrency,
        "duration_seconds": round(duration, 1),
        "sites": site_reports,
    }
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


async def check(
    file: str,
    output: str,
    output_dir: str | None,
    timeout: float,
    method: str,
    sites: list[str],
    verbose: bool,
    random_user_agent: bool,
    concurrency: int,
    retries: int,
    verify: bool,
    short_circuit: bool,
    limit: int | None,
    report: str | None,
    json_out: str | None,
) -> int:
    started = time.perf_counter()
    try:
        proxies = load_proxies(file)
    except OSError as exc:
        print(f"Could not read {file}: {exc}", file=sys.stderr)
        return 1
    if limit:
        proxies = proxies[:limit]

    if not proxies:
        print(f"No usable proxies found in {file}", file=sys.stderr)
        return 1

    urls = [site_url(site, method) for site in sites]
    # Deduplicate while preserving order (e.g. google.com and https://google.com).
    urls = list(dict.fromkeys(urls))
    user_agents = load_user_agents()
    semaphore = asyncio.Semaphore(concurrency)

    print(f"Checking {len(proxies)} {method} proxies against {len(urls)} site(s) "
          f"(concurrency {concurrency}, timeout {timeout}s)")

    results = await asyncio.gather(
        *(
            check_proxy(
                proxy=proxy,
                method=method,
                sites=urls,
                semaphore=semaphore,
                timeout=timeout,
                retries=retries,
                user_agents=user_agents,
                random_user_agent=random_user_agent,
                verify=verify,
                short_circuit=short_circuit,
            )
            for proxy in proxies
        )
    )

    for result in results:
        working = len(result.alive)
        verbose_print(verbose, f"  {result.proxy}: {working}/{len(urls)} site(s) ok")
        if verbose and result.errors:
            for url, error in result.errors.items():
                verbose_print(verbose, f"    {url}: {error}")

    total_alive = sum(len(result.alive) for result in results)
    if len(proxies) >= MIN_INPUT_FOR_GUARD and total_alive == 0:
        print(
            "No working proxies found; keeping existing output files untouched "
            "(this usually means an outage, not that every proxy died).",
            file=sys.stderr,
        )
        return 2

    slugs = unique_slugs(urls)
    write_results(results, urls, slugs, output, output_dir)

    duration = time.perf_counter() - started
    if json_out:
        write_json_results(json_out, method, file, len(proxies), results, urls, slugs, timeout, duration)
    if report:
        write_report(report, method, file, len(proxies), results, urls, slugs, timeout, concurrency, duration)

    print(f"Done in {duration:.1f}s")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check proxies and keep the working ones.")
    parser.add_argument("-t", "--timeout", type=float, default=DEFAULT_TIMEOUT, help="Timeout per request in seconds")
    parser.add_argument(
        "-p", "--proxy", default="http", choices=["http", "https", "socks", "socks4", "socks5"],
        help="Proxy type to test (socks is an alias for socks5)",
    )
    parser.add_argument("-l", "--list", default="output.txt", help="Input proxy list")
    parser.add_argument("-o", "--output", default="output.txt", help="Output file (single site only)")
    parser.add_argument("--output-dir", help="Write one <site>.txt per site into this directory")
    parser.add_argument(
        "-s", "--site", action="append",
        help="Site to test (repeatable). Default: google.com",
    )
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="Proxy checks in parallel")
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES, help="Retries per site on connection errors")
    parser.add_argument(
        "-r", "--random-agent", "--random_agent", dest="random_agent", action="store_true",
        help="Use a random user agent per proxy",
    )
    parser.add_argument("--verify", action="store_true", help="Verify TLS certificates (most public proxies fail this)")
    parser.add_argument(
        "--no-short-circuit", dest="short_circuit", action="store_false",
        help="Keep testing other sites even after the proxy connection fails",
    )
    parser.add_argument("--limit", type=int, help="Only check the first N proxies (debugging)")
    parser.add_argument("--report", help="Write a JSON summary to this path")
    parser.add_argument("--json-out", help="Write per-proxy results (for proxyCatalog.py) to this path")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print per-proxy results")
    args = parser.parse_args()

    method = "socks5" if args.proxy == "socks" else args.proxy

    sites = args.site or ["google.com"]
    if len(sites) > 1 and not args.output_dir:
        parser.error("--output-dir is required when checking more than one site")

    return asyncio.run(
        check(
            file=args.list,
            output=args.output,
            output_dir=args.output_dir,
            timeout=args.timeout,
            method=method,
            sites=sites,
            verbose=args.verbose,
            random_user_agent=args.random_agent,
            concurrency=args.concurrency,
            retries=args.retries,
            verify=args.verify,
            short_circuit=args.short_circuit,
            limit=args.limit,
            report=args.report,
            json_out=args.json_out,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
