#!/usr/bin/env python3
"""
Daily Net Worth Newsletter Generator
Calculates net worth from various assets, tracks history, and sends a formatted email.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
import requests
import yfinance as yf
import json
import os
import base64
from io import BytesIO

# Try to import matplotlib for charting
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("Warning: matplotlib not installed. Charts will be disabled.")

from config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD,
    MARKET_HOLDINGS, CASH_ACCOUNTS, RETIREMENT_ACCOUNTS,
    REAL_ESTATE, LIABILITIES, BASE_CURRENCY, HISTORY_FILE
)

# Try to import portfolio analytics
try:
    from portfolio_analytics import run_portfolio_analytics
    ANALYTICS_AVAILABLE = True
except ImportError:
    ANALYTICS_AVAILABLE = False
    print("Warning: portfolio_analytics not available. Risk analytics will be disabled.")

# Get the directory where the script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_PATH = os.path.join(SCRIPT_DIR, HISTORY_FILE)


def fetch_exchange_rate() -> float:
    """Fetch current USD/CAD exchange rate."""
    try:
        ticker = yf.Ticker("USDCAD=X")
        hist = ticker.history(period="1d")
        if not hist.empty:
            return hist['Close'].iloc[-1]
        return 1.35  # Fallback rate
    except Exception as e:
        print(f"Error fetching exchange rate: {e}")
        return 1.35  # Fallback rate


def fetch_commodity_price(ticker: str) -> float:
    """Fetch commodity price from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return hist['Close'].iloc[-1]
        return 0
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return 0


def fetch_crypto_price(coin_id: str) -> float:
    """Fetch cryptocurrency price from CoinGecko."""
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get(coin_id, {}).get("usd", 0)
    except Exception as e:
        print(f"Error fetching {coin_id}: {e}")
        return 0


