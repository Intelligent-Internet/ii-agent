"""
Enriched Data Fetcher for IB Toolkit

Combines multiple data sources to provide comprehensive company research:
- Yahoo Finance (financial data, price history)
- Web Search (news, analysis, industry trends)
- Content Extraction (deep dive into articles)

Usage:
    from ii_skills.ib_toolkit.enriched_data import EnrichedDataFetcher

    fetcher = EnrichedDataFetcher()

    # Get comprehensive company data
    data = await fetcher.get_company_data("AAPL")

    # Research for deal analysis
    research = await fetcher.research_for_deal(
        company_name="Apple Inc",
        ticker="AAPL",
        deal_type="lbo",
    )
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CompanyData:
    """Comprehensive company data."""
    ticker: str
    name: str
    sector: str = ""
    industry: str = ""
    description: str = ""
    website: str = ""
    country: str = ""
    exchange: str = ""

    # Financial metrics
    market_cap: float = 0
    enterprise_value: float = 0
    revenue_ttm: float = 0
    ebitda_ttm: float = 0
    net_income_ttm: float = 0
    free_cash_flow: float = 0

    # Margins
    gross_margin: float = 0
    ebitda_margin: float = 0
    net_margin: float = 0

    # Growth
    revenue_growth_yoy: float = 0
    earnings_growth_yoy: float = 0

    # Valuation
    pe_ratio: float = 0
    ev_ebitda: float = 0
    ev_revenue: float = 0
    price_to_book: float = 0

    # Price data
    current_price: float = 0
    price_change_1d: float = 0
    price_change_1m: float = 0
    price_change_1y: float = 0
    fifty_two_week_high: float = 0
    fifty_two_week_low: float = 0

    # Balance sheet
    total_debt: float = 0
    cash_and_equivalents: float = 0
    net_debt: float = 0

    # Research data
    recent_news: List[Dict] = field(default_factory=list)
    analyst_ratings: Dict = field(default_factory=dict)
    competitors: List[str] = field(default_factory=list)
    industry_trends: List[str] = field(default_factory=list)

    # Raw data
    raw_data: Dict = field(default_factory=dict)
    research_content: Dict = field(default_factory=dict)

    # Metadata
    data_as_of: datetime = field(default_factory=datetime.now)
    sources: List[str] = field(default_factory=list)


@dataclass
class DealResearch:
    """Research output for deal analysis."""
    company_name: str
    ticker: str
    deal_type: str

    # Company data
    company_data: Optional[CompanyData] = None

    # Research findings
    investment_thesis_points: List[str] = field(default_factory=list)
    risk_factors: List[str] = field(default_factory=list)
    growth_opportunities: List[str] = field(default_factory=list)
    competitive_advantages: List[str] = field(default_factory=list)

    # Industry context
    industry_overview: str = ""
    market_dynamics: List[str] = field(default_factory=list)
    regulatory_considerations: List[str] = field(default_factory=list)

    # Deal-specific research
    comparable_transactions: List[Dict] = field(default_factory=list)
    valuation_context: str = ""
    financing_considerations: List[str] = field(default_factory=list)

    # Sources
    news_articles: List[Dict] = field(default_factory=list)
    research_reports: List[Dict] = field(default_factory=list)
    extracted_content: Dict[str, str] = field(default_factory=dict)

    # Metadata
    research_date: datetime = field(default_factory=datetime.now)
    queries_used: List[str] = field(default_factory=list)


class EnrichedDataFetcher:
    """
    Fetches and enriches company data from multiple sources.

    Combines Yahoo Finance data with web research to provide
    comprehensive information for deal analysis.
    """

    def __init__(self, cache_duration_hours: int = 1):
        """
        Initialize the enriched data fetcher.

        Args:
            cache_duration_hours: How long to cache data
        """
        self.cache_duration = timedelta(hours=cache_duration_hours)
        self._cache: Dict[str, tuple] = {}  # ticker -> (data, timestamp)
        self._research_client = None

    def _get_research_client(self):
        """Lazy load research client."""
        if self._research_client is None:
            try:
                from ii_skills.shared.research import get_research_client
                self._research_client = get_research_client()
            except ImportError:
                logger.warning("Research client not available")
        return self._research_client

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached data if still valid."""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < self.cache_duration:
                return data
        return None

    def _set_cached(self, key: str, data: Any):
        """Cache data with timestamp."""
        self._cache[key] = (data, datetime.now())

    async def get_company_data(
        self,
        ticker: str,
        include_news: bool = True,
        include_competitors: bool = True,
        use_cache: bool = True,
    ) -> CompanyData:
        """
        Get comprehensive company data.

        Args:
            ticker: Stock ticker symbol
            include_news: Whether to fetch recent news
            include_competitors: Whether to identify competitors

        Returns:
            CompanyData with all available information
        """
        cache_key = f"company_{ticker}"
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached:
                return cached

        # Start with Yahoo Finance data
        company_data = await self._fetch_yahoo_finance(ticker)

        # Enrich with web research
        if include_news:
            company_data.recent_news = await self._fetch_news(
                company_data.name or ticker, ticker
            )

        if include_competitors and company_data.industry:
            company_data.competitors = await self._find_competitors(
                company_data.name, company_data.industry
            )
            company_data.industry_trends = await self._get_industry_trends(
                company_data.industry
            )

        company_data.sources = ["yahoo_finance"]
        if include_news:
            company_data.sources.append("web_search")

        self._set_cached(cache_key, company_data)
        return company_data

    async def _fetch_yahoo_finance(self, ticker: str) -> CompanyData:
        """Fetch data from Yahoo Finance."""
        try:
            import yfinance as yf

            stock = yf.Ticker(ticker)
            info = stock.info

            # Extract key metrics
            data = CompanyData(
                ticker=ticker,
                name=info.get("longName", info.get("shortName", ticker)),
                sector=info.get("sector", ""),
                industry=info.get("industry", ""),
                description=info.get("longBusinessSummary", ""),
                website=info.get("website", ""),
                country=info.get("country", ""),
                exchange=info.get("exchange", ""),

                # Financial metrics
                market_cap=info.get("marketCap", 0) or 0,
                enterprise_value=info.get("enterpriseValue", 0) or 0,
                revenue_ttm=info.get("totalRevenue", 0) or 0,
                ebitda_ttm=info.get("ebitda", 0) or 0,
                net_income_ttm=info.get("netIncomeToCommon", 0) or 0,
                free_cash_flow=info.get("freeCashflow", 0) or 0,

                # Margins
                gross_margin=info.get("grossMargins", 0) or 0,
                ebitda_margin=info.get("ebitdaMargins", 0) or 0,
                net_margin=info.get("profitMargins", 0) or 0,

                # Growth
                revenue_growth_yoy=info.get("revenueGrowth", 0) or 0,
                earnings_growth_yoy=info.get("earningsGrowth", 0) or 0,

                # Valuation
                pe_ratio=info.get("trailingPE", 0) or 0,
                ev_ebitda=info.get("enterpriseToEbitda", 0) or 0,
                ev_revenue=info.get("enterpriseToRevenue", 0) or 0,
                price_to_book=info.get("priceToBook", 0) or 0,

                # Price
                current_price=info.get("currentPrice", info.get("regularMarketPrice", 0)) or 0,
                fifty_two_week_high=info.get("fiftyTwoWeekHigh", 0) or 0,
                fifty_two_week_low=info.get("fiftyTwoWeekLow", 0) or 0,

                # Balance sheet
                total_debt=info.get("totalDebt", 0) or 0,
                cash_and_equivalents=info.get("totalCash", 0) or 0,

                raw_data=info,
            )

            # Calculate derived metrics
            data.net_debt = data.total_debt - data.cash_and_equivalents

            # Price changes
            if data.current_price and data.fifty_two_week_high:
                data.price_change_1y = (
                    (data.current_price - data.fifty_two_week_low)
                    / data.fifty_two_week_low * 100
                    if data.fifty_two_week_low > 0 else 0
                )

            return data

        except Exception as e:
            logger.error(f"Failed to fetch Yahoo Finance data for {ticker}: {e}")
            return CompanyData(ticker=ticker, name=ticker)

    async def _fetch_news(
        self,
        company_name: str,
        ticker: str,
        max_results: int = 5,
    ) -> List[Dict]:
        """Fetch recent news about the company."""
        research_client = self._get_research_client()
        if not research_client:
            return []

        try:
            # Search for recent news
            query = f"{company_name} {ticker} news"
            results = await research_client.search(query, max_results=max_results)

            return [
                {
                    "title": r.title,
                    "url": r.url,
                    "snippet": r.snippet,
                    "source": "web_search",
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Failed to fetch news: {e}")
            return []

    async def _find_competitors(
        self,
        company_name: str,
        industry: str,
        max_results: int = 5,
    ) -> List[str]:
        """Find competitor companies."""
        research_client = self._get_research_client()
        if not research_client:
            return []

        try:
            query = f"{company_name} competitors {industry}"
            results = await research_client.search(query, max_results=max_results)

            # Extract competitor names from snippets (simplified)
            competitors = []
            for r in results:
                if r.snippet and "competitor" in r.snippet.lower():
                    competitors.append(r.snippet[:100])

            return competitors[:5]
        except Exception as e:
            logger.error(f"Failed to find competitors: {e}")
            return []

    async def _get_industry_trends(
        self,
        industry: str,
        max_results: int = 5,
    ) -> List[str]:
        """Get industry trends."""
        research_client = self._get_research_client()
        if not research_client:
            return []

        try:
            query = f"{industry} industry trends 2024 2025"
            results = await research_client.search(query, max_results=max_results)

            return [r.snippet for r in results if r.snippet][:5]
        except Exception as e:
            logger.error(f"Failed to get industry trends: {e}")
            return []

    async def research_for_deal(
        self,
        company_name: str,
        ticker: str,
        deal_type: str = "lbo",
        focus_areas: Optional[List[str]] = None,
    ) -> DealResearch:
        """
        Conduct comprehensive research for a deal.

        Args:
            company_name: Target company name
            ticker: Stock ticker
            deal_type: Type of deal (lbo, growth_equity, add_on, carve_out)
            focus_areas: Specific areas to research

        Returns:
            DealResearch with comprehensive findings
        """
        research = DealResearch(
            company_name=company_name,
            ticker=ticker,
            deal_type=deal_type,
        )

        # Get company data
        research.company_data = await self.get_company_data(ticker)

        # Build research queries based on deal type
        queries = self._build_deal_queries(company_name, ticker, deal_type, focus_areas)
        research.queries_used = queries

        research_client = self._get_research_client()
        if not research_client:
            logger.warning("Research client not available, returning basic data only")
            return research

        # Execute research queries
        for query in queries:
            try:
                results = await research_client.search(query, max_results=5)

                # Categorize results
                for r in results:
                    article = {
                        "title": r.title,
                        "url": r.url,
                        "snippet": r.snippet,
                        "query": query,
                    }

                    # Categorize by content
                    snippet_lower = r.snippet.lower() if r.snippet else ""

                    if any(word in snippet_lower for word in ["risk", "challenge", "concern", "threat"]):
                        research.risk_factors.append(r.snippet[:200])
                    elif any(word in snippet_lower for word in ["growth", "opportunity", "expand", "increase"]):
                        research.growth_opportunities.append(r.snippet[:200])
                    elif any(word in snippet_lower for word in ["advantage", "moat", "leader", "dominant"]):
                        research.competitive_advantages.append(r.snippet[:200])
                    elif any(word in snippet_lower for word in ["regulation", "compliance", "law", "government"]):
                        research.regulatory_considerations.append(r.snippet[:200])
                    elif any(word in snippet_lower for word in ["deal", "acquisition", "transaction", "buyout"]):
                        research.comparable_transactions.append(article)

                    research.news_articles.append(article)

            except Exception as e:
                logger.error(f"Research query failed '{query}': {e}")

        # Extract content from top articles
        top_urls = [a["url"] for a in research.news_articles[:3] if a.get("url")]
        for url in top_urls:
            try:
                content = await research_client.extract_url(url, company_name)
                if content:
                    research.extracted_content[url] = content[:3000]
            except Exception as e:
                logger.warning(f"Failed to extract {url}: {e}")

        # Build investment thesis points
        research.investment_thesis_points = await self._build_thesis_points(research)

        # Industry overview
        if research.company_data and research.company_data.industry:
            research.industry_overview = f"Company operates in the {research.company_data.industry} industry within the {research.company_data.sector} sector."

        # Valuation context
        research.valuation_context = self._build_valuation_context(research.company_data)

        # Financing considerations
        research.financing_considerations = self._build_financing_considerations(
            research.company_data, deal_type
        )

        return research

    def _build_deal_queries(
        self,
        company_name: str,
        ticker: str,
        deal_type: str,
        focus_areas: Optional[List[str]],
    ) -> List[str]:
        """Build search queries based on deal type."""
        queries = [
            f"{company_name} {ticker} investment analysis",
            f"{company_name} competitive advantages moat",
            f"{company_name} growth strategy expansion",
            f"{company_name} risks challenges",
        ]

        # Add deal-type specific queries
        if deal_type == "lbo":
            queries.extend([
                f"{company_name} private equity buyout",
                f"{company_name} debt capacity leverage",
                f"{company_name} cash flow generation",
            ])
        elif deal_type == "growth_equity":
            queries.extend([
                f"{company_name} growth investment funding",
                f"{company_name} market opportunity TAM",
                f"{company_name} unit economics profitability",
            ])
        elif deal_type == "add_on":
            queries.extend([
                f"{company_name} acquisition target strategic",
                f"{company_name} synergies integration",
            ])
        elif deal_type == "carve_out":
            queries.extend([
                f"{company_name} spinoff divestiture",
                f"{company_name} standalone operations",
            ])

        # Add focus areas
        if focus_areas:
            for area in focus_areas[:3]:
                queries.append(f"{company_name} {area}")

        return queries[:10]  # Limit to 10 queries

    async def _build_thesis_points(self, research: DealResearch) -> List[str]:
        """Build investment thesis points from research."""
        points = []

        if research.company_data:
            cd = research.company_data

            # Financial strength
            if cd.ebitda_margin > 0.15:
                points.append(f"Strong EBITDA margins of {cd.ebitda_margin:.1%}")
            if cd.revenue_growth_yoy > 0.1:
                points.append(f"Revenue growth of {cd.revenue_growth_yoy:.1%} YoY")
            if cd.free_cash_flow > 0:
                points.append(f"Positive free cash flow of ${cd.free_cash_flow/1e9:.1f}B")

            # Market position
            if cd.market_cap > 1e10:
                points.append(f"Large cap company with ${cd.market_cap/1e9:.0f}B market cap")

        # Add from competitive advantages
        points.extend(research.competitive_advantages[:3])

        # Add from growth opportunities
        points.extend(research.growth_opportunities[:2])

        return points[:7]  # Limit to top 7 points

    def _build_valuation_context(self, company_data: Optional[CompanyData]) -> str:
        """Build valuation context summary."""
        if not company_data:
            return "Insufficient data for valuation context"

        cd = company_data
        lines = []

        if cd.ev_ebitda > 0:
            lines.append(f"EV/EBITDA: {cd.ev_ebitda:.1f}x")
        if cd.ev_revenue > 0:
            lines.append(f"EV/Revenue: {cd.ev_revenue:.1f}x")
        if cd.pe_ratio > 0:
            lines.append(f"P/E Ratio: {cd.pe_ratio:.1f}x")
        if cd.enterprise_value > 0 and cd.ebitda_ttm > 0:
            lines.append(f"Enterprise Value: ${cd.enterprise_value/1e9:.1f}B")

        return " | ".join(lines) if lines else "Valuation metrics not available"

    def _build_financing_considerations(
        self,
        company_data: Optional[CompanyData],
        deal_type: str,
    ) -> List[str]:
        """Build financing considerations for the deal."""
        considerations = []

        if not company_data:
            return ["Insufficient data for financing analysis"]

        cd = company_data

        # Leverage capacity
        if cd.ebitda_ttm > 0:
            current_leverage = cd.net_debt / cd.ebitda_ttm if cd.ebitda_ttm else 0
            considerations.append(f"Current leverage: {current_leverage:.1f}x Net Debt/EBITDA")

            if deal_type == "lbo":
                max_leverage = 5.0 if cd.ebitda_margin > 0.2 else 4.0
                considerations.append(f"Estimated debt capacity: {max_leverage:.1f}x EBITDA")

        # Cash flow
        if cd.free_cash_flow > 0:
            considerations.append(f"Annual FCF of ${cd.free_cash_flow/1e9:.1f}B supports debt service")
        else:
            considerations.append("Negative FCF may limit debt capacity")

        # Asset base
        if cd.total_debt > 0 and cd.cash_and_equivalents > 0:
            considerations.append(f"Cash position: ${cd.cash_and_equivalents/1e9:.1f}B")

        return considerations


# Convenience function
async def get_enriched_company_data(ticker: str) -> CompanyData:
    """Quick function to get enriched company data."""
    fetcher = EnrichedDataFetcher()
    return await fetcher.get_company_data(ticker)


async def research_deal(
    company_name: str,
    ticker: str,
    deal_type: str = "lbo",
) -> DealResearch:
    """Quick function to research a deal."""
    fetcher = EnrichedDataFetcher()
    return await fetcher.research_for_deal(company_name, ticker, deal_type)
