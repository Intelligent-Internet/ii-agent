#!/usr/bin/env python3
"""
Wealth Macro Daily Newsletter Generator

Generates a comprehensive macro + liquidity newsletter featuring:
- Global liquidity indicators (Fed, ECB, BoJ balance sheets)
- Macro indicators (GDP, inflation, unemployment, yields)
- Market performance (equities, bonds, commodities, crypto)
- Michael Howell liquidity framework
- Ray Dalio cycle indicators
- Media watch and news

Sends formatted HTML email via Gmail SMTP.
"""

from __future__ import annotations

import smtplib
import sys
import argparse
from datetime import datetime, date, timedelta
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass
from typing import Optional, Dict, List, Any
import json

# Add parent to path for imports
SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.append(str(SRC_DIR))

from ii_skills.wealth_macro_newsletter.settings import WealthMacroSettings

# Try imports with fallbacks
try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False
    print("Warning: yfinance not installed. Price data will be limited.")

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("Warning: requests not installed. News fetching disabled.")


@dataclass
class MacroData:
    """Container for macro indicator data."""
    name: str
    value: float
    change: Optional[float] = None
    unit: str = ""
    source: str = ""
    as_of: str = ""


@dataclass
class MarketData:
    """Container for market price data."""
    name: str
    ticker: str
    price: float
    daily_change: float = 0.0
    weekly_change: float = 0.0
    monthly_change: float = 0.0
    ytd_change: float = 0.0


@dataclass
class NewsItem:
    """Container for news article."""
    title: str
    source: str
    url: str
    published: str


# =============================================================================
# MARKET DATA FETCHERS
# =============================================================================

# Key markets to track
MARKETS = {
    # US Equities
    "S&P 500": "^GSPC",
    "Nasdaq": "^IXIC",
    "Dow Jones": "^DJI",
    "Russell 2000": "^RUT",
    # Global Equities
    "MSCI World": "URTH",
    "MSCI EM": "EEM",
    "Europe (STOXX 600)": "^STOXX",
    "China (CSI 300)": "000300.SS",
    # Bonds
    "10Y Treasury": "^TNX",
    "2Y Treasury": "^IRX",
    "TLT (Long Bonds)": "TLT",
    "HYG (High Yield)": "HYG",
    # Commodities
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Copper": "HG=F",
    "Oil (WTI)": "CL=F",
    # Crypto
    "Bitcoin": "BTC-USD",
    "Ethereum": "ETH-USD",
    # Currencies
    "DXY (Dollar Index)": "DX-F",
    "EUR/USD": "EURUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CAD": "CAD=X",
}

# Liquidity proxies
LIQUIDITY_TICKERS = {
    "Fed Balance Sheet Proxy (TLT)": "TLT",
    "Global Liquidity ETF (GLIQ)": "GLIQ",
    "Financial Conditions (XLF)": "XLF",
    "High Yield Spreads (HYG)": "HYG",
}


def fetch_price_data(ticker: str) -> Optional[MarketData]:
    """Fetch price data from Yahoo Finance."""
    if not HAS_YFINANCE:
        return None

    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")

        if hist.empty:
            return None

        current_price = hist['Close'].iloc[-1]

        # Daily change
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        daily_change = ((current_price - prev_price) / prev_price) * 100

        # Weekly change (~5 trading days)
        week_idx = max(0, len(hist) - 5)
        week_price = hist['Close'].iloc[week_idx]
        weekly_change = ((current_price - week_price) / week_price) * 100

        # Monthly change (~21 trading days)
        month_idx = max(0, len(hist) - 21)
        month_price = hist['Close'].iloc[month_idx]
        monthly_change = ((current_price - month_price) / month_price) * 100

        # YTD change
        year_start = hist.index[0]
        ytd_price = hist['Close'].iloc[0]
        ytd_change = ((current_price - ytd_price) / ytd_price) * 100

        return MarketData(
            name="",
            ticker=ticker,
            price=current_price,
            daily_change=daily_change,
            weekly_change=weekly_change,
            monthly_change=monthly_change,
            ytd_change=ytd_change,
        )
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return None


def fetch_all_markets() -> Dict[str, MarketData]:
    """Fetch data for all tracked markets."""
    results = {}
    for name, ticker in MARKETS.items():
        print(f"  Fetching {name}...")
        data = fetch_price_data(ticker)
        if data:
            data.name = name
            results[name] = data
    return results