def fetch_stock_price(ticker: str) -> float:
    """Fetch stock price from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1d")
        if not hist.empty:
            return hist['Close'].iloc[-1]
        return 0
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return 0


def calculate_market_holdings(usd_to_cad: float) -> list:
    """Calculate current value of all market holdings."""
    holdings = []

    for name, config in MARKET_HOLDINGS.items():
        quantity = config["quantity"]
        cost_basis = config.get("cost_basis", 0)
        ticker = config["ticker"]
        asset_type = config["type"]
        unit = config.get("unit", "units")
        currency = config.get("currency", "USD")  # Default to USD for backward compatibility
        account = config.get("account", "")

        # Fetch current price (in native currency)
        if asset_type == "crypto":
            # CoinGecko returns USD prices
            price_native = fetch_crypto_price(ticker)
            price_currency = "USD"
        else:
            # Yahoo Finance returns price in the stock's native currency
            price_native = fetch_commodity_price(ticker) if asset_type == "commodity" else fetch_stock_price(ticker)
            price_currency = currency

        # Calculate values based on currency
        if price_currency == "CAD":
            # Price is already in CAD (Canadian stocks like .TO, .V)
            price_cad = price_native
            price_usd = price_native / usd_to_cad
            value_cad = quantity * price_cad
            value_usd = value_cad / usd_to_cad
            # Cost basis is in the same currency as the holding
            cost_basis_cad = cost_basis
            cost_basis_usd = cost_basis / usd_to_cad
        else:
            # Price is in USD (US stocks, crypto)
            price_usd = price_native
            price_cad = price_native * usd_to_cad
            value_usd = quantity * price_usd
            value_cad = value_usd * usd_to_cad
            # Cost basis is in USD for USD-denominated holdings
            cost_basis_usd = cost_basis
            cost_basis_cad = cost_basis * usd_to_cad

        gain_loss_usd = value_usd - cost_basis_usd
        gain_loss_cad = value_cad - cost_basis_cad
        gain_loss_pct = ((value_cad / cost_basis_cad) - 1) * 100 if cost_basis_cad > 0 else 0

        holdings.append({
            "name": name,
            "quantity": quantity,
            "unit": unit,
            "currency": currency,
            "account": account,
            "asset_class": config.get("asset_class", "Other"),
            "price_native": price_native,
            "price_usd": price_usd,
            "price_cad": price_cad,
            "value_usd": value_usd,
            "value_cad": value_cad,
            "cost_basis_usd": cost_basis_usd,
            "cost_basis_cad": cost_basis_cad,
            "gain_loss_usd": gain_loss_usd,
            "gain_loss_cad": gain_loss_cad,
            "gain_loss_pct": gain_loss_pct
        })

    return holdings


def calculate_asset_allocation(market_holdings: list, cash_accounts: list,
                                retirement_accounts: list, real_estate: list) -> dict:
    """Calculate asset allocation by asset class."""
    allocation = {}

    # Add market holdings by asset class
    for h in market_holdings:
        asset_class = h.get("asset_class", "Other")
        if asset_class not in allocation:
            allocation[asset_class] = 0
        allocation[asset_class] += h["value_cad"]

    # Add cash accounts as "Cash"
    total_cash = sum(a["value_cad"] for a in cash_accounts)
    if total_cash > 0:
        allocation["Cash"] = allocation.get("Cash", 0) + total_cash

    # Add retirement accounts as "Retirement"
    total_retirement = sum(a["value_cad"] for a in retirement_accounts)
    if total_retirement > 0:
        allocation["Retirement"] = allocation.get("Retirement", 0) + total_retirement

    # Add real estate as "Real Estate"
    total_real_estate = sum(p["value_cad"] for p in real_estate)
    if total_real_estate > 0:
        allocation["Real Estate"] = allocation.get("Real Estate", 0) + total_real_estate

    # Calculate total and percentages
    total = sum(allocation.values())
    allocation_with_pct = {}
    for asset_class, value in sorted(allocation.items(), key=lambda x: -x[1]):
        pct = (value / total * 100) if total > 0 else 0
        allocation_with_pct[asset_class] = {
            "value_cad": value,
            "percentage": pct
        }

    allocation_with_pct["_total"] = total
    return allocation_with_pct


def calculate_cash_accounts(usd_to_cad: float) -> list:
    """Calculate total cash holdings."""
    accounts = []

    for name, config in CASH_ACCOUNTS.items():
        balance = config["balance"]
        currency = config["currency"]

        if currency == "USD":
            value_usd = balance
            value_cad = balance * usd_to_cad
        else:  # CAD
            value_cad = balance
            value_usd = balance / usd_to_cad

        accounts.append({
            "name": name,
            "balance": balance,
            "currency": currency,
            "value_usd": value_usd,
            "value_cad": value_cad
        })

    return accounts


def calculate_retirement_accounts(usd_to_cad: float) -> list:
    """Calculate total retirement holdings."""
    accounts = []

    for name, config in RETIREMENT_ACCOUNTS.items():
        balance = config["balance"]
        currency = config["currency"]

        if currency == "USD":
            value_usd = balance
            value_cad = balance * usd_to_cad
        else:  # CAD
            value_cad = balance
            value_usd = balance / usd_to_cad

        accounts.append({
            "name": name,
            "balance": balance,
            "currency": currency,
            "value_usd": value_usd,
            "value_cad": value_cad
        })

    return accounts


def calculate_real_estate(usd_to_cad: float) -> list:
    """Calculate real estate values."""
    properties = []

    for name, config in REAL_ESTATE.items():
        value = config["value"]
        currency = config.get("currency", "CAD")

        if currency == "USD":
            value_usd = value
            value_cad = value * usd_to_cad
        else:  # CAD
            value_cad = value
            value_usd = value / usd_to_cad

        properties.append({
            "name": name,
            "value_usd": value_usd,
            "value_cad": value_cad
        })

    return properties


def calculate_liabilities(usd_to_cad: float) -> list:
    """Calculate total liabilities."""
    debts = []

    for name, config in LIABILITIES.items():
        balance = config["balance"]
        currency = config["currency"]

        if currency == "USD":
            value_usd = balance
            value_cad = balance * usd_to_cad
        else:  # CAD
            value_cad = balance
            value_usd = balance / usd_to_cad

        debts.append({
            "name": name,
            "balance": balance,
            "currency": currency,
            "value_usd": value_usd,
            "value_cad": value_cad
        })

    return debts


def load_history() -> list:
    """Load historical net worth data."""
    if os.path.exists(HISTORY_PATH):
        try:
            with open(HISTORY_PATH, 'r') as f:
                return json.load(f)
        except:
            return []
    return []


def save_history(history: list):
    """Save historical net worth data."""
    with open(HISTORY_PATH, 'w') as f:
        json.dump(history, f, indent=2)


def add_to_history(net_worth_cad: float, net_worth_usd: float,
                   market_holdings: list = None, cash_accounts: list = None,
                   liabilities: list = None):
    """Add today's net worth to history with per-holding snapshots."""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")

    # Remove existing entry for today if present
    history = [h for h in history if h["date"] != today]

    # Build entry with snapshots for contribution analysis
    entry = {
        "date": today,
        "net_worth_cad": net_worth_cad,
        "net_worth_usd": net_worth_usd
    }

    # Store per-holding value snapshots
    if market_holdings:
        entry["holdings_snapshot"] = {
            h["name"]: {"value_cad": h["value_cad"], "asset_class": h.get("asset_class", "Other")}
            for h in market_holdings
        }
    if cash_accounts:
        entry["cash_snapshot"] = {
            a["name"]: a["value_cad"] for a in cash_accounts
        }
    if liabilities:
        entry["liabilities_snapshot"] = {
            d["name"]: d["value_cad"] for d in liabilities
        }

    history.append(entry)

    # Keep only last 365 days
    history = sorted(history, key=lambda x: x["date"])[-365:]

    save_history(history)
    return history


