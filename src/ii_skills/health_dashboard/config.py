# WHOOP Health Dashboard Newsletter Configuration
# ================================================

# Gmail Configuration (same as your other newsletters)
GMAIL_ADDRESS = "your-email@gmail.com"
GMAIL_APP_PASSWORD = "your-app-password"

# WHOOP API Configuration
# -----------------------
# Get these from https://developer-dashboard.whoop.com
# 1. Create an application
# 2. Copy your Client ID and Client Secret
# 3. Set Redirect URI to: http://localhost:8080/callback

WHOOP_CLIENT_ID = "your-client-id"
WHOOP_CLIENT_SECRET = "your-client-secret"
WHOOP_REDIRECT_URI = "http://localhost:8080/callback"

# WHOOP API Endpoints
WHOOP_AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
WHOOP_TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
WHOOP_API_BASE = "https://api.prod.whoop.com/developer/v2"

# Scopes needed for full dashboard
# https://developer.whoop.com/api#section/Authentication/OAuth-Scopes
WHOOP_SCOPES = [
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement"
]

# Token storage file
TOKEN_FILE = "whoop_tokens.json"
