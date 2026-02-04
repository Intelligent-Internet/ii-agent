# Market Newsletter Configuration
# ================================
# Fill in your credentials below before running

# Gmail Configuration
# -------------------
# 1. Enable 2-Factor Authentication on your Gmail account
# 2. Go to https://myaccount.google.com/apppasswords
# 3. Create an App Password for "Mail" and copy it here
GMAIL_ADDRESS = "your.email@gmail.com"  # Your Gmail address
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"  # 16-character app password (from Google App Passwords)

# NewsAPI Configuration
# ---------------------
# Sign up for free at https://newsapi.org/register
# Free tier allows 100 requests per day
NEWSAPI_KEY = "your_newsapi_key_here"

# Assets to Track
# ---------------
ASSETS = {
    # Precious Metals
    "Gold": {
        "ticker": "GC=F",  # Gold Futures
        "news_query": "gold price",
        "asset_class": "Precious Metals"
    },
    "Silver": {
        "ticker": "SI=F",  # Silver Futures
        "news_query": "silver price",
        "asset_class": "Precious Metals"
    },
    # Base Metals
    "Copper": {
        "ticker": "HG=F",  # Copper Futures
        "news_query": "copper price",
        "asset_class": "Base Metals"
    },
    "Alfamin Resources": {
        "ticker": "AFM.V",  # TSX Venture
        "news_query": "Alfamin Resources AFM",
        "asset_class": "Base Metals"
    },
    # Crypto
    "Bitcoin": {
        "ticker": "bitcoin",  # CoinGecko ID
        "news_query": "bitcoin",
        "asset_class": "Crypto"
    },
    "Ethereum": {
        "ticker": "ethereum",  # CoinGecko ID
        "news_query": "ethereum",
        "asset_class": "Crypto"
    },
    # Semiconductors & Tech
    "Lumentum": {
        "ticker": "LITE",  # NYSE stock
        "news_query": "Lumentum LITE stock",
        "asset_class": "Semiconductors"
    },
    "Coherent": {
        "ticker": "COHR",  # NYSE
        "news_query": "Coherent Corp COHR stock",
        "asset_class": "Semiconductors"
    },
    "Lattice Semiconductor": {
        "ticker": "LSCC",  # NASDAQ
        "news_query": "Lattice Semiconductor LSCC stock",
        "asset_class": "Semiconductors"
    },
    "Micron Technology": {
        "ticker": "MU",  # NASDAQ
        "news_query": "Micron Technology MU stock",
        "asset_class": "Semiconductors"
    },
    "iShares Semiconductor ETF": {
        "ticker": "SOXX",  # NASDAQ
        "news_query": "semiconductor ETF SOXX",
        "asset_class": "Semiconductors"
    },
    # ETFs & Other
    "Global X Copper Producers": {
        "ticker": "COPX",  # NYSE - Global X Copper Miners ETF
        "news_query": "copper producers ETF COPX",
        "asset_class": "Base Metals"
    },
    # Energy
    "Tourmaline Oil": {
        "ticker": "TOU.TO",  # TSX
        "news_query": "Tourmaline Oil TOU",
        "asset_class": "Energy"
    },
}

# Asset Class Definitions (for summary calculations)
# --------------------------------------------------
ASSET_CLASSES = {
    "Precious Metals": ["Gold", "Silver"],
    "Base Metals": ["Copper", "Alfamin Resources", "Global X Copper Producers"],
    "Crypto": ["Bitcoin", "Ethereum"],
    "Semiconductors": ["Lumentum", "Coherent", "Lattice Semiconductor", "Micron Technology", "iShares Semiconductor ETF"],
    "Energy": ["Tourmaline Oil"],
}

# Newsletter Settings
# -------------------
NEWS_ITEMS_PER_ASSET = 3  # Number of news headlines per asset