def calculate_contribution_analysis(history: list) -> dict:
    """Calculate day-over-day contribution analysis from history snapshots."""
    if len(history) < 2:
        return None

    today = history[-1]
    yesterday = history[-2]

    # Need snapshots in both entries
    if "holdings_snapshot" not in today or "holdings_snapshot" not in yesterday:
        return None

    total_change = today["net_worth_cad"] - yesterday["net_worth_cad"]

    # Compare per-holding values
    movers = []
    today_holdings = today.get("holdings_snapshot", {})
    yesterday_holdings = yesterday.get("holdings_snapshot", {})

    all_names = set(list(today_holdings.keys()) + list(yesterday_holdings.keys()))
    for name in all_names:
        today_val = today_holdings.get(name, {}).get("value_cad", 0) if isinstance(today_holdings.get(name), dict) else 0
        yesterday_val = yesterday_holdings.get(name, {}).get("value_cad", 0) if isinstance(yesterday_holdings.get(name), dict) else 0
        change = today_val - yesterday_val
        asset_class = today_holdings.get(name, {}).get("asset_class", "Other") if isinstance(today_holdings.get(name), dict) else "Other"
        if abs(change) > 0.01:
            movers.append({
                "name": name,
                "change_cad": change,
                "asset_class": asset_class,
                "today_val": today_val,
                "yesterday_val": yesterday_val,
            })

    # Compare cash accounts
    today_cash = today.get("cash_snapshot", {})
    yesterday_cash = yesterday.get("cash_snapshot", {})
    cash_change = sum(today_cash.values()) - sum(yesterday_cash.values())

    # Compare liabilities
    today_liab = today.get("liabilities_snapshot", {})
    yesterday_liab = yesterday.get("liabilities_snapshot", {})
    liab_change = sum(today_liab.values()) - sum(yesterday_liab.values())

    # Sort by absolute impact
    movers.sort(key=lambda x: abs(x["change_cad"]), reverse=True)

    # Roll up by asset class
    class_changes = {}
    for m in movers:
        ac = m["asset_class"]
        class_changes[ac] = class_changes.get(ac, 0) + m["change_cad"]
    if abs(cash_change) > 0.01:
        class_changes["Cash (Accounts)"] = cash_change
    if abs(liab_change) > 0.01:
        class_changes["Liabilities"] = -liab_change  # reduction in liabilities is positive

    class_changes_sorted = sorted(class_changes.items(), key=lambda x: abs(x[1]), reverse=True)

    return {
        "total_change": total_change,
        "movers": movers,
        "class_changes": class_changes_sorted,
        "cash_change": cash_change,
        "liabilities_change": liab_change,
        "prev_date": yesterday["date"],
    }


