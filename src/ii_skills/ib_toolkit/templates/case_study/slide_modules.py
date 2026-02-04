#!/usr/bin/env python3
"""
Modular Slide Generator for PE/IB Analysis

This module provides individual slide generation functions that can be
called independently based on the type of analysis requested.

Usage:
    from slide_modules import SlideGenerator

    gen = SlideGenerator()
    gen.add_industry_analysis(company_data)
    gen.add_competitive_analysis(company_data)
    gen.save("output.pptx")

Or for single-purpose outputs:
    gen = SlideGenerator()
    gen.add_debt_schedule(debt_data)
    gen.save("debt_analysis.pptx")
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
import os

# ============================================================
# STYLE CONSTANTS (Roberto's BCI/Northleaf style)
# ============================================================
NAVY = RGBColor(0, 54, 91)        # #00365B - Primary brand color
DARK_GRAY = RGBColor(0, 0, 0)     # #000000 - Body text
LIGHT_GRAY = RGBColor(245, 245, 245)
ACCENT_GREEN = RGBColor(34, 139, 34)
ACCENT_RED = RGBColor(178, 34, 34)
WHITE = RGBColor(255, 255, 255)
FONT_NAME = "Arial"

# ============================================================
# SLIDE MODULE REGISTRY
# ============================================================
# Maps user intents to available slide modules

SLIDE_MODULES = {
    # Industry Analysis
    "industry_analysis": {
        "name": "Industry Analysis",
        "description": "Market overview, TAM/SAM/SOM, growth drivers, industry dynamics",
        "slides": ["market_overview", "porters_five_forces", "industry_value_chain", "market_sizing"],
        "function": "add_industry_analysis"
    },

    # Competitive Analysis
    "competitive_analysis": {
        "name": "Competitive Analysis",
        "description": "Competitive landscape, market positioning, SWOT, competitive moat",
        "slides": ["competitive_landscape", "swot_analysis", "competitive_moat", "market_positioning"],
        "function": "add_competitive_analysis"
    },

    # Financial Analysis
    "financial_analysis": {
        "name": "Financial Analysis",
        "description": "Historical financials, projections, key metrics, quality of earnings",
        "slides": ["historical_summary", "projected_summary", "key_metrics", "margin_analysis"],
        "function": "add_financial_analysis"
    },

    # Valuation
    "valuation": {
        "name": "Valuation Analysis",
        "description": "Trading comps, transaction comps, DCF, football field",
        "slides": ["trading_comps", "transaction_comps", "dcf_summary", "football_field"],
        "function": "add_valuation"
    },

    # LBO / Transaction
    "lbo_analysis": {
        "name": "LBO / Transaction Analysis",
        "description": "Sources & uses, debt schedule, returns analysis, sensitivity",
        "slides": ["sources_uses", "debt_schedule", "returns_analysis", "sensitivity_matrix"],
        "function": "add_lbo_analysis"
    },

    # Debt Analysis
    "debt_analysis": {
        "name": "Debt / Capital Structure Analysis",
        "description": "Debt capacity, capital structure, coverage ratios, debt schedule",
        "slides": ["debt_capacity", "capital_structure", "coverage_analysis", "debt_schedule"],
        "function": "add_debt_analysis"
    },

    # Management Analysis
    "management_analysis": {
        "name": "Management / Team Analysis",
        "description": "Leadership team, organizational structure, compensation, track record",
        "slides": ["leadership_overview", "org_structure", "management_incentives", "track_record"],
        "function": "add_management_analysis"
    },

    # Investment Thesis
    "investment_thesis": {
        "name": "Investment Thesis & Risks",
        "description": "Thesis pillars, risk assessment, value creation, recommendation",
        "slides": ["thesis_summary", "risk_matrix", "value_creation_bridge", "recommendation"],
        "function": "add_investment_thesis"
    },

    # Company Overview
    "company_overview": {
        "name": "Company Overview",
        "description": "Business description, revenue breakdown, customer analysis, operations",
        "slides": ["business_description", "revenue_breakdown", "customer_analysis", "operations"],
        "function": "add_company_overview"
    },

    # Due Diligence
    "due_diligence": {
        "name": "Due Diligence Summary",
        "description": "DD findings, quality of earnings, key issues, next steps",
        "slides": ["dd_overview", "qoe_summary", "key_findings", "open_items"],
        "function": "add_due_diligence"
    },

    # ============================================================
    # INSTITUTIONAL MODULES (7+ Day Case)
    # ============================================================

    # Scenario Analysis
    "scenario_analysis": {
        "name": "Scenario Analysis",
        "description": "Bull/Bear/Base case comparison with probability-weighted returns",
        "slides": ["scenario_summary", "scenario_drivers", "probability_weighted_returns"],
        "function": "add_scenario_analysis"
    },

    # Management vs Buyer Case
    "management_vs_buyer": {
        "name": "Management vs Buyer Case",
        "description": "Side-by-side comparison of management projections vs buyer underwriting",
        "slides": ["case_comparison", "variance_analysis", "returns_bridge"],
        "function": "add_management_vs_buyer"
    },

    # DCF Valuation
    "dcf_valuation": {
        "name": "DCF Valuation",
        "description": "Discounted cash flow analysis with terminal value and sensitivity",
        "slides": ["dcf_summary", "fcf_bridge", "terminal_value_sensitivity"],
        "function": "add_dcf_valuation"
    },

    # Covenant Analysis
    "covenant_analysis": {
        "name": "Covenant Analysis",
        "description": "Debt covenant compliance, leverage ratios, coverage analysis",
        "slides": ["covenant_overview", "leverage_trajectory", "coverage_analysis"],
        "function": "add_covenant_analysis"
    },

    # ============================================================
    # DUE DILIGENCE & QUALITY MODULES
    # ============================================================

    # Quality of Earnings
    "quality_of_earnings": {
        "name": "Quality of Earnings",
        "description": "EBITDA normalization, adjustments, run-rate analysis",
        "slides": ["qoe_summary", "adjustment_detail", "run_rate_bridge"],
        "function": "add_quality_of_earnings"
    },

    # Working Capital
    "working_capital_analysis": {
        "name": "Working Capital Analysis",
        "description": "NWC components, days analysis, peg mechanism",
        "slides": ["nwc_components", "nwc_peg"],
        "function": "add_working_capital_analysis"
    },

    # Customer Quality
    "customer_quality": {
        "name": "Customer & Revenue Quality",
        "description": "Customer concentration, retention, unit economics",
        "slides": ["concentration", "retention_metrics", "unit_economics"],
        "function": "add_customer_quality_analysis"
    },

    # Credit Analysis
    "credit_analysis": {
        "name": "Credit & Debt Sizing",
        "description": "Credit ratios, debt capacity, stress testing",
        "slides": ["credit_ratios", "debt_capacity", "stress_test"],
        "function": "add_credit_analysis_slides"
    },

    # ============================================================
    # RETURNS & CAPITAL STRUCTURE MODULES
    # ============================================================

    # Dividend Recap
    "dividend_recap": {
        "name": "Dividend Recapitalization",
        "description": "Mid-hold dividend, capital return, returns impact",
        "slides": ["recap_overview", "returns_impact"],
        "function": "add_dividend_recap_slides"
    },

    # Refinancing
    "refinancing": {
        "name": "Refinancing Analysis",
        "description": "Rate savings, maturity extension, cost-benefit",
        "slides": ["structure_comparison", "savings_analysis"],
        "function": "add_refinancing_slides"
    },

    # Waterfall
    "waterfall": {
        "name": "Equity Waterfall",
        "description": "Cap table, distribution waterfall, LP/GP splits",
        "slides": ["cap_table", "waterfall"],
        "function": "add_waterfall_slides"
    },

    # Sponsor Economics
    "sponsor_economics": {
        "name": "Sponsor Economics",
        "description": "GP carry, management fees, fund-level returns",
        "slides": ["deal_economics", "fund_economics"],
        "function": "add_sponsor_economics_slides"
    },
}


@dataclass
class SlideData:
    """Container for slide-specific data."""
    title: str = ""
    subtitle: str = ""
    content: List[str] = field(default_factory=list)
    table_headers: List[str] = field(default_factory=list)
    table_rows: List[List[str]] = field(default_factory=list)
    source: str = ""
    notes: str = ""


class SlideGenerator:
    """
    Modular slide generator that creates specific analysis slides on demand.

    Example:
        gen = SlideGenerator(company_name="Acme Corp")
        gen.add_industry_analysis()
        gen.add_competitive_analysis()
        gen.save("acme_analysis.pptx")
    """

    def __init__(self, company_name: str = "[Company Name]", date_str: str = None):
        """Initialize the slide generator."""
        self.prs = Presentation()
        self.prs.slide_width = Inches(10)
        self.prs.slide_height = Inches(7.5)
        self.company_name = company_name
        self.date_str = date_str or datetime.now().strftime("%B %d, %Y")
        self.page_num = 0
        self._has_cover = False

    def _next_page(self) -> int:
        """Get next page number."""
        self.page_num += 1
        return self.page_num

    # ============================================================
    # CORE SLIDE BUILDERS
    # ============================================================

    def _add_cover_slide(self, title: str, subtitle: str = ""):
        """Add cover slide if not already present."""
        if self._has_cover:
            return

        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9.1), Inches(1))
        p = txBox.text_frame.paragraphs[0]
        p.text = title
        p.font.name = FONT_NAME
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = DARK_GRAY

        # Subtitle
        if subtitle:
            txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(5.2), Inches(9.1), Inches(1))
            p2 = txBox2.text_frame.paragraphs[0]
            p2.text = subtitle
            p2.font.name = FONT_NAME
            p2.font.size = Pt(14)
            p2.font.bold = True
            p2.font.color.rgb = DARK_GRAY

        # Date
        txBox3 = slide.shapes.add_textbox(Inches(2.3), Inches(6.3), Inches(2), Inches(0.2))
        p3 = txBox3.text_frame.paragraphs[0]
        p3.text = self.date_str
        p3.font.name = FONT_NAME
        p3.font.size = Pt(11)
        p3.font.color.rgb = DARK_GRAY

        self._has_cover = True

    def _add_section_header(self, section_title: str, section_number: int = None):
        """Add a section divider slide."""
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])

        # Section number
        if section_number:
            txBox = slide.shapes.add_textbox(Inches(0.5), Inches(3.0), Inches(1.5), Inches(1))
            p = txBox.text_frame.paragraphs[0]
            p.text = f"{section_number:02d}"
            p.font.name = FONT_NAME
            p.font.size = Pt(48)
            p.font.bold = True
            p.font.color.rgb = NAVY
            title_left = 2.0
        else:
            title_left = 0.5

        # Section title
        txBox2 = slide.shapes.add_textbox(Inches(title_left), Inches(3.0), Inches(7.5), Inches(1.5))
        p2 = txBox2.text_frame.paragraphs[0]
        p2.text = section_title
        p2.font.name = FONT_NAME
        p2.font.size = Pt(32)
        p2.font.bold = True
        p2.font.color.rgb = NAVY

    def _add_content_slide(self, title: str, content: List[str], subtitle: str = None,
                          source: str = None) -> Any:
        """Add a content slide with bullet points."""
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        page = self._next_page()

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.5), Inches(0.3))
        p = txBox.text_frame.paragraphs[0]
        p.text = title
        p.font.name = FONT_NAME
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = NAVY

        # Subtitle
        content_top = 1.0
        if subtitle:
            txBox_sub = slide.shapes.add_textbox(Inches(0.3), Inches(0.6), Inches(9.5), Inches(0.5))
            p_sub = txBox_sub.text_frame.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = FONT_NAME
            p_sub.font.size = Pt(11)
            p_sub.font.color.rgb = DARK_GRAY
            content_top = 1.2

        # Content
        txBox2 = slide.shapes.add_textbox(Inches(0.3), Inches(content_top), Inches(9.4), Inches(5.5))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True

        for i, item in enumerate(content):
            p = tf2.paragraphs[0] if i == 0 else tf2.add_paragraph()
            if isinstance(item, tuple):
                p.text = item[0]
                p.level = item[1]
            else:
                p.text = f"• {item}" if item and not item.startswith("•") else item
                p.level = 0
            p.font.name = FONT_NAME
            p.font.size = Pt(10)
            p.font.color.rgb = DARK_GRAY
            p.space_after = Pt(6)

        # Page number
        txBox_pg = slide.shapes.add_textbox(Inches(9.0), Inches(7.0), Inches(0.8), Inches(0.3))
        p_pg = txBox_pg.text_frame.paragraphs[0]
        p_pg.text = str(page)
        p_pg.font.name = FONT_NAME
        p_pg.font.size = Pt(10)
        p_pg.font.color.rgb = DARK_GRAY

        # Source
        if source:
            txBox_src = slide.shapes.add_textbox(Inches(0.3), Inches(7.0), Inches(8.5), Inches(0.3))
            p_src = txBox_src.text_frame.paragraphs[0]
            p_src.text = f"Source: {source}"
            p_src.font.name = FONT_NAME
            p_src.font.size = Pt(8)
            p_src.font.color.rgb = DARK_GRAY

        return slide

    def _add_table_slide(self, title: str, headers: List[str], rows: List[List[str]],
                        col_widths: List[float] = None, subtitle: str = None,
                        source: str = None) -> Any:
        """Add a slide with a data table."""
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        page = self._next_page()

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.5), Inches(0.3))
        p = txBox.text_frame.paragraphs[0]
        p.text = title
        p.font.name = FONT_NAME
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = NAVY

        # Subtitle
        table_top = 0.8
        if subtitle:
            txBox_sub = slide.shapes.add_textbox(Inches(0.3), Inches(0.6), Inches(9.5), Inches(0.5))
            p_sub = txBox_sub.text_frame.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = FONT_NAME
            p_sub.font.size = Pt(11)
            p_sub.font.color.rgb = DARK_GRAY
            table_top = 1.2

        # Table
        num_cols = len(headers)
        num_rows = len(rows) + 1

        if col_widths is None:
            col_widths = [Inches(9.4 / num_cols)] * num_cols
        else:
            col_widths = [Inches(w) for w in col_widths]

        table = slide.shapes.add_table(num_rows, num_cols, Inches(0.3), Inches(table_top),
                                       sum(col_widths), Inches(0.35 * num_rows)).table

        for i, width in enumerate(col_widths):
            table.columns[i].width = width

        # Header row
        for i, header in enumerate(headers):
            cell = table.cell(0, i)
            cell.text = header
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY
            p = cell.text_frame.paragraphs[0]
            p.font.name = FONT_NAME
            p.font.size = Pt(10)
            p.font.bold = True
            p.font.color.rgb = WHITE
            p.alignment = PP_ALIGN.CENTER

        # Data rows
        for row_idx, row_data in enumerate(rows):
            for col_idx, cell_value in enumerate(row_data):
                cell = table.cell(row_idx + 1, col_idx)
                cell.text = str(cell_value)
                p = cell.text_frame.paragraphs[0]
                p.font.name = FONT_NAME
                p.font.size = Pt(10)
                p.font.color.rgb = DARK_GRAY
                p.alignment = PP_ALIGN.LEFT if col_idx == 0 else PP_ALIGN.CENTER
                if col_idx == 0:
                    p.font.bold = True

        # Page number
        txBox_pg = slide.shapes.add_textbox(Inches(9.0), Inches(7.0), Inches(0.8), Inches(0.3))
        p_pg = txBox_pg.text_frame.paragraphs[0]
        p_pg.text = str(page)
        p_pg.font.name = FONT_NAME
        p_pg.font.size = Pt(10)
        p_pg.font.color.rgb = DARK_GRAY

        # Source
        if source:
            txBox_src = slide.shapes.add_textbox(Inches(0.3), Inches(7.0), Inches(8.5), Inches(0.3))
            p_src = txBox_src.text_frame.paragraphs[0]
            p_src.text = f"Source: {source}"
            p_src.font.name = FONT_NAME
            p_src.font.size = Pt(8)
            p_src.font.color.rgb = DARK_GRAY

        return slide

    def _add_framework_slide(self, title: str, framework_type: str, items: List,
                            subtitle: str = None) -> Any:
        """Add a framework slide (2x2, five forces, etc.)."""
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        page = self._next_page()

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(9.5), Inches(0.3))
        p = txBox.text_frame.paragraphs[0]
        p.text = title
        p.font.name = FONT_NAME
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = NAVY

        content_top = 1.0
        if subtitle:
            txBox_sub = slide.shapes.add_textbox(Inches(0.3), Inches(0.6), Inches(9.5), Inches(0.5))
            p_sub = txBox_sub.text_frame.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = FONT_NAME
            p_sub.font.size = Pt(11)
            p_sub.font.color.rgb = DARK_GRAY
            content_top = 1.2

        if framework_type == "2x2":
            positions = [
                (0.3, content_top, 4.5, 2.7),
                (5.0, content_top, 4.5, 2.7),
                (0.3, content_top + 2.9, 4.5, 2.7),
                (5.0, content_top + 2.9, 4.5, 2.7),
            ]
            colors = [NAVY, ACCENT_GREEN, RGBColor(200, 150, 50), ACCENT_RED]

            for i, (item_title, item_content) in enumerate(items[:4]):
                left, top, width, height = positions[i]

                box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                            Inches(left), Inches(top), Inches(width), Inches(height))
                box.fill.solid()
                box.fill.fore_color.rgb = RGBColor(248, 250, 252)
                box.line.color.rgb = colors[i]
                box.line.width = Pt(1.5)

                # Box title
                txBox_item = slide.shapes.add_textbox(Inches(left + 0.15), Inches(top + 0.1),
                                                      Inches(width - 0.3), Inches(0.4))
                p_item = txBox_item.text_frame.paragraphs[0]
                p_item.text = item_title
                p_item.font.name = FONT_NAME
                p_item.font.size = Pt(11)
                p_item.font.bold = True
                p_item.font.color.rgb = colors[i]

                # Box content
                txBox2 = slide.shapes.add_textbox(Inches(left + 0.15), Inches(top + 0.5),
                                                  Inches(width - 0.3), Inches(height - 0.6))
                tf2 = txBox2.text_frame
                tf2.word_wrap = True
                for j, bullet in enumerate(item_content):
                    p2 = tf2.paragraphs[0] if j == 0 else tf2.add_paragraph()
                    p2.text = f"• {bullet}"
                    p2.font.name = FONT_NAME
                    p2.font.size = Pt(9)
                    p2.font.color.rgb = DARK_GRAY

        elif framework_type == "five_forces":
            # Center - Competitive Rivalry
            center = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(3.6), Inches(3.0),
                                           Inches(2.5), Inches(1.3))
            center.fill.solid()
            center.fill.fore_color.rgb = NAVY
            center.line.fill.background()

            txBox_center = slide.shapes.add_textbox(Inches(3.7), Inches(3.2), Inches(2.3), Inches(1))
            p_center = txBox_center.text_frame.paragraphs[0]
            p_center.text = "Competitive\nRivalry"
            p_center.font.name = FONT_NAME
            p_center.font.size = Pt(12)
            p_center.font.bold = True
            p_center.font.color.rgb = WHITE
            p_center.alignment = PP_ALIGN.CENTER

            # Four forces
            force_positions = [
                (3.6, 1.0, "Threat of\nNew Entrants"),
                (3.6, 5.0, "Threat of\nSubstitutes"),
                (0.5, 3.0, "Supplier\nPower"),
                (7.0, 3.0, "Buyer\nPower"),
            ]

            for left, top, text in force_positions:
                box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                            Inches(left), Inches(top), Inches(2.5), Inches(1.2))
                box.fill.solid()
                box.fill.fore_color.rgb = RGBColor(248, 250, 252)
                box.line.color.rgb = NAVY
                box.line.width = Pt(1.5)

                txBox_force = slide.shapes.add_textbox(Inches(left + 0.1), Inches(top + 0.2),
                                                       Inches(2.3), Inches(1))
                p_force = txBox_force.text_frame.paragraphs[0]
                p_force.text = text
                p_force.font.name = FONT_NAME
                p_force.font.size = Pt(11)
                p_force.font.bold = True
                p_force.font.color.rgb = NAVY
                p_force.alignment = PP_ALIGN.CENTER

        # Page number
        txBox_pg = slide.shapes.add_textbox(Inches(9.0), Inches(7.0), Inches(0.8), Inches(0.3))
        p_pg = txBox_pg.text_frame.paragraphs[0]
        p_pg.text = str(page)
        p_pg.font.name = FONT_NAME
        p_pg.font.size = Pt(10)
        p_pg.font.color.rgb = DARK_GRAY

        return slide

    # ============================================================
    # MODULE: INDUSTRY ANALYSIS
    # ============================================================

    def add_industry_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add industry analysis slides.

        Args:
            data: Optional dict with keys: tam, sam, som, growth_rate, drivers, headwinds
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Industry Analysis")

        # Market Overview
        self._add_content_slide(
            "Market Overview",
            [
                "Total Addressable Market (TAM)",
                (f"Global market size: ${data.get('tam', 'XX')} billion (2024)", 1),
                (f"Expected CAGR: {data.get('growth_rate', 'X')}% (2024-2029)", 1),
                "",
                "Key Market Drivers",
                (data.get('drivers', ['[Driver 1]', '[Driver 2]', '[Driver 3]'])[0], 1),
                (data.get('drivers', ['[Driver 1]', '[Driver 2]', '[Driver 3]'])[1] if len(data.get('drivers', [])) > 1 else '[Driver 2]', 1),
                "",
                "Market Headwinds",
                (data.get('headwinds', ['[Risk 1]', '[Risk 2]'])[0], 1),
            ],
            subtitle=f"Industry dynamics for {self.company_name}'s target market"
        )

        # Porter's Five Forces
        self._add_framework_slide(
            "Porter's Five Forces Analysis",
            "five_forces",
            [],
            subtitle="Competitive intensity assessment"
        )

        # Industry Value Chain
        self._add_content_slide(
            "Industry Value Chain",
            [
                "Upstream (Suppliers)",
                ("[Raw materials / components suppliers]", 1),
                ("[Technology / IP providers]", 1),
                "",
                "Midstream (Operations)",
                ("[Manufacturing / service delivery]", 1),
                ("[Distribution / logistics]", 1),
                "",
                "Downstream (Customers)",
                ("[End customers / channel partners]", 1),
                "",
                f"Company Position: {self.company_name} operates in [position in value chain]",
            ],
            subtitle="Value chain positioning and integration opportunities"
        )

        return self

    # ============================================================
    # MODULE: COMPETITIVE ANALYSIS
    # ============================================================

    def add_competitive_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add competitive analysis slides.

        Args:
            data: Optional dict with competitors list and SWOT items
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Competitive Positioning")

        # Competitive Landscape Table
        competitors = data.get('competitors', [
            [self.company_name, "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor A", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor B", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor C", "$XXX", "XX%", "[Strength]", "[Weakness]"],
        ])

        self._add_table_slide(
            "Competitive Landscape",
            ["Company", "Revenue", "Share", "Key Strengths", "Key Weaknesses"],
            competitors,
            col_widths=[1.8, 1.2, 1.0, 2.4, 2.4],
            subtitle="Market share and competitive positioning",
            source="Company filings, Capital IQ, industry reports"
        )

        # SWOT Analysis
        swot = data.get('swot', {
            'strengths': ["[Market leadership]", "[Proprietary technology]", "[Strong relationships]"],
            'weaknesses': ["[Customer concentration]", "[Geographic limitations]", "[Tech gaps]"],
            'opportunities': ["[New market expansion]", "[Product extension]", "[M&A potential]"],
            'threats': ["[New entrants]", "[Technology disruption]", "[Regulatory changes]"],
        })

        self._add_framework_slide(
            "SWOT Analysis",
            "2x2",
            [
                ("STRENGTHS", swot['strengths']),
                ("WEAKNESSES", swot['weaknesses']),
                ("OPPORTUNITIES", swot['opportunities']),
                ("THREATS", swot['threats']),
            ],
            subtitle=f"Strategic positioning assessment for {self.company_name}"
        )

        # Competitive Moat
        self._add_content_slide(
            "Competitive Moat Assessment",
            [
                "Sources of Competitive Advantage",
                "",
                "1. Switching Costs: [HIGH / MEDIUM / LOW]",
                ("   [Explanation of customer lock-in]", 1),
                "",
                "2. Network Effects: [HIGH / MEDIUM / LOW]",
                ("   [Explanation of network dynamics]", 1),
                "",
                "3. Cost Advantages: [HIGH / MEDIUM / LOW]",
                ("   [Explanation of cost position]", 1),
                "",
                "4. Intangible Assets: [HIGH / MEDIUM / LOW]",
                ("   [Brands, patents, regulatory licenses]", 1),
            ],
            subtitle="Durability of competitive advantages"
        )

        return self

    # ============================================================
    # MODULE: FINANCIAL ANALYSIS
    # ============================================================

    def add_financial_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add financial analysis slides.

        Args:
            data: Optional dict with historical and projected financials
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Financial Analysis")

        # Historical Summary
        historical = data.get('historical', [
            ["Revenue", "$XXX", "$XXX", "$XXX", "X%"],
            ["% Growth", "X%", "X%", "X%", "—"],
            ["Gross Profit", "$XX", "$XX", "$XX", "X%"],
            ["% Margin", "XX%", "XX%", "XX%", "—"],
            ["EBITDA", "$XX", "$XX", "$XX", "X%"],
            ["% Margin", "XX%", "XX%", "XX%", "—"],
            ["Free Cash Flow", "$XX", "$XX", "$XX", "X%"],
        ])

        self._add_table_slide(
            "Historical Financial Summary",
            ["($M)", "FY2022", "FY2023", "FY2024", "CAGR"],
            historical,
            col_widths=[2.5, 1.5, 1.5, 1.5, 1.5],
            subtitle="3-year historical performance summary",
            source="Company filings, management data"
        )

        # Projected Summary
        projected = data.get('projected', [
            ["Revenue", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
            ["% Growth", "X%", "X%", "X%", "X%", "X%"],
            ["EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX"],
            ["% Margin", "XX%", "XX%", "XX%", "XX%", "XX%"],
            ["Unlevered FCF", "$XX", "$XX", "$XX", "$XX", "$XX"],
        ])

        self._add_table_slide(
            "Projected Financial Summary",
            ["($M)", "FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY2029E"],
            projected,
            col_widths=[1.9, 1.3, 1.3, 1.3, 1.3, 1.3],
            subtitle="5-year projected operating performance"
        )

        # Key Metrics Comparison
        self._add_table_slide(
            "Key Operating Metrics",
            ["Metric", "Company", "Peer Median", "Variance", "Commentary"],
            [
                ["Revenue Growth (3Y)", "X%", "X%", "+/- X%", "[vs peers]"],
                ["Gross Margin", "XX%", "XX%", "+/- X%", "[vs peers]"],
                ["EBITDA Margin", "XX%", "XX%", "+/- X%", "[vs peers]"],
                ["FCF Conversion", "XX%", "XX%", "+/- X%", "[quality]"],
            ],
            col_widths=[2.2, 1.3, 1.5, 1.2, 2.3],
            subtitle="Benchmarking vs. peer group median"
        )

        return self

    # ============================================================
    # MODULE: DEBT / CAPITAL STRUCTURE ANALYSIS
    # ============================================================

    def add_debt_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add debt and capital structure analysis slides.

        Args:
            data: Optional dict with debt schedule, coverage ratios, etc.
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Capital Structure Analysis")

        # Capital Structure Overview
        self._add_table_slide(
            "Current Capital Structure",
            ["Tranche", "Amount ($M)", "Rate", "Maturity", "Covenants"],
            data.get('debt_tranches', [
                ["Senior Secured (TLB)", "$XX", "L+XXX", "20XX", "X.Xx Leverage"],
                ["Second Lien", "$XX", "L+XXX", "20XX", "X.Xx Leverage"],
                ["Revolving Credit", "$XX", "L+XXX", "20XX", "—"],
                ["Total Debt", "$XXX", "—", "—", "—"],
                ["Cash", "($XX)", "—", "—", "—"],
                ["Net Debt", "$XXX", "—", "—", "—"],
            ]),
            col_widths=[2.2, 1.5, 1.3, 1.3, 2.2],
            subtitle="Existing debt facilities and key terms"
        )

        # Debt Capacity Analysis
        self._add_table_slide(
            "Debt Capacity Analysis",
            ["Metric", "Current", "Conservative", "Moderate", "Aggressive"],
            data.get('debt_capacity', [
                ["EBITDA", "$XX", "$XX", "$XX", "$XX"],
                ["Total Debt / EBITDA", "X.Xx", "3.0x", "4.5x", "6.0x"],
                ["Senior Debt / EBITDA", "X.Xx", "2.0x", "3.0x", "4.0x"],
                ["Interest Coverage", "X.Xx", "3.0x", "2.5x", "2.0x"],
                ["Implied Debt Capacity", "$XXX", "$XXX", "$XXX", "$XXX"],
            ]),
            col_widths=[2.4, 1.5, 1.5, 1.5, 1.5],
            subtitle="Incremental debt capacity under various leverage scenarios"
        )

        # Coverage Analysis
        self._add_content_slide(
            "Coverage Ratio Analysis",
            [
                "Interest Coverage (EBITDA / Cash Interest)",
                ("Current: X.Xx | Pro Forma: X.Xx | Covenant: X.Xx", 1),
                ("Headroom: $XX million or XX%", 1),
                "",
                "Fixed Charge Coverage ((EBITDA - CapEx) / Fixed Charges)",
                ("Current: X.Xx | Pro Forma: X.Xx | Covenant: X.Xx", 1),
                ("Headroom: $XX million or XX%", 1),
                "",
                "Leverage (Total Debt / EBITDA)",
                ("Current: X.Xx | Pro Forma: X.Xx | Covenant: X.Xx", 1),
                ("Deleveraging trajectory: X.Xx by Year 3", 1),
                "",
                "Assessment: [COMFORTABLE / TIGHT / AT RISK]",
            ],
            subtitle="Covenant compliance and cushion analysis"
        )

        return self

    # ============================================================
    # MODULE: LBO / TRANSACTION ANALYSIS
    # ============================================================

    def add_lbo_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add LBO and transaction analysis slides.

        Args:
            data: Optional dict with S&U, returns, sensitivities
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Transaction Analysis")

        # Sources & Uses
        self._add_table_slide(
            "Sources and Uses of Funds",
            ["Sources", "$M", "%", "", "Uses", "$M", "%"],
            data.get('sources_uses', [
                ["Senior Debt", "$XX", "XX%", "", "Purchase Price", "$XXX", "XX%"],
                ["Subordinated Debt", "$XX", "XX%", "", "Refinance Debt", "$XX", "XX%"],
                ["Rollover Equity", "$XX", "XX%", "", "Transaction Fees", "$XX", "XX%"],
                ["Sponsor Equity", "$XX", "XX%", "", "Financing Fees", "$XX", "XX%"],
                ["Total Sources", "$XXX", "100%", "", "Total Uses", "$XXX", "100%"],
            ]),
            col_widths=[1.6, 1.0, 0.9, 0.2, 1.6, 1.0, 0.9],
            subtitle="Transaction funding structure"
        )

        # Returns Analysis
        self._add_table_slide(
            "LBO Returns Analysis",
            ["Exit Yr", "EBITDA", "Multiple", "Exit EV", "Equity", "MOIC", "IRR"],
            data.get('returns', [
                ["Year 3", "$XX", "X.Xx", "$XXX", "$XXX", "X.Xx", "XX%"],
                ["Year 4", "$XX", "X.Xx", "$XXX", "$XXX", "X.Xx", "XX%"],
                ["Year 5", "$XX", "X.Xx", "$XXX", "$XXX", "X.Xx", "XX%"],
            ]),
            col_widths=[1.2, 1.2, 1.4, 1.4, 1.4, 1.2, 1.2],
            subtitle="Returns by exit year (base case multiple)"
        )

        # Sensitivity Matrix
        self._add_content_slide(
            "Returns Sensitivity Analysis",
            [
                "[Insert sensitivity matrix here]",
                "",
                "Key Sensitivities:",
                ("Entry Multiple: X.Xx - X.Xx (IRR range: XX% - XX%)", 1),
                ("Exit Multiple: X.Xx - X.Xx (IRR range: XX% - XX%)", 1),
                ("Revenue Growth: X% - X% (IRR range: XX% - XX%)", 1),
                ("EBITDA Margin: XX% - XX% (IRR range: XX% - XX%)", 1),
                "",
                "Downside Protection:",
                ("Break-even exit multiple: X.Xx (vs. entry of X.Xx)", 1),
                ("Capital protection in downside: X.Xx MOIC", 1),
            ],
            subtitle="IRR sensitivity to key value drivers"
        )

        return self

    # ============================================================
    # MODULE: MANAGEMENT ANALYSIS
    # ============================================================

    def add_management_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add management and team analysis slides.

        Args:
            data: Optional dict with management team info
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Management Analysis")

        # Leadership Overview
        self._add_table_slide(
            "Leadership Team Overview",
            ["Name", "Title", "Tenure", "Background", "Ownership"],
            data.get('leadership', [
                ["[CEO Name]", "CEO", "X yrs", "[Prior experience]", "X%"],
                ["[CFO Name]", "CFO", "X yrs", "[Prior experience]", "X%"],
                ["[COO Name]", "COO", "X yrs", "[Prior experience]", "X%"],
                ["[CTO Name]", "CTO", "X yrs", "[Prior experience]", "X%"],
            ]),
            col_widths=[1.8, 1.2, 1.0, 3.2, 1.2],
            subtitle="Key executives and management depth"
        )

        # Management Assessment
        self._add_content_slide(
            "Management Assessment",
            [
                "Strengths",
                ("[Deep industry expertise and relationships]", 1),
                ("[Proven track record of execution]", 1),
                ("[Strong alignment through equity ownership]", 1),
                "",
                "Areas to Monitor",
                ("[Succession planning for key roles]", 1),
                ("[Bandwidth for growth initiatives]", 1),
                "",
                "Key Person Risk",
                ("CEO: [HIGH / MEDIUM / LOW] - [Mitigation plan]", 1),
                ("Technical Leadership: [HIGH / MEDIUM / LOW]", 1),
                "",
                "Incentive Alignment",
                ("Management rollover: XX% of existing equity", 1),
                ("Option pool: XX% fully diluted", 1),
            ],
            subtitle="Leadership quality and continuity assessment"
        )

        return self

    # ============================================================
    # MODULE: INVESTMENT THESIS
    # ============================================================

    def add_investment_thesis(self, data: Dict = None, include_cover: bool = True):
        """
        Add investment thesis and recommendation slides.

        Args:
            data: Optional dict with thesis pillars, risks, recommendation
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Investment Thesis & Risks")

        # Investment Thesis
        self._add_content_slide(
            "Investment Thesis",
            [
                "Pillar 1: [Attractive Market Dynamics]",
                ("[Supporting point A]", 1),
                ("[Supporting point B]", 1),
                "",
                "Pillar 2: [Defensible Competitive Position]",
                ("[Supporting point A]", 1),
                ("[Supporting point B]", 1),
                "",
                "Pillar 3: [Multiple Paths to Value Creation]",
                ("[Organic growth initiatives]", 1),
                ("[Margin expansion opportunities]", 1),
                ("[M&A / tuck-in potential]", 1),
            ],
            subtitle=f"Core investment rationale for {self.company_name}"
        )

        # Risk Matrix
        risks = data.get('risks', {
            'high_high': ["[Key risk 1]", "[Key risk 2]", "Mitigant: [Action]"],
            'high_low': ["[Tail risk 1]", "Mitigant: [Action]"],
            'low_high': ["[Operational risk 1]", "Mitigant: [Action]"],
            'low_low': ["[Minor risk]", "Monitor"],
        })

        self._add_framework_slide(
            "Risk Assessment Matrix",
            "2x2",
            [
                ("HIGH IMPACT / HIGH PROBABILITY", risks['high_high']),
                ("HIGH IMPACT / LOW PROBABILITY", risks['high_low']),
                ("LOW IMPACT / HIGH PROBABILITY", risks['low_high']),
                ("LOW IMPACT / LOW PROBABILITY", risks['low_low']),
            ],
            subtitle="Risk prioritization and mitigation strategies"
        )

        # Recommendation
        recommendation = data.get('recommendation', 'INVEST')
        self._add_content_slide(
            "Investment Recommendation",
            [
                f"RECOMMENDATION: {recommendation}",
                "",
                "Key Reasons:",
                ("[Reason 1: Most compelling factor]", 1),
                ("[Reason 2: Second factor]", 1),
                ("[Reason 3: Third factor]", 1),
                "",
                "Key Conditions / Next Steps:",
                ("[Condition 1: e.g., Complete management meetings]", 1),
                ("[Condition 2: e.g., Validate customer relationships]", 1),
                "",
                "Proposed Terms:",
                ("Entry Multiple: X.Xx LTM EBITDA | Equity Check: $XX million", 1),
                ("Target IRR: XX% | Target MOIC: X.Xx", 1),
            ],
            subtitle="Final investment recommendation and terms"
        )

        return self

    # ============================================================
    # MODULE: COMPANY OVERVIEW
    # ============================================================

    def add_company_overview(self, data: Dict = None, include_cover: bool = True):
        """
        Add company overview slides.

        Args:
            data: Optional dict with company info
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Company Overview")

        # Business Description
        self._add_content_slide(
            "Business Description",
            [
                "Company Background",
                (f"Founded in [YEAR], headquartered in [LOCATION]", 1),
                ("[Brief description of core business]", 1),
                ("[Number of employees, locations, geographies]", 1),
                "",
                "Key Business Segments",
                ("[Segment 1]: XX% of revenue - [Description]", 1),
                ("[Segment 2]: XX% of revenue - [Description]", 1),
                ("[Segment 3]: XX% of revenue - [Description]", 1),
            ],
            subtitle=f"Overview of {self.company_name}'s operations"
        )

        # Revenue Breakdown
        self._add_table_slide(
            "Revenue Breakdown",
            ["Segment", "Revenue ($M)", "% of Total", "Growth", "Margin"],
            data.get('segments', [
                ["Segment A", "$XX", "XX%", "+X%", "XX%"],
                ["Segment B", "$XX", "XX%", "+X%", "XX%"],
                ["Segment C", "$XX", "XX%", "+X%", "XX%"],
                ["Total", "$XXX", "100%", "+X%", "XX%"],
            ]),
            col_widths=[2.5, 1.5, 1.5, 1.5, 1.5],
            subtitle="LTM revenue breakdown by business segment"
        )

        # Customer Analysis
        self._add_content_slide(
            "Customer Analysis",
            [
                "Customer Base Profile",
                ("Total customers: [X,XXX]", 1),
                ("Average contract value: $[XX,XXX]", 1),
                ("Customer retention rate: [XX%]", 1),
                "",
                "Top Customer Concentration",
                ("Top 10 customers: XX% of revenue", 1),
                ("Largest customer: XX% of revenue", 1),
                ("Average relationship tenure: [X] years", 1),
            ],
            subtitle="Customer concentration and retention analysis"
        )

        return self

    # ============================================================
    # MODULE: VALUATION
    # ============================================================

    def add_valuation(self, data: Dict = None, include_cover: bool = True):
        """
        Add valuation analysis slides.

        Args:
            data: Optional dict with comps and valuation data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Valuation")

        # Trading Comps
        self._add_table_slide(
            "Public Comparable Companies",
            ["Company", "EV ($M)", "EV/Rev", "EV/EBITDA", "Growth", "Margin"],
            data.get('trading_comps', [
                ["Comp A", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
                ["Comp B", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
                ["Comp C", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
                ["Mean", "—", "X.Xx", "XX.Xx", "X%", "XX%"],
                ["Median", "—", "X.Xx", "XX.Xx", "X%", "XX%"],
            ]),
            col_widths=[1.8, 1.3, 1.3, 1.5, 1.3, 1.3],
            subtitle="Trading comparables as of [Date]",
            source="Capital IQ, Company filings"
        )

        # Transaction Comps
        self._add_table_slide(
            "Precedent Transactions",
            ["Date", "Target", "Acquirer", "EV ($M)", "EV/Rev", "EV/EBITDA"],
            data.get('transaction_comps', [
                ["MM/YY", "Target A", "Buyer A", "$XXX", "X.Xx", "XX.Xx"],
                ["MM/YY", "Target B", "Buyer B", "$XXX", "X.Xx", "XX.Xx"],
                ["Mean", "—", "—", "—", "X.Xx", "XX.Xx"],
            ]),
            col_widths=[1.0, 1.8, 1.8, 1.3, 1.3, 1.5],
            subtitle="Selected M&A transactions",
            source="Capital IQ, PitchBook"
        )

        # Football Field
        self._add_content_slide(
            "Valuation Summary",
            [
                "[Insert football field chart here]",
                "",
                "Methodology Summary:",
                ("Trading Comps: $XXX - $XXX million", 1),
                ("Transaction Comps: $XXX - $XXX million", 1),
                ("DCF Analysis: $XXX - $XXX million", 1),
                ("LBO Analysis: $XXX - $XXX million (at XX% IRR)", 1),
                "",
                "Selected Valuation Range: $XXX - $XXX million",
                "Implied Multiple: X.Xx - X.Xx LTM EBITDA",
            ],
            subtitle="Valuation range across methodologies"
        )

        return self

    # ============================================================
    # INSTITUTIONAL MODULES (7+ Day Case)
    # ============================================================

    def add_scenario_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add scenario analysis slides (Bull/Bear/Base case comparison).

        Args:
            data: Optional dict with scenario assumptions and returns
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Scenario Analysis")

        # Scenario Summary
        self._add_table_slide(
            "Scenario Comparison Summary",
            ["Metric", "Bear Case", "Base Case", "Bull Case"],
            data.get('scenario_summary', [
                ["Probability", "20%", "60%", "20%"],
                ["Revenue CAGR", "3%", "6%", "10%"],
                ["Exit EBITDA Margin", "18%", "22%", "26%"],
                ["Exit Multiple", "7.0x", "8.0x", "9.0x"],
                ["Exit Year", "5", "5", "5"],
                ["MOIC", "1.5x", "2.2x", "3.0x"],
                ["IRR", "8%", "17%", "25%"],
            ]),
            col_widths=[2.5, 2.0, 2.0, 2.0],
            subtitle="Key assumptions and returns by scenario"
        )

        # Scenario Drivers
        self._add_content_slide(
            "Scenario Key Drivers",
            [
                "Bear Case Assumptions (20% probability)",
                ("Revenue growth limited to GDP + inflation", 1),
                ("Margin compression from competitive pressure", 1),
                ("Multiple contraction to historical trough", 1),
                "",
                "Base Case Assumptions (60% probability)",
                ("Revenue growth aligned with industry", 1),
                ("Margin improvement from operational initiatives", 1),
                ("Exit multiple at entry (no expansion)", 1),
                "",
                "Bull Case Assumptions (20% probability)",
                ("Market share gains driving above-market growth", 1),
                ("Full margin potential realized", 1),
                ("Multiple expansion to premium peer levels", 1),
            ],
            subtitle="Key assumptions driving each scenario"
        )

        # Probability-Weighted Returns
        self._add_table_slide(
            "Probability-Weighted Returns",
            ["Scenario", "Probability", "MOIC", "IRR", "Weighted MOIC", "Weighted IRR"],
            data.get('weighted_returns', [
                ["Bear Case", "20%", "1.5x", "8%", "0.30x", "1.6%"],
                ["Base Case", "60%", "2.2x", "17%", "1.32x", "10.2%"],
                ["Bull Case", "20%", "3.0x", "25%", "0.60x", "5.0%"],
                ["Blended", "100%", "—", "—", "2.22x", "16.8%"],
            ]),
            col_widths=[1.8, 1.3, 1.3, 1.3, 1.5, 1.5],
            subtitle="Expected returns under probability-weighted scenarios"
        )

        # Downside Protection
        self._add_content_slide(
            "Downside Protection Analysis",
            [
                "Bear Case Return Profile",
                ("Bear case MOIC: 1.5x", 1),
                ("Implies return of capital plus modest return", 1),
                ("Key downside drivers:", 1),
                ("  - Revenue shortfall: [X]% impact", 2),
                ("  - Margin compression: [X]% impact", 2),
                ("  - Multiple contraction: [X]% impact", 2),
                "",
                "Mitigants",
                ("Asset value floor: $[XXX]M (Y.Yx coverage)", 1),
                ("Debt paydown provides equity accretion", 1),
                ("Contractual revenue base of [X]%", 1),
                ("Management incentive alignment", 1),
            ],
            subtitle="Downside scenario analysis and protection measures"
        )

        return self

    def add_management_vs_buyer(self, data: Dict = None, include_cover: bool = True):
        """
        Add management vs buyer case comparison slides.

        Args:
            data: Optional dict with management and buyer projections
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Management vs Buyer Case")

        # Case Comparison Table
        self._add_table_slide(
            "Projection Case Comparison",
            ["Year", "1", "2", "3", "4", "5", "CAGR"],
            data.get('case_comparison', [
                ["Management Revenue", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX", "X%"],
                ["Buyer Revenue", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX", "X%"],
                ["  Variance", "($X)", "($X)", "($X)", "($X)", "($X)", "—"],
                ["", "", "", "", "", "", ""],
                ["Management EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX", "X%"],
                ["Buyer EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX", "X%"],
                ["  Variance", "($X)", "($X)", "($X)", "($X)", "($X)", "—"],
            ]),
            col_widths=[2.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            subtitle="Management plan vs buyer underwriting assumptions"
        )

        # Variance Drivers
        self._add_content_slide(
            "Key Variance Drivers",
            [
                "Revenue Haircut Rationale",
                ("New product launch timing: [X]% haircut", 1),
                ("Market growth assumptions: [X]% haircut", 1),
                ("Pricing assumptions: [X]% haircut", 1),
                "",
                "Margin Haircut Rationale",
                ("Cost savings timing: [X] bps haircut", 1),
                ("Synergy realization: [X] bps haircut", 1),
                ("Investment requirements: [X] bps haircut", 1),
                "",
                "Total Impact",
                ("Year 5 Revenue variance: [X]%", 1),
                ("Year 5 EBITDA variance: [X]%", 1),
                ("IRR impact: [X] percentage points", 1),
            ],
            subtitle="Justification for buyer case adjustments"
        )

        # Returns Bridge
        self._add_table_slide(
            "Returns Comparison (Year 5 Exit)",
            ["Metric", "Management Case", "Buyer Case", "Difference"],
            data.get('returns_comparison', [
                ["Exit EBITDA", "$XXM", "$XXM", "($XM)"],
                ["Exit EV", "$XXXM", "$XXXM", "($XXM)"],
                ["Exit Equity", "$XXXM", "$XXXM", "($XXM)"],
                ["MOIC", "X.Xx", "X.Xx", "(X.Xx)"],
                ["IRR", "XX%", "XX%", "(X%)"],
            ]),
            col_widths=[2.5, 2.0, 2.0, 2.0],
            subtitle="Return impact of buyer case haircuts"
        )

        return self

    def add_dcf_valuation(self, data: Dict = None, include_cover: bool = True):
        """
        Add DCF valuation slides.

        Args:
            data: Optional dict with DCF inputs and outputs
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("DCF Valuation")

        # DCF Summary
        self._add_table_slide(
            "DCF Valuation Summary",
            ["Component", "Value ($M)", "Notes"],
            data.get('dcf_summary', [
                ["PV of Projection Period FCF", "$XXX", "Years 1-5"],
                ["PV of Terminal Value", "$XXX", "Exit multiple / perpetuity"],
                ["Enterprise Value", "$XXX", "—"],
                ["Less: Net Debt", "($XX)", "As of close"],
                ["Equity Value", "$XXX", "—"],
                ["Implied EV/EBITDA", "X.Xx", "Based on LTM"],
            ]),
            col_widths=[3.5, 2.0, 3.0],
            subtitle="DCF-derived valuation"
        )

        # FCF Bridge
        self._add_table_slide(
            "Free Cash Flow Build",
            ["Year", "1", "2", "3", "4", "5", "Terminal"],
            data.get('fcf_build', [
                ["EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX", "$XX"],
                ["(-) D&A", "($X)", "($X)", "($X)", "($X)", "($X)", "($X)"],
                ["EBIT", "$XX", "$XX", "$XX", "$XX", "$XX", "$XX"],
                ["(-) Taxes", "($X)", "($X)", "($X)", "($X)", "($X)", "($X)"],
                ["(+) D&A", "$X", "$X", "$X", "$X", "$X", "$X"],
                ["(-) CapEx", "($X)", "($X)", "($X)", "($X)", "($X)", "($X)"],
                ["(-) NWC", "($X)", "($X)", "($X)", "($X)", "($X)", "$0"],
                ["UFCF", "$XX", "$XX", "$XX", "$XX", "$XX", "$XX"],
            ]),
            col_widths=[2.2, 1.0, 1.0, 1.0, 1.0, 1.0, 1.3],
            subtitle="Unlevered free cash flow projection"
        )

        # Terminal Value Sensitivity
        self._add_table_slide(
            "DCF Sensitivity Analysis",
            ["", "8.0x", "8.5x", "9.0x", "9.5x", "10.0x"],
            data.get('dcf_sensitivity', [
                ["WACC 8.0%", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["WACC 9.0%", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["WACC 10.0%", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["WACC 11.0%", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["WACC 12.0%", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
            ]),
            col_widths=[1.8, 1.4, 1.4, 1.4, 1.4, 1.4],
            subtitle="Enterprise value sensitivity to WACC and exit multiple"
        )

        return self

    def add_covenant_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add covenant analysis slides.

        Args:
            data: Optional dict with covenant projections
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Covenant Analysis")

        # Covenant Overview
        self._add_table_slide(
            "Covenant Package Overview",
            ["Covenant", "Threshold", "Test Frequency", "Cure Rights"],
            data.get('covenant_package', [
                ["Max Leverage Ratio", "X.Xx Total Debt / EBITDA", "Quarterly", "Yes - equity cure"],
                ["Min Interest Coverage", "X.Xx EBITDA / Interest", "Quarterly", "Yes - equity cure"],
                ["Min Fixed Charge Coverage", "X.Xx (EBITDA-CapEx) / Debt Service", "Quarterly", "Limited"],
                ["Max CapEx", "$XXM annually", "Annual", "Carry-forward"],
                ["Dividend Restrictions", "Available basket + RP growth", "Ongoing", "N/A"],
            ]),
            col_widths=[2.5, 2.5, 1.5, 2.0],
            subtitle="Summary of financial covenant package"
        )

        # Leverage Trajectory
        self._add_table_slide(
            "Leverage Ratio Trajectory",
            ["Year", "Close", "1", "2", "3", "4", "5"],
            data.get('leverage_trajectory', [
                ["Total Debt", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX", "$XX"],
                ["Leverage Ratio", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Covenant", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Headroom", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Status", "Pass", "Pass", "Pass", "Pass", "Pass", "Pass"],
            ]),
            col_widths=[2.0, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2],
            subtitle="Leverage covenant compliance over projection period"
        )

        # Coverage Analysis
        self._add_table_slide(
            "Interest Coverage Trajectory",
            ["Year", "Close", "1", "2", "3", "4", "5"],
            data.get('coverage_trajectory', [
                ["EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX", "$XX"],
                ["Interest Expense", "$X", "$X", "$X", "$X", "$X", "$X"],
                ["Coverage Ratio", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Covenant", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Headroom", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
                ["Status", "Pass", "Pass", "Pass", "Pass", "Pass", "Pass"],
            ]),
            col_widths=[2.0, 1.2, 1.2, 1.2, 1.2, 1.2, 1.2],
            subtitle="Interest coverage covenant compliance"
        )

        # Covenant Stress Test
        self._add_content_slide(
            "Covenant Stress Test",
            [
                "Downside Scenario Impact on Covenants",
                "",
                "Leverage Ratio Stress Test:",
                ("Base case: X.Xx (passes with X.Xx headroom)", 1),
                ("Bear case: X.Xx (passes with X.Xx headroom)", 1),
                ("Break-even EBITDA: $XXM (XX% below plan)", 1),
                "",
                "Interest Coverage Stress Test:",
                ("Base case: X.Xx (passes with X.Xx headroom)", 1),
                ("Bear case: X.Xx (passes with X.Xx headroom)", 1),
                ("Break-even EBITDA: $XXM (XX% below plan)", 1),
                "",
                "Key Takeaway: Covenant package provides [adequate/tight] flexibility",
            ],
            subtitle="Covenant compliance under stress scenarios"
        )

        return self

    # ============================================================
    # DUE DILIGENCE & QUALITY MODULES
    # ============================================================

    def add_quality_of_earnings(self, data: Dict = None, include_cover: bool = True):
        """
        Add Quality of Earnings analysis slides.

        Args:
            data: Optional dict with QoE data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Quality of Earnings")

        # QoE Summary
        self._add_table_slide(
            "EBITDA Normalization Summary",
            ["Adjustment", "LTM ($M)", "FY-1 ($M)", "Commentary"],
            data.get('adjustments', [
                ["Reported EBITDA", "$XX.X", "$XX.X", "Per management accounts"],
                ["Owner comp normalization", "+$X.X", "+$X.X", "Above-market compensation"],
                ["One-time legal costs", "+$X.X", "+$X.X", "Settlement costs"],
                ["Non-recurring consulting", "+$X.X", "+$X.X", "Carve-out related"],
                ["Stock-based compensation", "+$X.X", "+$X.X", "Non-cash expense"],
                ["Run-rate cost savings", "+$X.X", "—", "In-progress initiatives"],
                ["Adjusted EBITDA", "$XX.X", "$XX.X", "Normalized earnings"],
            ]),
            col_widths=[2.5, 1.5, 1.5, 3.0],
            subtitle="EBITDA adjustments and normalization"
        )

        # Adjustment Categories
        self._add_content_slide(
            "Key QoE Findings",
            [
                "Revenue Quality",
                ("XX% of revenue is recurring/contractual", 1),
                ("Top 10 customers represent XX% of revenue", 1),
                ("No material revenue recognition issues identified", 1),
                "",
                "Cost Structure",
                ("Gross margin stable at XX% over 3 years", 1),
                ("SG&A includes $X.XM of one-time items", 1),
                ("Identified $X.XM of run-rate cost savings", 1),
                "",
                "Key Adjustments",
                ("Total add-backs: $X.XM (XX% of reported EBITDA)", 1),
                ("Largest adjustment: [description]", 1),
                ("All adjustments supported by documentation", 1),
            ],
            subtitle="Summary of due diligence findings"
        )

        # Run-Rate Bridge
        self._add_table_slide(
            "Run-Rate EBITDA Bridge",
            ["Item", "Amount ($M)", "Timing", "Confidence"],
            data.get('run_rate', [
                ["Adjusted LTM EBITDA", "$XX.X", "—", "—"],
                ["Full-year price increase", "+$X.X", "Q1 implementation", "High"],
                ["New customer annualization", "+$X.X", "Signed contracts", "High"],
                ["Planned cost reductions", "+$X.X", "In progress", "Medium"],
                ["Lost customer impact", "($X.X)", "Known churn", "High"],
                ["Run-Rate EBITDA", "$XX.X", "—", "—"],
            ]),
            col_widths=[3.0, 1.5, 2.0, 1.5],
            subtitle="Bridge from adjusted to run-rate EBITDA"
        )

        return self

    def add_working_capital_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add Working Capital analysis slides.

        Args:
            data: Optional dict with NWC data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Working Capital Analysis")

        # NWC Components
        self._add_table_slide(
            "Working Capital Components",
            ["Component", "LTM ($M)", "FY-1", "FY-2", "Avg", "Days"],
            data.get('nwc_components', [
                ["Accounts Receivable", "$XX", "$XX", "$XX", "$XX", "XX"],
                ["Inventory", "$XX", "$XX", "$XX", "$XX", "XX"],
                ["Prepaid Expenses", "$X", "$X", "$X", "$X", "—"],
                ["Accounts Payable", "($XX)", "($XX)", "($XX)", "($XX)", "XX"],
                ["Accrued Expenses", "($X)", "($X)", "($X)", "($X)", "—"],
                ["Deferred Revenue", "($X)", "($X)", "($X)", "($X)", "—"],
                ["Net Working Capital", "$XX", "$XX", "$XX", "$XX", "—"],
            ]),
            col_widths=[2.5, 1.2, 1.2, 1.2, 1.2, 1.2],
            subtitle="Historical NWC components and days analysis"
        )

        # NWC Peg Analysis
        self._add_content_slide(
            "NWC Peg Mechanism",
            [
                "Target NWC Calculation",
                ("Methodology: Trailing 12-month average", 1),
                ("Target NWC: $XX.XM", 1),
                ("Estimated closing NWC: $XX.XM", 1),
                "",
                "Purchase Agreement Mechanism",
                ("Estimated adjustment: $X.XM [to buyer/seller]", 1),
                ("True-up period: 90 days post-close", 1),
                ("Dispute resolution: Independent accountant", 1),
                "",
                "Key Considerations",
                ("Seasonality impact: Q4 NWC typically XX% higher", 1),
                ("Excluded items: Cash, debt, transaction expenses", 1),
                ("Collar: +/- $X.XM de minimis threshold", 1),
            ],
            subtitle="NWC target and adjustment mechanism"
        )

        return self

    def add_customer_quality_analysis(self, data: Dict = None, include_cover: bool = True):
        """
        Add Customer/Revenue Quality analysis slides.

        Args:
            data: Optional dict with customer data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Customer & Revenue Quality")

        # Customer Concentration
        self._add_table_slide(
            "Customer Concentration Analysis",
            ["Customer", "Revenue ($M)", "% of Total", "Tenure", "Contract"],
            data.get('customers', [
                ["Customer A", "$XX", "XX%", "X yrs", "Multi-year"],
                ["Customer B", "$XX", "XX%", "X yrs", "Annual"],
                ["Customer C", "$XX", "XX%", "X yrs", "Multi-year"],
                ["Customer D", "$XX", "XX%", "X yrs", "Annual"],
                ["Customer E", "$XX", "XX%", "X yrs", "M-t-M"],
                ["Other (XXX customers)", "$XXX", "XX%", "Avg X yrs", "Various"],
                ["Total", "$XXX", "100%", "—", "—"],
            ]),
            col_widths=[2.5, 1.5, 1.2, 1.2, 1.5],
            subtitle="Top customer analysis and concentration risk"
        )

        # Retention Metrics
        self._add_table_slide(
            "Revenue Retention & Churn",
            ["Metric", "FY-2", "FY-1", "LTM", "Trend"],
            data.get('retention', [
                ["Gross Revenue Retention", "XX%", "XX%", "XX%", "→"],
                ["Net Revenue Retention", "XXX%", "XXX%", "XXX%", "↑"],
                ["Logo Churn Rate", "X%", "X%", "X%", "↓"],
                ["Dollar Churn Rate", "X%", "X%", "X%", "↓"],
            ]),
            col_widths=[3.0, 1.5, 1.5, 1.5, 1.0],
            subtitle="Customer retention and churn analysis"
        )

        # Unit Economics
        self._add_content_slide(
            "Unit Economics Summary",
            [
                "Customer Acquisition",
                ("Customer Acquisition Cost (CAC): $X,XXX", 1),
                ("CAC Payback Period: XX months", 1),
                ("Sales efficiency: X.Xx (LTV/CAC)", 1),
                "",
                "Customer Lifetime Value",
                ("Average Revenue Per User: $XX,XXX", 1),
                ("Gross Margin: XX%", 1),
                ("Annual Churn: X%", 1),
                ("LTV: $XXX,XXX", 1),
                "",
                "Assessment",
                ("LTV/CAC of X.Xx indicates [healthy/marginal] unit economics", 1),
                ("[Revenue quality is strong due to X, Y, Z]", 1),
            ],
            subtitle="Customer acquisition and lifetime value analysis"
        )

        return self

    def add_credit_analysis_slides(self, data: Dict = None, include_cover: bool = True):
        """
        Add Credit/Debt Sizing analysis slides.

        Args:
            data: Optional dict with credit data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Credit Analysis")

        # Credit Metrics
        self._add_table_slide(
            "Key Credit Ratios",
            ["Ratio", "Current", "Covenant", "Headroom", "Status"],
            data.get('ratios', [
                ["Total Debt / EBITDA", "X.Xx", "X.Xx", "X.Xx", "Pass"],
                ["Net Debt / EBITDA", "X.Xx", "X.Xx", "X.Xx", "Pass"],
                ["EBITDA / Interest", "X.Xx", "X.Xx", "X.Xx", "Pass"],
                ["(EBITDA-CapEx) / Interest", "X.Xx", "X.Xx", "X.Xx", "Pass"],
                ["Fixed Charge Coverage", "X.Xx", "X.Xx", "X.Xx", "Pass"],
            ]),
            col_widths=[2.5, 1.3, 1.3, 1.3, 1.3],
            subtitle="Current leverage and coverage metrics"
        )

        # Debt Capacity
        self._add_table_slide(
            "Debt Capacity Analysis",
            ["Constraint", "Max Debt ($M)", "Implied Multiple", "Binding?"],
            data.get('capacity', [
                ["Leverage Ratio (5.5x)", "$XXX", "5.5x", ""],
                ["Interest Coverage (2.0x)", "$XXX", "X.Xx", ""],
                ["Fixed Charge (1.5x)", "$XXX", "X.Xx", "✓"],
                ["Senior Secured (4.0x)", "$XXX", "4.0x", ""],
            ]),
            col_widths=[3.0, 2.0, 2.0, 1.5],
            subtitle="Maximum debt capacity under various constraints"
        )

        # Stress Test
        self._add_table_slide(
            "EBITDA Stress Test",
            ["Decline", "EBITDA ($M)", "Leverage", "Coverage", "Status"],
            data.get('stress_test', [
                ["Base Case", "$XX", "X.Xx", "X.Xx", "Pass"],
                ["-10%", "$XX", "X.Xx", "X.Xx", "Pass"],
                ["-20%", "$XX", "X.Xx", "X.Xx", "Pass"],
                ["-30%", "$XX", "X.Xx", "X.Xx", "Tight"],
                ["-40%", "$XX", "X.Xx", "X.Xx", "Breach"],
            ]),
            col_widths=[1.5, 1.5, 1.5, 1.5, 1.5],
            subtitle="Covenant compliance under EBITDA stress scenarios"
        )

        return self

    # ============================================================
    # RETURNS & CAPITAL STRUCTURE MODULES
    # ============================================================

    def add_dividend_recap_slides(self, data: Dict = None, include_cover: bool = True):
        """
        Add Dividend Recapitalization analysis slides.

        Args:
            data: Optional dict with recap data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Dividend Recapitalization")

        # Recap Structure
        self._add_content_slide(
            "Dividend Recap Overview",
            [
                "Transaction Summary",
                ("Timing: Year [X] of hold period", 1),
                ("New debt raised: $XXM", 1),
                ("Net dividend to equity: $XXM", 1),
                "",
                "Capital Structure Impact",
                ("Pre-recap leverage: X.Xx", 1),
                ("Post-recap leverage: X.Xx", 1),
                ("Interest rate on new debt: X.X%", 1),
                "",
                "Rationale",
                ("Return capital to LPs while maintaining ownership", 1),
                ("De-risk investment ahead of exit", 1),
                ("Take advantage of favorable debt markets", 1),
            ],
            subtitle="Mid-hold dividend recapitalization"
        )

        # Returns Impact
        self._add_table_slide(
            "Returns Impact Analysis",
            ["Metric", "Without Recap", "With Recap", "Impact"],
            data.get('returns_impact', [
                ["Initial Equity", "$XXXM", "$XXXM", "—"],
                ["Dividend (Year X)", "—", "$XXM", "+$XXM"],
                ["Exit Equity", "$XXXM", "$XXXM", "($XXM)"],
                ["Total Proceeds", "$XXXM", "$XXXM", "+$XXM"],
                ["MOIC", "X.Xx", "X.Xx", "+X.Xx"],
                ["IRR", "XX%", "XX%", "+X%"],
            ]),
            col_widths=[2.5, 2.0, 2.0, 1.5],
            subtitle="Comparison of returns with and without recap"
        )

        return self

    def add_refinancing_slides(self, data: Dict = None, include_cover: bool = True):
        """
        Add Refinancing Analysis slides.

        Args:
            data: Optional dict with refinancing data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Refinancing Analysis")

        # Current vs New Structure
        self._add_table_slide(
            "Debt Structure Comparison",
            ["Tranche", "Current ($M)", "Rate", "New ($M)", "Rate"],
            data.get('structure', [
                ["Term Loan A", "$XXX", "X.X%", "—", "—"],
                ["Term Loan B", "$XXX", "X.X%", "$XXX", "X.X%"],
                ["Senior Notes", "$XX", "X.X%", "—", "—"],
                ["Total", "$XXX", "X.X%", "$XXX", "X.X%"],
            ]),
            col_widths=[2.0, 1.5, 1.2, 1.5, 1.2],
            subtitle="Current debt structure vs. refinancing proposal"
        )

        # Savings Analysis
        self._add_content_slide(
            "Refinancing Economics",
            [
                "Annual Savings",
                ("Current interest expense: $X.XM", 1),
                ("New interest expense: $X.XM", 1),
                ("Annual savings: $X.XM", 1),
                ("Rate reduction: XXX bps", 1),
                "",
                "Transaction Costs",
                ("Call premium / make-whole: $X.XM", 1),
                ("Arrangement fee: $X.XM", 1),
                ("Legal & advisory: $X.XM", 1),
                ("Total costs: $X.XM", 1),
                "",
                "Payback Analysis",
                ("Payback period: X.X years", 1),
                ("Recommendation: [Proceed / Wait]", 1),
            ],
            subtitle="Cost-benefit analysis of refinancing"
        )

        return self

    def add_waterfall_slides(self, data: Dict = None, include_cover: bool = True):
        """
        Add Cap Table / Waterfall analysis slides.

        Args:
            data: Optional dict with waterfall data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Equity Waterfall")

        # Cap Table
        self._add_table_slide(
            "Capitalization Table",
            ["Investor", "Invested ($M)", "Ownership", "Security"],
            data.get('cap_table', [
                ["Sponsor Fund", "$XXX", "XX%", "Common"],
                ["Co-Investors", "$XX", "XX%", "Common"],
                ["Management", "$X", "X%", "Common"],
                ["Rollover Equity", "$X", "X%", "Common"],
                ["Total", "$XXX", "100%", "—"],
            ]),
            col_widths=[2.5, 2.0, 1.5, 2.0],
            subtitle="Ownership structure at close"
        )

        # Waterfall
        self._add_table_slide(
            "Distribution Waterfall by Exit Value",
            ["Component", "$200M", "$300M", "$400M", "$500M"],
            data.get('waterfall', [
                ["Return of Capital", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["Preferred Return", "$XX", "$XX", "$XX", "$XX"],
                ["GP Catch-Up", "$X", "$XX", "$XX", "$XX"],
                ["Remaining (80/20)", "$X", "$XX", "$XX", "$XX"],
                ["Total to LPs", "$XXX", "$XXX", "$XXX", "$XXX"],
                ["Total to GP (Carry)", "$X", "$XX", "$XX", "$XX"],
                ["LP MOIC", "X.Xx", "X.Xx", "X.Xx", "X.Xx"],
            ]),
            col_widths=[2.5, 1.5, 1.5, 1.5, 1.5],
            subtitle="LP and GP distributions at various exit values"
        )

        return self

    def add_sponsor_economics_slides(self, data: Dict = None, include_cover: bool = True):
        """
        Add Sponsor Economics analysis slides.

        Args:
            data: Optional dict with sponsor data
            include_cover: Whether to add a section header
        """
        data = data or {}

        if include_cover:
            self._add_section_header("Sponsor Economics")

        # Deal Economics
        self._add_content_slide(
            "GP Economics - This Deal",
            [
                "Deal Investment",
                ("Deal equity: $XXXM (XX% of fund)", 1),
                ("Expected MOIC: X.Xx", 1),
                ("Expected IRR: XX%", 1),
                "",
                "GP Economics",
                ("Carried interest (20% of profit): $XXM", 1),
                ("GP co-invest return: $X.XM", 1),
                ("Total GP economics: $XXM", 1),
                "",
                "Fund Context",
                ("Fund size: $XXXM", 1),
                ("This deal as % of fund: XX%", 1),
                ("Hurdle rate: X%", 1),
            ],
            subtitle="GP carried interest and co-investment returns"
        )

        # Fund Level
        self._add_table_slide(
            "Fund-Level Economics (Illustrative)",
            ["Component", "Amount ($M)", "% of Fund"],
            data.get('fund_economics', [
                ["Fund Size (Committed)", "$XXX", "1.0x"],
                ["Gross Proceeds", "$X,XXX", "X.Xx"],
                ["Gross Profit", "$XXX", "—"],
                ["", "", ""],
                ["Management Fees (total)", "$XX", "X%"],
                ["Carried Interest (20%)", "$XXX", "XX%"],
                ["GP Co-Invest Profit", "$XX", "X%"],
                ["", "", ""],
                ["Total GP Revenue", "$XXX", "—"],
            ]),
            col_widths=[3.5, 2.0, 1.5],
            subtitle="Illustrative fund-level GP economics"
        )

        return self

    # ============================================================
    # FULL DECK GENERATION
    # ============================================================

    def add_full_deck(self, data: Dict = None):
        """
        Generate a complete investment memo deck with all modules.

        Args:
            data: Optional dict with all data for population
        """
        data = data or {}

        # Cover
        self._add_cover_slide(
            f"{self.company_name} Investment Analysis",
            "Private Equity Case Study"
        )

        # Table of Contents
        self._add_content_slide(
            "Table of Contents",
            [
                "1. Executive Summary",
                "2. Company Overview",
                "3. Industry Analysis",
                "4. Competitive Positioning",
                "5. Financial Analysis",
                "6. Valuation",
                "7. Transaction Analysis",
                "8. Investment Thesis & Risks",
            ]
        )

        # Add all modules
        self.add_company_overview(data.get('company'), include_cover=True)
        self.add_industry_analysis(data.get('industry'), include_cover=True)
        self.add_competitive_analysis(data.get('competitive'), include_cover=True)
        self.add_financial_analysis(data.get('financial'), include_cover=True)
        self.add_valuation(data.get('valuation'), include_cover=True)
        self.add_lbo_analysis(data.get('lbo'), include_cover=True)
        self.add_investment_thesis(data.get('thesis'), include_cover=True)

        return self

    # ============================================================
    # OUTPUT
    # ============================================================

    def save(self, filepath: str) -> str:
        """Save the presentation to file."""
        self.prs.save(filepath)
        print(f"Presentation saved: {filepath}")
        print(f"Total slides: {len(self.prs.slides)}")
        return filepath

    def get_presentation(self) -> Presentation:
        """Return the raw presentation object for further manipulation."""
        return self.prs


# ============================================================
# QUICK ACCESS FUNCTIONS
# ============================================================

def generate_industry_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just industry analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Industry Analysis", "Market & Competitive Dynamics")
    gen.add_industry_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_competitive_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just competitive analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Competitive Analysis", "Market Positioning Assessment")
    gen.add_competitive_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_financial_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just financial analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Financial Analysis", "Historical & Projected Performance")
    gen.add_financial_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_debt_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just debt/capital structure slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Capital Structure Analysis", "Debt Capacity & Coverage")
    gen.add_debt_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_lbo_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just LBO/transaction slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Transaction Analysis", "LBO Returns & Sensitivity")
    gen.add_lbo_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_management_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just management analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Management Analysis", "Leadership & Team Assessment")
    gen.add_management_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_valuation_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just valuation slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Valuation Analysis", "Comparable Companies & Transactions")
    gen.add_valuation(data, include_cover=False)
    return gen.save(output_path)


def generate_investment_thesis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate just thesis and recommendation slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Investment Recommendation", "Thesis, Risks & Decision")
    gen.add_investment_thesis(data, include_cover=False)
    return gen.save(output_path)


def generate_full_deck(company_name: str, output_path: str, data: Dict = None) -> str:
    """Generate a complete investment memo deck."""
    gen = SlideGenerator(company_name)
    gen.add_full_deck(data)
    return gen.save(output_path)


# ============================================================
# INSTITUTIONAL MODULE QUICK ACCESS FUNCTIONS (7+ Day Case)
# ============================================================

def generate_scenario_analysis(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate scenario analysis slides (Bull/Bear/Base)."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Scenario Analysis", "Bull/Bear/Base Case Comparison")
    gen.add_scenario_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_management_vs_buyer(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate management vs buyer case comparison slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Case Comparison", "Management vs Buyer Underwriting")
    gen.add_management_vs_buyer(data, include_cover=False)
    return gen.save(output_path)


def generate_dcf_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate DCF valuation slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - DCF Analysis", "Discounted Cash Flow Valuation")
    gen.add_dcf_valuation(data, include_cover=False)
    return gen.save(output_path)


def generate_covenant_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate covenant analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Covenant Analysis", "Financial Covenant Compliance")
    gen.add_covenant_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_institutional_deck(company_name: str, output_path: str, data: Dict = None) -> str:
    """Generate all institutional-quality slides (7+ day case depth)."""
    data = data or {}
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Institutional Analysis", "Comprehensive Investment Analysis")

    # Core modules
    gen.add_company_overview(data.get('company'), include_cover=True)
    gen.add_industry_analysis(data.get('industry'), include_cover=True)
    gen.add_competitive_analysis(data.get('competitive'), include_cover=True)
    gen.add_financial_analysis(data.get('financial'), include_cover=True)
    gen.add_valuation(data.get('valuation'), include_cover=True)
    gen.add_lbo_analysis(data.get('lbo'), include_cover=True)

    # Institutional modules
    gen.add_scenario_analysis(data.get('scenarios'), include_cover=True)
    gen.add_management_vs_buyer(data.get('mgmt_vs_buyer'), include_cover=True)
    gen.add_dcf_valuation(data.get('dcf'), include_cover=True)
    gen.add_covenant_analysis(data.get('covenants'), include_cover=True)

    # Thesis and recommendation
    gen.add_investment_thesis(data.get('thesis'), include_cover=True)

    return gen.save(output_path)


# ============================================================
# DUE DILIGENCE & QUALITY QUICK ACCESS
# ============================================================

def generate_qoe_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Quality of Earnings slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Quality of Earnings", "EBITDA Normalization & Run-Rate Analysis")
    gen.add_quality_of_earnings(data, include_cover=False)
    return gen.save(output_path)


def generate_nwc_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Working Capital analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Working Capital Analysis", "NWC Components & Peg Mechanism")
    gen.add_working_capital_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_customer_quality_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Customer/Revenue Quality slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Customer Quality", "Concentration, Retention & Unit Economics")
    gen.add_customer_quality_analysis(data, include_cover=False)
    return gen.save(output_path)


def generate_credit_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Credit Analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Credit Analysis", "Debt Capacity & Stress Testing")
    gen.add_credit_analysis_slides(data, include_cover=False)
    return gen.save(output_path)


# ============================================================
# RETURNS & CAPITAL STRUCTURE QUICK ACCESS
# ============================================================

def generate_dividend_recap_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Dividend Recap slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Dividend Recapitalization", "Capital Return Analysis")
    gen.add_dividend_recap_slides(data, include_cover=False)
    return gen.save(output_path)


def generate_refinancing_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Refinancing Analysis slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Refinancing Analysis", "Rate Savings & Cost-Benefit")
    gen.add_refinancing_slides(data, include_cover=False)
    return gen.save(output_path)


def generate_waterfall_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Equity Waterfall slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Equity Waterfall", "Cap Table & Distribution Analysis")
    gen.add_waterfall_slides(data, include_cover=False)
    return gen.save(output_path)


def generate_sponsor_economics_slides(company_name: str, output_path: str, data: Dict = None) -> str:
    """Quick function to generate Sponsor Economics slides."""
    gen = SlideGenerator(company_name)
    gen._add_cover_slide(f"{company_name} - Sponsor Economics", "GP Carry & Fund Returns")
    gen.add_sponsor_economics_slides(data, include_cover=False)
    return gen.save(output_path)


# ============================================================
# MODULE LISTING
# ============================================================

def list_available_modules() -> Dict:
    """Return the registry of available slide modules."""
    return SLIDE_MODULES


def get_module_info(module_name: str) -> Dict:
    """Get information about a specific module."""
    return SLIDE_MODULES.get(module_name, {})


if __name__ == "__main__":
    print("=" * 60)
    print("Modular Slide Generator - Available Modules")
    print("=" * 60)

    for key, info in SLIDE_MODULES.items():
        print(f"\n{info['name']} ({key})")
        print(f"  {info['description']}")
        print(f"  Slides: {', '.join(info['slides'])}")

    print("\n" + "=" * 60)
    print("Quick Generation Functions:")
    print("=" * 60)
    print("  generate_industry_analysis(company, path)")
    print("  generate_competitive_analysis(company, path)")
    print("  generate_financial_analysis(company, path)")
    print("  generate_debt_analysis(company, path)")
    print("  generate_lbo_analysis(company, path)")
    print("  generate_management_analysis(company, path)")
    print("  generate_valuation_analysis(company, path)")
    print("  generate_investment_thesis(company, path)")
    print("  generate_full_deck(company, path)")

    print("\n" + "=" * 60)
    print("Institutional Functions (7+ Day Case):")
    print("=" * 60)
    print("  generate_scenario_analysis(company, path)")
    print("  generate_management_vs_buyer(company, path)")
    print("  generate_dcf_slides(company, path)")
    print("  generate_covenant_slides(company, path)")
    print("  generate_institutional_deck(company, path)")
