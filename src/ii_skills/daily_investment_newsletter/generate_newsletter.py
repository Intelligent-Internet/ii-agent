#!/usr/bin/env python3
"""
Daily Canadian Investment Newsletter Generator

This script fetches news via Brave Search API and generates a formatted
newsletter for delivery via Gmail.

Usage:
    python generate_newsletter.py [--dry-run] [--focus TOPIC]

Requirements:
    - Config/brave-api-key.txt
    - Config/google-credentials.json
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import requests
from typing import Optional

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_DIR = BASE_DIR / "Claire" / "Config"
MEMORY_DIR = BASE_DIR / "Claire" / "Memory"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# Search queries for Canadian investment news
SEARCH_QUERIES = {
    "markets": [
        "TSX Toronto Stock Exchange today",
        "Canadian stock market news today",
        "TSX top movers today",
    ],
    "political": [
        "Canada federal government economic policy",
        "Canadian investment regulation news",
        "Canada US trade relations today",
        "Bank of Canada policy announcement",
    ],
    "energy": [
        "Canadian oil gas energy news today",
        "Alberta energy sector news",
        "Canada renewable energy investment",
    ],
    "financial": [
        "Canadian banks financial news today",
        "Canada real estate investment news",
    ],
    "economic": [
        "Canada inflation CPI latest",
        "Canada interest rate Bank of Canada",
        "Canadian dollar exchange rate news",
    ],
}


def load_api_key() -> Optional[str]:
    """Load Brave API key from config."""
    key_file = CONFIG_DIR / "brave-api-key.txt"
    if not key_file.exists():
        print(f"ERROR: Brave API key not found at {key_file}")
        return None
    return key_file.read_text().strip()


def search_brave(query: str, api_key: str, count: int = 5) -> list:
    """Execute a Brave search query."""
    url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": api_key,
    }
    params = {
        "q": query,
        "count": count,
        "freshness": "pd",  # Past day
        "country": "CA",
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("web", {}).get("results", [])
    except requests.RequestException as e:
        print(f"Search error for '{query}': {e}")
        return []


def fetch_all_news(api_key: str) -> dict:
    """Fetch news for all categories."""
    all_results = {}

    for category, queries in SEARCH_QUERIES.items():
        category_results = []
        for query in queries:
            results = search_brave(query, api_key)
            category_results.extend(results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for result in category_results:
            url = result.get("url", "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)

        all_results[category] = unique_results[:5]  # Top 5 per category

    return all_results


def format_story(result: dict) -> str:
    """Format a single news result."""
    title = result.get("title", "Untitled")
    description = result.get("description", "")
    url = result.get("url", "")

    return f"**[{title}]({url})**\n{description}\n"


def generate_executive_summary(all_results: dict) -> str:
    """Generate executive summary from top results."""
    summaries = []

    # Get top story from each category
    for category, results in all_results.items():
        if results:
            top = results[0]
            summaries.append(f"- **{category.title()}**: {top.get('title', 'N/A')}")

    return "\n".join(summaries[:5])


def generate_section(results: list) -> str:
    """Generate a section from results."""
    if not results:
        return "_No significant news today._\n"

    return "\n\n".join(format_story(r) for r in results[:3])


def generate_sources(all_results: dict) -> str:
    """Generate sources list."""
    sources = set()
    for results in all_results.values():
        for r in results:
            url = r.get("url", "")
            if url:
                # Extract domain
                from urllib.parse import urlparse
                domain = urlparse(url).netloc
                sources.add(domain)

    return "\n".join(f"- {s}" for s in sorted(sources)[:10])


def generate_newsletter(all_results: dict, date: datetime) -> str:
    """Generate the full newsletter content."""
    template_file = TEMPLATE_DIR / "newsletter-template.md"
    template = template_file.read_text()

    # Replace placeholders
    replacements = {
        "{{DATE}}": date.strftime("%A, %B %d, %Y"),
        "{{TIMESTAMP}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "{{EXECUTIVE_SUMMARY}}": generate_executive_summary(all_results),
        "{{MARKET_TABLE}}": "| TSX Composite | -- | -- | -- |\n| S&P/TSX 60 | -- | -- | -- |\n| CAD/USD | -- | -- | -- |",
        "{{TOP_STORIES}}": generate_section(all_results.get("markets", [])),
        "{{POLITICAL_SECTION}}": generate_section(all_results.get("political", [])),
        "{{ENERGY_SECTION}}": generate_section(all_results.get("energy", [])),
        "{{FINANCIAL_SECTION}}": generate_section(all_results.get("financial", [])),
        "{{TECH_SECTION}}": "_See general market news._",
        "{{ECONOMIC_CALENDAR}}": generate_section(all_results.get("economic", [])),
        "{{UPCOMING_EVENTS}}": "- Check Bank of Canada schedule\n- Monitor earnings calendar",
        "{{SOURCES}}": generate_sources(all_results),
    }

    for placeholder, value in replacements.items():
        template = template.replace(placeholder, value)

    return template


def save_newsletter(content: str, date: datetime) -> Path:
    """Save newsletter to Memory directory."""
    newsletters_dir = MEMORY_DIR / "newsletters"
    newsletters_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{date.strftime('%Y-%m-%d')}-daily-investment.md"
    filepath = newsletters_dir / filename
    filepath.write_text(content)

    return filepath


def main():
    parser = argparse.ArgumentParser(description="Generate Canadian Investment Newsletter")
    parser.add_argument("--dry-run", action="store_true", help="Generate without sending")
    parser.add_argument("--focus", type=str, help="Focus on specific topic")
    args = parser.parse_args()

    print("=" * 60)
    print("Canadian Investment Newsletter Generator")
    print("=" * 60)

    # Load API key
    api_key = load_api_key()
    if not api_key:
        print("\nRunning in DEMO mode (no API key found)")
        print("To enable live search, add your Brave API key to:")
        print(f"  {CONFIG_DIR / 'brave-api-key.txt'}")

        # Generate demo newsletter
        demo_results = {
            "markets": [{"title": "[Demo] TSX closes higher", "description": "Demo content - configure API for live data", "url": "#"}],
            "political": [{"title": "[Demo] Federal budget preview", "description": "Demo content", "url": "#"}],
            "energy": [{"title": "[Demo] Oil prices steady", "description": "Demo content", "url": "#"}],
            "financial": [{"title": "[Demo] Bank earnings", "description": "Demo content", "url": "#"}],
            "economic": [{"title": "[Demo] Inflation data", "description": "Demo content", "url": "#"}],
        }
        all_results = demo_results
    else:
        print("\nFetching news...")
        all_results = fetch_all_news(api_key)

    # Generate newsletter
    today = datetime.now()
    newsletter = generate_newsletter(all_results, today)

    # Save to file
    saved_path = save_newsletter(newsletter, today)
    print(f"\nNewsletter saved to: {saved_path}")

    if args.dry_run:
        print("\n[DRY RUN] Newsletter not sent")
        print("\n" + "=" * 60)
        print("PREVIEW:")
        print("=" * 60)
        print(newsletter)
    else:
        print("\nTo send via email, integrate with gog skill")
        print("(Gmail sending requires google-credentials.json)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
