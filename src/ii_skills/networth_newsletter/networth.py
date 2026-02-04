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


def add_to_history(net_worth_cad: float, net_worth_usd: float):
    """Add today's net worth to history."""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")

    # Remove existing entry for today if present
    history = [h for h in history if h["date"] != today]

    # Add new entry
    history.append({
        "date": today,
        "net_worth_cad": net_worth_cad,
        "net_worth_usd": net_worth_usd
    })

    # Keep only last 365 days
    history = sorted(history, key=lambda x: x["date"])[-365:]

    save_history(history)
    return history


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


def generate_html(data: dict, chart_base64: str = None) -> str:
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

    # Market holdings section
    if data["market_holdings"]:
        html += """
    <div class="section">
        <h2>Market Assets</h2>
        <table>
            <thead>
                <tr>
                    <th>Asset</th>
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
        for h in data["market_holdings"]:
            total_market_cad += h["value_cad"]
            total_cost_cad += h["cost_basis_cad"]
            gain_class = "positive" if h["gain_loss_cad"] >= 0 else "negative"
            # Show price in native currency
            currency = h.get("currency", "USD")
            if currency == "CAD":
                price_display = f"C${h['price_cad']:,.2f}"
            else:
                price_display = f"${h['price_usd']:,.2f}"
            html += f"""
                <tr>
                    <td><strong>{h["name"]}</strong></td>
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
                    <td colspan="3"><strong>Total Market Assets</strong></td>
                    <td><strong>{format_currency(total_market_cad, "CAD")}</strong></td>
                    <td>{format_currency(total_cost_cad, "CAD")}</td>
                    <td class="{gain_class}"><strong>{format_change(total_gain)}</strong></td>
                </tr>
            </tbody>
        </table>
    </div>
"""

    # Cash accounts section
    if data["cash_accounts"]:
        html += """
    <div class="section">
        <h2>Cash & Bank Accounts</h2>
        <table>
            <thead>
                <tr>
                    <th>Account</th>
                    <th>Balance</th>
                    <th>Value (USD)</th>
                    <th>Value (CAD)</th>
                </tr>
            </thead>
            <tbody>
"""
        total_cash_cad = 0
        for a in data["cash_accounts"]:
            total_cash_cad += a["value_cad"]
            html += f"""
                <tr>
                    <td><strong>{a["name"]}</strong></td>
                    <td>{a["currency"]} ${a["balance"]:,.2f}</td>
                    <td>${a["value_usd"]:,.2f}</td>
                    <td>{format_currency(a["value_cad"], "CAD")}</td>
                </tr>
"""
        html += f"""
                <tr class="total-row">
                    <td colspan="3"><strong>Total Cash</strong></td>
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

    # Update history
    print("Updating history...")
    history = add_to_history(net_worth_cad, net_worth_usd)
    print(f"History entries: {len(history)}")
    print()

    # Generate chart
    print("Generating chart...")
    chart_base64 = generate_chart(history)
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
        "history": history
    }

    # Generate HTML
    print("Generating newsletter...")
    html_content = generate_html(data, chart_base64)

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
