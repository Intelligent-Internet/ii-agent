"""
IR Toolkit PowerPoint Generator

Generates slides paired with Excel modules for infrastructure IR deliverables.
Each Excel module has a corresponding slide with headline and key takeaways.

Core Principle: Every Excel analysis has a matching PowerPoint slide.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

try:
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.oxml.ns import qn
    from pptx.oxml import parse_xml
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False
    logger.warning("python-pptx not installed. Slide generation will be limited.")


@dataclass
class SlideSpec:
    """Specification for a slide."""
    title: str
    headline: str
    takeaways: List[str]
    data_table: Optional[Dict] = None
    chart_type: Optional[str] = None
    footer_note: Optional[str] = None


# Slide specifications by module
SLIDE_SPECS = {
    "performance_summary": SlideSpec(
        title="Fund Performance Summary",
        headline="Returns remain in top-quartile driven by stable cash yield",
        takeaways=[
            "Net IRR of X% positions fund in top quartile",
            "DPI of X.Xx demonstrates strong cash generation",
            "TVPI of X.Xx reflects both realized and unrealized value",
        ],
        chart_type="performance_bar",
    ),
    "cash_flow_waterfall": SlideSpec(
        title="Cash Flow Summary",
        headline="Distributions supported by contracted revenue",
        takeaways=[
            "Total distributions of $Xm to date",
            "Net cash flow positive for X consecutive quarters",
            "Coverage ratio remains above target at X.Xx",
        ],
        chart_type="waterfall",
    ),
    "asset_kpi_dashboard": SlideSpec(
        title="Asset KPI Dashboard",
        headline="Operational performance exceeds targets",
        takeaways=[
            "Availability improved to X% post-maintenance",
            "Utilization at X% reflects strong demand",
            "Safety metrics remain excellent (TRIR: X.X)",
        ],
        chart_type="kpi_table",
    ),
    "nav_rollforward": SlideSpec(
        title="NAV Roll-Forward",
        headline="NAV growth driven by cash yield and FX tailwinds",
        takeaways=[
            "Opening NAV: $Xm",
            "Valuation gains of $Xm from operational improvements",
            "Closing NAV: $Xm (+X% QoQ)",
        ],
        chart_type="waterfall",
    ),
    "leverage_coverage": SlideSpec(
        title="Leverage & Coverage Profile",
        headline="Conservative leverage with strong coverage ratios",
        takeaways=[
            "Net Debt/EBITDA at X.Xx (target: <5.0x)",
            "DSCR at X.Xx provides ample covenant headroom",
            "No near-term maturities; refinancing risk minimal",
        ],
        chart_type="leverage_chart",
    ),
    "risk_register": SlideSpec(
        title="Risk Register Summary",
        headline="Key risks identified with mitigation plans",
        takeaways=[
            "X high-priority risks under active management",
            "Regulatory exposure mitigated through diversification",
            "Counterparty risk within acceptable limits",
        ],
        chart_type="risk_matrix",
    ),
    "fund_snapshot": SlideSpec(
        title="Fund Overview",
        headline="Diversified infrastructure strategy with proven track record",
        takeaways=[
            "Fund size: $X billion",
            "Vintage: XXXX",
            "Strategy: Core/Core+ infrastructure",
        ],
        chart_type="overview_table",
    ),
    "portfolio_composition": SlideSpec(
        title="Portfolio Composition",
        headline="Diversified portfolio reduces concentration risk",
        takeaways=[
            "X assets across Y sectors",
            "Geographic diversification across Z regions",
            "X% contracted revenue provides stability",
        ],
        chart_type="pie_chart",
    ),
    "track_record": SlideSpec(
        title="Track Record",
        headline="Consistent top-quartile performance across vintages",
        takeaways=[
            "X funds with combined AUM of $X billion",
            "Average net IRR of X% across realized investments",
            "X.Xx average MOIC on exited deals",
        ],
        chart_type="track_record_table",
    ),
    "term_sheet": SlideSpec(
        title="Terms Summary",
        headline="Aligned terms with strong LP protections",
        takeaways=[
            "Management fee: X% on committed capital",
            "Carry: X% with X% hurdle",
            "Key person and no-fault termination provisions",
        ],
        chart_type="terms_table",
    ),
    "esg_metrics": SlideSpec(
        title="ESG Performance",
        headline="Strong ESG performance across key metrics",
        takeaways=[
            "Scope 1+2 emissions: X tCO2e",
            "TRIR: X.X (below industry average)",
            "X% of portfolio with ESG certifications",
        ],
        chart_type="esg_scorecard",
    ),
    "ddq_tracker": SlideSpec(
        title="DDQ Status",
        headline="X% of DDQ items closed; X high-priority pending",
        takeaways=[
            "Total questions: X",
            "Completed: X (X%)",
            "Target completion date: XXXX",
        ],
        chart_type="status_table",
    ),
    "fundraising_pipeline": SlideSpec(
        title="Fundraising Pipeline",
        headline="Strong LP interest with diverse investor base",
        takeaways=[
            "Pipeline value: $X billion",
            "X% in advanced stages",
            "Regional mix: X% NA, X% Europe, X% APAC",
        ],
        chart_type="funnel",
    ),
}


class IRSlideGenerator:
    """
    Generates PowerPoint slides for IR modules.

    Each module produces a slide with:
    - Clear headline summarizing key insight
    - Supporting data visualization or table
    - 3 key takeaways
    - Source/footnote attribution
    """

    def __init__(self, output_dir: Path):
        """
        Initialize the slide generator.

        Args:
            output_dir: Directory for output files
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_module_slide(
        self,
        module,  # IRModule from orchestrator
        state,   # IRState from orchestrator
    ) -> str:
        """
        Generate a slide for a module.

        Args:
            module: The IR module to generate slide for
            state: Current IR state with data

        Returns:
            Path to generated slide file
        """
        if not PPTX_AVAILABLE:
            logger.warning("python-pptx not available, creating placeholder")
            return await self._create_placeholder(module)

        # Get slide spec
        spec = SLIDE_SPECS.get(module.id)
        if not spec:
            spec = self._create_default_spec(module)

        # Create presentation
        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # Add slide
        slide = self._add_content_slide(prs, spec, module, state)

        # Save
        filename = f"{module.id}_slide.pptx"
        output_path = self.output_dir / filename
        prs.save(str(output_path))

        logger.info(f"Generated slide: {output_path}")
        return str(output_path)

    def _add_content_slide(
        self,
        prs: "Presentation",
        spec: SlideSpec,
        module,
        state,
    ):
        """Add a content slide to the presentation."""
        # Use blank layout
        blank_layout = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank_layout)

        # Add title bar (dark blue background)
        title_shape = slide.shapes.add_shape(
            1,  # Rectangle
            Inches(0), Inches(0),
            Inches(13.333), Inches(0.8)
        )
        title_shape.fill.solid()
        self._set_rgb_color(title_shape.fill, "1F4E79")  # Dark blue
        title_shape.line.fill.background()

        # Add title text
        title_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(0.15),
            Inches(12), Inches(0.5)
        )
        title_frame = title_box.text_frame
        title_para = title_frame.paragraphs[0]
        title_para.text = spec.title
        title_para.font.size = Pt(28)
        title_para.font.bold = True
        self._set_font_color(title_para, "FFFFFF")

        # Add headline
        headline_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(1.0),
            Inches(12), Inches(0.6)
        )
        headline_frame = headline_box.text_frame
        headline_para = headline_frame.paragraphs[0]
        headline_para.text = spec.headline
        headline_para.font.size = Pt(24)
        headline_para.font.bold = True
        self._set_font_color(headline_para, "1F4E79")

        # Add takeaways
        takeaway_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(1.8),
            Inches(6), Inches(4)
        )
        takeaway_frame = takeaway_box.text_frame
        takeaway_frame.word_wrap = True

        for i, takeaway in enumerate(spec.takeaways):
            if i == 0:
                para = takeaway_frame.paragraphs[0]
            else:
                para = takeaway_frame.add_paragraph()
            para.text = f"• {takeaway}"
            para.font.size = Pt(16)
            para.space_after = Pt(12)
            self._set_font_color(para, "333333")

        # Add placeholder for chart/table area
        chart_box = slide.shapes.add_shape(
            1,  # Rectangle
            Inches(7), Inches(1.8),
            Inches(5.8), Inches(4.5)
        )
        chart_box.fill.solid()
        self._set_rgb_color(chart_box.fill, "F5F5F5")  # Light gray
        chart_box.line.fill.solid()
        self._set_rgb_color(chart_box.line.fill, "CCCCCC")

        # Add chart placeholder text
        chart_label = slide.shapes.add_textbox(
            Inches(7.5), Inches(3.8),
            Inches(4.8), Inches(0.5)
        )
        chart_label_frame = chart_label.text_frame
        chart_para = chart_label_frame.paragraphs[0]
        chart_para.text = f"[{spec.chart_type or 'Data Visualization'}]"
        chart_para.font.size = Pt(14)
        chart_para.font.italic = True
        chart_para.alignment = PP_ALIGN.CENTER
        self._set_font_color(chart_para, "666666")

        # Add footer
        footer_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(6.8),
            Inches(12), Inches(0.4)
        )
        footer_frame = footer_box.text_frame
        footer_para = footer_frame.paragraphs[0]
        footer_text = f"{state.fund_name} | {state.reporting_period}"
        if spec.footer_note:
            footer_text += f" | {spec.footer_note}"
        footer_para.text = footer_text
        footer_para.font.size = Pt(10)
        self._set_font_color(footer_para, "666666")

        # Add infra nuance callout
        if module.infra_nuance:
            nuance_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(6.2),
                Inches(12), Inches(0.4)
            )
            nuance_frame = nuance_box.text_frame
            nuance_para = nuance_frame.paragraphs[0]
            nuance_para.text = f"Infrastructure Focus: {module.infra_nuance}"
            nuance_para.font.size = Pt(11)
            nuance_para.font.italic = True
            self._set_font_color(nuance_para, "1F4E79")

        return slide

    def _set_rgb_color(self, fill_obj, hex_color: str):
        """Set RGB color using XML approach (avoids RgbColor import issues)."""
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        # Access the underlying XML element
        spPr = fill_obj._xPr if hasattr(fill_obj, '_xPr') else None
        if spPr is not None:
            srgbClr = spPr.find(qn('a:srgbClr'))
            if srgbClr is not None:
                srgbClr.set('val', hex_color.upper())
        else:
            # Fallback: use theme color (won't be exact but will work)
            try:
                from pptx.enum.dml import MSO_THEME_COLOR
                fill_obj.fore_color.theme_color = MSO_THEME_COLOR.DARK_1
            except Exception:
                pass

    def _set_font_color(self, para, hex_color: str):
        """Set font color for a paragraph."""
        try:
            from pptx.dml.color import RGBColor
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            para.font.color.rgb = RGBColor(r, g, b)
        except Exception:
            # If RGBColor fails, leave default
            pass

    def _create_default_spec(self, module) -> SlideSpec:
        """Create a default slide spec for unknown modules."""
        return SlideSpec(
            title=module.name,
            headline=module.description,
            takeaways=[
                f"Analysis complete for {module.name}",
                f"Category: {module.category}",
                f"Infra focus: {module.infra_nuance}",
            ],
            chart_type="data_table",
        )

    async def _create_placeholder(self, module) -> str:
        """Create a placeholder text file when pptx not available."""
        filename = f"{module.id}_slide_placeholder.txt"
        output_path = self.output_dir / filename

        spec = SLIDE_SPECS.get(module.id, self._create_default_spec(module))

        content = f"""
IR SLIDE PLACEHOLDER
====================
Module: {module.id}
Title: {spec.title}

HEADLINE:
{spec.headline}

KEY TAKEAWAYS:
{chr(10).join(f'• {t}' for t in spec.takeaways)}

Chart Type: {spec.chart_type}

Note: Install python-pptx to generate actual slides.
"""
        output_path.write_text(content)
        return str(output_path)


