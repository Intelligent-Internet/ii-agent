# Newsletter Scheduler Setup

## Overview

This guide explains how to schedule the daily investment newsletter on your personal laptop.

## macOS (launchd)

### Step 1: Create the Launch Agent

Create file at `~/Library/LaunchAgents/com.claire.investment-newsletter.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.claire.investment-newsletter</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/Claire/Skills/daily-investment-newsletter/generate_newsletter.py</string>
    </array>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/tmp/claire-newsletter.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/claire-newsletter-error.log</string>

    <key>WorkingDirectory</key>
    <string>/path/to/Claire</string>
</dict>
</plist>
```

### Step 2: Update Paths

Replace `/path/to/Claire` with your actual path (e.g., `/Users/yourname/python/Claire`).

### Step 3: Load the Agent

```bash
# Load the job
launchctl load ~/Library/LaunchAgents/com.claire.investment-newsletter.plist

# Verify it's loaded
launchctl list | grep claire

# Test run immediately
launchctl start com.claire.investment-newsletter

# Check logs
cat /tmp/claire-newsletter.log
```

### Step 4: Manage

```bash
# Stop the job
launchctl unload ~/Library/LaunchAgents/com.claire.investment-newsletter.plist

# Reload after changes
launchctl unload ~/Library/LaunchAgents/com.claire.investment-newsletter.plist
launchctl load ~/Library/LaunchAgents/com.claire.investment-newsletter.plist
```

---

## Linux (cron)

### Step 1: Edit Crontab

```bash
crontab -e
```

### Step 2: Add Entry

```cron
# Daily Canadian Investment Newsletter at 6:00 AM (Mon-Fri)
0 6 * * 1-5 /usr/bin/python3 /path/to/Claire/Skills/daily-investment-newsletter/generate_newsletter.py >> /tmp/claire-newsletter.log 2>&1
```

### Step 3: Verify

```bash
crontab -l
```

---

## Windows (Task Scheduler)

### Step 1: Open Task Scheduler

Press `Win + R`, type `taskschd.msc`, press Enter.

### Step 2: Create Basic Task

1. Click "Create Basic Task..."
2. Name: `Claire Investment Newsletter`
3. Trigger: Daily at 6:00 AM
4. Action: Start a program
5. Program: `python`
6. Arguments: `C:\path\to\Claire\Skills\daily-investment-newsletter\generate_newsletter.py`
7. Start in: `C:\path\to\Claire`

### Step 3: Configure

- Check "Run only when user is logged on"
- Uncheck "Stop the task if it runs longer than"

---

## Schedule Options

| Schedule | Cron Expression | Description |
|----------|-----------------|-------------|
| Weekdays 6 AM | `0 6 * * 1-5` | Before market open |
| Daily 7 AM | `0 7 * * *` | Every day |
| Weekdays 5 PM | `0 17 * * 1-5` | After market close |

---

## Troubleshooting

### Newsletter not generating

1. Check Python path: `which python3`
2. Verify script path exists
3. Check Config/ credentials are present
4. Review error logs

### Permission issues (macOS)

```bash
chmod +x /path/to/generate_newsletter.py
```

### Missing dependencies

```bash
pip3 install requests
```

---

## Environment Variables

If needed, add to your scheduler:

```bash
export CLAIRE_CONFIG=/path/to/Claire/Config
export CLAIRE_MEMORY=/path/to/Claire/Memory
```

---

## Testing

Always test before relying on scheduled runs:

```bash
# Test with dry run (no email)
python3 generate_newsletter.py --dry-run

# Full test
python3 generate_newsletter.py
```
