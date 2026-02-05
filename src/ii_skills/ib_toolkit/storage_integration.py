"""
IB Toolkit Storage Integration

Wraps the Excel and PowerPoint generators to provide:
- Automatic GCS upload
- Output tracking in database
- Signed download URLs

Usage:
    from ii_skills.ib_toolkit.storage_integration import IBToolkitStorage

    storage = IBToolkitStorage(user_id="...")

    # Generate and upload Excel model
    result = await storage.generate_lbo_model(
        company_name="Acme Corp",
        company_symbol="ACME",
        timeframe="48_hour",
        assumptions={"entry_multiple": 10.0}
    )

    print(result["storage_url"])  # GCS URL
    print(result["local_path"])   # Local file path
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
import asyncio

logger = logging.getLogger(__name__)

# Default output directory
DEFAULT_OUTPUT_DIR = Path(__file__).parent / "outputs"


class IBToolkitStorage:
    """
    Storage-integrated IB Toolkit generator.

    Wraps Excel and PowerPoint generators with GCS upload and database tracking.
    """

    def __init__(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        output_dir: Optional[str] = None,
        upload_to_cloud: bool = True,
        track_outputs: bool = True,
    ):
        """
        Initialize the storage-integrated generator.

        Args:
            user_id: User ID for tracking
            session_id: Optional session ID
            output_dir: Local output directory (uses default if not specified)
            upload_to_cloud: Whether to upload to GCS
            track_outputs: Whether to track in database
        """
        self.user_id = user_id
        self.session_id = session_id
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
        self.upload_to_cloud = upload_to_cloud
        self.track_outputs = track_outputs

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Lazy-loaded storage helper
        self._storage = None

    def _get_storage(self):
        """Get the storage helper."""
        if self._storage is None and self.upload_to_cloud:
            try:
                from ii_skills.shared.storage import get_skill_storage
                self._storage = get_skill_storage()
            except ImportError:
                logger.warning("SkillStorage not available - local files only")
        return self._storage

    def _generate_filename(
        self,
        company_name: str,
        model_type: str,
        extension: str,
    ) -> str:
        """Generate a filename for the output."""
        safe_name = company_name.replace(" ", "_").replace("/", "-")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{model_type}_{timestamp}.{extension}"

    async def _upload_and_track(
        self,
        filepath: str,
        company_symbol: Optional[str] = None,
        module_name: Optional[str] = None,
        input_parameters: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Upload file to storage and track in database."""
        result = {
            "local_path": filepath,
            "file_name": os.path.basename(filepath),
            "storage_path": None,
            "storage_url": None,
            "output_id": None,
        }

        storage = self._get_storage()
        if storage and self.upload_to_cloud:
            try:
                upload_result = await storage.upload_file(
                    user_id=self.user_id,
                    skill_name="ib_toolkit",
                    file_path=filepath,
                    module_name=module_name,
                    company_symbol=company_symbol,
                    session_id=self.session_id,
                    input_parameters=input_parameters,
                    tags=tags,
                    track_output=self.track_outputs,
                )
                result.update(upload_result)
            except Exception as e:
                logger.error(f"Failed to upload/track output: {e}")

        return result

    # =========================================================================
    # EXCEL MODEL GENERATORS
    # =========================================================================

    async def generate_lbo_model(
        self,
        company_name: str,
        company_symbol: Optional[str] = None,
        timeframe: str = "48_hour",
        assumptions: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate an LBO model Excel file.

        Args:
            company_name: Name of the target company
            company_symbol: Stock symbol (optional)
            timeframe: One of "24_hour", "48_hour", "5_day", "7_day_plus"
            assumptions: Model assumptions (entry_multiple, ltm_ebitda, etc.)

        Returns:
            Dict with local_path, storage_url, output_id, etc.
        """
        from ii_skills.ib_toolkit.templates.excel_models.excel_modules import (
            ExcelModelGenerator,
            ModelAssumptions,
        )

        # Create model assumptions
        model_assumptions = None
        if assumptions:
            model_assumptions = ModelAssumptions(
                company_name=company_name,
                **{k: v for k, v in assumptions.items() if v is not None}
            )

        # Generate model
        generator = ExcelModelGenerator(
            company_name=company_name,
            assumptions=model_assumptions,
        )
        generator.build_for_timeframe(timeframe)

        # Save locally
        filename = self._generate_filename(company_name, f"LBO_{timeframe}", "xlsx")
        filepath = str(self.output_dir / filename)
        generator.save(filepath)

        # Upload and track
        result = await self._upload_and_track(
            filepath=filepath,
            company_symbol=company_symbol,
            module_name=f"lbo_model_{timeframe}",
            input_parameters={
                "timeframe": timeframe,
                "assumptions": assumptions or {},
            },
            tags=["lbo", "excel", timeframe],
        )

        result["timeframe"] = timeframe
        result["sheets_created"] = generator.sheets_created

        return result

    async def generate_custom_model(
        self,
        company_name: str,
        modules: List[str],
        company_symbol: Optional[str] = None,
        assumptions: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate a custom Excel model with specified modules.

        Args:
            company_name: Name of the target company
            modules: List of module names to include
                     (e.g., ["sources_uses", "operating_model", "debt_schedule"])
            company_symbol: Stock symbol (optional)
            assumptions: Model assumptions

        Returns:
            Dict with local_path, storage_url, output_id, etc.
        """
        from ii_skills.ib_toolkit.templates.excel_models.excel_modules import (
            ExcelModelGenerator,
            ModelAssumptions,
        )

        # Create model assumptions
        model_assumptions = None
        if assumptions:
            model_assumptions = ModelAssumptions(
                company_name=company_name,
                **{k: v for k, v in assumptions.items() if v is not None}
            )

        # Generate model
        generator = ExcelModelGenerator(
            company_name=company_name,
            assumptions=model_assumptions,
        )

        # Add requested modules
        for module in modules:
            method_name = f"add_{module}"
            if hasattr(generator, method_name):
                getattr(generator, method_name)()
            else:
                logger.warning(f"Unknown module: {module}")

        # Save locally
        module_names = "_".join(modules[:3])  # First 3 modules in filename
        filename = self._generate_filename(company_name, f"Model_{module_names}", "xlsx")
        filepath = str(self.output_dir / filename)
        generator.save(filepath)

        # Upload and track
        result = await self._upload_and_track(
            filepath=filepath,
            company_symbol=company_symbol,
            module_name="custom_model",
            input_parameters={
                "modules": modules,
                "assumptions": assumptions or {},
            },
            tags=["excel", "custom"] + modules[:5],
        )

        result["modules"] = modules
        result["sheets_created"] = generator.sheets_created

        return result

    # =========================================================================
    # POWERPOINT GENERATORS
    # =========================================================================

    async def generate_industry_deck(
        self,
        industry: str,
        company_symbol: Optional[str] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate an industry analysis PowerPoint deck.

        Args:
            industry: Industry name
            company_symbol: Related company symbol (optional)
            data: Industry data (size, growth, segments, trends, key_players)

        Returns:
            Dict with local_path, storage_url, output_id, etc.
        """
        from ii_skills.ib_toolkit.pptx_generator import create_industry_deck

        data = data or {}
        filepath = create_industry_deck(industry, data)

        # Upload and track
        result = await self._upload_and_track(
            filepath=filepath,
            company_symbol=company_symbol,
            module_name="industry_analysis",
            input_parameters={"industry": industry, "data": data},
            tags=["powerpoint", "industry", industry.lower().replace(" ", "_")],
        )

        return result

    async def generate_company_deck(
        self,
        company_name: str,
        ticker: str,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate a company profile PowerPoint deck.

        Args:
            company_name: Company name
            ticker: Stock ticker symbol
            data: Company data (description, financials, comps, thesis, risks)

        Returns:
            Dict with local_path, storage_url, output_id, etc.
        """
        from ii_skills.ib_toolkit.pptx_generator import create_company_profile_deck

        data = data or {}
        filepath = create_company_profile_deck(company_name, ticker, data)

        # Upload and track
        result = await self._upload_and_track(
            filepath=filepath,
            company_symbol=ticker,
            module_name="company_profile",
            input_parameters={"company": company_name, "ticker": ticker},
            tags=["powerpoint", "company", ticker],
        )

        return result

    async def generate_investment_deck(
        self,
        company_name: str,
        company_symbol: str,
        deck_type: str = "standard",
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Generate an investment deck.

        Args:
            company_name: Company name
            company_symbol: Stock symbol
            deck_type: "standard" (25 slides), "institutional" (60+), "comprehensive" (80+)
            data: Presentation data

        Returns:
            Dict with local_path, storage_url, output_id, etc.
        """
        from ii_skills.ib_toolkit.templates.case_study.slide_modules import (
            SlideGenerator,
        )

        # Map deck type to modules
        if deck_type == "institutional":
            modules = [
                "industry", "competitive", "company", "financials",
                "valuation", "transaction", "thesis", "risks",
                "management", "deal_team",
            ]
        elif deck_type == "comprehensive":
            modules = [
                "executive_summary", "industry", "competitive", "company",
                "financials", "valuation", "transaction", "thesis",
                "risks", "opportunities", "value_creation", "exit",
                "management", "deal_team", "appendix",
            ]
        else:
            modules = ["industry", "company", "financials", "valuation", "thesis"]

        # Generate deck
        generator = SlideGenerator(title=f"{company_name} Investment Thesis")
        for module in modules:
            method_name = f"add_{module}_slides"
            if hasattr(generator, method_name):
                getattr(generator, method_name)(data or {})

        filename = self._generate_filename(company_name, f"Investment_{deck_type}", "pptx")
        filepath = str(self.output_dir / filename)
        generator.save(filepath)

        # Upload and track
        result = await self._upload_and_track(
            filepath=filepath,
            company_symbol=company_symbol,
            module_name=f"investment_deck_{deck_type}",
            input_parameters={"deck_type": deck_type, "modules": modules},
            tags=["powerpoint", "investment", deck_type, company_symbol],
        )

        result["deck_type"] = deck_type
        result["modules"] = modules

        return result

    # =========================================================================
    # RESEARCH-ENHANCED GENERATION
    # =========================================================================

    async def generate_research_enhanced_model(
        self,
        company_name: str,
        ticker: str,
        timeframe: str = "48_hour",
        deal_type: str = "lbo",
        include_research_report: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate an LBO model with research-enhanced data.

        Automatically fetches company data and conducts web research
        to populate model assumptions and create a companion research report.

        Args:
            company_name: Company name
            ticker: Stock ticker symbol
            timeframe: LBO model timeframe
            deal_type: Type of deal (lbo, growth_equity, add_on)
            include_research_report: Generate markdown research report

        Returns:
            Dict with model, research data, and optional report
        """
        from ii_skills.ib_toolkit.enriched_data import EnrichedDataFetcher

        results = {
            "company": company_name,
            "ticker": ticker,
            "deal_type": deal_type,
        }

        # Fetch enriched data
        fetcher = EnrichedDataFetcher()
        research = await fetcher.research_for_deal(
            company_name=company_name,
            ticker=ticker,
            deal_type=deal_type,
        )

        results["research"] = {
            "company_data": research.company_data.__dict__ if research.company_data else {},
            "investment_thesis": research.investment_thesis_points,
            "risks": research.risk_factors,
            "opportunities": research.growth_opportunities,
            "competitive_advantages": research.competitive_advantages,
            "news_articles": research.news_articles[:5],
            "queries_used": research.queries_used,
        }

        # Build assumptions from research
        assumptions = {}
        if research.company_data:
            cd = research.company_data
            if cd.ebitda_ttm > 0:
                assumptions["ltm_ebitda"] = cd.ebitda_ttm / 1e6  # Convert to millions
            if cd.ev_ebitda > 0:
                assumptions["entry_multiple"] = cd.ev_ebitda
            if cd.revenue_ttm > 0 and cd.ebitda_ttm > 0:
                assumptions["ebitda_margin"] = cd.ebitda_ttm / cd.revenue_ttm

        # Generate LBO model
        excel_result = await self.generate_lbo_model(
            company_name=company_name,
            company_symbol=ticker,
            timeframe=timeframe,
            assumptions=assumptions,
        )
        results["excel"] = excel_result

        # Generate research report if requested
        if include_research_report:
            report_content = self._build_research_report(research)
            report_filename = f"{company_name.replace(' ', '_')}_Research_{datetime.now().strftime('%Y%m%d')}.md"
            report_path = self.output_dir / report_filename

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_content)

            # Upload report
            report_result = await self._upload_and_track(
                filepath=str(report_path),
                company_symbol=ticker,
                module_name="research_report",
                input_parameters={"deal_type": deal_type},
                tags=["research", "markdown", deal_type, ticker],
            )
            results["research_report"] = report_result

        return results

    def _build_research_report(self, research) -> str:
        """Build a markdown research report from deal research."""
        lines = [
            f"# {research.company_name} ({research.ticker}) - Deal Research",
            f"",
            f"**Deal Type:** {research.deal_type.upper()}",
            f"**Research Date:** {research.research_date.strftime('%B %d, %Y')}",
            "",
            "---",
            "",
        ]

        # Company Overview
        if research.company_data:
            cd = research.company_data
            lines.extend([
                "## Company Overview",
                "",
                f"**Name:** {cd.name}",
                f"**Sector:** {cd.sector}",
                f"**Industry:** {cd.industry}",
                f"**Country:** {cd.country}",
                "",
                cd.description[:500] if cd.description else "",
                "",
            ])

            # Financial Summary
            lines.extend([
                "## Financial Summary",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Market Cap | ${cd.market_cap/1e9:.1f}B |" if cd.market_cap else "",
                f"| Enterprise Value | ${cd.enterprise_value/1e9:.1f}B |" if cd.enterprise_value else "",
                f"| Revenue (TTM) | ${cd.revenue_ttm/1e9:.1f}B |" if cd.revenue_ttm else "",
                f"| EBITDA (TTM) | ${cd.ebitda_ttm/1e9:.1f}B |" if cd.ebitda_ttm else "",
                f"| EBITDA Margin | {cd.ebitda_margin:.1%} |" if cd.ebitda_margin else "",
                f"| Net Debt | ${cd.net_debt/1e9:.1f}B |" if cd.net_debt else "",
                "",
                "### Valuation",
                "",
                "| Multiple | Value |",
                "|----------|-------|",
                f"| EV/EBITDA | {cd.ev_ebitda:.1f}x |" if cd.ev_ebitda else "",
                f"| EV/Revenue | {cd.ev_revenue:.1f}x |" if cd.ev_revenue else "",
                f"| P/E Ratio | {cd.pe_ratio:.1f}x |" if cd.pe_ratio else "",
                "",
            ])

        # Investment Thesis
        if research.investment_thesis_points:
            lines.extend([
                "## Investment Thesis",
                "",
            ])
            for point in research.investment_thesis_points:
                lines.append(f"- {point}")
            lines.append("")

        # Competitive Advantages
        if research.competitive_advantages:
            lines.extend([
                "## Competitive Advantages",
                "",
            ])
            for adv in research.competitive_advantages[:5]:
                lines.append(f"- {adv[:200]}")
            lines.append("")

        # Growth Opportunities
        if research.growth_opportunities:
            lines.extend([
                "## Growth Opportunities",
                "",
            ])
            for opp in research.growth_opportunities[:5]:
                lines.append(f"- {opp[:200]}")
            lines.append("")

        # Risk Factors
        if research.risk_factors:
            lines.extend([
                "## Risk Factors",
                "",
            ])
            for risk in research.risk_factors[:5]:
                lines.append(f"- {risk[:200]}")
            lines.append("")

        # Recent News
        if research.news_articles:
            lines.extend([
                "## Recent News & Articles",
                "",
            ])
            for article in research.news_articles[:5]:
                lines.append(f"- [{article.get('title', 'Article')}]({article.get('url', '#')})")
            lines.append("")

        # Financing Considerations
        if research.financing_considerations:
            lines.extend([
                "## Financing Considerations",
                "",
            ])
            for cons in research.financing_considerations:
                lines.append(f"- {cons}")
            lines.append("")

        # Sources
        lines.extend([
            "---",
            "",
            "## Research Queries Used",
            "",
        ])
        for query in research.queries_used:
            lines.append(f"- {query}")

        return "\n".join([line for line in lines if line is not None])

    async def generate_research_enhanced_deck(
        self,
        company_name: str,
        ticker: str,
        deck_type: str = "standard",
        deal_type: str = "lbo",
    ) -> Dict[str, Any]:
        """
        Generate a PowerPoint deck with research-enhanced data.

        Args:
            company_name: Company name
            ticker: Stock ticker symbol
            deck_type: standard, institutional, comprehensive
            deal_type: Type of deal for research focus

        Returns:
            Dict with deck and research data
        """
        from ii_skills.ib_toolkit.enriched_data import EnrichedDataFetcher

        results = {
            "company": company_name,
            "ticker": ticker,
        }

        # Fetch enriched data
        fetcher = EnrichedDataFetcher()
        company_data = await fetcher.get_company_data(ticker)

        # Build data dict for deck generation
        deck_data = {
            "company": {
                "name": company_data.name,
                "description": company_data.description,
                "sector": company_data.sector,
                "industry": company_data.industry,
            },
            "financials": {
                "revenue": company_data.revenue_ttm,
                "ebitda": company_data.ebitda_ttm,
                "ebitda_margin": company_data.ebitda_margin,
                "market_cap": company_data.market_cap,
                "ev": company_data.enterprise_value,
            },
            "valuation": {
                "ev_ebitda": company_data.ev_ebitda,
                "ev_revenue": company_data.ev_revenue,
                "pe_ratio": company_data.pe_ratio,
            },
            "news": company_data.recent_news,
            "competitors": company_data.competitors,
            "industry_trends": company_data.industry_trends,
        }

        # Generate deck
        deck_result = await self.generate_investment_deck(
            company_name=company_name,
            company_symbol=ticker,
            deck_type=deck_type,
            data=deck_data,
        )

        results["deck"] = deck_result
        results["research_data"] = deck_data

        return results

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def generate_full_package(
        self,
        company_name: str,
        company_symbol: str,
        timeframe: str = "48_hour",
        assumptions: Optional[Dict] = None,
        include_slides: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate a complete deal package (Excel model + PowerPoint deck).

        Args:
            company_name: Company name
            company_symbol: Stock symbol
            timeframe: LBO model timeframe
            assumptions: Model assumptions
            include_slides: Whether to include PowerPoint deck

        Returns:
            Dict with excel and slides results
        """
        results = {"company": company_name, "symbol": company_symbol}

        # Generate Excel model
        excel_result = await self.generate_lbo_model(
            company_name=company_name,
            company_symbol=company_symbol,
            timeframe=timeframe,
            assumptions=assumptions,
        )
        results["excel"] = excel_result

        # Generate slides if requested
        if include_slides:
            slides_result = await self.generate_investment_deck(
                company_name=company_name,
                company_symbol=company_symbol,
                deck_type="standard",
            )
            results["slides"] = slides_result

        return results


# Convenience function for quick generation
async def generate_and_upload(
    user_id: str,
    company_name: str,
    company_symbol: str = None,
    model_type: str = "lbo",
    timeframe: str = "48_hour",
    **kwargs,
) -> Dict[str, Any]:
    """
    Quick function to generate a model and upload to storage.

    Args:
        user_id: User ID
        company_name: Company name
        company_symbol: Stock symbol
        model_type: "lbo", "industry_deck", "company_deck", "investment_deck"
        timeframe: For LBO models, the timeframe
        **kwargs: Additional arguments for the generator

    Returns:
        Result dictionary
    """
    storage = IBToolkitStorage(user_id=user_id)

    if model_type == "lbo":
        return await storage.generate_lbo_model(
            company_name=company_name,
            company_symbol=company_symbol,
            timeframe=timeframe,
            **kwargs,
        )
    elif model_type == "industry_deck":
        return await storage.generate_industry_deck(
            industry=company_name,
            company_symbol=company_symbol,
            **kwargs,
        )
    elif model_type == "company_deck":
        return await storage.generate_company_deck(
            company_name=company_name,
            ticker=company_symbol or "TICKER",
            **kwargs,
        )
    elif model_type == "investment_deck":
        return await storage.generate_investment_deck(
            company_name=company_name,
            company_symbol=company_symbol or "TICKER",
            **kwargs,
        )
    else:
        raise ValueError(f"Unknown model_type: {model_type}")
