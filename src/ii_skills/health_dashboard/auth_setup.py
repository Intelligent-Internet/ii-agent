#!/usr/bin/env python3
"""
WHOOP OAuth2 Authentication Setup
Run this script once to authenticate with WHOOP and save your tokens.
"""

import webbrowser
import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
import requests

from config import (
    WHOOP_CLIENT_ID, WHOOP_CLIENT_SECRET, WHOOP_REDIRECT_URI,
    WHOOP_AUTH_URL, WHOOP_TOKEN_URL, WHOOP_SCOPES, TOKEN_FILE
)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(SCRIPT_DIR, TOKEN_FILE)

# Global to store the auth code
auth_code = None


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle the OAuth callback from WHOOP."""

    def do_GET(self):
        global auth_code

        # Parse the authorization code from the URL
        query = parse_qs(urlparse(self.path).query)

        if 'code' in query:
            auth_code = query['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: #22c55e;">Success!</h1>
                    <p>WHOOP authorization complete. You can close this window.</p>
                    <p>Return to the terminal to complete setup.</p>
                </body>
                </html>
            """)
        else:
            error = query.get('error', ['Unknown error'])[0]
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: #ef4444;">Error</h1>
                    <p>Authorization failed: {error}</p>
                </body>
                </html>
            """.encode())

    def log_message(self, format, *args):
        # Suppress HTTP server logging
        pass


def get_authorization_url() -> str:
    """Generate the WHOOP authorization URL."""
    params = {
        'client_id': WHOOP_CLIENT_ID,
        'redirect_uri': WHOOP_REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(WHOOP_SCOPES),
        'state': 'whoop_auth'
    }
    return f"{WHOOP_AUTH_URL}?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict:
    """Exchange authorization code for access and refresh tokens."""
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': WHOOP_REDIRECT_URI,
        'client_id': WHOOP_CLIENT_ID,
        'client_secret': WHOOP_CLIENT_SECRET
    }

    response = requests.post(WHOOP_TOKEN_URL, data=data)
    response.raise_for_status()
    return response.json()


def save_tokens(tokens: dict):
    """Save tokens to file."""
    with open(TOKEN_PATH, 'w') as f:
        json.dump(tokens, f, indent=2)
    print(f"Tokens saved to {TOKEN_PATH}")


def main():
    global auth_code

    print("=" * 50)
    print("WHOOP OAuth2 Authentication Setup")
    print("=" * 50)
    print()

    # Check if credentials are configured
    if WHOOP_CLIENT_ID == "YOUR_CLIENT_ID_HERE":
        print("ERROR: Please configure your WHOOP credentials in config.py first!")
        print()
        print("Steps:")
        print("1. Go to https://developer-dashboard.whoop.com")
        print("2. Create a new application")
        print("3. Copy your Client ID and Client Secret")
        print("4. Update config.py with your credentials")
        print("5. Run this script again")
        return

    # Generate auth URL
    auth_url = get_authorization_url()

    print("Opening browser for WHOOP authorization...")
    print()
    print("If the browser doesn't open, visit this URL manually:")
    print(auth_url)
    print()

    # Open browser
    webbrowser.open(auth_url)

    # Start local server to receive callback
    print("Waiting for authorization callback...")
    print("(Press Ctrl+C to cancel)")
    print()

    server = HTTPServer(('localhost', 8080), OAuthCallbackHandler)

    # Wait for the callback (with timeout)
    server.timeout = 300  # 5 minute timeout
    while auth_code is None:
        server.handle_request()

    server.server_close()

    if auth_code:
        print("Authorization code received!")
        print("Exchanging for access tokens...")

        try:
            tokens = exchange_code_for_tokens(auth_code)
            save_tokens(tokens)

            print()
            print("=" * 50)
            print("SUCCESS! Authentication complete.")
            print("=" * 50)
            print()
            print("You can now run the WHOOP newsletter:")
            print("  python whoop_newsletter.py")

        except Exception as e:
            print(f"ERROR exchanging code for tokens: {e}")
            raise


if __name__ == "__main__":
    main()
