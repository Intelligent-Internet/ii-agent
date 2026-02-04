#!/usr/bin/env python3
"""
WHOOP Health Dashboard Newsletter
Fetches health data from WHOOP API and sends a daily dashboard email.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
import json
import os

from config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
    WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET,
    WHOOP_TOKEN_URL, WHOOP_API_BASE, TOKEN_FILE
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, TOKEN_FILE)


def load_tokens() -> dict:
    """Load tokens from file."""
    if not os.path.exists(TOKEN_PATH):
        raise FileNotFoundError(
            "No tokens found. Run auth_setup.py first to authenticate with WHOOP."
        )
    with open(TOKEN_PATH, 'r') as f:
        return json.load(f)


def save_tokens(tokens: dict):
    """Save tokens to file."""
    with open(TOKEN_PATH, 'w') as f:
        json.dump(tokens, f, indent=2)


def refresh_access_token(refresh_token: str) -> dict:
    """Refresh the access token using the refresh token."""
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token,
        'client_id': WHOOP_CLIENT_ID,
        'client_secret': WHOOP_CLIENT_SECRET
    }

    response = requests.post(WHOOP_TOKEN_URL, data=data)
    response.raise_for_status()
    return response.json()


def get_valid_token() -> str:
    """Get a valid access token, refreshing if necessary."""
    tokens = load_tokens()

    # Try to use existing token first
    access_token = tokens.get('access_token')

    # Check if we need to refresh (WHOOP tokens expire in ~1 hour typically)
    # For simplicity, we'll refresh every time to ensure validity
    try:
        refresh_token = tokens.get('refresh_token')
        if refresh_token:
            print("Refreshing access token...")
            new_tokens = refresh_access_token(refresh_token)
            save_tokens(new_tokens)
            return new_tokens['access_token']
    except Exception as e:
        print(f"Token refresh failed: {e}")
        print("Using existing token...")

    return access_token


def api_request(endpoint: str, access_token: str, params: dict = None) -> dict:
    """Make an authenticated request to the WHOOP API."""
    url = f"{WHOOP_API_BASE}{endpoint}"
    headers = {
        'Authorization': f'Bearer {access_token}',
        'Content-Type': 'application/json'
    }

    response = requests.get(url, headers=headers, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_user_profile(token: str) -> dict:
    """Fetch user profile information."""
    try:
        return api_request("/user/profile/basic", token)
    except Exception as e:
        print(f"Error fetching profile: {e}")
        return {}


def fetch_recovery(token: str) -> dict:
    """Fetch recent recovery data."""
    try:
        # Get last 7 days of recovery data
        end = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000Z")

        params = {
            'start': start,
            'end': end,
            'limit': 7
        }
        return api_request("/recovery", token, params)
    except Exception as e:
        print(f"Error fetching recovery: {e}")
        return {"records": []}


def fetch_sleep(token: str) -> dict:
    """Fetch recent sleep data."""
    try:
        end = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000Z")

        params = {
            'start': start,
            'end': end,
            'limit': 7
        }
        return api_request("/activity/sleep", token, params)
    except Exception as e:
        print(f"Error fetching sleep: {e}")
        return {"records": []}


def fetch_workouts(token: str) -> dict:
    """Fetch recent workout data."""
    try:
        end = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000Z")

        params = {
            'start': start,
            'end': end,
            'limit': 10
        }
        return api_request("/activity/workout", token, params)
    except Exception as e:
        print(f"Error fetching workouts: {e}")
        return {"records": []}


def fetch_cycles(token: str) -> dict:
    """Fetch recent cycle (strain) data."""
    try:
        end = datetime.now().strftime("%Y-%m-%dT23:59:59.999Z")
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00.000Z")

        params = {
            'start': start,
            'end': end,
            'limit': 7
        }
        return api_request("/cycle", token, params)
    except Exception as e:
        print(f"Error fetching cycles: {e}")
        return {"records": []}


def get_recovery_color(score: float) -> tuple:
    """Get color based on recovery score."""
    if score >= 67:
        return "#22c55e", "Green"  # Green - recovered
    elif score >= 34:
        return "#eab308", "Yellow"  # Yellow - moderate
    else:
        return "#ef4444", "Red"  # Red - not recovered


def get_strain_color(strain: float) -> str:
    """Get color based on strain level."""
    if strain >= 18:
        return "#ef4444"  # Red - overreaching
    elif strain >= 14:
        return "#f97316"  # Orange - high
    elif strain >= 10:
        return "#eab308"  # Yellow - moderate
    else:
        return "#22c55e"  # Green - light


def format_duration(milliseconds) -> str:
    """Format milliseconds to hours and minutes."""
    if not milliseconds:
        return "N/A"
    # Handle v2 API which may return dict or nested values
    if isinstance(milliseconds, dict):
        milliseconds = milliseconds.get("duration_milliseconds", 0) or milliseconds.get("total_milliseconds", 0)
    if not isinstance(milliseconds, (int, float)):
        return "N/A"
    total_minutes = int(milliseconds) // 60000
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours}h {minutes}m"


def generate_html(data: dict) -> str:
    """Generate the HTML newsletter."""
    today = datetime.now().strftime("%B %d, %Y")

    # Get most recent data
    recovery_records = data.get("recovery", {}).get("records", [])
    sleep_records = data.get("sleep", {}).get("records", [])
    cycle_records = data.get("cycles", {}).get("records", [])
    workout_records = data.get("workouts", {}).get("records", [])

    # Latest recovery
    latest_recovery = recovery_records[0] if recovery_records else {}
    recovery_score = latest_recovery.get("score", {}).get("recovery_score", 0)
    hrv = latest_recovery.get("score", {}).get("hrv_rmssd_milli", 0)
    rhr = latest_recovery.get("score", {}).get("resting_heart_rate", 0)
    recovery_color, recovery_status = get_recovery_color(recovery_score)

    # Latest sleep (handle v2 API structure)
    latest_sleep = sleep_records[0] if sleep_records else {}
    sleep_score_data = latest_sleep.get("score", {})
    sleep_score = sleep_score_data.get("sleep_performance_percentage", 0) or 0
    # v2 API: duration fields may be in milliseconds directly or nested
    sleep_duration = sleep_score_data.get("total_sleep_duration", 0)
    if isinstance(sleep_duration, dict):
        sleep_duration = sleep_duration.get("total_milliseconds", 0)
    sleep_needed = sleep_score_data.get("sleep_needed", {})
    if isinstance(sleep_needed, dict):
        sleep_needed = sleep_needed.get("baseline_milli", 0) or sleep_needed.get("need_milliseconds", 0)
    sleep_debt = sleep_score_data.get("sleep_debt", {})
    if isinstance(sleep_debt, dict):
        sleep_debt = sleep_debt.get("debt_milliseconds", 0) or 0

    # Latest cycle (strain)
    latest_cycle = cycle_records[0] if cycle_records else {}
    strain = latest_cycle.get("score", {}).get("strain", 0)
    calories = latest_cycle.get("score", {}).get("kilojoule", 0)
    if calories:
        calories = round(calories / 4.184)  # Convert kJ to kcal
    strain_color = get_strain_color(strain)

    # Calculate 7-day averages
    avg_recovery = sum(r.get("score", {}).get("recovery_score", 0) for r in recovery_records) / len(recovery_records) if recovery_records else 0
    avg_hrv = sum(r.get("score", {}).get("hrv_rmssd_milli", 0) for r in recovery_records) / len(recovery_records) if recovery_records else 0
    avg_strain = sum(c.get("score", {}).get("strain", 0) for c in cycle_records) / len(cycle_records) if cycle_records else 0

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 700px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9fafb;
        }}
        .header {{
            background: linear-gradient(135deg, #0f172a 0%, #334155 100%);
            color: white;
            padding: 30px;
            border-radius: 12px;
            margin-bottom: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .header .date {{
            margin: 10px 0 0;
            opacity: 0.9;
        }}
        .score-grid {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }}
        .score-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .score-label {{
            font-size: 12px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .score-value {{
            font-size: 36px;
            font-weight: 700;
            margin: 10px 0;
        }}
        .score-unit {{
            font-size: 14px;
            color: #6b7280;
        }}
        .section {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .section h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            color: #1e3a8a;
            border-bottom: 2px solid #e5e7eb;
            padding-bottom: 10px;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #f3f4f6;
        }}
        .metric-row:last-child {{
            border-bottom: none;
        }}
        .metric-label {{
            color: #6b7280;
        }}
        .metric-value {{
            font-weight: 600;
        }}
        .trend-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
            margin-top: 10px;
        }}
        .trend-table th {{
            background: #f3f4f6;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
        }}
        .trend-table td {{
            padding: 10px 8px;
            border-bottom: 1px solid #e5e7eb;
        }}
        .workout-item {{
            padding: 10px 0;
            border-bottom: 1px solid #f3f4f6;
        }}
        .workout-item:last-child {{
            border-bottom: none;
        }}
        .workout-name {{
            font-weight: 600;
        }}
        .workout-details {{
            font-size: 13px;
            color: #6b7280;
        }}
        .footer {{
            text-align: center;
            color: #6b7280;
            font-size: 12px;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>WHOOP Health Dashboard</h1>
        <p class="date">{today}</p>
    </div>

    <div class="score-grid">
        <div class="score-card">
            <div class="score-label">Recovery</div>
            <div class="score-value" style="color: {recovery_color};">{recovery_score:.0f}%</div>
            <div class="score-unit">{recovery_status}</div>
        </div>
        <div class="score-card">
            <div class="score-label">Strain</div>
            <div class="score-value" style="color: {strain_color};">{strain:.1f}</div>
            <div class="score-unit">out of 21</div>
        </div>
        <div class="score-card">
            <div class="score-label">Sleep</div>
            <div class="score-value" style="color: #3b82f6;">{sleep_score:.0f}%</div>
            <div class="score-unit">{format_duration(sleep_duration)}</div>
        </div>
    </div>

    <div class="section">
        <h2>Recovery Details</h2>
        <div class="metric-row">
            <span class="metric-label">Recovery Score</span>
            <span class="metric-value" style="color: {recovery_color};">{recovery_score:.0f}%</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">HRV (Heart Rate Variability)</span>
            <span class="metric-value">{hrv:.1f} ms</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Resting Heart Rate</span>
            <span class="metric-value">{rhr:.0f} bpm</span>
        </div>
    </div>

    <div class="section">
        <h2>Sleep Details</h2>
        <div class="metric-row">
            <span class="metric-label">Sleep Performance</span>
            <span class="metric-value">{sleep_score:.0f}%</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Time Asleep</span>
            <span class="metric-value">{format_duration(sleep_duration)}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Sleep Needed</span>
            <span class="metric-value">{format_duration(sleep_needed)}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Sleep Debt</span>
            <span class="metric-value">{format_duration(sleep_debt)}</span>
        </div>
    </div>

    <div class="section">
        <h2>Strain & Activity</h2>
        <div class="metric-row">
            <span class="metric-label">Day Strain</span>
            <span class="metric-value" style="color: {strain_color};">{strain:.1f}</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Calories Burned</span>
            <span class="metric-value">{calories:,} kcal</span>
        </div>
    </div>
"""

    # Recent workouts section
    if workout_records:
        html += """
    <div class="section">
        <h2>Recent Workouts</h2>
"""
        for workout in workout_records[:5]:
            sport_id = workout.get("sport_id", 0)
            workout_strain = workout.get("score", {}).get("strain", 0)
            workout_calories = workout.get("score", {}).get("kilojoule", 0)
            if workout_calories:
                workout_calories = round(workout_calories / 4.184)

            # Map sport IDs to names (common ones)
            sport_names = {
                0: "Activity", 1: "Running", 44: "Walking", 71: "Cycling",
                52: "Swimming", 43: "Weightlifting", 82: "HIIT", 48: "Yoga",
                -1: "Activity"
            }
            sport_name = sport_names.get(sport_id, f"Activity ({sport_id})")

            start_time = workout.get("start", "")
            if start_time:
                try:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    workout_date = dt.strftime("%b %d, %I:%M %p")
                except:
                    workout_date = start_time[:10]
            else:
                workout_date = "Unknown"

            html += f"""
        <div class="workout-item">
            <div class="workout-name">{sport_name}</div>
            <div class="workout-details">
                {workout_date} • Strain: {workout_strain:.1f} • {workout_calories} kcal
            </div>
        </div>
"""
        html += "    </div>\n"

    # 7-day averages
    html += f"""
    <div class="section">
        <h2>7-Day Averages</h2>
        <div class="metric-row">
            <span class="metric-label">Avg Recovery</span>
            <span class="metric-value">{avg_recovery:.0f}%</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Avg HRV</span>
            <span class="metric-value">{avg_hrv:.1f} ms</span>
        </div>
        <div class="metric-row">
            <span class="metric-label">Avg Strain</span>
            <span class="metric-value">{avg_strain:.1f}</span>
        </div>
    </div>

    <div class="footer">
        <p>Generated automatically by WHOOP Health Dashboard</p>
        <p>Data sourced from WHOOP API</p>
    </div>
</body>
</html>
"""
    return html


