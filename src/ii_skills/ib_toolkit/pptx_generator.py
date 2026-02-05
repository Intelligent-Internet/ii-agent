#!/usr/bin/env python3
"""
Investment Banking PowerPoint Generator
Creates professional presentations for industry research, company profiles, and pitch books.

Design patterns extracted from institutional presentations:
- TD Securities (Florence, Northview, Spring Living)
- PropelR Investor Presentation

See: docs/skills/SLIDE_DESIGN_GUIDE.md for complete template reference.
"""

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.xmlchemy import OxmlElement
from pptx.oxml.ns import qn
from pptx.dml.color import RGBColor as RgbColor
import os
from datetime import datetime
from typing import List, Dict, Optional, Any

from config import (
    OUTPUT_DIR, COLORS, DEFAULT_FONT,
    TITLE_FONT_SIZE, SUBTITLE_FONT_SIZE, BODY_FONT_SIZE
)

# Professional color palette (TD Securities style)
COLORS_PROFESSIONAL = {
    "primary": "00A651",      # TD Green
    "secondary": "006341",    # Dark Green
    "header_gray": "4A4A4A",  # Dark gray for headers
    "light_gray": "F0F0F0",   # Light gray backgrounds
    "text": "333333",         # Body text
    "negative": "C00000",     # Red for negative values
    "highlight": "FF0000",    # Red for highlight boxes
    "white": "FFFFFF",
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, OUTPUT_DIR)


def hex_to_rgb(hex_color: str) -> RgbColor:
    """Convert hex color to RgbColor."""
    hex_color = hex_color.lstrip('#')
    return RgbColor(
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16)
    )


def set_cell_fill(cell, hex_color: str):
    """Set cell background color."""
    cell_elem = cell._tc
    tcPr = cell_elem.get_or_add_tcPr()
    solidFill = OxmlElement('a:solidFill')
    srgbClr = OxmlElement('a:srgbClr')
    srgbClr.set('val', hex_color)
    solidFill.append(srgbClr)
    tcPr.append(solidFill)


