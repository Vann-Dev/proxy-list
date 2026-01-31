#!/bin/bash

# Proxy list daily update script for OpenClaw cron
# Runs daily at 2 AM UTC+7

cd /home/komi/.openclaw/workspace/proxy-list

echo "Starting daily proxy list update - $(date)"

# Update dependencies (if pip available)
if command -v pip3 &> /dev/null; then
    echo "Updating dependencies..."
    pip3 install --upgrade -r requirements.txt 2>/dev/null || echo "pip3 not available or dependencies already up to date"
fi

# Scrape fresh proxies
echo "Scraping HTTP proxies..."
python3 proxyScraper.py -p http -o proxies/http-temp.txt 2>/dev/null || echo "HTTP scraping failed"

echo "Scraping HTTPS proxies..."  
python3 proxyScraper.py -p https -o proxies/https-temp.txt 2>/dev/null || echo "HTTPS scraping failed"

# Test proxies (only if files exist)
if [ -f "proxies/http-temp.txt" ]; then
    echo "Testing HTTP proxies..."
    python3 proxyChecker.py -t 10 -s google.com -l proxies/http-temp.txt 2>/dev/null || echo "HTTP testing failed"
fi

if [ -f "proxies/https-temp.txt" ]; then
    echo "Testing HTTPS proxies..."
    python3 proxyChecker.py -t 10 -s google.com -l proxies/https-temp.txt 2>/dev/null || echo "HTTPS testing failed"
fi

# Replace old files with new ones
if [ -f "proxies/http-temp.txt" ]; then
    mv proxies/http-temp.txt proxies/http.txt
    echo "Updated HTTP proxy list"
fi

if [ -f "proxies/https-temp.txt" ]; then
    mv proxies/https-temp.txt proxies/https.txt
    echo "Updated HTTPS proxy list"
fi

# Commit and push changes
git config user.email "komi-bot@vann.my.id"
git config user.name "Komi-Misaki"

git add proxies/http.txt proxies/https.txt

if ! git diff --staged --quiet; then
    git commit -m "chore: daily proxy list update $(date -u +'%Y-%m-%d')"
    git push origin main
    echo "Successfully committed and pushed proxy list updates"
else
    echo "No changes to commit - proxy lists may be up to date"
fi

echo "Daily proxy list update completed - $(date)"