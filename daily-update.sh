#!/bin/bash

# Daily proxy list update script
# Runs at 2 AM UTC+7 (9 AM UTC)

cd /home/komi/.openclaw/workspace/proxy-list

# Activate virtual environment if exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Update dependencies
pip install --upgrade -r requirements.txt

# Scrape fresh proxies
python3 proxyScraper.py -p http -o proxies/http-temp.txt
python3 proxyScraper.py -p https -o proxies/https-temp.txt

# Test proxies
python3 proxyChecker.py -t 10 -s google.com -l proxies/http-temp.txt
python3 proxyChecker.py -t 10 -s google.com -l proxies/https-temp.txt

# Replace old files
mv proxies/http-temp.txt proxies/http.txt
mv proxies/https-temp.txt proxies/https.txt

# Commit and push changes
git config user.email "komi-bot@vann.my.id"
git config user.name "Komi-Misaki"
git add proxies/http.txt proxies/https.txt
if ! git diff --staged --quiet; then
    git commit -m "chore: daily proxy list update $(date -u +'%Y-%m-%d')"
    git push origin main
fi

echo "Daily proxy update completed: $(date)"