class IBPresentation:
    """Investment Banking Presentation Generator."""

    def __init__(self, title: str = "Investment Analysis"):
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)  # Widescreen 16:9
        self.prs.slide_height = Inches(7.5)
        self.title = title

    def _add_slide(self, layout_index: int = 6):
        """Add a blank slide."""
        layout = self.prs.slide_layouts[layout_index]  # Blank layout
        return self.prs.slides.add_slide(layout)

    def _add_title_shape(self, slide, text: str, top: float = 0.3,
                         font_size: int = TITLE_FONT_SIZE, bold: bool = True):
        """Add a title text box."""
        shape = slide.shapes.add_textbox(
            Inches(0.5), Inches(top), Inches(12.33), Inches(0.7)
        )
        frame = shape.text_frame
        frame.word_wrap = True
        p = frame.paragraphs[0]
        p.text = text
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.color.rgb = hex_to_rgb(COLORS["primary"])
        return shape

    def _add_subtitle_shape(self, slide, text: str, top: float = 0.9):
        """Add a subtitle text box."""
        shape = slide.shapes.add_textbox(
            Inches(0.5), Inches(top), Inches(12.33), Inches(0.5)
        )
        frame = shape.text_frame
        p = frame.paragraphs[0]
        p.text = text
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(SUBTITLE_FONT_SIZE)
        p.font.color.rgb = hex_to_rgb(COLORS["text"])
        return shape

    def _add_body_text(self, slide, text: str, left: float, top: float,
                       width: float, height: float):
        """Add body text box."""
        shape = slide.shapes.add_textbox(
            Inches(left), Inches(top), Inches(width), Inches(height)
        )
        frame = shape.text_frame
        frame.word_wrap = True
        p = frame.paragraphs[0]
        p.text = text
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(BODY_FONT_SIZE)
        p.font.color.rgb = hex_to_rgb(COLORS["text"])
        return shape

    def _add_bullet_points(self, slide, points: list, left: float, top: float,
                           width: float, height: float):
        """Add bullet points."""
        shape = slide.shapes.add_textbox(
            Inches(left), Inches(top), Inches(width), Inches(height)
        )
        frame = shape.text_frame
        frame.word_wrap = True

        for i, point in enumerate(points):
            if i == 0:
                p = frame.paragraphs[0]
            else:
                p = frame.add_paragraph()
            p.text = f"• {point}"
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(BODY_FONT_SIZE)
            p.font.color.rgb = hex_to_rgb(COLORS["text"])
            p.space_after = Pt(6)

        return shape

    def _add_table(self, slide, data: list, left: float, top: float,
                   width: float, row_height: float = 0.4):
        """Add a table with data. First row is header."""
        rows = len(data)
        cols = len(data[0]) if data else 0

        if rows == 0 or cols == 0:
            return None

        table = slide.shapes.add_table(
            rows, cols, Inches(left), Inches(top),
            Inches(width), Inches(row_height * rows)
        ).table

        # Set column widths evenly
        col_width = Inches(width / cols)
        for col in table.columns:
            col.width = col_width

        # Populate table
        for row_idx, row_data in enumerate(data):
            for col_idx, cell_value in enumerate(row_data):
                cell = table.cell(row_idx, col_idx)
                cell.text = str(cell_value)

                # Format cell
                for paragraph in cell.text_frame.paragraphs:
                    paragraph.font.name = DEFAULT_FONT
                    paragraph.font.size = Pt(10)
                    paragraph.alignment = PP_ALIGN.CENTER

                    if row_idx == 0:  # Header row
                        paragraph.font.bold = True
                        paragraph.font.color.rgb = RgbColor(255, 255, 255)
                        set_cell_fill(cell, COLORS["primary"])
                    else:
                        paragraph.font.color.rgb = hex_to_rgb(COLORS["text"])

                cell.vertical_anchor = MSO_ANCHOR.MIDDLE

        return table

    def _add_footer(self, slide, text: str = "CONFIDENTIAL"):
        """Add footer to slide."""
        shape = slide.shapes.add_textbox(
            Inches(0.5), Inches(7.0), Inches(12.33), Inches(0.3)
        )
        frame = shape.text_frame
        p = frame.paragraphs[0]
        p.text = f"{text} | {datetime.now().strftime('%B %Y')}"
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(8)
        p.font.color.rgb = hex_to_rgb("9ca3af")
        p.alignment = PP_ALIGN.RIGHT

    def _add_key_takeaway_bar(self, slide, text: str):
        """Add green key takeaway bar at bottom of slide (TD Securities style)."""
        # Green background bar
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(6.5),
            Inches(13.333), Inches(0.6)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["primary"])
        bar.line.fill.background()

        # Takeaway text (italic, white)
        text_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(6.55), Inches(12.33), Inches(0.5)
        )
        frame = text_box.text_frame
        p = frame.paragraphs[0]
        p.text = text
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(12)
        p.font.italic = True
        p.font.color.rgb = RgbColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER
        return bar

    def _add_header_bar(self, slide, text: str, subtitle: str = None, top: float = 0.9):
        """Add gray header bar with white text (TD Securities style)."""
        # Gray header bar
        bar = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(top),
            Inches(12.33), Inches(0.4)
        )
        bar.fill.solid()
        bar.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["header_gray"])
        bar.line.fill.background()

        # Header text
        text_content = text
        if subtitle:
            text_content = f"{text} | {subtitle}"
        text_box = slide.shapes.add_textbox(
            Inches(0.6), Inches(top + 0.05), Inches(12), Inches(0.35)
        )
        frame = text_box.text_frame
        p = frame.paragraphs[0]
        p.text = text_content
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)
        return bar

    def _add_source_citation(self, slide, source_text: str, footnotes: List[str] = None):
        """Add source citation and footnotes (TD Securities style)."""
        y_pos = 7.1

        # Source line
        source_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(y_pos), Inches(6), Inches(0.2)
        )
        frame = source_box.text_frame
        p = frame.paragraphs[0]
        p.text = f"Source: {source_text}"
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(8)
        p.font.color.rgb = hex_to_rgb("666666")

        # Footnotes
        if footnotes:
            for i, note in enumerate(footnotes, 1):
                y_pos += 0.15
                note_box = slide.shapes.add_textbox(
                    Inches(0.5), Inches(y_pos), Inches(12), Inches(0.15)
                )
                frame = note_box.text_frame
                p = frame.paragraphs[0]
                p.text = f"{i}. {note}"
                p.font.name = DEFAULT_FONT
                p.font.size = Pt(7)
                p.font.color.rgb = hex_to_rgb("666666")

    def add_peer_benchmarking_slide(
        self,
        title: str,
        metric_name: str,
        peers: List[Dict[str, Any]],  # [{"name": str, "value": float, "is_subject": bool}]
        takeaway: str = None,
        source: str = "Company filings"
    ):
        """
        Add peer benchmarking bar chart slide (TD Securities style).

        Peers highlighted in gray, subject company in green.
        Values shown above bars, company names below.
        """
        slide = self._add_slide()
        self._add_title_shape(slide, title)
        self._add_header_bar(slide, metric_name, datetime.now().strftime("%B %Y"))

        # Sort peers by value descending
        sorted_peers = sorted(peers, key=lambda x: x.get("value", 0), reverse=True)

        # Calculate bar positions
        num_peers = len(sorted_peers)
        bar_width = min(1.2, 11.0 / num_peers)
        total_width = bar_width * num_peers
        start_x = (13.333 - total_width) / 2

        max_value = max(p.get("value", 0) for p in sorted_peers) or 1
        max_bar_height = 3.5

        for i, peer in enumerate(sorted_peers):
            x = start_x + (i * bar_width)
            value = peer.get("value", 0)
            bar_height = (value / max_value) * max_bar_height
            y = 5.0 - bar_height  # Bottom aligned at y=5.0

            # Bar
            bar = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(x + 0.1), Inches(y),
                Inches(bar_width - 0.2), Inches(bar_height)
            )
            bar.fill.solid()
            if peer.get("is_subject", False):
                bar.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["primary"])
            else:
                bar.fill.fore_color.rgb = hex_to_rgb("808080")  # Gray
            bar.line.fill.background()

            # Value label above bar
            val_box = slide.shapes.add_textbox(
                Inches(x), Inches(y - 0.35), Inches(bar_width), Inches(0.3)
            )
            frame = val_box.text_frame
            p = frame.paragraphs[0]
            # Format value (handle multiples vs percentages)
            if isinstance(value, float) and value < 100:
                p.text = f"{value:.1f}x" if "x" not in str(value) else str(value)
            else:
                p.text = f"{value:.1f}%"
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(10)
            p.font.bold = True
            p.alignment = PP_ALIGN.CENTER

            # Company name below bar
            name_box = slide.shapes.add_textbox(
                Inches(x), Inches(5.1), Inches(bar_width), Inches(0.6)
            )
            frame = name_box.text_frame
            frame.word_wrap = True
            p = frame.paragraphs[0]
            p.text = peer.get("name", f"Peer {i+1}")
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(8)
            p.alignment = PP_ALIGN.CENTER

        if takeaway:
            self._add_key_takeaway_bar(slide, takeaway)

        self._add_source_citation(slide, source)
        return slide

    def add_comps_table_slide(
        self,
        title: str,
        headers: List[str],
        data: List[List[Any]],  # Each row: [company, ...metrics], subject row marked
        subject_row_index: int = None,
        takeaway: str = None,
        source: str = "Company filings"
    ):
        """
        Add comprehensive comps table slide with subject row highlighted.

        Subject company row gets green background highlighting.
        Supports peer average row at bottom.
        """
        slide = self._add_slide()
        self._add_title_shape(slide, title)

        # Header bar
        self._add_header_bar(slide, "Peer Comparison")

        # Build table
        rows = len(data) + 1  # +1 for header
        cols = len(headers)
        table = slide.shapes.add_table(
            rows, cols, Inches(0.5), Inches(1.4),
            Inches(12.33), Inches(rows * 0.4)
        ).table

        # Set column widths
        col_widths = [Inches(2.0)] + [Inches((10.33) / (cols - 1))] * (cols - 1)
        for i, width in enumerate(col_widths[:cols]):
            table.columns[i].width = width

        # Header row
        for col_idx, header in enumerate(headers):
            cell = table.cell(0, col_idx)
            cell.text = str(header)
            for p in cell.text_frame.paragraphs:
                p.font.name = DEFAULT_FONT
                p.font.size = Pt(9)
                p.font.bold = True
                p.font.color.rgb = RgbColor(255, 255, 255)
                p.alignment = PP_ALIGN.CENTER
            set_cell_fill(cell, COLORS_PROFESSIONAL["header_gray"])
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

        # Data rows
        for row_idx, row_data in enumerate(data):
            is_subject = (subject_row_index is not None and row_idx == subject_row_index)
            for col_idx, value in enumerate(row_data):
                cell = table.cell(row_idx + 1, col_idx)
                cell.text = str(value)
                for p in cell.text_frame.paragraphs:
                    p.font.name = DEFAULT_FONT
                    p.font.size = Pt(9)
                    p.alignment = PP_ALIGN.CENTER if col_idx > 0 else PP_ALIGN.LEFT
                    if is_subject:
                        p.font.bold = True

                if is_subject:
                    set_cell_fill(cell, COLORS_PROFESSIONAL["primary"])
                    for p in cell.text_frame.paragraphs:
                        p.font.color.rgb = RgbColor(255, 255, 255)

                cell.vertical_anchor = MSO_ANCHOR.MIDDLE

        if takeaway:
            self._add_key_takeaway_bar(slide, takeaway)

        self._add_source_citation(slide, source)
        return slide

    def add_sources_uses_slide(
        self,
        title: str,
        sources: List[Dict[str, Any]],  # [{"item": str, "low": val, "mid": val, "high": val}]
        uses: List[Dict[str, Any]],
        valuation_summary: Dict[str, Any] = None,
        takeaway: str = None
    ):
        """
        Add Sources & Uses / Transaction Summary slide (TD Securities style).

        Multiple scenario columns (Low/Mid/High), valuation summary on left.
        """
        slide = self._add_slide()
        self._add_title_shape(slide, title)

        # Valuation summary table (left side)
        if valuation_summary:
            self._add_header_bar(slide, "Valuation Summary", top=0.9)
            val_data = [["Metric", "Low", "Mid", "High"]]
            for metric, values in valuation_summary.items():
                if isinstance(values, dict):
                    val_data.append([metric, values.get("low", ""), values.get("mid", ""), values.get("high", "")])
                else:
                    val_data.append([metric, values, "", ""])
            self._add_table(slide, val_data, 0.5, 1.4, 5.8, row_height=0.35)

        # Sources & Uses (right side)
        su_left = 6.8 if valuation_summary else 0.5
        su_width = 6.0 if valuation_summary else 12.33

        # Sources header
        sources_y = 0.9 if not valuation_summary else 1.4
        sources_header = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(su_left), Inches(sources_y),
            Inches(su_width), Inches(0.35)
        )
        sources_header.fill.solid()
        sources_header.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["primary"])
        sources_header.line.fill.background()

        # Sources header text
        sh_text = slide.shapes.add_textbox(
            Inches(su_left + 0.1), Inches(sources_y + 0.05),
            Inches(su_width - 0.2), Inches(0.3)
        )
        p = sh_text.text_frame.paragraphs[0]
        p.text = "Sources & Uses"
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)

        # Sources table
        sources_data = [["Sources", "Low", "Mid", "High"]]
        for s in sources:
            sources_data.append([s["item"], s.get("low", ""), s.get("mid", ""), s.get("high", "")])
        sources_data.append(["Total Sources",
                            sum(s.get("low", 0) for s in sources if isinstance(s.get("low"), (int, float))),
                            sum(s.get("mid", 0) for s in sources if isinstance(s.get("mid"), (int, float))),
                            sum(s.get("high", 0) for s in sources if isinstance(s.get("high"), (int, float)))])

        self._add_table(slide, sources_data, su_left, sources_y + 0.4, su_width, row_height=0.3)

        # Uses table
        uses_y = sources_y + 0.4 + (len(sources_data) * 0.3) + 0.2
        uses_data = [["Uses", "Low", "Mid", "High"]]
        for u in uses:
            uses_data.append([u["item"], u.get("low", ""), u.get("mid", ""), u.get("high", "")])
        uses_data.append(["Total Uses",
                         sum(u.get("low", 0) for u in uses if isinstance(u.get("low"), (int, float))),
                         sum(u.get("mid", 0) for u in uses if isinstance(u.get("mid"), (int, float))),
                         sum(u.get("high", 0) for u in uses if isinstance(u.get("high"), (int, float)))])

        self._add_table(slide, uses_data, su_left, uses_y, su_width, row_height=0.3)

        if takeaway:
            self._add_key_takeaway_bar(slide, takeaway)

        self._add_source_citation(slide, "Management, Company filings")
        return slide

    def add_numbered_highlights_slide(
        self,
        number: int,
        title: str,
        narrative_points: List[str],
        charts_data: List[Dict] = None,  # [{type: "bar", data: [...]}]
        takeaway: str = None
    ):
        """
        Add numbered key point slide (TD Securities style).

        Number in box before title, narrative on left, charts on bottom.
        """
        slide = self._add_slide()

        # Number box
        num_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.3), Inches(0.3),
            Inches(0.5), Inches(0.5)
        )
        num_box.fill.solid()
        num_box.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["primary"])
        num_box.line.fill.background()

        # Number text
        num_text = slide.shapes.add_textbox(Inches(0.3), Inches(0.35), Inches(0.5), Inches(0.4))
        p = num_text.text_frame.paragraphs[0]
        p.text = str(number)
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(20)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)
        p.alignment = PP_ALIGN.CENTER

        # Title (after number)
        self._add_title_shape(slide, title, top=0.35)
        # Adjust title position to account for number box
        for shape in slide.shapes:
            if hasattr(shape, 'text_frame'):
                if shape.text_frame.paragraphs[0].text == title:
                    shape.left = Inches(0.9)
                    break

        # Narrative points
        self._add_bullet_points(slide, narrative_points, 0.5, 1.0, 12.33, 3.0)

        # Charts area (if provided)
        if charts_data:
            chart_width = 12.33 / len(charts_data)
            for i, chart in enumerate(charts_data):
                x = 0.5 + (i * chart_width)
                # Placeholder for chart - actual chart generation would go here
                chart_box = slide.shapes.add_shape(
                    MSO_SHAPE.RECTANGLE, Inches(x), Inches(4.2),
                    Inches(chart_width - 0.3), Inches(2.0)
                )
                chart_box.fill.solid()
                chart_box.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["light_gray"])
                chart_box.line.color.rgb = hex_to_rgb("CCCCCC")

                # Chart title
                ct_box = slide.shapes.add_textbox(Inches(x), Inches(4.0), Inches(chart_width - 0.3), Inches(0.3))
                p = ct_box.text_frame.paragraphs[0]
                p.text = chart.get("title", f"Chart {i+1}")
                p.font.name = DEFAULT_FONT
                p.font.size = Pt(10)
                p.font.bold = True

        if takeaway:
            self._add_key_takeaway_bar(slide, takeaway)

        self._add_footer(slide)
        return slide

    def add_before_after_slide(
        self,
        title: str,
        kpi_grid: List[Dict],  # [{"label": str, "value": str}]
        case_study_name: str,
        before_after_metrics: List[Dict],  # [{"metric": str, "before": val, "after": val, "change": str}]
        takeaway: str = None
    ):
        """
        Add Before/After comparison slide (TD Securities style).

        KPI grid on top-right, case study with data table at bottom.
        """
        slide = self._add_slide()
        self._add_title_shape(slide, title)

        # KPI Grid (2x2 colored boxes)
        kpi_start_x = 7.5
        kpi_start_y = 1.0
        kpi_width = 2.5
        kpi_height = 1.0

        colors = [COLORS_PROFESSIONAL["primary"], COLORS_PROFESSIONAL["secondary"],
                  COLORS_PROFESSIONAL["header_gray"], COLORS_PROFESSIONAL["primary"]]

        for i, kpi in enumerate(kpi_grid[:4]):
            row = i // 2
            col = i % 2
            x = kpi_start_x + (col * kpi_width)
            y = kpi_start_y + (row * kpi_height)

            box = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(x), Inches(y),
                Inches(kpi_width - 0.1), Inches(kpi_height - 0.1)
            )
            box.fill.solid()
            box.fill.fore_color.rgb = hex_to_rgb(colors[i % len(colors)])
            box.line.fill.background()

            # Label
            label_box = slide.shapes.add_textbox(Inches(x + 0.1), Inches(y + 0.1), Inches(kpi_width - 0.3), Inches(0.3))
            p = label_box.text_frame.paragraphs[0]
            p.text = kpi.get("label", "")
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(10)
            p.font.color.rgb = RgbColor(255, 255, 255)
            p.alignment = PP_ALIGN.CENTER

            # Value
            val_box = slide.shapes.add_textbox(Inches(x + 0.1), Inches(y + 0.4), Inches(kpi_width - 0.3), Inches(0.5))
            p = val_box.text_frame.paragraphs[0]
            p.text = str(kpi.get("value", ""))
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(18)
            p.font.bold = True
            p.font.color.rgb = RgbColor(255, 255, 255)
            p.alignment = PP_ALIGN.CENTER

        # Case Study header
        cs_header = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(3.5),
            Inches(12.33), Inches(0.35)
        )
        cs_header.fill.solid()
        cs_header.fill.fore_color.rgb = hex_to_rgb(COLORS_PROFESSIONAL["header_gray"])
        cs_header.line.fill.background()

        cs_text = slide.shapes.add_textbox(Inches(0.6), Inches(3.55), Inches(12), Inches(0.3))
        p = cs_text.text_frame.paragraphs[0]
        p.text = f"Case Study: {case_study_name}"
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(11)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)

        # Before/After table
        ba_data = [["Metric", "Before", "After", "Gain $", "Gain %"]]
        for m in before_after_metrics:
            ba_data.append([
                m.get("metric", ""),
                m.get("before", ""),
                m.get("after", ""),
                m.get("gain_dollar", ""),
                m.get("gain_pct", "")
            ])

        self._add_table(slide, ba_data, 5.5, 4.0, 7.3, row_height=0.4)

        if takeaway:
            self._add_key_takeaway_bar(slide, takeaway)

        self._add_footer(slide)
        return slide

    def add_cover_slide(self, title: str, subtitle: str = "",
                        prepared_for: str = "", date: str = None):
        """Add a cover/title slide."""
        slide = self._add_slide()

        # Background shape
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0), Inches(0),
            Inches(13.333), Inches(3)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = hex_to_rgb(COLORS["primary"])
        shape.line.fill.background()

        # Title
        title_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(1), Inches(12.33), Inches(1)
        )
        tf = title_box.text_frame
        p = tf.paragraphs[0]
        p.text = title
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(40)
        p.font.bold = True
        p.font.color.rgb = RgbColor(255, 255, 255)

        # Subtitle
        if subtitle:
            sub_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(2), Inches(12.33), Inches(0.6)
            )
            tf = sub_box.text_frame
            p = tf.paragraphs[0]
            p.text = subtitle
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(20)
            p.font.color.rgb = RgbColor(255, 255, 255)

        # Prepared for
        if prepared_for:
            prep_box = slide.shapes.add_textbox(
                Inches(0.5), Inches(4), Inches(12.33), Inches(0.5)
            )
            tf = prep_box.text_frame
            p = tf.paragraphs[0]
            p.text = f"Prepared for: {prepared_for}"
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(14)
            p.font.color.rgb = hex_to_rgb(COLORS["text"])

        # Date
        date_text = date or datetime.now().strftime("%B %d, %Y")
        date_box = slide.shapes.add_textbox(
            Inches(0.5), Inches(4.6), Inches(12.33), Inches(0.5)
        )
        tf = date_box.text_frame
        p = tf.paragraphs[0]
        p.text = date_text
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(14)
        p.font.color.rgb = hex_to_rgb(COLORS["text"])

        return slide

    def add_executive_summary(self, key_points: list, investment_highlights: list = None):
        """Add executive summary slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, "Executive Summary")

        self._add_bullet_points(slide, key_points, 0.5, 1.2, 6, 5)

        if investment_highlights:
            self._add_subtitle_shape(slide, "Investment Highlights", top=1.0)
            # Add highlights box on right side
            shape = slide.shapes.add_shape(
                MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7), Inches(1.2),
                Inches(5.8), Inches(5.5)
            )
            shape.fill.solid()
            shape.fill.fore_color.rgb = hex_to_rgb(COLORS["light_bg"])
            shape.line.color.rgb = hex_to_rgb(COLORS["secondary"])

            self._add_bullet_points(slide, investment_highlights, 7.2, 1.5, 5.4, 5)

        self._add_footer(slide)
        return slide

    def add_industry_overview(self, industry_name: str, market_size: str,
                              growth_rate: str, key_trends: list,
                              key_players: list):
        """Add industry overview slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, f"Industry Overview: {industry_name}")

        # Market stats
        stats_data = [
            ["Market Size", "Growth Rate (CAGR)", "Key Segments"],
            [market_size, growth_rate, str(len(key_players)) + " Major Players"]
        ]
        self._add_table(slide, stats_data, 0.5, 1.2, 12.33)

        # Key trends
        self._add_subtitle_shape(slide, "Key Industry Trends", top=2.3)
        self._add_bullet_points(slide, key_trends, 0.5, 2.8, 6, 3)

        # Key players
        self._add_subtitle_shape(slide, "Competitive Landscape", top=2.3)
        players_box = slide.shapes.add_textbox(
            Inches(7), Inches(2.8), Inches(5.8), Inches(3)
        )
        tf = players_box.text_frame
        tf.word_wrap = True
        for i, player in enumerate(key_players[:6]):
            if i == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.text = f"• {player}"
            p.font.name = DEFAULT_FONT
            p.font.size = Pt(BODY_FONT_SIZE)

        self._add_footer(slide)
        return slide

    def add_company_overview(self, company_name: str, ticker: str,
                             description: str, key_metrics: dict):
        """Add company overview slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, f"Company Overview: {company_name} ({ticker})")

        # Description
        self._add_body_text(slide, description, 0.5, 1.2, 7.5, 2)

        # Key metrics table
        metrics_data = [["Metric", "Value"]]
        for metric, value in key_metrics.items():
            metrics_data.append([metric, str(value)])

        self._add_table(slide, metrics_data, 8.5, 1.2, 4.3)

        self._add_footer(slide)
        return slide

    def add_financial_summary(self, company_name: str, financials: dict):
        """Add financial summary slide with key metrics."""
        slide = self._add_slide()
        self._add_title_shape(slide, f"Financial Summary: {company_name}")

        # Create financial table
        headers = ["Metric"] + list(financials.get("years", ["FY1", "FY2", "FY3"]))
        table_data = [headers]

        for metric, values in financials.get("metrics", {}).items():
            row = [metric] + [str(v) for v in values]
            table_data.append(row)

        self._add_table(slide, table_data, 0.5, 1.2, 12.33, row_height=0.45)

        self._add_footer(slide)
        return slide

    def add_valuation_summary(self, company_name: str, valuation_data: dict):
        """Add valuation summary slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, f"Valuation Summary: {company_name}")

        # DCF valuation
        dcf_data = [
            ["DCF Valuation", "Value"],
            ["Enterprise Value", valuation_data.get("ev", "N/A")],
            ["(-) Net Debt", valuation_data.get("net_debt", "N/A")],
            ["Equity Value", valuation_data.get("equity_value", "N/A")],
            ["Shares Outstanding", valuation_data.get("shares", "N/A")],
            ["Implied Share Price", valuation_data.get("share_price", "N/A")],
        ]
        self._add_table(slide, dcf_data, 0.5, 1.2, 5.5)

        # Comparable companies
        if "comps" in valuation_data:
            self._add_subtitle_shape(slide, "Comparable Companies", top=1.0)
            comps_data = [["Company", "EV/Revenue", "EV/EBITDA", "P/E"]]
            for comp in valuation_data["comps"]:
                comps_data.append([
                    comp.get("name", ""),
                    comp.get("ev_revenue", ""),
                    comp.get("ev_ebitda", ""),
                    comp.get("pe", "")
                ])
            self._add_table(slide, comps_data, 6.5, 1.2, 6.3)

        self._add_footer(slide)
        return slide

    def add_investment_thesis(self, thesis_points: list, risks: list):
        """Add investment thesis slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, "Investment Thesis")

        # Thesis points (left side)
        self._add_subtitle_shape(slide, "Key Investment Merits", top=0.9)
        self._add_bullet_points(slide, thesis_points, 0.5, 1.4, 6, 4)

        # Risks (right side)
        risk_box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(7), Inches(1.0),
            Inches(5.8), Inches(5.5)
        )
        risk_box.fill.solid()
        risk_box.fill.fore_color.rgb = hex_to_rgb("fef2f2")  # Light red
        risk_box.line.color.rgb = hex_to_rgb(COLORS["negative"])

        risk_title = slide.shapes.add_textbox(
            Inches(7.2), Inches(1.2), Inches(5.4), Inches(0.4)
        )
        tf = risk_title.text_frame
        p = tf.paragraphs[0]
        p.text = "Key Risks"
        p.font.name = DEFAULT_FONT
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = hex_to_rgb(COLORS["negative"])

        self._add_bullet_points(slide, risks, 7.2, 1.7, 5.4, 4.5)

        self._add_footer(slide)
        return slide

    def add_transaction_overview(self, deal_type: str, target: str,
                                 acquirer: str, deal_value: str,
                                 deal_terms: list):
        """Add M&A transaction overview slide."""
        slide = self._add_slide()
        self._add_title_shape(slide, f"Transaction Overview: {deal_type}")

        # Deal summary
        deal_data = [
            ["Target", "Acquirer", "Transaction Value"],
            [target, acquirer, deal_value]
        ]
        self._add_table(slide, deal_data, 0.5, 1.2, 12.33)

        # Deal terms
        self._add_subtitle_shape(slide, "Key Transaction Terms", top=2.3)
        self._add_bullet_points(slide, deal_terms, 0.5, 2.8, 12, 4)

        self._add_footer(slide)
        return slide

    def save(self, filename: str = None):
        """Save the presentation."""
        if not os.path.exists(OUTPUT_PATH):
            os.makedirs(OUTPUT_PATH)

        if not filename:
            filename = f"{self.title.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.pptx"

        filepath = os.path.join(OUTPUT_PATH, filename)
        self.prs.save(filepath)
        print(f"Presentation saved: {filepath}")
        return filepath


# ============================================================
# Template Functions for Common Deck Types
# ============================================================

def create_industry_research_deck(industry: str, data: dict) -> str:
    """Create a complete industry research deck."""
    prs = IBPresentation(f"{industry} Industry Analysis")

    # Cover
    prs.add_cover_slide(
        title=f"{industry} Industry Analysis",
        subtitle="Market Overview & Investment Opportunities",
        prepared_for=data.get("client", "Internal Use")
    )

    # Executive Summary
    prs.add_executive_summary(
        key_points=data.get("summary_points", [
            "Market overview and size",
            "Key growth drivers",
            "Competitive landscape",
            "Investment opportunities"
        ]),
        investment_highlights=data.get("highlights", [])
    )

    # Industry Overview
    prs.add_industry_overview(
        industry_name=industry,
        market_size=data.get("market_size", "TBD"),
        growth_rate=data.get("growth_rate", "TBD"),
        key_trends=data.get("trends", []),
        key_players=data.get("key_players", [])
    )

    return prs.save()


def create_company_profile_deck(company: str, ticker: str, data: dict) -> str:
    """Create a company profile/deep-dive deck."""
    prs = IBPresentation(f"{company} Company Profile")

    # Cover
    prs.add_cover_slide(
        title=f"{company} ({ticker})",
        subtitle="Company Profile & Investment Analysis",
        prepared_for=data.get("client", "Internal Use")
    )

    # Executive Summary
    prs.add_executive_summary(
        key_points=data.get("summary_points", []),
        investment_highlights=data.get("highlights", [])
    )

    # Company Overview
    prs.add_company_overview(
        company_name=company,
        ticker=ticker,
        description=data.get("description", ""),
        key_metrics=data.get("key_metrics", {})
    )

    # Financial Summary
    if "financials" in data:
        prs.add_financial_summary(company, data["financials"])

    # Valuation
    if "valuation" in data:
        prs.add_valuation_summary(company, data["valuation"])

    # Investment Thesis
    if "thesis" in data and "risks" in data:
        prs.add_investment_thesis(data["thesis"], data["risks"])

    return prs.save()


def create_pitch_book(deal_name: str, data: dict) -> str:
    """Create an M&A pitch book."""
    prs = IBPresentation(f"{deal_name} - Pitch Book")

    # Cover
    prs.add_cover_slide(
        title=deal_name,
        subtitle=data.get("subtitle", "Confidential Information Memorandum"),
        prepared_for=data.get("client", "")
    )

    # Executive Summary
    prs.add_executive_summary(
        key_points=data.get("summary_points", []),
        investment_highlights=data.get("highlights", [])
    )

    # Transaction Overview
    if "transaction" in data:
        txn = data["transaction"]
        prs.add_transaction_overview(
            deal_type=txn.get("type", "Acquisition"),
            target=txn.get("target", ""),
            acquirer=txn.get("acquirer", ""),
            deal_value=txn.get("value", ""),
            deal_terms=txn.get("terms", [])
        )

    # Company Overview (Target)
    if "target_company" in data:
        tc = data["target_company"]
        prs.add_company_overview(
            company_name=tc.get("name", ""),
            ticker=tc.get("ticker", ""),
            description=tc.get("description", ""),
            key_metrics=tc.get("metrics", {})
        )

    # Financials
    if "financials" in data:
        prs.add_financial_summary(data.get("target_company", {}).get("name", "Target"), data["financials"])

    # Valuation
    if "valuation" in data:
        prs.add_valuation_summary("Target", data["valuation"])

    return prs.save()


if __name__ == "__main__":
    # Example: Create a sample industry research deck
    sample_data = {
        "client": "Sample Client",
        "market_size": "$500 Billion",
        "growth_rate": "8.5% CAGR",
        "summary_points": [
            "Large and growing addressable market",
            "Favorable regulatory tailwinds",
            "Consolidation opportunity among fragmented players",
            "Technology disruption creating new winners"
        ],
        "highlights": [
            "8.5% market CAGR through 2028",
            "Top 5 players control only 35% market share",
            "Margins expanding due to scale benefits"
        ],
        "trends": [
            "Digital transformation accelerating",
            "ESG considerations becoming critical",
            "Supply chain reshoring",
            "AI/ML adoption increasing"
        ],
        "key_players": [
            "Company A - Market Leader (15% share)",
            "Company B - Fast Growing (12% share)",
            "Company C - Niche Player (8% share)",
            "Company D - Regional Focus (5% share)"
        ]
    }

    filepath = create_industry_research_deck("Technology Services", sample_data)
    print(f"\nSample deck created: {filepath}")