def generate_chart(history: list) -> str:
    """Generate a net worth chart and return as base64 string."""
    if not MATPLOTLIB_AVAILABLE or len(history) < 2:
        return None

    # Filter to last 90 days
    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    recent = [h for h in history if h["date"] >= cutoff]

    if len(recent) < 2:
        # If not enough recent data, use all available
        recent = history[-90:] if len(history) > 90 else history

    if len(recent) < 2:
        return None

    dates = [datetime.strptime(h["date"], "%Y-%m-%d") for h in recent]
    values = [h["net_worth_cad"] for h in recent]

    # Create figure
    fig, ax = plt.subplots(figsize=(10, 4))

    # Plot line
    ax.plot(dates, values, color='#2563eb', linewidth=2, marker='o', markersize=4)

    # Fill under the line
    ax.fill_between(dates, values, alpha=0.1, color='#2563eb')

    # Formatting
    ax.set_title('Net Worth - Last 3 Months', fontsize=14, fontweight='bold', color='#1e3a8a')
    ax.set_ylabel('CAD $', fontsize=10)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))

    # Date formatting
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=45)

    # Grid
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)

    # Style
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    plt.tight_layout()

    # Save to bytes
    buffer = BytesIO()
    plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    buffer.seek(0)
    plt.close()

    return base64.b64encode(buffer.read()).decode()


def format_currency(value: float, currency: str = "CAD") -> str:
    """Format a value as currency."""
    symbol = "C$" if currency == "CAD" else "$"
    if value < 0:
        return f"-{symbol}{abs(value):,.2f}"
    return f"{symbol}{value:,.2f}"


def parse_holding_name(name: str) -> tuple:
    """Split 'Asset Name (Account)' into (asset, account). Falls back to (name, '')."""
    if "(" in name and name.endswith(")"):
        asset = name[:name.rfind("(")].strip()
        account = name[name.rfind("(") + 1:-1].strip()
        return asset, account
    return name, ""


def format_change(value: float, is_percent: bool = False) -> str:
    """Format a change value with color."""
    if is_percent:
        formatted = f"{value:+.2f}%"
    else:
        formatted = f"{value:+,.2f}"

    if value >= 0:
        return f'<span style="color: #22c55e;">{formatted}</span>'
    else:
        return f'<span style="color: #ef4444;">{formatted}</span>'


