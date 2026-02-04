# Investment Banking Toolkit Configuration
# =========================================

# Output Settings
OUTPUT_DIR = "output"
TEMPLATE_DIR = "templates"

# Company Data APIs (free tiers)
# Financial Modeling Prep API - https://financialmodelingprep.com/developer/docs/
# Get free API key at: https://financialmodelingprep.com/developer/docs/
FMP_API_KEY = "YOUR_FMP_API_KEY_HERE"

# Alpha Vantage API - https://www.alphavantage.co/
# Get free API key at: https://www.alphavantage.co/support/#api-key
ALPHA_VANTAGE_API_KEY = "YOUR_ALPHA_VANTAGE_KEY_HERE"

# Presentation Defaults
DEFAULT_FONT = "Calibri"
TITLE_FONT_SIZE = 32
SUBTITLE_FONT_SIZE = 18
BODY_FONT_SIZE = 12

# Color Scheme (Investment Bank Blue)
COLORS = {
    "primary": "1e3a5f",      # Dark blue
    "secondary": "2563eb",    # Bright blue
    "accent": "10b981",       # Green (for positive)
    "negative": "ef4444",     # Red (for negative)
    "text": "1f2937",         # Dark gray
    "light_bg": "f8fafc",     # Light background
}

# Valuation Defaults
DEFAULT_WACC = 0.10           # 10% discount rate
DEFAULT_TERMINAL_GROWTH = 0.025  # 2.5% terminal growth
DEFAULT_TAX_RATE = 0.25       # 25% tax rate
PROJECTION_YEARS = 5          # 5-year projection period