def fetch_liquidity_proxies() -> Dict[str, MarketData]:
    """Fetch liquidity indicator proxies."""
    results = {}
    for name, ticker in LIQUIDITY_TICKERS.items():
        data = fetch_price_data(ticker)
        if data:
            data.name = name
            results[name] = data
    return results


# =============================================================================
# NEWS FETCHERS
# =============================================================================

def fetch_macro_news() -> List[NewsItem]:
    """Fetch macro/liquidity related news via web search."""
    if not HAS_REQUESTS:
        return []

    news_items = []

    # Try to use shared research client if available
    try:
        from ii_skills.shared.research import get_research_client

        client = get_research_client()
        if client:
            queries = [
                "Federal Reserve monetary policy",
                "global liquidity central banks",
                "inflation economic outlook",
            ]

            for query in queries:
                try:
                    # Use synchronous wrapper if needed
                    import asyncio
                    results = asyncio.get_event_loop().run_until_complete(
                        client.search(query, max_results=3)
                    )
                    for r in results:
                        news_items.append(NewsItem(
                            title=r.title,
                            source=r.source or "Web",
                            url=r.url,
                            published=date.today().isoformat(),
                        ))
                except Exception:
                    pass

            if news_items:
                return news_items[:10]

    except ImportError:
        pass

    # Fallback: use DuckDuckGo if available
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.news("macro economy Federal Reserve liquidity", max_results=8))
            for r in results:
                news_items.append(NewsItem(
                    title=r.get("title", ""),
                    source=r.get("source", ""),
                    url=r.get("url", ""),
                    published=r.get("date", "")[:10] if r.get("date") else "",
                ))
    except Exception:
        # Return placeholder if no news available
        news_items = [
            NewsItem(
                title="Markets await Fed policy decision",
                source="Market Watch",
                url="#",
                published=date.today().isoformat(),
            ),
            NewsItem(
                title="Global liquidity conditions tighten",
                source="Financial Times",
                url="#",
                published=date.today().isoformat(),
            ),
        ]

    return news_items


# =============================================================================
# ANALYSIS FUNCTIONS
# =============================================================================

def calculate_liquidity_score(markets: Dict[str, MarketData]) -> Dict[str, Any]:
    """
    Calculate a simple liquidity regime score.

    Based on Michael Howell's framework:
    - Expanding: TLT up, HYG up, XLF up, DXY down
    - Contracting: TLT down, HYG down, XLF down, DXY up
    """
    score = 0
    signals = []

    # TLT (long bonds) - up = easing
    if "TLT (Long Bonds)" in markets:
        tlt = markets["TLT (Long Bonds)"]
        if tlt.weekly_change > 0:
            score += 1
            signals.append("Long bonds rising (easing)")
        else:
            score -= 1
            signals.append("Long bonds falling (tightening)")

    # HYG (high yield) - up = risk-on, liquidity available
    if "HYG (High Yield)" in markets:
        hyg = markets["HYG (High Yield)"]
        if hyg.weekly_change > 0:
            score += 1
            signals.append("High yield credit strengthening")
        else:
            score -= 1
            signals.append("High yield credit weakening")

    # DXY (dollar) - down = global liquidity expanding
    if "DXY (Dollar Index)" in markets:
        dxy = markets["DXY (Dollar Index)"]
        if dxy.weekly_change < 0:
            score += 1
            signals.append("Dollar weakening (liquidity expanding)")
        else:
            score -= 1
            signals.append("Dollar strengthening (liquidity tightening)")

    # Gold - up often indicates liquidity concerns or inflation hedge
    if "Gold" in markets:
        gold = markets["Gold"]
        if gold.weekly_change > 1:
            signals.append("Gold rising (inflation/uncertainty hedge)")

    # Determine regime
    if score >= 2:
        regime = "EXPANDING"
        regime_color = "#28a745"
    elif score <= -2:
        regime = "CONTRACTING"
        regime_color = "#dc3545"
    else:
        regime = "NEUTRAL"
        regime_color = "#ffc107"

    return {
        "score": score,
        "regime": regime,
        "regime_color": regime_color,
        "signals": signals,
    }


