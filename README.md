# List of Public Proxies Scraper

This repository originally created by [iw4p](https://github.com/iw4p/proxy-scraper) and I just added some features to it.

Please check the original repository too.

___

# Directory

## [Raw HTTP proxies](https://github.com/Vann-Dev/proxy-list/blob/main/proxies/http.txt)
## [Tested HTTP proxies](https://github.com/Vann-Dev/proxy-list/blob/main/proxies/http-tested/)

## [Raw HTTPS proxies](https://github.com/Vann-Dev/proxy-list/blob/main/proxies/https.txt)
## [Tested HTTPS proxies](https://github.com/Vann-Dev/proxy-list/blob/main/proxies/https-tested/)

___

## Installation

Use this command to install dependencies.


```bash
pip3 install -r requirements.txt
```

## Usage

For scraping:

```bash
python3 proxyScraper.py -p http
```
* With `-p` or `--proxy`, You can choose your proxy type. Supported proxy types are: **HTTP - HTTPS - Socks (Both 4 and 5) - Socks4 - Socks5** 
* With `-o` or `--output`, create and write to a .txt file. (Default is **output.txt**)
* With `-v` or `--verbose`, more details.
* With `-h` or `--help`, Show help to who did't read this README.

For checking:

```bash
python3 proxyChecker.py -t 20 -s google.com -l output.txt
```

* With `-t` or `--timeout`, dismiss the proxy after -t seconds (Default is **20**)
* With `-p` or `--proxy`, check HTTPS or HTTP proxies (Default is **HTTP**)
* With `-l` or `--list`, path to your list.txt. (Default is **output.txt**)
* With `-s` or `--site`, check with specific website like google.com. (Default is **google.com**)
* With `-r` or `--random_agent`, it will use a random user agent per proxy.
* With `-v` or `--verbose`, more details.
* With `-h` or `--help`, Show help to who did't read this README.

## Good to know
* Dead proxies will be removed and just alive proxies will stay.
* This script is also able to scrape Socks, but proxyChecker only checks HTTP(S) proxies.

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=vann-dev/proxy-list&type=Date)](https://star-history.com/#iw4p/proxy-scraper&Date)

