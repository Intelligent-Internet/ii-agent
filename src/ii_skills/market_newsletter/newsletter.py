#!/usr/bin/env python3
"""
Daily Market Newsletter Generator
Fetches prices and news for Gold, Silver, Copper, Bitcoin, and Lumentum,
then sends a formatted HTML email via Gmail.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import requests
import yfinance as yf

from config import (
    GMAIL_ADDRESS, GMAIL_APP_PASSWORD, NEWSAPI_KEY,
    ASSETS, NEWS_ITEMS_PER_ASSET, ASSET_CLASSES
)


def fetch_yahoo_price(ticker: str) -> dict:
    """Fetch price data from Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")

        if hist.empty:
            return {"error": "No data available"}

        current_price = hist['Close'].iloc[-1]

        # Daily change (1 day ago)
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        daily_change = ((current_price - prev_price) / prev_price) * 100

        # Weekly change (7 days ago)
        week_idx = max(0, len(hist) - 5)  # ~5 trading days
        week_ago_price = hist['Close'].iloc[week_idx]
        weekly_change = ((current_price - week_ago_price) / week_ago_price) * 100

        # Monthly change (30 days ago)
        month_idx = max(0, len(hist) - 21)  # ~21 trading days
        month_ago_price = hist['Close'].iloc[month_idx]
        monthly_change = ((current_price - month_ago_price) / month_ago_price) * 100

        # Yearly change (1 year ago)
        year_ago_price = hist['Close'].iloc[0]
        yearly_change = ((current_price - year_ago_price) / year_ago_price) * 100

        return {
            "price": current_price,
            "daily_change": daily_change,
            "weekly_change": weekly_change,
            "monthly_change": monthly_change,
            "yearly_change": yearly_change,
            "currency": "USD"
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_crypto_price(coin_id: str) -> dict:
    """Fetch cryptocurrency price from CoinGecko API."""
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}"
        params = {
            "localization": "false",
            "tickers": "false",
            "community_data": "false",
            "developer_data": "false"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        market_data = data.get("market_data", {})
        current_price = market_data.get("current_price", {}).get("usd", 0)
        daily_change = market_data.get("price_change_percentage_24h", 0)
        weekly_change = market_data.get("price_change_percentage_7d", 0)
        monthly_change = market_data.get("price_change_percentage_30d", 0)
        yearly_change = market_data.get("price_change_percentage_1y", 0)

        return {
            "price": current_price,
            "daily_change": daily_change if daily_change else 0,
            "weekly_change": weekly_change if weekly_change else 0,
            "monthly_change": monthly_change if monthly_change else 0,
            "yearly_change": yearly_change if yearly_change else 0,
            "currency": "USD"
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_news(query: str) -> list:
    """Fetch news headlines from NewsAPI."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": NEWS_ITEMS_PER_ASSET,
            "language": "en",
            "apiKey": NEWSAPI_KEY
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        articles = data.get("articles", [])
        return [
            {
                "title": article.get("title", "No title"),
                "url": article.get("url", "#"),
                "source": article.get("source", {}).get("name", "Unknown"),
                "published": article.get("publishedAt", "")[:10]
            }
            for article in articles
        ]
    except Exception as e:
        return [{"title": f"Error fetching news: {e}", "url": "#", "source": "", "published": ""}]


def fetch_all_data() -> dict:
    """Fetch price and news data for all assets."""
    data = {}

    for name, config in ASSETS.items():
        print(f"Fetching data for {name}...")

        # Get price data
        ticker = config["ticker"]
        if ticker in ["bitcoin", "ethereum"]:
            price_data = fetch_crypto_price(ticker)
        else:
            price_data = fetch_yahoo_price(ticker)

        # Get news
        news = fetch_news(config["news_query"])

        data[name] = {
            "price_data": price_data,
            "news": news,
            "asset_class": config.get("asset_class", "Other")
        }

    return data


def calculate_asset_class_performance(data: dict) -> dict:
    """Calculate equal-weighted performance for each asset class."""
    class_performance = {}

    for class_name, asset_names in ASSET_CLASSES.items():
        daily_changes = []
        weekly_changes = []
        monthly_changes = []
        yearly_changes = []

        for asset_name in asset_names:
            if asset_name in data:
                price_info = data[asset_name]["price_data"]
                if "error" not in price_info:
                    daily_changes.append(price_info.get("daily_change", 0))
                    weekly_changes.append(price_info.get("weekly_change", 0))
                    monthly_changes.append(price_info.get("monthly_change", 0))
                    yearly_changes.append(price_info.get("yearly_change", 0))

        if daily_changes:
            class_performance[class_name] = {
                "daily_change": sum(daily_changes) / len(daily_changes),
                "weekly_change": sum(weekly_changes) / len(weekly_changes),
                "monthly_change": sum(monthly_changes) / len(monthly_changes),
                "yearly_change": sum(yearly_changes) / len(yearly_changes),
                "asset_count": len(daily_changes)
            }

    return class_performance


def format_price(price: float, asset_name: str) -> str:
    """Format price with appropriate precision."""
    if asset_name == "Bitcoin":
        return f"${price:,.2f}"
    elif asset_name in ["Gold", "Silver", "Copper"]:
        return f"${price:,.2f}"
    else:
        return f"${price:,.2f}"


def format_change(change: float) -> str:
    """Format percentage change with color indicator."""
    if change >= 0:
        return f'<span style="color: #22c55e;">+{change:.2f}%</span>'
    else:
        return f'<span style="color: #ef4444;">{change:.2f}%</span>'


def generate_html(data: dict) -> str:
    """Generate HTML newsletter content."""
    today = datetime.now().strftime("%B %d, %Y")

    # Calculate asset class performance
    class_performance = calculate_asset_class_performance(data)

    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9fafb;
        }}
        .header {{
            background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%);
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
        .header p {{
            margin: 10px 0 0;
            opacity: 0.9;
        }}
        .summary-table {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            overflow-x: auto;
        }}
        .summary-table h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            color: #1e3a8a;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th {{
            background: #f3f4f6;
            padding: 10px 6px;
            text-align: left;
            font-weight: 600;
            color: #374151;
            border-bottom: 2px solid #e5e7eb;
            white-space: nowrap;
        }}
        td {{
            padding: 10px 6px;
            border-bottom: 1px solid #e5e7eb;
            vertical-align: top;
        }}
        tr:last-child td {{
            border-bottom: none;
        }}
        .asset-name-cell {{
            font-weight: 600;
            color: #1e3a8a;
        }}
        .price-cell {{
            font-weight: 500;
            color: #374151;
            white-space: nowrap;
        }}
        .positive {{
            color: #22c55e;
        }}
        .negative {{
            color: #ef4444;
        }}
        .drivers {{
            font-size: 11px;
            color: #4b5563;
            max-width: 300px;
        }}
        .drivers ul {{
            margin: 0;
            padding-left: 14px;
        }}
        .drivers li {{
            margin-bottom: 3px;
        }}
        .class-table {{
            background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .class-table h2 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            color: #0369a1;
        }}
        .class-table table {{
            background: white;
            border-radius: 8px;
        }}
        .class-table th {{
            background: #0369a1;
            color: white;
        }}
        .class-name-cell {{
            font-weight: 600;
            color: #0369a1;
        }}
        .asset-card {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .asset-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e5e7eb;
        }}
        .asset-name {{
            font-size: 20px;
            font-weight: 600;
            color: #1e3a8a;
        }}
        .asset-price {{
            font-size: 24px;
            font-weight: 700;
        }}
        .changes {{
            display: flex;
            gap: 20px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}
        .change-item {{
            font-size: 14px;
        }}
        .change-label {{
            color: #6b7280;
        }}
        .news-section {{
            margin-top: 15px;
        }}
        .news-title {{
            font-size: 14px;
            font-weight: 600;
            color: #374151;
            margin-bottom: 10px;
        }}
        .news-item {{
            padding: 8px 0;
            border-bottom: 1px solid #f3f4f6;
        }}
        .news-item:last-child {{
            border-bottom: none;
        }}
        .news-item a {{
            color: #2563eb;
            text-decoration: none;
            font-size: 14px;
        }}
        .news-item a:hover {{
            text-decoration: underline;
        }}
        .news-meta {{
            font-size: 12px;
            color: #9ca3af;
            margin-top: 3px;
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
        <h1>Daily Market Newsletter</h1>
        <p>{today}</p>
    </div>

    <div class="summary-table">
        <h2>Asset Performance Summary</h2>
        <table>
            <thead>
                <tr>
                    <th>Asset</th>
                    <th>Price (USD)</th>
                    <th>1 Day</th>
                    <th>7 Days</th>
                    <th>1 Month</th>
                    <th>1 Year</th>
                    <th>Key Drivers</th>
                </tr>
            </thead>
            <tbody>
"""

    # Generate summary table rows
    for name, asset_data in data.items():
        price_info = asset_data["price_data"]
        news = asset_data["news"]

        if "error" in price_info:
            price_display = "N/A"
            daily = monthly = weekly = yearly = "N/A"
            daily_class = monthly_class = weekly_class = yearly_class = ""
        else:
            price_display = format_price(price_info["price"], name)
            daily = price_info.get("daily_change", 0)
            weekly = price_info.get("weekly_change", 0)
            monthly = price_info.get("monthly_change", 0)
            yearly = price_info.get("yearly_change", 0)

            daily_class = "positive" if daily >= 0 else "negative"
            weekly_class = "positive" if weekly >= 0 else "negative"
            monthly_class = "positive" if monthly >= 0 else "negative"
            yearly_class = "positive" if yearly >= 0 else "negative"

            daily = f"{'+' if daily >= 0 else ''}{daily:.2f}%"
            weekly = f"{'+' if weekly >= 0 else ''}{weekly:.2f}%"
            monthly = f"{'+' if monthly >= 0 else ''}{monthly:.2f}%"
            yearly = f"{'+' if yearly >= 0 else ''}{yearly:.2f}%"

        # Extract key drivers from news headlines (first 3)
        drivers_html = "<ul>"
        for i, item in enumerate(news[:3]):
            title = item.get("title", "")
            # Truncate long titles
            if len(title) > 60:
                title = title[:57] + "..."
            drivers_html += f"<li>{title}</li>"
        drivers_html += "</ul>"

        html += f"""
                <tr>
                    <td class="asset-name-cell">{name}</td>
                    <td class="price-cell">{price_display}</td>
                    <td class="{daily_class}">{daily}</td>
                    <td class="{weekly_class}">{weekly}</td>
                    <td class="{monthly_class}">{monthly}</td>
                    <td class="{yearly_class}">{yearly}</td>
                    <td class="drivers">{drivers_html}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
    </div>

    <div class="class-table">
        <h2>Asset Class Performance (Equal-Weighted)</h2>
        <table>
            <thead>
                <tr>
                    <th>Asset Class</th>
                    <th>Assets</th>
                    <th>1 Day</th>
                    <th>7 Days</th>
                    <th>1 Month</th>
                    <th>1 Year</th>
                </tr>
            </thead>
            <tbody>
"""

    # Generate asset class summary rows
    for class_name, perf in class_performance.items():
        daily = perf["daily_change"]
        weekly = perf["weekly_change"]
        monthly = perf["monthly_change"]
        yearly = perf["yearly_change"]
        count = perf["asset_count"]

        daily_class = "positive" if daily >= 0 else "negative"
        weekly_class = "positive" if weekly >= 0 else "negative"
        monthly_class = "positive" if monthly >= 0 else "negative"
        yearly_class = "positive" if yearly >= 0 else "negative"

        daily_str = f"{'+' if daily >= 0 else ''}{daily:.2f}%"
        weekly_str = f"{'+' if weekly >= 0 else ''}{weekly:.2f}%"
        monthly_str = f"{'+' if monthly >= 0 else ''}{monthly:.2f}%"
        yearly_str = f"{'+' if yearly >= 0 else ''}{yearly:.2f}%"

        html += f"""
                <tr>
                    <td class="class-name-cell">{class_name}</td>
                    <td>{count}</td>
                    <td class="{daily_class}">{daily_str}</td>
                    <td class="{weekly_class}">{weekly_str}</td>
                    <td class="{monthly_class}">{monthly_str}</td>
                    <td class="{yearly_class}">{yearly_str}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
    </div>
"""

    # Generate detailed asset cards
    for name, asset_data in data.items():
        price_info = asset_data["price_data"]
        news = asset_data["news"]

        if "error" in price_info:
            price_display = "N/A"
            daily_change = weekly_change = monthly_change = yearly_change = "N/A"
        else:
            price_display = format_price(price_info["price"], name)
            daily_change = format_change(price_info["daily_change"])
            weekly_change = format_change(price_info["weekly_change"])
            monthly_change = format_change(price_info.get("monthly_change", 0))
            yearly_change = format_change(price_info.get("yearly_change", 0))

        html += f"""
    <div class="asset-card">
        <div class="asset-header">
            <span class="asset-name">{name}</span>
            <span class="asset-price">{price_display}</span>
        </div>
        <div class="changes">
            <div class="change-item">
                <span class="change-label">24h:</span> {daily_change}
            </div>
            <div class="change-item">
                <span class="change-label">7d:</span> {weekly_change}
            </div>
            <div class="change-item">
                <span class="change-label">1m:</span> {monthly_change}
            </div>
            <div class="change-item">
                <span class="change-label">1y:</span> {yearly_change}
            </div>
        </div>
        <div class="news-section">
            <div class="news-title">Latest News</div>
"""

        for item in news:
            html += f"""
            <div class="news-item">
                <a href="{item['url']}" target="_blank">{item['title']}</a>
                <div class="news-meta">{item['source']} - {item['published']}</div>
            </div>
"""

        html += """
        </div>
    </div>
"""

    html += """
    <div class="footer">
        <p>Generated automatically by Market Newsletter</p>
        <p>Data sources: Yahoo Finance, CoinGecko, NewsAPI</p>
    </div>
</body>
</html>
"""

    return html


def send_email(html_content: str) -> bool:
    """Send the newsletter via Gmail SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"Daily Market Newsletter - {datetime.now().strftime('%B %d, %Y')}"
        msg["From"] = GMAIL_ADDRESS
        msg["To"] = GMAIL_ADDRESS

        # Attach HTML content
        html_part = MIMEText(html_content, "html")
        msg.attach(html_part)

        # Send via Gmail SMTP
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
    """Main function to generate and send the newsletter."""
    print("=" * 50)
    print("Daily Market Newsletter Generator")
    print("=" * 50)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Fetch all data
    print("Fetching market data...")
    data = fetch_all_data()
    print()

    # Generate HTML
    print("Generating newsletter...")
    html_content = generate_html(data)

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