def send_email(html_content: str) -> bool:
    """Send the newsletter via Gmail SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"WHOOP Health Dashboard - {datetime.now().strftime('%B %d, %Y')}"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = GMAIL_ADDRESS

        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        print("Newsletter sent successfully!")
        return True

    except Exception as e:
        print(f"Error sending email: {e}")
        return False


def main():
    """Main function to generate and send the WHOOP dashboard."""
    print("=" * 50)
    print("WHOOP Health Dashboard Newsletter")
    print("=" * 50)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Get valid access token
    print("Getting access token...")
    try:
        access_token = get_valid_token()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        print("Please run auth_setup.py first to authenticate with WHOOP.")
        return

    print()

    # Fetch all data
    print("Fetching WHOOP data...")

    print("  - Fetching profile...")
    profile = fetch_user_profile(access_token)

    print("  - Fetching recovery...")
    recovery = fetch_recovery(access_token)

    print("  - Fetching sleep...")
    sleep = fetch_sleep(access_token)

    print("  - Fetching cycles (strain)...")
    cycles = fetch_cycles(access_token)

    print("  - Fetching workouts...")
    workouts = fetch_workouts(access_token)

    print()

    # Prepare data
    data = {
        "profile": profile,
        "recovery": recovery,
        "sleep": sleep,
        "cycles": cycles,
        "workouts": workouts
    }

    # Generate HTML
    print("Generating newsletter...")
    html_content = generate_html(data)

    # Send email
    print("Sending email...")
    success = send_email(html_content)

    if success:
        print("\nNewsletter sent successfully!")
    else:
        print("\nFailed to send newsletter.")

    print("=" * 50)


if __name__ == "__main__":
    main()
