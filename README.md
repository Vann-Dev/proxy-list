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
   `httpcore` only speaks SOCKS5.
3. **Publish** — GitHub Actions runs the scrape every 3 hours and the check
   afterwards, then commits the updated files.

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
* `-v`, `--verbose` — print every proxy and the sites it passed

Exit code `2` means no proxy worked; in that case existing output files are left
untouched so a network outage cannot wipe the published lists.

### Local automation

```bash
./daily-update.sh --no-commit   # scrape + check all protocols
./daily-update.sh               # same, then git commit and push
```

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

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vann-dev/proxy-list,Vann-Dev/proxy-list&type=Date)](https://star-history.com/#vann-dev/proxy-list&Vann-Dev/proxy-list&Date)
