# Proxy Update Handler

This script handles the daily proxy list update triggered by OpenClaw cron.

## How it works:

1. OpenClaw cron triggers at 2 AM UTC+7 daily
2. Sends system event: "run_proxy_update_script" 
3. This script detects the event and runs the proxy update
4. Updates proxy lists and commits changes to git

## Usage:

The script runs automatically when the cron event is received.

## Manual testing:

```bash
# Test the update script directly
./cron-proxy-update.sh

# Or trigger via cron system event (handled automatically)
```

## Schedule:

- **Time:** 2 AM UTC+7 daily (9 AM UTC)
- **Frequency:** Every 24 hours
- **Trigger:** OpenClaw cron system