#!/usr/bin/env python3
"""
PE/IB Analysis Slides Template Generator

Creates a 30-slide PowerPoint template covering:
- Financial Analysis (LBO outputs, returns, sensitivities)
- Strategic Analysis (Porter's 5 Forces, SWOT, value chain)
- Industry Analysis (market sizing, competitive landscape)
- Company Analysis (business overview, management)
- Deal Analysis (investment thesis, risks, recommendation)

Formatting: Goldman Sachs / McKinsey presentation standards
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor
from datetime import datetime
import os

# Color scheme (Goldman Sachs / institutional)
NAVY = RGBColor(30, 58, 95)      # #1E3A5F - Headers
DARK_GRAY = RGBColor(51, 51, 51) # #333333 - Body text
LIGHT_GRAY = RGBColor(240, 240, 240)  # Background
ACCENT_BLUE = RGBColor(37, 99, 235)   # #2563EB - Highlights
ACCENT_GREEN = RGBColor(34, 197, 94)  # #22C55E - Positive
ACCENT_RED = RGBColor(239, 68, 68)    # #EF4444 - Negative
WHITE = RGBColor(255, 255, 255)


def add_title_slide(prs, title, subtitle=""):
    """Add a title slide."""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)

    # Navy background bar at top
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(2))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()

    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.6), Inches(12), Inches(1))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(36)
    p.font.bold = True
    p.font.color.rgb = WHITE

    # Subtitle
    if subtitle:
        txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(1.4), Inches(12), Inches(0.5))
        tf2 = txBox2.text_frame
        p2 = tf2.paragraphs[0]
        p2.text = subtitle
        p2.font.size = Pt(18)
        p2.font.color.rgb = RGBColor(200, 200, 200)

    return slide


def add_section_header(prs, section_title, section_number):
    """Add a section divider slide."""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)

    # Full navy background
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(7.5))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()

    # Section number
    txBox = slide.shapes.add_textbox(Inches(0.75), Inches(2.5), Inches(2), Inches(1))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = f"{section_number:02d}"
    p.font.size = Pt(72)
    p.font.bold = True
    p.font.color.rgb = ACCENT_BLUE

    # Section title
    txBox2 = slide.shapes.add_textbox(Inches(0.75), Inches(3.5), Inches(11), Inches(1.5))
    tf2 = txBox2.text_frame
    p2 = tf2.paragraphs[0]
    p2.text = section_title
    p2.font.size = Pt(44)
    p2.font.bold = True
    p2.font.color.rgb = WHITE

    return slide


def add_content_slide(prs, title, content_items=None, has_table=False, table_data=None):
    """Add a standard content slide with title and bullet points or table."""
    slide_layout = prs.slide_layouts[6]  # Blank
    slide = prs.slides.add_slide(slide_layout)

    # Header bar
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(1.1))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()

    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.color.rgb = WHITE

    # Content area
    if content_items:
        txBox2 = slide.shapes.add_textbox(Inches(0.5), Inches(1.4), Inches(12), Inches(5.5))
        tf2 = txBox2.text_frame
        tf2.word_wrap = True

        for i, item in enumerate(content_items):
            if i == 0:
                p = tf2.paragraphs[0]
            else:
                p = tf2.add_paragraph()

            if isinstance(item, tuple):
                # (text, level) format
                p.text = item[0]
                p.level = item[1]
            else:
                p.text = f"• {item}"
                p.level = 0

            p.font.size = Pt(14)
            p.font.color.rgb = DARK_GRAY
            p.space_after = Pt(8)

    return slide


def add_table_slide(prs, title, headers, rows, col_widths=None):
    """Add a slide with a data table."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)

    # Header bar
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(1.1))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()

    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.color.rgb = WHITE

    # Table
    num_cols = len(headers)
    num_rows = len(rows) + 1  # +1 for header

    if col_widths is None:
        col_widths = [Inches(12 / num_cols)] * num_cols

    table = slide.shapes.add_table(num_rows, num_cols, Inches(0.5), Inches(1.4), sum(col_widths), Inches(0.4 * num_rows)).table

    # Set column widths
    for i, width in enumerate(col_widths):
        table.columns[i].width = width

    # Header row
    for i, header in enumerate(headers):
        cell = table.cell(0, i)
        cell.text = header
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        p = cell.text_frame.paragraphs[0]
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER

    # Data rows
    for row_idx, row_data in enumerate(rows):
        for col_idx, cell_value in enumerate(row_data):
            cell = table.cell(row_idx + 1, col_idx)
            cell.text = str(cell_value)
            p = cell.text_frame.paragraphs[0]
            p.font.size = Pt(10)
            p.font.color.rgb = DARK_GRAY
            if col_idx == 0:
                p.alignment = PP_ALIGN.LEFT
            else:
                p.alignment = PP_ALIGN.CENTER

    return slide


