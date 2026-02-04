# Daily Net Worth Newsletter Configuration
# =========================================
# Copy this file and fill in your actual values

# Gmail Configuration
# -------------------
# 1. Enable 2-Factor Authentication on your Gmail account
# 2. Go to https://myaccount.google.com/apppasswords
# 3. Create an App Password for "Mail" and copy it here
GMAIL_ADDRESS = "your.email@gmail.com"
GMAIL_APP_PASSWORD = "xxxx xxxx xxxx xxxx"  # 16-character app password

# ===========================================
# HOLDINGS - Update with your actual holdings
# ===========================================

# Asset Class Definitions
# - Equities: Individual stocks, equity ETFs
# - Fixed Income: Bonds, bond ETFs, money market
# - Commodities: Physical metals, commodity trusts
# - Crypto: Cryptocurrencies
# - Cash: Cash, high-interest savings
# - Retirement: Pension funds (mixed/unknown allocation)

# Market Assets - Fetches live prices from Yahoo Finance / CoinGecko
MARKET_HOLDINGS = {
    # Example: Stock holding
    "Example Stock": {
        "quantity": 100,
        "cost_basis": 5000,  # Total cost basis in the holding's currency
        "ticker": "AAPL",    # Yahoo Finance ticker
        "type": "stock",
        "asset_class": "Equities",
        "currency": "USD",   # USD or CAD
        "unit": "shares",
        "account": "Brokerage"
    },
    # Example: Canadian stock (TSX)
    "Example Canadian Stock": {
        "quantity": 50,
        "cost_basis": 2500,
        "ticker": "BN.TO",   # .TO suffix for TSX, .V for TSX-V
        "type": "stock",
        "asset_class": "Equities",
        "currency": "CAD",
        "unit": "shares",
        "account": "TFSA"
    },
    # Example: Cryptocurrency
    "Bitcoin": {
        "quantity": 0.1,
        "cost_basis": 5000,
        "ticker": "bitcoin",  # CoinGecko ID
        "type": "crypto",
        "asset_class": "Crypto",
        "currency": "USD",
        "unit": "BTC",
        "account": "Coinbase"
    },
    # Example: Commodity
    "Physical Gold": {
        "quantity": 1.0,
        "cost_basis": 2000,
        "ticker": "GC=F",    # Gold futures ticker
        "type": "commodity",
        "asset_class": "Commodities",
        "currency": "USD",
        "unit": "oz",
        "account": "Physical"
    },
}

# Cash & Bank Accounts (all classified as "Cash" asset class)
CASH_ACCOUNTS = {
    "Checking Account": {
        "balance": 5000.00,
        "currency": "CAD"
    },
    "Savings Account": {
        "balance": 10000.00,
        "currency": "CAD"
    },
}

# Retirement Accounts (classified as "Retirement" asset class)
RETIREMENT_ACCOUNTS = {
    "401k / RRSP": {
        "balance": 50000.00,
        "currency": "CAD"
    },
}

# Real Estate (classified as "Real Estate" asset class)
REAL_ESTATE = {
    # "Primary Residence": {
    #     "value": 500000,
    #     "currency": "CAD"
    # },
}

# Liabilities (Debts)
LIABILITIES = {
    "Student Loans": {
        "balance": 20000.00,
        "currency": "CAD"
    },
}

# ===========================================
# DISPLAY SETTINGS
# ===========================================
BASE_CURRENCY = "CAD"  # Primary display currency
HISTORY_FILE = "networth_history.json"