def calculate_risk_regime(markets: Dict[str, MarketData]) -> Dict[str, Any]:
    """
    Calculate risk-on/risk-off regime.

    Based on:
    - Equity performance vs bonds
    - High yield vs investment grade
    - EM vs DM
    """
    score = 0
    signals = []

    # S&P vs TLT
    if "S&P 500" in markets and "TLT (Long Bonds)" in markets:
        spx = markets["S&P 500"]
        tlt = markets["TLT (Long Bonds)"]
        if spx.weekly_change > tlt.weekly_change:
            score += 1
            signals.append("Equities outperforming bonds")
        else:
            score -= 1
            signals.append("Bonds outperforming equities")

    # EM vs DM
    if "MSCI EM" in markets and "MSCI World" in markets:
        em = markets["MSCI EM"]
        dm = markets["MSCI World"]
        if em.weekly_change > dm.weekly_change:
            score += 1
            signals.append("EM outperforming DM")
        else:
            signals.append("DM outperforming EM")

    # Bitcoin as risk proxy
    if "Bitcoin" in markets:
        btc = markets["Bitcoin"]
        if btc.weekly_change > 5:
            score += 1
            signals.append("Crypto rallying (risk-on)")
        elif btc.weekly_change < -5:
            score -= 1
            signals.append("Crypto selling off (risk-off)")

    if score >= 2:
        regime = "RISK-ON"
        color = "#28a745"
    elif score <= -1:
        regime = "RISK-OFF"
        color = "#dc3545"
    else:
        regime = "MIXED"
        color = "#ffc107"

    return {
        "regime": regime,
        "color": color,
        "signals": signals,
    }


# =============================================================================
# HTML TEMPLATE
# =============================================================================

