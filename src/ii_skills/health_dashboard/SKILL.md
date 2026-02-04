# WHOOP Health Dashboard Skill

## Overview
Automated daily health dashboard that fetches data from the WHOOP API and sends a formatted email with recovery, sleep, strain, and workout metrics.

## Capabilities
- Fetches data via WHOOP Developer API (OAuth 2.0)
- Tracks recovery score, HRV, resting heart rate
- Monitors sleep performance, duration, debt
- Records daily strain and calories
- Shows recent workouts
- Calculates 7-day averages
- Auto-refreshes OAuth tokens

## Dashboard Contents
1. **Recovery Score** (color-coded: Green/Yellow/Red)
2. **Strain Score** (0-21 scale)
3. **Sleep Performance** (percentage and duration)
4. **Recovery Details** (HRV, RHR)
5. **Sleep Details** (duration, needed, debt)
6. **Strain & Activity** (calories burned)
7. **Recent Workouts** (last 5)
8. **7-Day Averages**

## Required Configuration
| Config File | Description | Required |
|-------------|-------------|----------|
| `Config/gmail-credentials.txt` | Gmail address and app password | Yes |
| `Config/whoop-client-id.txt` | WHOOP Developer Client ID | Yes |
| `Config/whoop-client-secret.txt` | WHOOP Developer Client Secret | Yes |

## Initial Setup

### 1. Register as WHOOP Developer
1. Go to https://developer-dashboard.whoop.com
2. Sign in with your WHOOP account
3. Create a new application
4. Set Redirect URI to: `http://localhost:8080/callback`
5. Copy Client ID and Client Secret

### 2. Configure Credentials
Add to `config.py`:
```python
WHOOP_CLIENT_ID = "your_client_id"
WHOOP_CLIENT_SECRET = "your_client_secret"
```

### 3. Authenticate (One-Time)
```bash
python auth_setup.py
```
This opens a browser for WHOOP authorization and saves tokens.

## Output
- Email sent to configured Gmail address
- Tokens stored: `whoop_tokens.json`
- Log file: `whoop.log`

## Usage

### Manual Run
```bash
python Claire/Skills/whoop-dashboard/whoop_newsletter.py
```

### Scheduled (Windows Task Scheduler)
Task Name: "Daily WHOOP Dashboard"
Schedule: Daily at 7:00 AM
Script: `run_whoop.bat`

## API Scopes Used
- `read:recovery` - Recovery scores, HRV, RHR
- `read:cycles` - Daily strain data
- `read:sleep` - Sleep metrics
- `read:workout` - Workout details
- `read:profile` - User profile
- `read:body_measurement` - Body metrics

## Example Prompts for Claude

> "Set up the WHOOP health dashboard newsletter"

> "Show me my average recovery score for the past week"

> "Add a weekly summary comparison to the WHOOP dashboard"

> "What time should I go to bed based on my sleep debt?"

## Troubleshooting

### Token Expired
Run `auth_setup.py` again to re-authenticate.

### API Rate Limits
WHOOP API has rate limits. If you see 429 errors, reduce polling frequency.

### Missing Data
Some metrics may be unavailable if WHOOP hasn't synced. Check the WHOOP app first.

## Dependencies
```
requests>=2.28.0
```

## Resources
- WHOOP Developer Portal: https://developer.whoop.com
- API Documentation: https://developer.whoop.com/api

---
*Skill Version: 1.0.0*
*Last Updated: 2026-02-04*
*Status: Requires WHOOP Developer credentials to activate*