def add_framework_slide(prs, title, framework_type, items):
    """Add a strategic framework slide (2x2, quadrant, etc.)."""
    slide_layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(slide_layout)

    # Header bar
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(1.1))
    shape.fill.solid()
    shape.fill.fore_color.rgb = NAVY
    shape.line.fill.background()

    # Title
    txBox = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(24)
    p.font.bold = True
    p.font.color.rgb = WHITE

    if framework_type == "2x2":
        # Create 2x2 grid
        positions = [
            (Inches(0.75), Inches(1.5), Inches(5.5), Inches(2.7)),   # Top-left
            (Inches(6.75), Inches(1.5), Inches(5.5), Inches(2.7)),   # Top-right
            (Inches(0.75), Inches(4.4), Inches(5.5), Inches(2.7)),   # Bottom-left
            (Inches(6.75), Inches(4.4), Inches(5.5), Inches(2.7)),   # Bottom-right
        ]
        colors = [ACCENT_BLUE, ACCENT_GREEN, RGBColor(245, 158, 11), ACCENT_RED]

        for i, (item_title, item_content) in enumerate(items[:4]):
            left, top, width, height = positions[i]

            # Box
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(248, 250, 252)
            box.line.color.rgb = colors[i]
            box.line.width = Pt(2)

            # Title
            txBox = slide.shapes.add_textbox(left + Inches(0.15), top + Inches(0.1), width - Inches(0.3), Inches(0.4))
            tf = txBox.text_frame
            p = tf.paragraphs[0]
            p.text = item_title
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.color.rgb = colors[i]

            # Content
            txBox2 = slide.shapes.add_textbox(left + Inches(0.15), top + Inches(0.5), width - Inches(0.3), height - Inches(0.6))
            tf2 = txBox2.text_frame
            tf2.word_wrap = True
            for j, bullet in enumerate(item_content):
                if j == 0:
                    p2 = tf2.paragraphs[0]
                else:
                    p2 = tf2.add_paragraph()
                p2.text = f"• {bullet}"
                p2.font.size = Pt(10)
                p2.font.color.rgb = DARK_GRAY

    elif framework_type == "five_forces":
        # Porter's Five Forces layout
        # Center box
        center = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.25), Inches(3.2), Inches(2.8), Inches(1.5))
        center.fill.solid()
        center.fill.fore_color.rgb = NAVY
        center.line.fill.background()

        txBox = slide.shapes.add_textbox(Inches(5.35), Inches(3.5), Inches(2.6), Inches(1))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = "Competitive\nRivalry"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p.alignment = PP_ALIGN.CENTER

        # Five forces positions
        force_positions = [
            (Inches(5.25), Inches(1.3), "Threat of\nNew Entrants", "↓"),   # Top
            (Inches(5.25), Inches(5.3), "Threat of\nSubstitutes", "↑"),    # Bottom
            (Inches(1.5), Inches(3.2), "Supplier\nPower", "→"),             # Left
            (Inches(9.0), Inches(3.2), "Buyer\nPower", "←"),                # Right
        ]

        for left, top, text, arrow in force_positions:
            box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, Inches(2.8), Inches(1.3))
            box.fill.solid()
            box.fill.fore_color.rgb = RGBColor(248, 250, 252)
            box.line.color.rgb = ACCENT_BLUE
            box.line.width = Pt(1.5)

            txBox = slide.shapes.add_textbox(left + Inches(0.1), top + Inches(0.2), Inches(2.6), Inches(1))
            tf = txBox.text_frame
            p = tf.paragraphs[0]
            p.text = text
            p.font.size = Pt(12)
            p.font.bold = True
            p.font.color.rgb = NAVY
            p.alignment = PP_ALIGN.CENTER

    return slide


