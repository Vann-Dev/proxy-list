# Public Proxy List Scraper

Scraped and checked public proxy lists, updated automatically every few hours by
GitHub Actions. Proxies are collected from over 40 independent sources, validated,
de-duplicated and then tested against popular domains so you can pick a list that
already works for your target.

Originally created by [iw4p](https://github.com/iw4p/proxy-scraper); this fork adds
more sources, SOCKS support, faster checking and per-domain result files.

> [!WARNING]
> These are public proxies. They are unreliable, may log your traffic and may be
> malicious. Use them for learning and testing only. Any issue caused by using a
> proxy is your own responsibility.

## Proxy lists

| Protocol | Raw list | Checked lists |
| --- | --- | --- |
| HTTP | [`proxies/http.txt`](proxies/http.txt) | [`proxies/http-tested/`](proxies/http-tested/) |
| HTTPS | [`proxies/https.txt`](proxies/https.txt) | [`proxies/https-tested/`](proxies/https-tested/) |
| SOCKS4 | [`proxies/socks4.txt`](proxies/socks4.txt) | [`proxies/socks4-tested/`](proxies/socks4-tested/) |
| SOCKS5 | [`proxies/socks5.txt`](proxies/socks5.txt) | [`proxies/socks5-tested/`](proxies/socks5-tested/) |

Raw lists contain one `ip:port` per line, sorted numerically and de-duplicated.

Checked lists are split per domain: `google.txt`, `facebook.txt`, `twitter.txt`,
`tiktok.txt`, `youtube.txt`, `whatsapp.txt`, `microsoft.txt`, `discord.txt`,
`instagram.txt`. Each file is sorted by measured latency (fastest first) and only
contains proxies that answered successfully. `meta.json` next to them records how
many proxies were checked and how many survived.

Direct URLs work with `curl`, `wget`, or any HTTP client:

```bash
curl -s https://raw.githubusercontent.com/Vann-Dev/proxy-list/main/proxies/http-tested/google.txt
```

### JSON catalog

For programmatic use, [`proxies/proxies.json`](proxies/proxies.json) contains one
entry per unique working proxy across all protocols, enriched with country and
ASN data and per-domain latency:

```json
{
  "schema": 1,
  "generated_at": "2026-11-06T13:12:33Z",
  "count": 1,
  "proxies": [
    {
      "address": "8.8.8.8:8080",
      "ip": "8.8.8.8",
      "port": 8080,
      "protocols": ["http", "https"],
      "country": "US",
      "asn": "AS15169",
      "as_name": "GOOGLE",
      "anonymity": "elite",
      "sites": {"google": 123, "discord": 456}
    }
  ]
}
```

Anonymity is one of `transparent` (your IP leaks to the target),
`anonymous` (the proxy is visible but your IP is not), `elite` (neither is
visible) or `null` when the check was not run. When one address works as
several protocols, the least private result wins.

[`proxies/stats.json`](proxies/stats.json) holds per-protocol, per-domain,
per-country and per-anonymity counts. Latency values are milliseconds.
Country/ASN data comes from the free [iptoasn.com](https://iptoasn.com) dataset
and is refreshed on every run; a proxy outside the dataset has `null` geo
fields.

## How it works

1. **Scrape** (`proxyScraper.py`) — pulls 40+ source URLs in parallel: raw GitHub
   lists, JSON APIs and HTML tables. Every candidate is validated (public IPv4
   only, no private/loopback/reserved ranges) and de-duplicated. The output is
   written atomically, and a scrape that returns suspiciously few proxies never
   overwrites the previous list.
2. **Check** (`proxyChecker.py`) — tests proxies concurrently with `asyncio` +
   `httpx` (no more one thread per proxy). A proxy is tested against the first
   domain once; if the connection is dead, the remaining domains are skipped.
   Working proxies are grouped per domain and sorted by latency. SOCKS5 goes
   through `httpx[socks]`; SOCKS4 uses a small standard-library client because
   `httpcore` only speaks SOCKS5. With `--anonymity`, every working proxy also
   loads a public echo endpoint so the headers the target would see can be
   classified as transparent, anonymous or elite.
3. **Publish** — `proxyCatalog.py` merges the per-protocol results, adds
   country/ASN metadata and writes `proxies/proxies.json` plus `proxies/stats.json`.
   GitHub Actions checks the four protocols on separate runners in parallel,
   then merges everything and pushes a single data commit per run.

The freshness state (`--state`) is kept in `.cache/` and never committed; CI
stores it with the actions cache. A proxy that fails twice in a row is skipped
for 24 hours and then retried, so a temporary outage does not blacklist it
forever.

### Sources

| Source | Protocols |
| --- | --- |
| [TheSpeedX/PROXY-List](https://github.com/TheSpeedX/PROXY-List) | HTTP, SOCKS4, SOCKS5 |
| [monosans/proxy-list](https://github.com/monosans/proxy-list) | HTTP, SOCKS4, SOCKS5 |
| [proxifly/free-proxy-list](https://github.com/proxifly/free-proxy-list) | HTTP, HTTPS, SOCKS4, SOCKS5 |
| [ShiftyTR/Proxy-List](https://github.com/ShiftyTR/Proxy-List) | HTTP, HTTPS, SOCKS4, SOCKS5 |
| [clarketm/proxy-list](https://github.com/clarketm/proxy-list) | HTTP |
| [mmpx12/proxy-list](https://github.com/mmpx12/proxy-list) | HTTP, SOCKS5 |
| [vakhov/fresh-proxy-list](https://github.com/vakhov/fresh-proxy-list) | HTTP, SOCKS5 |
| [sunny9577/proxy-scraper](https://github.com/sunny9577/proxy-scraper) | HTTP |
| [ALIILAPRO/Proxy](https://github.com/ALIILAPRO/Proxy) | HTTP, SOCKS4, SOCKS5 |
| [hookzof/socks5_list](https://github.com/hookzof/socks5_list) | SOCKS5 |
| [roosterkid/openproxylist](https://github.com/roosterkid/openproxylist) | HTTPS, SOCKS4, SOCKS5 |
| [zloi-user/hideip.me](https://github.com/zloi-user/hideip.me) | HTTP, SOCKS4, SOCKS5 |
| [spys.me](https://spys.me) | HTTP |
| [free-proxy-list.net](https://free-proxy-list.net), [sslproxies.org](https://www.sslproxies.org), [us-proxy.org](https://www.us-proxy.org) | HTTP, HTTPS |
| [ProxyScrape](https://proxyscrape.com) v4 API | HTTP, HTTPS, SOCKS4, SOCKS5 |
| [Geonode](https://geonode.com) API | HTTP, HTTPS, SOCKS4, SOCKS5 |

Source definitions live in `SOURCES` at the top of [`proxyScraper.py`](proxyScraper.py).

## Installation

```bash
python3 -m pip install -r requirements.txt
```

SOCKS5 checking needs `httpx[socks]`, which the requirements file includes.

## Usage

### Scrape

```bash
python3 proxyScraper.py -p http -o proxies/http.txt
```

* `-p`, `--proxy` — `http`, `https`, `socks4`, `socks5` or `socks` (socks4 + socks5)
* `-o`, `--output` — output file (default `output.txt`)
* `-v`, `--verbose` — print the number of proxies found per source
* `--timeout` — request timeout in seconds (default 30)
* `--retries` — retries per source (default 1)
* `--concurrency` — source downloads in parallel (default 16)
* `--report` — write a JSON report with per-source counts and errors

### Check

```bash
python3 proxyChecker.py -p http -l proxies/http.txt \
  --output-dir proxies/http-tested \
  -s google.com -s discord.com --timeout 10
```

* `-p`, `--proxy` — `http`, `https`, `socks4`, `socks5` (`socks` is an alias for `socks5`)
* `-l`, `--list` — input proxy list
* `-s`, `--site` — site to test, repeatable (default `google.com`)
* `-o`, `--output` — output file when testing a single site
* `--output-dir` — write one `<site>.txt` per site (required for multiple sites)
* `-t`, `--timeout` — per-request timeout in seconds (default 10)
* `--concurrency` — parallel proxy checks (default 200)
* `--retries` — retries per site on connection errors (default 1)
* `-r`, `--random-agent` — random user agent per proxy
* `--verify` — verify TLS certificates (most public proxies fail this, so it is off)
* `--no-short-circuit` — keep testing other sites after a fatal proxy error
* `--limit` — only check the first N proxies
* `--report` — write a JSON summary to this path
* `--json-out` — write machine-readable results (address, working sites, latency
  in ms) for this protocol; this is the input of the catalog builder
* `--anonymity` — classify working proxies as `transparent`, `anonymous` or
  `elite` with one extra request each
* `--anonymity-url` — comma-separated echo endpoints returning the request
  headers (default `httpbin.org/headers`, then `httpbingo.org/headers`)
* `--state` — JSON file with failure history; recently dead proxies are skipped
  so they are not retested on every run
* `--skip-after` — consecutive failures before a proxy is skipped (default 2)
* `--skip-failed-hours` — retry skipped proxies after this many hours
  (default 24; `0` disables skipping)
* `-v`, `--verbose` — print every proxy and the sites it passed

Exit code `2` means no proxy worked; in that case existing output files are left
untouched so a network outage cannot wipe the published lists.

### Local automation

```bash
./daily-update.sh --no-commit   # scrape + check all protocols
./daily-update.sh               # same, then git commit and push
```

### Build the JSON catalog

After checking, merge every `proxies/*-tested/proxies.json` into a single
catalog and add country/ASN metadata:

```bash
python3 proxyCatalog.py --geo-cache .cache/ip2asn-v4-u32.tsv.gz
```

* `--proxies-dir` — directory holding the `*-tested` folders (default `proxies`)
* `--output` — catalog path (default `proxies/proxies.json`)
* `--stats` — stats path (default `proxies/stats.json`)
* `--geo-cache` — path of the downloaded ip2asn dataset
* `--no-geo` — skip enrichment and leave country/ASN fields `null`
* `--refresh-geo` — force a fresh download of the ip2asn dataset

The dataset is cached locally and is not committed; `--no-geo` keeps the build
fully offline.

## Development

```bash
python3 -m unittest discover -s tests -v
```

No network access is required for the tests. CI (`.github/workflows/test.yaml`)
runs them on every push and pull request.

## Limitations

* Only globally routable IPv4 proxies are published; IPv6 is not supported yet.
* "HTTPS proxy" means an HTTP proxy that supports `CONNECT`, which is how HTTPS
  traffic is tunnelled.
* A proxy can work for one domain and fail for another; always use the per-domain
  file that matches your target.
* Anonymity is inferred from headers only, so a proxy that leaks the client IP in
  another way can still be labelled `anonymous`. A failed echo request is
  reported as `unknown` rather than guessed.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vann-dev/proxy-list,Vann-Dev/proxy-list&type=Date)](https://star-history.com/#vann-dev/proxy-list&Vann-Dev/proxy-list&Date)