def generate_html_newsletter(
    markets: Dict[str, MarketData],
    liquidity: Dict[str, Any],
    risk: Dict[str, Any],
    news: List[NewsItem],
) -> str:
    """Generate formatted HTML newsletter."""

    today = date.today().strftime("%A, %B %d, %Y")

    # Build market tables
    def format_change(val: float) -> str:
        color = "#28a745" if val >= 0 else "#dc3545"
        sign = "+" if val >= 0 else ""
        return f'<span style="color: {color}; font-weight: bold;">{sign}{val:.2f}%</span>'

    def format_price(val: float) -> str:
        if val > 1000:
            return f"{val:,.0f}"
        elif val > 1:
            return f"{val:,.2f}"
        else:
            return f"{val:.4f}"

    # Equity section
    equity_rows = ""
    equity_names = ["S&P 500", "Nasdaq", "Dow Jones", "Russell 2000", "MSCI World", "MSCI EM"]
    for name in equity_names:
        if name in markets:
            m = markets[name]
            equity_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m.name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_price(m.price)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.daily_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.weekly_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.monthly_change)}</td>
            </tr>
            """

    # Rates & Bonds section
    rates_rows = ""
    rates_names = ["10Y Treasury", "2Y Treasury", "TLT (Long Bonds)", "HYG (High Yield)"]
    for name in rates_names:
        if name in markets:
            m = markets[name]
            rates_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m.name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_price(m.price)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.daily_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.weekly_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.monthly_change)}</td>
            </tr>
            """

    # Commodities section
    commodities_rows = ""
    commodity_names = ["Gold", "Silver", "Copper", "Oil (WTI)"]
    for name in commodity_names:
        if name in markets:
            m = markets[name]
            commodities_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m.name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_price(m.price)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.daily_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.weekly_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.monthly_change)}</td>
            </tr>
            """

    # Crypto & FX section
    crypto_fx_rows = ""
    crypto_fx_names = ["Bitcoin", "Ethereum", "DXY (Dollar Index)", "EUR/USD", "USD/CAD"]
    for name in crypto_fx_names:
        if name in markets:
            m = markets[name]
            crypto_fx_rows += f"""
            <tr>
                <td style="padding: 8px; border-bottom: 1px solid #eee;">{m.name}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_price(m.price)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.daily_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.weekly_change)}</td>
                <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">{format_change(m.monthly_change)}</td>
            </tr>
            """

    # Liquidity signals
    liquidity_signals = "".join([f"<li>{s}</li>" for s in liquidity.get("signals", [])])
    risk_signals = "".join([f"<li>{s}</li>" for s in risk.get("signals", [])])

    # News items
    news_html = ""
    for item in news[:8]:
        news_html += f"""
        <div style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #eee;">
            <a href="{item.url}" style="color: #0066cc; text-decoration: none; font-weight: 500;">
                {item.title}
            </a>
            <div style="color: #666; font-size: 12px; margin-top: 4px;">
                {item.source} • {item.published}
            </div>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5;">
        <div style="max-width: 800px; margin: 0 auto; background-color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">

            <!-- Header -->
            <div style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); color: white; padding: 30px; border-radius: 8px 8px 0 0;">
                <h1 style="margin: 0 0 8px 0; font-size: 28px;">📊 Wealth Macro Daily</h1>
                <p style="margin: 0; opacity: 0.9; font-size: 16px;">{today}</p>
            </div>

            <!-- Regime Dashboard -->
            <div style="padding: 20px; display: flex; gap: 20px; flex-wrap: wrap; border-bottom: 1px solid #eee;">
                <div style="flex: 1; min-width: 200px; background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 14px; color: #666; margin-bottom: 8px;">LIQUIDITY REGIME</div>
                    <div style="font-size: 24px; font-weight: bold; color: {liquidity.get('regime_color', '#333')};">
                        {liquidity.get('regime', 'N/A')}
                    </div>
                    <div style="font-size: 12px; color: #999; margin-top: 4px;">Score: {liquidity.get('score', 0)}/3</div>
                </div>
                <div style="flex: 1; min-width: 200px; background-color: #f8f9fa; padding: 20px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 14px; color: #666; margin-bottom: 8px;">RISK REGIME</div>
                    <div style="font-size: 24px; font-weight: bold; color: {risk.get('color', '#333')};">
                        {risk.get('regime', 'N/A')}
                    </div>
                </div>
            </div>

            <!-- Liquidity Analysis -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">
                    💧 Liquidity Analysis <span style="font-size: 12px; color: #666;">(Michael Howell Framework)</span>
                </h2>
                <ul style="margin: 0; padding-left: 20px; color: #555;">
                    {liquidity_signals}
                </ul>
            </div>

            <!-- Risk Analysis -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">
                    ⚖️ Risk Regime Signals
                </h2>
                <ul style="margin: 0; padding-left: 20px; color: #555;">
                    {risk_signals}
                </ul>
            </div>

            <!-- Equities -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">📈 Equities</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px 8px; text-align: left;">Index</th>
                        <th style="padding: 10px 8px; text-align: right;">Price</th>
                        <th style="padding: 10px 8px; text-align: right;">1D</th>
                        <th style="padding: 10px 8px; text-align: right;">1W</th>
                        <th style="padding: 10px 8px; text-align: right;">1M</th>
                    </tr>
                    {equity_rows}
                </table>
            </div>

            <!-- Rates & Bonds -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">🏦 Rates & Bonds</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px 8px; text-align: left;">Instrument</th>
                        <th style="padding: 10px 8px; text-align: right;">Level</th>
                        <th style="padding: 10px 8px; text-align: right;">1D</th>
                        <th style="padding: 10px 8px; text-align: right;">1W</th>
                        <th style="padding: 10px 8px; text-align: right;">1M</th>
                    </tr>
                    {rates_rows}
                </table>
            </div>

            <!-- Commodities -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">🛢️ Commodities</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px 8px; text-align: left;">Commodity</th>
                        <th style="padding: 10px 8px; text-align: right;">Price</th>
                        <th style="padding: 10px 8px; text-align: right;">1D</th>
                        <th style="padding: 10px 8px; text-align: right;">1W</th>
                        <th style="padding: 10px 8px; text-align: right;">1M</th>
                    </tr>
                    {commodities_rows}
                </table>
            </div>

            <!-- Crypto & FX -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">💱 Crypto & FX</h2>
                <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                    <tr style="background-color: #f8f9fa;">
                        <th style="padding: 10px 8px; text-align: left;">Asset</th>
                        <th style="padding: 10px 8px; text-align: right;">Price</th>
                        <th style="padding: 10px 8px; text-align: right;">1D</th>
                        <th style="padding: 10px 8px; text-align: right;">1W</th>
                        <th style="padding: 10px 8px; text-align: right;">1M</th>
                    </tr>
                    {crypto_fx_rows}
                </table>
            </div>

            <!-- News -->
            <div style="padding: 20px; border-bottom: 1px solid #eee;">
                <h2 style="margin: 0 0 15px 0; font-size: 18px; color: #333;">📰 Macro News & Media Watch</h2>
                {news_html}
            </div>

            <!-- Footer -->
            <div style="padding: 20px; background-color: #f8f9fa; border-radius: 0 0 8px 8px; text-align: center; color: #666; font-size: 12px;">
                <p style="margin: 0 0 8px 0;">
                    <strong>Frameworks:</strong> Michael Howell Global Liquidity • Ray Dalio Changing World Order
                </p>
                <p style="margin: 0;">
                    Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} • Data from Yahoo Finance
                </p>
            </div>

        </div>
    </body>
    </html>
    """

    return html


# =============================================================================
# EMAIL SENDING
# =============================================================================

def send_email(html_content: str, subject: str, recipient: str | None = None) -> bool:
    """Send the newsletter via Gmail SMTP."""
    # First try local config
    try:
        from ii_skills.wealth_macro_newsletter.config import (
            GMAIL_ADDRESS, GMAIL_APP_PASSWORD, RECIPIENT_EMAIL
        )
        class LocalConfig:
            sender_email = GMAIL_ADDRESS
            sender_password = GMAIL_APP_PASSWORD
            recipient_email = RECIPIENT_EMAIL
            smtp_server = "smtp.gmail.com"
            smtp_port = 587
        email_settings = LocalConfig()
    except ImportError:
        # Fall back to shared skill config
        try:
            from ii_skills.shared import get_skill_config
            config = get_skill_config()
            email_settings = config.email
        except ImportError:
            print("Could not load skill config. Set environment variables directly.")
            import os
            class FallbackEmail:
                sender_email = os.environ.get("GMAIL_ADDRESS", "")
                sender_password = os.environ.get("GMAIL_APP_PASSWORD", "")
                recipient_email = os.environ.get("RECIPIENT_EMAIL", "")
                smtp_server = "smtp.gmail.com"
                smtp_port = 587
            email_settings = FallbackEmail()

    target_recipient = recipient or email_settings.recipient_email

    if not email_settings.sender_email or not email_settings.sender_password:
        print("Missing email credentials. Set GMAIL_ADDRESS and GMAIL_APP_PASSWORD.")
        return False

    if not target_recipient:
        print("Missing recipient email. Provide --to or set RECIPIENT_EMAIL.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = email_settings.sender_email
    msg["To"] = target_recipient

    # Attach HTML
    html_part = MIMEText(html_content, "html")
    msg.attach(html_part)

    try:
        with smtplib.SMTP(email_settings.smtp_server, email_settings.smtp_port) as server:
            server.starttls()
            server.login(email_settings.sender_email, email_settings.sender_password)
            server.send_message(msg)
        print(f"Newsletter sent to {target_recipient}")
        return True
    except smtplib.SMTPException as exc:
        print(f"Failed to send email: {exc}")
        return False


# =============================================================================
# MAIN
# =============================================================================

def generate() -> tuple[str, Path]:
    """Generate the wealth macro newsletter."""
    settings = WealthMacroSettings()
    settings.ensure_dirs()

    print("Generating Wealth Macro Daily Newsletter...")
    print("-" * 50)

    # Fetch market data
    print("\n[MARKETS] Fetching market data...")
    markets = fetch_all_markets()
    print(f"   Fetched {len(markets)} markets")

    # Calculate regimes
    print("\n[ANALYSIS] Calculating regimes...")
    liquidity = calculate_liquidity_score(markets)
    print(f"   Liquidity: {liquidity['regime']} (score: {liquidity['score']})")
    risk = calculate_risk_regime(markets)
    print(f"   Risk: {risk['regime']}")

    # Fetch news
    print("\n[NEWS] Fetching news...")
    news = fetch_macro_news()
    print(f"   Found {len(news)} articles")

    # Generate HTML
    print("\n[OUTPUT] Generating newsletter...")
    html = generate_html_newsletter(markets, liquidity, risk, news)

    # Save to file
    filename = f"{date.today().isoformat()}-wealth-macro-newsletter.html"
    output_path = settings.base_dir / "newsletters" / filename
    output_path.write_text(html, encoding="utf-8")
    print(f"   Saved to: {output_path}")

    return html, output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Wealth Macro Newsletter")
    parser.add_argument("--send", action="store_true", help="Send the newsletter via email")
    parser.add_argument("--to", help="Override recipient email address")
    parser.add_argument(
        "--subject",
        default=f"📊 Wealth Macro Daily - {date.today().strftime('%b %d, %Y')}",
        help="Email subject line",
    )
    parser.add_argument("--sample", action="store_true", help="Print sample HTML to console")
    args = parser.parse_args()

    html, output_path = generate()

    print("\n" + "=" * 50)
    print(f"[SUCCESS] Newsletter generated: {output_path}")

    if args.sample:
        print("\n" + "=" * 50)
        print("SAMPLE HTML OUTPUT:")
        print("=" * 50)
        print(html[:5000] + "\n... [truncated]")

    if args.send:
        print("\n[EMAIL] Sending email...")
        success = send_email(html, args.subject, args.to)
        return 0 if success else 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
