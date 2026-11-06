#!/usr/bin/env bash
# Local equivalent of the GitHub Actions pipeline.
# Usage: ./daily-update.sh [--no-commit]
set -euo pipefail

cd "$(dirname "$0")"

PROTOCOLS=(http https socks4 socks5)
DOMAINS=(google.com facebook.com twitter.com tiktok.com youtube.com whatsapp.com microsoft.com discord.com instagram.com)

if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

python3 -m pip install --upgrade -r requirements.txt

for protocol in "${PROTOCOLS[@]}"; do
    python3 proxyScraper.py -p "$protocol" -o "proxies/$protocol.txt"
done

sites=()
for domain in "${DOMAINS[@]}"; do
    sites+=("-s" "$domain")
done

for protocol in http https socks4 socks5; do
    python3 proxyChecker.py \
        -p "$protocol" \
        -l "proxies/$protocol.txt" \
        --output-dir "proxies/$protocol-tested" \
        --timeout 6 \
        --concurrency 300 \
        --retries 0 \
        --report "proxies/$protocol-tested/meta.json" \
        --json-out "proxies/$protocol-tested/proxies.json" \
        "${sites[@]}"
done

python3 proxyCatalog.py --geo-cache .cache/ip2asn-v4-u32.tsv.gz

if [ "${1:-}" = "--no-commit" ]; then
    echo "Skipping commit (--no-commit)."
    exit 0
fi

git add proxies
if git diff --cached --quiet; then
    echo "No changes to commit."
    exit 0
fi

git commit -m "feat: update proxies $(date -u +'%Y-%m-%d')"
git push origin main
