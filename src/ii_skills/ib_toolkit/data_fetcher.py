#!/usr/bin/env python3
"""
Financial Data Fetcher
Fetches company financial data from free APIs for use in presentations and models.
"""

import requests
import yfinance as yf
from datetime import datetime
import json

from config import FMP_API_KEY, ALPHA_VANTAGE_API_KEY


def fetch_company_profile_yf(ticker: str) -> dict:
    """Fetch company profile using Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "name": info.get("longName", ticker),
            "ticker": ticker,
            "sector": info.get("sector", "N/A"),
            "industry": info.get("industry", "N/A"),
            "description": info.get("longBusinessSummary", ""),
            "website": info.get("website", ""),
            "employees": info.get("fullTimeEmployees", "N/A"),
            "headquarters": f"{info.get('city', '')}, {info.get('country', '')}",
            "key_metrics": {
                "Market Cap": format_large_number(info.get("marketCap", 0)),
                "Enterprise Value": format_large_number(info.get("enterpriseValue", 0)),
                "Revenue (TTM)": format_large_number(info.get("totalRevenue", 0)),
                "EBITDA": format_large_number(info.get("ebitda", 0)),
                "Net Income": format_large_number(info.get("netIncomeToCommon", 0)),
                "EPS": f"${info.get('trailingEps', 0):.2f}",
                "P/E Ratio": f"{info.get('trailingPE', 0):.1f}x",
                "EV/EBITDA": f"{info.get('enterpriseToEbitda', 0):.1f}x",
                "EV/Revenue": f"{info.get('enterpriseToRevenue', 0):.1f}x",
                "Profit Margin": f"{info.get('profitMargins', 0)*100:.1f}%",
                "ROE": f"{info.get('returnOnEquity', 0)*100:.1f}%",
                "Debt/Equity": f"{info.get('debtToEquity', 0):.2f}",
            },
            "stock_price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
            "52w_high": info.get("fiftyTwoWeekHigh", 0),
            "52w_low": info.get("fiftyTwoWeekLow", 0),
            "beta": info.get("beta", 1.0),
            "dividend_yield": info.get("dividendYield", 0),
            "shares_outstanding": info.get("sharesOutstanding", 0),
        }
    except Exception as e:
        print(f"Error fetching profile for {ticker}: {e}")
        return {"error": str(e)}


def fetch_financials_yf(ticker: str) -> dict:
    """Fetch historical financials using Yahoo Finance."""
    try:
        stock = yf.Ticker(ticker)

        # Get financial statements
        income_stmt = stock.financials
        balance_sheet = stock.balance_sheet
        cash_flow = stock.cashflow

        # Extract years
        years = [col.strftime("%Y") for col in income_stmt.columns[:4]]

        # Build metrics dict
        metrics = {}

        # Income Statement Items
        if "Total Revenue" in income_stmt.index:
            metrics["Revenue"] = [format_large_number(v) for v in income_stmt.loc["Total Revenue"].values[:4]]

        if "Gross Profit" in income_stmt.index:
            metrics["Gross Profit"] = [format_large_number(v) for v in income_stmt.loc["Gross Profit"].values[:4]]

        if "Operating Income" in income_stmt.index:
            metrics["Operating Income"] = [format_large_number(v) for v in income_stmt.loc["Operating Income"].values[:4]]

        if "EBITDA" in income_stmt.index:
            metrics["EBITDA"] = [format_large_number(v) for v in income_stmt.loc["EBITDA"].values[:4]]

        if "Net Income" in income_stmt.index:
            metrics["Net Income"] = [format_large_number(v) for v in income_stmt.loc["Net Income"].values[:4]]

        # Calculate margins
        if "Total Revenue" in income_stmt.index and "Gross Profit" in income_stmt.index:
            gross_margins = (income_stmt.loc["Gross Profit"] / income_stmt.loc["Total Revenue"] * 100).values[:4]
            metrics["Gross Margin"] = [f"{v:.1f}%" for v in gross_margins]

        if "Total Revenue" in income_stmt.index and "Operating Income" in income_stmt.index:
            op_margins = (income_stmt.loc["Operating Income"] / income_stmt.loc["Total Revenue"] * 100).values[:4]
            metrics["Operating Margin"] = [f"{v:.1f}%" for v in op_margins]

        # Balance Sheet Items
        if "Total Assets" in balance_sheet.index:
            metrics["Total Assets"] = [format_large_number(v) for v in balance_sheet.loc["Total Assets"].values[:4]]

        if "Total Debt" in balance_sheet.index:
            metrics["Total Debt"] = [format_large_number(v) for v in balance_sheet.loc["Total Debt"].values[:4]]

        if "Cash And Cash Equivalents" in balance_sheet.index:
            metrics["Cash"] = [format_large_number(v) for v in balance_sheet.loc["Cash And Cash Equivalents"].values[:4]]

        # Cash Flow Items
        if "Operating Cash Flow" in cash_flow.index:
            metrics["Operating Cash Flow"] = [format_large_number(v) for v in cash_flow.loc["Operating Cash Flow"].values[:4]]

        if "Capital Expenditure" in cash_flow.index:
            metrics["CapEx"] = [format_large_number(v) for v in cash_flow.loc["Capital Expenditure"].values[:4]]

        if "Free Cash Flow" in cash_flow.index:
            metrics["Free Cash Flow"] = [format_large_number(v) for v in cash_flow.loc["Free Cash Flow"].values[:4]]

        return {
            "years": years,
            "metrics": metrics
        }

    except Exception as e:
        print(f"Error fetching financials for {ticker}: {e}")
        return {"error": str(e), "years": [], "metrics": {}}


def fetch_comparable_companies(tickers: list) -> list:
    """Fetch data for comparable companies analysis."""
    comps = []

    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            comps.append({
                "name": info.get("shortName", ticker),
                "ticker": ticker,
                "market_cap": format_large_number(info.get("marketCap", 0)),
                "ev": format_large_number(info.get("enterpriseValue", 0)),
                "revenue": format_large_number(info.get("totalRevenue", 0)),
                "ebitda": format_large_number(info.get("ebitda", 0)),
                "ev_revenue": f"{info.get('enterpriseToRevenue', 0):.1f}x",
                "ev_ebitda": f"{info.get('enterpriseToEbitda', 0):.1f}x",
                "pe": f"{info.get('trailingPE', 0):.1f}x" if info.get('trailingPE') else "N/A",
                "profit_margin": f"{info.get('profitMargins', 0)*100:.1f}%",
                "revenue_growth": f"{info.get('revenueGrowth', 0)*100:.1f}%",
            })
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            continue

    return comps


def format_large_number(num) -> str:
    """Format large numbers with B/M suffix."""
    if num is None or num == 0:
        return "N/A"

    try:
        num = float(num)
        if abs(num) >= 1e12:
            return f"${num/1e12:.1f}T"
        elif abs(num) >= 1e9:
            return f"${num/1e9:.1f}B"
        elif abs(num) >= 1e6:
            return f"${num/1e6:.1f}M"
        elif abs(num) >= 1e3:
            return f"${num/1e3:.1f}K"
        else:
            return f"${num:.0f}"
    except:
        return "N/A"


def build_company_deck_data(ticker: str, comp_tickers: list = None) -> dict:
    """Build complete data package for a company deck."""
    print(f"Fetching data for {ticker}...")

    profile = fetch_company_profile_yf(ticker)
    financials = fetch_financials_yf(ticker)

    data = {
        "name": profile.get("name", ticker),
        "ticker": ticker,
        "description": profile.get("description", ""),
        "key_metrics": profile.get("key_metrics", {}),
        "financials": financials,
        "summary_points": [
            f"{profile.get('name')} operates in the {profile.get('industry', 'N/A')} industry",
            f"Market capitalization of {profile.get('key_metrics', {}).get('Market Cap', 'N/A')}",
            f"Trading at {profile.get('key_metrics', {}).get('P/E Ratio', 'N/A')} P/E ratio",
            f"Profit margin of {profile.get('key_metrics', {}).get('Profit Margin', 'N/A')}",
        ],
        "highlights": [
            f"Revenue: {profile.get('key_metrics', {}).get('Revenue (TTM)', 'N/A')}",
            f"EBITDA: {profile.get('key_metrics', {}).get('EBITDA', 'N/A')}",
            f"EV/EBITDA: {profile.get('key_metrics', {}).get('EV/EBITDA', 'N/A')}",
        ],
        "thesis": [
            "Strong market position in growing industry",
            "Consistent revenue and earnings growth",
            "Attractive valuation relative to peers",
            "Experienced management team"
        ],
        "risks": [
            "Competitive pressure from new entrants",
            "Regulatory and compliance risks",
            "Economic sensitivity",
            "Execution risk on growth initiatives"
        ],
        "valuation": {
            "ev": profile.get("key_metrics", {}).get("Enterprise Value", "N/A"),
            "equity_value": profile.get("key_metrics", {}).get("Market Cap", "N/A"),
            "shares": format_large_number(profile.get("shares_outstanding", 0)),
            "share_price": f"${profile.get('stock_price', 0):.2f}",
            "net_debt": "TBD",
        }
    }

    # Add comps if provided
    if comp_tickers:
        print(f"Fetching comparable companies: {comp_tickers}")
        comps = fetch_comparable_companies(comp_tickers)
        data["valuation"]["comps"] = comps

    return data


if __name__ == "__main__":
    # Example usage
    print("=" * 50)
    print("Financial Data Fetcher")
    print("=" * 50)

    # Fetch Apple data with comps
    data = build_company_deck_data("AAPL", ["MSFT", "GOOGL", "META"])

    print("\nCompany Profile:")
    print(f"  Name: {data['name']}")
    print(f"  Ticker: {data['ticker']}")
    print("\nKey Metrics:")
    for k, v in data.get("key_metrics", {}).items():
        print(f"  {k}: {v}")

    # Save to JSON for reference
    with open("output/sample_data.json", "w") as f:
        json.dump(data, f, indent=2, default=str)
    print("\nData saved to output/sample_data.json")