def create_analysis_slides_template(output_path=None):
    """Create the full 30-slide analysis template."""
    prs = Presentation()
    prs.slide_width = Inches(13.33)
    prs.slide_height = Inches(7.5)

    # ========== SLIDE 1: TITLE ==========
    add_title_slide(prs, "[COMPANY NAME]", "Investment Analysis | Confidential")

    # ========== SLIDE 2: TABLE OF CONTENTS ==========
    add_content_slide(prs, "Table of Contents", [
        "1. Executive Summary",
        "2. Company Overview",
        "3. Industry Analysis",
        "4. Competitive Positioning",
        "5. Financial Analysis",
        "6. Valuation",
        "7. Transaction Analysis",
        "8. Investment Thesis & Risks",
        "9. Appendix",
    ])

    # ========== SECTION 1: EXECUTIVE SUMMARY ==========
    add_section_header(prs, "Executive Summary", 1)

    # Slide 4: Investment Highlights
    add_content_slide(prs, "Investment Highlights", [
        "[Highlight 1: Market leadership position in attractive end market]",
        "[Highlight 2: Strong recurring revenue base with high retention]",
        "[Highlight 3: Multiple levers for margin expansion]",
        "[Highlight 4: Experienced management team with aligned incentives]",
        "[Highlight 5: Clear path to value creation through operational improvements]",
    ])

    # Slide 5: Transaction Summary
    add_table_slide(prs, "Transaction Summary",
        ["Metric", "Value", "Commentary"],
        [
            ["Enterprise Value", "$XXX million", "X.Xx LTM EBITDA"],
            ["Equity Value", "$XXX million", "X.Xx LTM Net Income"],
            ["LTM Revenue", "$XXX million", "X% growth YoY"],
            ["LTM EBITDA", "$XXX million", "XX% margin"],
            ["Total Leverage", "X.Xx", "Senior + Sub debt"],
            ["Sponsor Equity", "$XXX million", "XX% of total cap"],
        ],
        [Inches(2.5), Inches(2), Inches(7.5)]
    )

    # ========== SECTION 2: COMPANY OVERVIEW ==========
    add_section_header(prs, "Company Overview", 2)

    # Slide 7: Business Description
    add_content_slide(prs, "Business Description", [
        "Company Background",
        ("Founded in [YEAR], headquartered in [LOCATION]", 1),
        ("[Brief description of core business and products/services]", 1),
        ("[Number of employees, locations, key geographies]", 1),
        "",
        "Key Business Segments",
        ("[Segment 1]: XX% of revenue - [Description]", 1),
        ("[Segment 2]: XX% of revenue - [Description]", 1),
        ("[Segment 3]: XX% of revenue - [Description]", 1),
    ])

    # Slide 8: Revenue Breakdown
    add_table_slide(prs, "Revenue Breakdown",
        ["Segment", "Revenue ($M)", "% of Total", "Growth Rate", "Margin"],
        [
            ["Segment A", "$XX", "XX%", "+X%", "XX%"],
            ["Segment B", "$XX", "XX%", "+X%", "XX%"],
            ["Segment C", "$XX", "XX%", "+X%", "XX%"],
            ["Total", "$XXX", "100%", "+X%", "XX%"],
        ],
        [Inches(3), Inches(2), Inches(2), Inches(2), Inches(2)]
    )

    # Slide 9: Customer Overview
    add_content_slide(prs, "Customer Analysis", [
        "Customer Base Profile",
        ("Total customers: [X,XXX]", 1),
        ("Average contract value: $[XX,XXX]", 1),
        ("Customer retention rate: [XX%]", 1),
        "",
        "Top Customer Concentration",
        ("Top 10 customers: XX% of revenue", 1),
        ("Largest customer: XX% of revenue", 1),
        ("Average relationship tenure: [X] years", 1),
        "",
        "Customer Segments",
        ("[Enterprise / Mid-Market / SMB breakdown]", 1),
    ])

    # ========== SECTION 3: INDUSTRY ANALYSIS ==========
    add_section_header(prs, "Industry Analysis", 3)

    # Slide 11: Market Overview
    add_content_slide(prs, "Market Overview", [
        "Total Addressable Market (TAM)",
        ("Global market size: $XX billion (2024)", 1),
        ("Expected CAGR: X% (2024-2029)", 1),
        ("North America: $XX billion (XX% of global)", 1),
        "",
        "Key Market Drivers",
        ("[Driver 1: e.g., Digital transformation]", 1),
        ("[Driver 2: e.g., Regulatory changes]", 1),
        ("[Driver 3: e.g., Demographic shifts]", 1),
        "",
        "Market Headwinds",
        ("[Risk 1]", 1),
        ("[Risk 2]", 1),
    ])

    # Slide 12: Porter's Five Forces
    add_framework_slide(prs, "Porter's Five Forces Analysis", "five_forces", [])

    # Slide 13: Industry Value Chain
    add_content_slide(prs, "Industry Value Chain", [
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
        ("[After-market services]", 1),
        "",
        "Company's Position: [Description of where company sits in value chain]",
    ])

    # ========== SECTION 4: COMPETITIVE ANALYSIS ==========
    add_section_header(prs, "Competitive Positioning", 4)

    # Slide 15: Competitive Landscape
    add_table_slide(prs, "Competitive Landscape",
        ["Competitor", "Revenue", "Market Share", "Key Strengths", "Key Weaknesses"],
        [
            ["Company (Target)", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor A", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor B", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Competitor C", "$XXX", "XX%", "[Strength]", "[Weakness]"],
            ["Other", "$XXX", "XX%", "—", "—"],
        ],
        [Inches(2.2), Inches(1.5), Inches(1.8), Inches(3), Inches(3)]
    )

    # Slide 16: SWOT Analysis
    add_framework_slide(prs, "SWOT Analysis", "2x2", [
        ("STRENGTHS", [
            "[Market leadership]",
            "[Proprietary technology]",
            "[Strong customer relationships]",
            "[Experienced team]",
        ]),
        ("WEAKNESSES", [
            "[Customer concentration]",
            "[Geographic limitations]",
            "[Technology gaps]",
            "[Working capital intensity]",
        ]),
        ("OPPORTUNITIES", [
            "[New market expansion]",
            "[Product line extension]",
            "[M&A / tuck-ins]",
            "[Pricing optimization]",
        ]),
        ("THREATS", [
            "[New entrants]",
            "[Technology disruption]",
            "[Customer consolidation]",
            "[Regulatory changes]",
        ]),
    ])

    # Slide 17: Competitive Moat
    add_content_slide(prs, "Competitive Moat Assessment", [
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
    ])

    # ========== SECTION 5: FINANCIAL ANALYSIS ==========
    add_section_header(prs, "Financial Analysis", 5)

    # Slide 19: Historical Financial Summary
    add_table_slide(prs, "Historical Financial Summary",
        ["($M)", "FY2022", "FY2023", "FY2024", "CAGR"],
        [
            ["Revenue", "$XXX", "$XXX", "$XXX", "X%"],
            ["% Growth", "X%", "X%", "X%", "—"],
            ["Gross Profit", "$XX", "$XX", "$XX", "X%"],
            ["% Margin", "XX%", "XX%", "XX%", "—"],
            ["EBITDA", "$XX", "$XX", "$XX", "X%"],
            ["% Margin", "XX%", "XX%", "XX%", "—"],
            ["CapEx", "($X)", "($X)", "($X)", "—"],
            ["% of Revenue", "X%", "X%", "X%", "—"],
            ["Free Cash Flow", "$XX", "$XX", "$XX", "X%"],
        ],
        [Inches(3), Inches(2), Inches(2), Inches(2), Inches(2)]
    )

    # Slide 20: Projected Financials
    add_table_slide(prs, "Projected Financial Summary",
        ["($M)", "FY2025E", "FY2026E", "FY2027E", "FY2028E", "FY2029E"],
        [
            ["Revenue", "$XXX", "$XXX", "$XXX", "$XXX", "$XXX"],
            ["% Growth", "X%", "X%", "X%", "X%", "X%"],
            ["EBITDA", "$XX", "$XX", "$XX", "$XX", "$XX"],
            ["% Margin", "XX%", "XX%", "XX%", "XX%", "XX%"],
            ["CapEx", "($X)", "($X)", "($X)", "($X)", "($X)"],
            ["Unlevered FCF", "$XX", "$XX", "$XX", "$XX", "$XX"],
        ],
        [Inches(2.5), Inches(1.8), Inches(1.8), Inches(1.8), Inches(1.8), Inches(1.8)]
    )

    # Slide 21: Key Financial Metrics
    add_table_slide(prs, "Key Operating Metrics",
        ["Metric", "Company", "Peer Median", "Variance", "Commentary"],
        [
            ["Revenue Growth (3Y CAGR)", "X%", "X%", "+/- X%", "[Above/Below peers]"],
            ["Gross Margin", "XX%", "XX%", "+/- X%", "[Position vs peers]"],
            ["EBITDA Margin", "XX%", "XX%", "+/- X%", "[Position vs peers]"],
            ["FCF Conversion", "XX%", "XX%", "+/- X%", "[Quality of earnings]"],
            ["Revenue per Employee", "$XXX", "$XXX", "+/- $XX", "[Efficiency]"],
            ["Days Sales Outstanding", "XX", "XX", "+/- X", "[Working capital]"],
        ],
        [Inches(2.8), Inches(1.8), Inches(1.8), Inches(1.5), Inches(3.5)]
    )

    # ========== SECTION 6: VALUATION ==========
    add_section_header(prs, "Valuation", 6)

    # Slide 23: Trading Comps
    add_table_slide(prs, "Public Comparable Companies",
        ["Company", "EV ($M)", "EV/Revenue", "EV/EBITDA", "Revenue Gr.", "EBITDA Margin"],
        [
            ["Comp A", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
            ["Comp B", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
            ["Comp C", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
            ["Comp D", "$X,XXX", "X.Xx", "XX.Xx", "X%", "XX%"],
            ["Mean", "—", "X.Xx", "XX.Xx", "X%", "XX%"],
            ["Median", "—", "X.Xx", "XX.Xx", "X%", "XX%"],
        ],
        [Inches(2.2), Inches(1.8), Inches(1.8), Inches(2), Inches(1.8), Inches(2)]
    )

    # Slide 24: Transaction Comps
    add_table_slide(prs, "Precedent Transactions",
        ["Date", "Target", "Acquirer", "EV ($M)", "EV/Revenue", "EV/EBITDA"],
        [
            ["MM/YY", "Target A", "Buyer A", "$XXX", "X.Xx", "XX.Xx"],
            ["MM/YY", "Target B", "Buyer B", "$XXX", "X.Xx", "XX.Xx"],
            ["MM/YY", "Target C", "Buyer C", "$XXX", "X.Xx", "XX.Xx"],
            ["MM/YY", "Target D", "Buyer D", "$XXX", "X.Xx", "XX.Xx"],
            ["Mean", "—", "—", "—", "X.Xx", "XX.Xx"],
            ["Median", "—", "—", "—", "X.Xx", "XX.Xx"],
        ],
        [Inches(1.3), Inches(2.2), Inches(2.2), Inches(1.8), Inches(1.8), Inches(2)]
    )

    # Slide 25: Football Field
    add_content_slide(prs, "Valuation Summary (Football Field)", [
        "",
        "[Insert Football Field chart here]",
        "",
        "Methodology Summary:",
        ("Trading Comps: $XXX - $XXX million", 1),
        ("Transaction Comps: $XXX - $XXX million", 1),
        ("DCF Analysis: $XXX - $XXX million", 1),
        ("LBO Analysis: $XXX - $XXX million (at XX% IRR)", 1),
        "",
        "Selected Valuation Range: $XXX - $XXX million",
        "Implied Entry Multiple: X.Xx - X.Xx LTM EBITDA",
    ])

    # ========== SECTION 7: TRANSACTION ANALYSIS ==========
    add_section_header(prs, "Transaction Analysis", 7)

    # Slide 27: Sources & Uses
    add_table_slide(prs, "Sources and Uses of Funds",
        ["Sources", "$M", "% Total", "", "Uses", "$M", "% Total"],
        [
            ["Senior Debt", "$XX", "XX%", "", "Purchase Price", "$XXX", "XX%"],
            ["Subordinated Debt", "$XX", "XX%", "", "Refinance Debt", "$XX", "XX%"],
            ["Rollover Equity", "$XX", "XX%", "", "Transaction Fees", "$XX", "XX%"],
            ["Sponsor Equity", "$XX", "XX%", "", "Financing Fees", "$XX", "XX%"],
            ["", "", "", "", "Cash to B/S", "$XX", "XX%"],
            ["Total Sources", "$XXX", "100%", "", "Total Uses", "$XXX", "100%"],
        ],
        [Inches(2), Inches(1.3), Inches(1.2), Inches(0.3), Inches(2), Inches(1.3), Inches(1.2)]
    )

    # Slide 28: Returns Analysis
    add_table_slide(prs, "LBO Returns Analysis",
        ["Exit Year", "Exit EBITDA", "Exit Multiple", "Exit EV", "Net Debt", "Equity Value", "MOIC", "IRR"],
        [
            ["Year 3", "$XX", "X.Xx", "$XXX", "$XX", "$XXX", "X.Xx", "XX%"],
            ["Year 4", "$XX", "X.Xx", "$XXX", "$XX", "$XXX", "X.Xx", "XX%"],
            ["Year 5", "$XX", "X.Xx", "$XXX", "$XX", "$XXX", "X.Xx", "XX%"],
            ["Year 6", "$XX", "X.Xx", "$XXX", "$XX", "$XXX", "X.Xx", "XX%"],
            ["Year 7", "$XX", "X.Xx", "$XXX", "$XX", "$XXX", "X.Xx", "XX%"],
        ],
        [Inches(1.2), Inches(1.5), Inches(1.5), Inches(1.3), Inches(1.3), Inches(1.5), Inches(1.2), Inches(1.2)]
    )

    # ========== SECTION 8: INVESTMENT THESIS ==========
    add_section_header(prs, "Investment Thesis & Risks", 8)

    # Slide 30: Investment Thesis
    add_content_slide(prs, "Investment Thesis", [
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
    ])

    # Slide 31: Risk Assessment
    add_framework_slide(prs, "Risk Assessment Matrix", "2x2", [
        ("HIGH IMPACT / HIGH PROBABILITY", [
            "[Key risk 1]",
            "[Key risk 2]",
            "Mitigant: [Action]",
        ]),
        ("HIGH IMPACT / LOW PROBABILITY", [
            "[Tail risk 1]",
            "[Tail risk 2]",
            "Mitigant: [Action]",
        ]),
        ("LOW IMPACT / HIGH PROBABILITY", [
            "[Operational risk 1]",
            "[Operational risk 2]",
            "Mitigant: [Action]",
        ]),
        ("LOW IMPACT / LOW PROBABILITY", [
            "[Minor risk 1]",
            "[Minor risk 2]",
            "Monitor",
        ]),
    ])

    # Slide 32: Value Creation Bridge
    add_content_slide(prs, "Value Creation Bridge", [
        "",
        "[Insert waterfall chart here]",
        "",
        "Value Creation Sources:",
        ("Entry Equity: $XX million", 1),
        ("(+) EBITDA Growth: $XX million (XX% of gain)", 1),
        ("(+) Multiple Expansion: $XX million (XX% of gain)", 1),
        ("(+) Debt Paydown: $XX million (XX% of gain)", 1),
        ("(=) Exit Equity: $XXX million", 1),
        "",
        "Total Value Created: $XX million | MOIC: X.Xx | IRR: XX%",
    ])

    # Slide 33: Recommendation
    add_content_slide(prs, "Investment Recommendation", [
        "RECOMMENDATION: [INVEST / PASS / FURTHER DILIGENCE]",
        "",
        "Key Reasons:",
        ("[Reason 1: Summarize the most compelling factor]", 1),
        ("[Reason 2: Second most important factor]", 1),
        ("[Reason 3: Third factor]", 1),
        "",
        "Key Conditions / Next Steps:",
        ("[Condition 1: e.g., Complete management meetings]", 1),
        ("[Condition 2: e.g., Validate key customer relationships]", 1),
        ("[Condition 3: e.g., Confirm technology DD]", 1),
        "",
        "Proposed Terms:",
        ("Entry Multiple: X.Xx LTM EBITDA | Equity Check: $XX million", 1),
    ])

    # Save
    if output_path is None:
        output_path = os.path.dirname(os.path.abspath(__file__))

    filename = f"PE_IB_Analysis_Slides_Template_{datetime.now().strftime('%Y%m%d')}.pptx"
    filepath = os.path.join(output_path, filename)
    prs.save(filepath)

    print(f"Analysis Slides Template created: {filepath}")
    print(f"Total slides: {len(prs.slides)}")
    return filepath


if __name__ == "__main__":
    print("=" * 60)
    print("PE/IB Analysis Slides Template Generator")
    print("=" * 60)

    filepath = create_analysis_slides_template()

    print("\nSlide Categories:")
    print("  - Executive Summary (3 slides)")
    print("  - Company Overview (3 slides)")
    print("  - Industry Analysis (3 slides)")
    print("  - Competitive Positioning (3 slides)")
    print("  - Financial Analysis (3 slides)")
    print("  - Valuation (3 slides)")
    print("  - Transaction Analysis (2 slides)")
    print("  - Investment Thesis & Risks (4 slides)")
    print("  - Section headers (8 slides)")
    print("\nTotal: 30+ slides")