def generate_html(data: dict, chart_base64: str = None, analytics_html: str = None) -> str:
    """Generate the HTML newsletter."""
    today = datetime.now().strftime("%B %d, %Y")
    usd_cad = data["exchange_rate"]

    # Calculate totals
    total_assets_cad = data["total_assets_cad"]
    total_liabilities_cad = data["total_liabilities_cad"]
    net_worth_cad = data["net_worth_cad"]
    net_worth_usd = data["net_worth_usd"]

    # Get previous day's data for change
    history = data.get("history", [])
    daily_change_cad = 0
    if len(history) >= 2:
        daily_change_cad = history[-1]["net_worth_cad"] - history[-2]["net_worth_cad"]

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
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9fafb;
        }}
        .header {{
            background: linear-gradient(135deg, #065f46 0%, #10b981 100%);
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
        .net-worth-box {{
            background: white;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .net-worth-label {{
            font-size: 14px;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .net-worth-value {{
            font-size: 48px;
            font-weight: 700;
            color: #065f46;
            margin: 10px 0;
        }}
        .net-worth-usd {{
            font-size: 18px;
            color: #6b7280;
        }}
        .daily-change {{
            font-size: 16px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #e5e7eb;
        }}
        .exchange-rate {{
            font-size: 12px;
            color: #9ca3af;
            margin-top: 10px;
        }}
        .summary-row {{
            display: flex;
            justify-content: space-between;
            padding: 15px 0;
            border-bottom: 1px solid #e5e7eb;
        }}
        .summary-row:last-child {{
            border-bottom: none;
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
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}
        th {{
            background: #f3f4f6;
            padding: 10px 8px;
            text-align: left;
            font-weight: 600;
            color: #374151;
        }}
        td {{
            padding: 10px 8px;
            border-bottom: 1px solid #e5e7eb;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .positive {{
            color: #22c55e;
        }}
        .negative {{
            color: #ef4444;
        }}
        .total-row {{
            font-weight: 600;
            background: #f9fafb;
        }}
        .chart-section {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            text-align: center;
        }}
        .chart-section h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            color: #1e3a8a;
        }}
        .chart-section img {{
            max-width: 100%;
            height: auto;
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
        <h1>Daily Net Worth Report</h1>
        <p class="date">{today}</p>
    </div>

    <div class="net-worth-box">
        <div class="net-worth-label">Total Net Worth</div>
        <div class="net-worth-value">{format_currency(net_worth_cad, "CAD")}</div>
        <div class="net-worth-usd">{format_currency(net_worth_usd, "USD")} USD</div>
        <div class="daily-change">
            Daily Change: {format_change(daily_change_cad)} CAD
        </div>
        <div class="exchange-rate">USD/CAD: {usd_cad:.4f}</div>
    </div>
"""

    # Contribution Analysis section
    contribution = data.get("contribution")
    if contribution:
        total_chg = contribution["total_change"]
        prev_date = contribution["prev_date"]
        chg_color = "#22c55e" if total_chg >= 0 else "#ef4444"

        html += f"""
    <div class="section">
        <h2>What Moved Your Net Worth</h2>
        <p style="font-size: 13px; color: #6b7280; margin: 0 0 15px 0;">
            Change since {prev_date}: <strong style="color: {chg_color};">{format_change(total_chg)} CAD</strong>
        </p>
        <table>
            <thead>
                <tr>
                    <th>Asset</th>
                    <th>Account</th>
                    <th>Yesterday (CAD)</th>
                    <th>Today (CAD)</th>
                    <th>Change (CAD)</th>
                </tr>
            </thead>
            <tbody>
"""
        for m in contribution["movers"]:
            chg_class = "positive" if m["change_cad"] >= 0 else "negative"
            asset_name, account_name = parse_holding_name(m["name"])
            html += f"""
                <tr>
                    <td><strong>{asset_name}</strong></td>
                    <td style="color: #6b7280; font-size: 13px;">{account_name}</td>
                    <td>{format_currency(m["yesterday_val"], "CAD")}</td>
                    <td>{format_currency(m["today_val"], "CAD")}</td>
                    <td class="{chg_class}">{format_change(m["change_cad"])}</td>
                </tr>
"""
        # Cash and liability changes
        if abs(contribution["cash_change"]) > 0.01:
            chg_class = "positive" if contribution["cash_change"] >= 0 else "negative"
            html += f"""
                <tr>
                    <td><strong>Cash Accounts</strong></td>
                    <td></td>
                    <td colspan="2" style="color: #6b7280;">net change</td>
                    <td class="{chg_class}">{format_change(contribution["cash_change"])}</td>
                </tr>
"""
        if abs(contribution["liabilities_change"]) > 0.01:
            liab_impact = -contribution["liabilities_change"]
            chg_class = "positive" if liab_impact >= 0 else "negative"
            html += f"""
                <tr>
                    <td><strong>Liabilities</strong></td>
                    <td></td>
                    <td colspan="2" style="color: #6b7280;">net change</td>
                    <td class="{chg_class}">{format_change(liab_impact)}</td>
                </tr>
"""

        html += """
            </tbody>
        </table>
"""

        # Asset class rollup
        if contribution["class_changes"]:
            html += """
        <h3 style="font-size: 15px; color: #1e3a8a; margin: 20px 0 10px 0; padding-top: 15px; border-top: 1px solid #e5e7eb;">By Asset Class</h3>
        <table>
            <thead>
                <tr>
                    <th>Asset Class</th>
                    <th>Change (CAD)</th>
                </tr>
            </thead>
            <tbody>
"""
            for ac, chg in contribution["class_changes"]:
                chg_class = "positive" if chg >= 0 else "negative"
                html += f"""
                <tr>
                    <td><strong>{ac}</strong></td>
                    <td class="{chg_class}">{format_change(chg)}</td>
                </tr>
"""
            html += """
            </tbody>
        </table>
"""

        html += """
    </div>
"""

    # Chart section
    if chart_base64:
        html += f"""
    <div class="chart-section">
        <h2>Net Worth Trend (3 Months)</h2>
        <img src="data:image/png;base64,{chart_base64}" alt="Net Worth Chart">
    </div>
"""

    # Summary section
    html += f"""
    <div class="section">
        <h2>Summary</h2>
        <div class="summary-row">
            <span>Total Assets</span>
            <span style="color: #22c55e; font-weight: 600;">{format_currency(total_assets_cad, "CAD")}</span>
        </div>
        <div class="summary-row">
            <span>Total Liabilities</span>
            <span style="color: #ef4444; font-weight: 600;">-{format_currency(total_liabilities_cad, "CAD")}</span>
        </div>
        <div class="summary-row" style="font-weight: 700; font-size: 18px;">
            <span>Net Worth</span>
            <span style="color: #065f46;">{format_currency(net_worth_cad, "CAD")}</span>
        </div>
    </div>
"""

    # Asset Allocation section
    asset_allocation = data.get("asset_allocation", {})
    if asset_allocation:
        # Color map for asset classes
        colors = {
            "Equities": "#3b82f6",      # Blue
            "Fixed Income": "#10b981",  # Green
            "Commodities": "#f59e0b",   # Amber
            "Crypto": "#8b5cf6",        # Purple
            "Cash": "#6b7280",          # Gray
            "Retirement": "#ec4899",    # Pink
            "Real Estate": "#14b8a6",   # Teal
            "Other": "#94a3b8"          # Slate
        }

        html += """
    <div class="section">
        <h2>Asset Allocation</h2>
        <table>
            <thead>
                <tr>
                    <th>Asset Class</th>
                    <th>Value (CAD)</th>
                    <th>Weight</th>
                    <th>Allocation</th>
                </tr>
            </thead>
            <tbody>
"""
        for asset_class, alloc_data in asset_allocation.items():
            if asset_class == "_total":
                continue
            value = alloc_data["value_cad"]
            pct = alloc_data["percentage"]
            color = colors.get(asset_class, "#94a3b8")
            bar_width = min(pct, 100)  # Cap at 100% for display
            html += f"""
                <tr>
                    <td><strong style="color: {color};">{asset_class}</strong></td>
                    <td>{format_currency(value, "CAD")}</td>
                    <td>{pct:.1f}%</td>
                    <td>
                        <div style="background: #e5e7eb; border-radius: 4px; height: 20px; width: 100%;">
                            <div style="background: {color}; border-radius: 4px; height: 20px; width: {bar_width}%;"></div>
                        </div>
                    </td>
                </tr>
"""
        html += """
            </tbody>
        </table>
    </div>
"""

    # Risk Analytics section (if available)
    if analytics_html:
        html += analytics_html

    # Split market holdings into investable assets vs cash-equivalents
    cash_holdings = [h for h in data["market_holdings"] if h.get("asset_class") == "Cash"]
    market_only = [h for h in data["market_holdings"] if h.get("asset_class") != "Cash"]

    # Market holdings section (excludes cash-classified holdings)
    if market_only:
        html += """
    <div class="section">
        <h2>Market Assets</h2>
        <table>
            <thead>
                <tr>
                    <th>Asset</th>
                    <th>Account</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Value (CAD)</th>
                    <th>Cost Basis</th>
                    <th>Gain/Loss</th>
                </tr>
            </thead>
            <tbody>
"""
        total_market_cad = 0
        total_cost_cad = 0
        for h in market_only:
            total_market_cad += h["value_cad"]
            total_cost_cad += h["cost_basis_cad"]
            gain_class = "positive" if h["gain_loss_cad"] >= 0 else "negative"
            asset_name, account_name = parse_holding_name(h["name"])
            currency = h.get("currency", "USD")
            if currency == "CAD":
                price_display = f"C${h['price_cad']:,.2f}"
            else:
                price_display = f"${h['price_usd']:,.2f}"
            html += f"""
                <tr>
                    <td><strong>{asset_name}</strong></td>
                    <td style="color: #6b7280; font-size: 13px;">{account_name}</td>
                    <td>{h["quantity"]} {h["unit"]}</td>
                    <td>{price_display}</td>
                    <td>{format_currency(h["value_cad"], "CAD")}</td>
                    <td>{format_currency(h["cost_basis_cad"], "CAD")}</td>
                    <td class="{gain_class}">{format_change(h["gain_loss_cad"])} ({h["gain_loss_pct"]:+.1f}%)</td>
                </tr>
"""
        total_gain = total_market_cad - total_cost_cad
        gain_class = "positive" if total_gain >= 0 else "negative"
        html += f"""
                <tr class="total-row">
                    <td colspan="4"><strong>Total Market Assets</strong></td>
                    <td><strong>{format_currency(total_market_cad, "CAD")}</strong></td>
                    <td>{format_currency(total_cost_cad, "CAD")}</td>
                    <td class="{gain_class}"><strong>{format_change(total_gain)}</strong></td>
                </tr>
            </tbody>
        </table>
    </div>
"""

    # Cash & Cash Equivalents section (account cash + cash-classified market holdings)
    all_cash = data["cash_accounts"] or []
    if all_cash or cash_holdings:
        html += """
    <div class="section">
        <h2>Cash &amp; Cash Equivalents</h2>
        <table>
            <thead>
                <tr>
                    <th>Instrument</th>
                    <th>Account</th>
                    <th>Details</th>
                    <th>Value (USD)</th>
                    <th>Value (CAD)</th>
                </tr>
            </thead>
            <tbody>
"""
        total_cash_cad = 0

        # Cash-equivalent market holdings first (JPST, CASH.TO, TCSH, etc.)
        for h in cash_holdings:
            total_cash_cad += h["value_cad"]
            asset_name, account_name = parse_holding_name(h["name"])
            currency = h.get("currency", "USD")
            if currency == "CAD":
                price_display = f"{h['quantity']} shares @ C${h['price_cad']:,.2f}"
            else:
                price_display = f"{h['quantity']} shares @ ${h['price_usd']:,.2f}"
            html += f"""
                <tr>
                    <td><strong>{asset_name}</strong></td>
                    <td style="color: #6b7280; font-size: 13px;">{account_name}</td>
                    <td>{price_display}</td>
                    <td>${h["value_usd"]:,.2f}</td>
                    <td>{format_currency(h["value_cad"], "CAD")}</td>
                </tr>
"""

        # Account cash balances
        for a in all_cash:
            total_cash_cad += a["value_cad"]
            html += f"""
                <tr>
                    <td><strong>Cash</strong></td>
                    <td style="color: #6b7280; font-size: 13px;">{a["name"]}</td>
                    <td>{a["currency"]} ${a["balance"]:,.2f}</td>
                    <td>${a["value_usd"]:,.2f}</td>
                    <td>{format_currency(a["value_cad"], "CAD")}</td>
                </tr>
"""
        html += f"""
                <tr class="total-row">
                    <td colspan="4"><strong>Total Cash &amp; Equivalents</strong></td>
                    <td><strong>{format_currency(total_cash_cad, "CAD")}</strong></td>
                </tr>
            </tbody>
        </table>
    </div>
"""

    # Liabilities section
    if data["liabilities"]:
        html += """
    <div class="section">
        <h2>Liabilities</h2>
        <table>
            <thead>
                <tr>
                    <th>Debt</th>
                    <th>Balance</th>
                    <th>Value (USD)</th>
                    <th>Value (CAD)</th>
                </tr>
            </thead>
            <tbody>
"""
        total_debt_cad = 0
        for d in data["liabilities"]:
            total_debt_cad += d["value_cad"]
            html += f"""
                <tr>
                    <td><strong>{d["name"]}</strong></td>
                    <td>{d["currency"]} ${d["balance"]:,.2f}</td>
                    <td style="color: #ef4444;">-${d["value_usd"]:,.2f}</td>
                    <td style="color: #ef4444;">-{format_currency(d["value_cad"], "CAD")}</td>
                </tr>
"""
        html += f"""
                <tr class="total-row">
                    <td colspan="3"><strong>Total Liabilities</strong></td>
                    <td style="color: #ef4444;"><strong>-{format_currency(total_debt_cad, "CAD")}</strong></td>
                </tr>
            </tbody>
        </table>
    </div>
"""

    html += """
    <div class="footer">
        <p>Generated automatically by Daily Net Worth Newsletter</p>
        <p>Prices sourced from Yahoo Finance and CoinGecko</p>
    </div>
</body>
</html>
"""
    return html


def send_email(html_content: str) -> bool:
    """Send the newsletter via Gmail SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Daily Net Worth Report - {datetime.now().strftime('%B %d, %Y')}"
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
    """Main function to generate and send the net worth newsletter."""
    print("=" * 50)
    print("Daily Net Worth Newsletter Generator")
    print("=" * 50)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Fetch exchange rate
    print("Fetching USD/CAD exchange rate...")
    usd_to_cad = fetch_exchange_rate()
    print(f"USD/CAD: {usd_to_cad:.4f}")
    print()

    # Calculate all holdings
    print("Calculating market holdings...")
    market_holdings = calculate_market_holdings(usd_to_cad)

    print("Calculating cash accounts...")
    cash_accounts = calculate_cash_accounts(usd_to_cad)

    print("Calculating retirement accounts...")
    retirement_accounts = calculate_retirement_accounts(usd_to_cad)

    print("Calculating real estate...")
    real_estate = calculate_real_estate(usd_to_cad)

    print("Calculating liabilities...")
    liabilities = calculate_liabilities(usd_to_cad)
    print()

    # Calculate totals
    total_market_cad = sum(h["value_cad"] for h in market_holdings)
    total_cash_cad = sum(a["value_cad"] for a in cash_accounts)
    total_retirement_cad = sum(a["value_cad"] for a in retirement_accounts)
    total_real_estate_cad = sum(p["value_cad"] for p in real_estate)
    total_liabilities_cad = sum(d["value_cad"] for d in liabilities)

    total_assets_cad = total_market_cad + total_cash_cad + total_retirement_cad + total_real_estate_cad
    net_worth_cad = total_assets_cad - total_liabilities_cad
    net_worth_usd = net_worth_cad / usd_to_cad

    print(f"Total Assets (CAD): ${total_assets_cad:,.2f}")
    print(f"Total Liabilities (CAD): ${total_liabilities_cad:,.2f}")
    print(f"Net Worth (CAD): ${net_worth_cad:,.2f}")
    print(f"Net Worth (USD): ${net_worth_usd:,.2f}")
    print()

    # Calculate asset allocation
    print("Calculating asset allocation...")
    asset_allocation = calculate_asset_allocation(
        market_holdings, cash_accounts, retirement_accounts, real_estate
    )
    for asset_class, data in asset_allocation.items():
        if asset_class != "_total":
            print(f"  {asset_class}: ${data['value_cad']:,.2f} ({data['percentage']:.1f}%)")
    print()

    # Update history (with per-holding snapshots for contribution analysis)
    print("Updating history...")
    history = add_to_history(net_worth_cad, net_worth_usd,
                             market_holdings, cash_accounts, liabilities)
    print(f"History entries: {len(history)}")

    # Calculate contribution analysis
    print("Calculating contribution analysis...")
    contribution = calculate_contribution_analysis(history)
    if contribution:
        print(f"  Net worth change: ${contribution['total_change']:+,.2f} CAD")
        for m in contribution["movers"][:5]:
            print(f"  {m['name']}: ${m['change_cad']:+,.2f}")
    else:
        print("  No previous snapshot available (will be available tomorrow)")
    print()

    # Generate chart
    print("Generating chart...")
    chart_base64 = generate_chart(history)
    print()

    # Run portfolio analytics (if available)
    analytics_html = None
    if ANALYTICS_AVAILABLE:
        try:
            print("Running portfolio risk analytics...")
            # Build holdings dict with current values for analytics
            holdings_for_analytics = {}
            for h in market_holdings:
                name = h["name"]
                holdings_for_analytics[name] = {
                    "ticker": MARKET_HOLDINGS[name]["ticker"],
                    "value_cad": h["value_cad"],
                    "asset_class": h.get("asset_class", "Other"),
                    "type": MARKET_HOLDINGS[name].get("type", "stock"),
                }

            _, _, _, analytics_html = run_portfolio_analytics(
                holdings_for_analytics,
                asset_allocation
            )
            print("Portfolio analytics completed.")
        except Exception as e:
            print(f"Warning: Portfolio analytics failed: {e}")
            analytics_html = None
    print()

    # Prepare data for HTML
    data = {
        "exchange_rate": usd_to_cad,
        "market_holdings": market_holdings,
        "cash_accounts": cash_accounts,
        "retirement_accounts": retirement_accounts,
        "real_estate": real_estate,
        "liabilities": liabilities,
        "asset_allocation": asset_allocation,
        "total_assets_cad": total_assets_cad,
        "total_liabilities_cad": total_liabilities_cad,
        "net_worth_cad": net_worth_cad,
        "net_worth_usd": net_worth_usd,
        "history": history,
        "contribution": contribution
    }

    # Generate HTML
    print("Generating newsletter...")
    html_content = generate_html(data, chart_base64, analytics_html)

    # Send email
    print("Sending email...")
    success = send_email(html_content)

    if success:
        print("\nNewsletter sent successfully!")
    else:
        print("\nFailed to send newsletter. Check your config.py settings.")

    print("=" * 50)


if __name__ == "__main__":
    main()