async def generate_ir_deck(
    state,  # IRState
    output_path: Path,
    include_modules: Optional[List[str]] = None,
) -> str:
    """
    Generate a complete IR deck from state.

    Args:
        state: IRState with completed analysis
        output_path: Path for output deck
        include_modules: Optional list of modules to include (all if None)

    Returns:
        Path to generated deck
    """
    if not PPTX_AVAILABLE:
        logger.error("python-pptx required for deck generation")
        return None

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    generator = IRSlideGenerator(output_path.parent)

    # Add title slide
    _add_title_slide(prs, state)

    # Add content slides for each module
    modules = state.modules.values()
    if include_modules:
        modules = [m for m in modules if m.id in include_modules]

    for module in modules:
        spec = SLIDE_SPECS.get(module.id, generator._create_default_spec(module))
        generator._add_content_slide(prs, spec, module, state)

    # Add closing slide
    _add_closing_slide(prs, state)

    # Save
    prs.save(str(output_path))
    logger.info(f"Generated IR deck: {output_path}")
    return str(output_path)


def _add_title_slide(prs: "Presentation", state):
    """Add title slide to presentation."""
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # Title
    title_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(2.5),
        Inches(12), Inches(1.5)
    )
    title_frame = title_box.text_frame
    title_para = title_frame.paragraphs[0]
    title_para.text = state.fund_name
    title_para.font.size = Pt(44)
    title_para.font.bold = True
    title_para.alignment = PP_ALIGN.CENTER

    # Subtitle
    subtitle_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(4.0),
        Inches(12), Inches(0.8)
    )
    subtitle_frame = subtitle_box.text_frame
    subtitle_para = subtitle_frame.paragraphs[0]
    subtitle_para.text = f"{state.case_type.value.replace('_', ' ').title()} | {state.reporting_period}"
    subtitle_para.font.size = Pt(24)
    subtitle_para.alignment = PP_ALIGN.CENTER

    # Date
    date_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(5.0),
        Inches(12), Inches(0.5)
    )
    date_frame = date_box.text_frame
    date_para = date_frame.paragraphs[0]
    date_para.text = datetime.now().strftime("%B %Y")
    date_para.font.size = Pt(16)
    date_para.alignment = PP_ALIGN.CENTER


def _add_closing_slide(prs: "Presentation", state):
    """Add closing slide to presentation."""
    blank_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(blank_layout)

    # Thank you text
    thanks_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(3.0),
        Inches(12), Inches(1.0)
    )
    thanks_frame = thanks_box.text_frame
    thanks_para = thanks_frame.paragraphs[0]
    thanks_para.text = "Thank You"
    thanks_para.font.size = Pt(44)
    thanks_para.font.bold = True
    thanks_para.alignment = PP_ALIGN.CENTER

    # Contact info placeholder
    contact_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(4.5),
        Inches(12), Inches(1.0)
    )
    contact_frame = contact_box.text_frame
    contact_para = contact_frame.paragraphs[0]
    contact_para.text = "[Contact Information]"
    contact_para.font.size = Pt(18)
    contact_para.alignment = PP_ALIGN.CENTER
