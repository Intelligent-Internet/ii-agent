"""
Generate Excel backup templates for slide generation.
Creates 18+ template files with sample data and charts.

Professional formatting extracted from:
- BCI 2026 Case Study (Growth Equity/SaaS)
- Northleaf 2026 Model (LBO)
"""

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, NamedStyle
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from pathlib import Path

# =============================================================================
# PROFESSIONAL COLOR PALETTE (from BCI/Northleaf)
# =============================================================================

# Headers
NAVY_BLUE = PatternFill(start_color="01395D", end_color="01395D", fill_type="solid")
DARK_GRAY = PatternFill(start_color="4A4A4A", end_color="4A4A4A", fill_type="solid")

# Quartile colors (for benchmarking)
BOTTOM_QUARTILE = PatternFill(start_color="FFCDD2", end_color="FFCDD2", fill_type="solid")  # Light red
SECOND_QUARTILE = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")  # Light yellow
THIRD_QUARTILE = PatternFill(start_color="C8E6C9", end_color="C8E6C9", fill_type="solid")   # Light green
TOP_QUARTILE = PatternFill(start_color="81C784", end_color="81C784", fill_type="solid")     # Green

# Subject highlighting
GREEN_FILL = PatternFill(start_color="00A651", end_color="00A651", fill_type="solid")
LIGHT_GREEN_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")

# Alternating rows
LIGHT_GRAY_FILL = PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")
WHITE_FILL = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")

# Scenario colors
BEAR_FILL = PatternFill(start_color="FFEBEE", end_color="FFEBEE", fill_type="solid")  # Light red
BASE_FILL = PatternFill(start_color="E3F2FD", end_color="E3F2FD", fill_type="solid")  # Light blue
BULL_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")  # Light green

# Fonts
WHITE_FONT = Font(color="FFFFFF", bold=True)
NAVY_FONT = Font(color="01395D", bold=True)
HEADER_FONT = Font(bold=True, size=11)
TITLE_FONT = Font(bold=True, size=14, color="01395D")
SUBTITLE_FONT = Font(italic=True, size=10, color="666666")

# Borders
THIN_BORDER = Border(
    left=Side(style='thin', color='CCCCCC'),
    right=Side(style='thin', color='CCCCCC'),
    top=Side(style='thin', color='CCCCCC'),
    bottom=Side(style='thin', color='CCCCCC')
)
BOTTOM_BORDER = Border(bottom=Side(style='thin', color='CCCCCC'))

OUTPUT_DIR = Path(__file__).parent


def apply_header_style(ws, row, start_col=1, end_col=None, fill=NAVY_BLUE):
    """Apply professional header styling."""
    if end_col is None:
        end_col = ws.max_column
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = fill
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')


def apply_data_styling(ws, start_row=2, end_row=None, start_col=1, end_col=None):
    """Apply alternating row styling and borders."""
    if end_row is None:
        end_row = ws.max_row
    if end_col is None:
        end_col = ws.max_column
    for row in range(start_row, end_row + 1):
        for col in range(start_col, end_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = THIN_BORDER
            if row % 2 == 0:
                cell.fill = LIGHT_GRAY_FILL


def auto_column_width(ws, min_width=8, max_width=40):
    """Auto-adjust column widths."""
    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = max(min(max_length + 2, max_width), min_width)
        ws.column_dimensions[column_letter].width = adjusted_width


# =============================================================================
# Template 3: Peer Benchmarking (SaaS Style with Quartiles)
# =============================================================================
def create_peer_benchmarking():
    wb = Workbook()
    ws = wb.active
    ws.title = "Peer_Benchmarking"

    # Title
    ws['B2'] = "SaaS Peer Benchmarking Analysis"
    ws['B2'].font = TITLE_FONT

    # Headers (BCI style with quartile columns)
    headers = ["", "Metric", "Bottom", "2nd", "3rd", "Top", "", "Actual", "Quartile", "", "Projected", "Quartile"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 12)

    # Quartile header colors
    ws.cell(row=4, column=3).fill = BOTTOM_QUARTILE
    ws.cell(row=4, column=3).font = Font(bold=True)
    ws.cell(row=4, column=4).fill = SECOND_QUARTILE
    ws.cell(row=4, column=4).font = Font(bold=True)
    ws.cell(row=4, column=5).fill = THIRD_QUARTILE
    ws.cell(row=4, column=5).font = Font(bold=True)
    ws.cell(row=4, column=6).fill = TOP_QUARTILE
    ws.cell(row=4, column=6).font = Font(bold=True)

    # Section: Growth
    ws['B6'] = "Growth"
    ws['B6'].font = HEADER_FONT

    metrics = [
        ("ARR Growth (YoY)", "<9%", "9-13%", "13-21%", ">21%", "35%", "Top", "28%", "Top"),
        ("", "", "", "", "", "", "", "", ""),
        ("Retention", "", "", "", "", "", "", "", ""),
        ("Net Dollar Retention", "<97%", "97-105%", "105-115%", ">115%", "118%", "Top", "115%", "Top"),
        ("Gross Dollar Retention", "<78%", "78-85%", "85-90%", ">90%", "92%", "Top", "91%", "Top"),
        ("", "", "", "", "", "", "", "", ""),
        ("Efficiency", "", "", "", "", "", "", "", ""),
        ("Magic Number", "<0.37x", "0.37-0.47x", "0.47-0.72x", ">0.72x", "0.85x", "Top", "0.65x", "3rd"),
        ("LTV/CAC", "<2.0x", "2.0-3.0x", "3.0-4.5x", ">4.5x", "3.8x", "3rd", "4.2x", "3rd"),
        ("CAC Payback (months)", ">44", "32-44", "23-32", "<23", "28", "3rd", "25", "3rd"),
        ("Burn Multiple", ">3.5x", "2.5-3.5x", "1.8-2.5x", "<1.8x", "1.5x", "Top", "Pos. EBITDA", "Top"),
        ("", "", "", "", "", "", "", "", ""),
        ("Profitability", "", "", "", "", "", "", "", ""),
        ("Gross Margin", "<73%", "73-78%", "78-82%", ">82%", "85%", "Top", "86%", "Top"),
        ("Rule of 40", "<28%", "28-37%", "37-45%", ">45%", "42%", "3rd", "38%", "3rd"),
    ]

    for row_idx, row_data in enumerate(metrics, 7):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            # Apply quartile coloring to Quartile columns
            if col_idx in [9, 12] and value:
                if value == "Top":
                    cell.fill = TOP_QUARTILE
                elif value == "3rd":
                    cell.fill = THIRD_QUARTILE
                elif value == "2nd":
                    cell.fill = SECOND_QUARTILE
                elif value == "Bottom":
                    cell.fill = BOTTOM_QUARTILE
            # Section headers
            if value in ["Growth", "Retention", "Efficiency", "Profitability"]:
                cell.font = HEADER_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "03_peer_benchmarking.xlsx")
    print("Created: 03_peer_benchmarking.xlsx")


# =============================================================================
# Template 4: Comps Table (Professional Trading Comps)
# =============================================================================
def create_comps_table():
    wb = Workbook()
    ws = wb.active
    ws.title = "Trading_Comps"

    # Title
    ws['B2'] = "Public Comparable Companies"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "$ in millions, unless otherwise noted"
    ws['B3'].font = SUBTITLE_FONT

    headers = ["", "Company", "Ticker", "Price", "Mkt Cap", "EV", "EV/Rev", "EV/EBITDA", "P/E CY", "P/E NY", "Rev Growth", "EBITDA Margin"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=5, column=col, value=header)
    apply_header_style(ws, 5, 2, 12)

    data = [
        ("", "Peer Company A", "PEER.TO", 45.50, 2450, 3100, "8.5x", "12.3x", 18.5, 16.2, "15%", "28%"),
        ("", "Peer Company B", "PB.TO", 32.25, 1890, 2350, "7.2x", "14.1x", 21.2, 18.7, "12%", "24%"),
        ("", "Peer Company C", "PC.TO", 58.75, 3200, 4100, "9.8x", "13.2x", 19.8, 17.5, "18%", "32%"),
        ("", "Peer Company D", "PD.TO", 41.20, 2100, 2800, "6.8x", "11.8x", 17.2, 15.3, "10%", "26%"),
    ]

    for row_idx, row_data in enumerate(data, 6):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 4 and value:
                cell.number_format = '$#,##0.00'
            elif col_idx in [5, 6] and value:
                cell.number_format = '#,##0'
        cell.border = THIN_BORDER

    # Subject row (highlighted)
    subject_row = 10
    subject_data = ("", "Subject Company", "SUBJ.TO", 28.00, 1450, 1850, "5.5x", "10.5x", 15.8, 14.1, "22%", "30%")
    for col_idx, value in enumerate(subject_data, 1):
        cell = ws.cell(row=subject_row, column=col_idx, value=value)
        cell.fill = GREEN_FILL
        cell.font = WHITE_FONT
        if col_idx == 4 and value:
            cell.number_format = '$#,##0.00'
        elif col_idx in [5, 6] and value:
            cell.number_format = '#,##0'

    # Summary rows
    ws.cell(row=12, column=2, value="Mean").font = HEADER_FONT
    ws.cell(row=13, column=2, value="Median").font = HEADER_FONT
    ws.cell(row=12, column=7, value="8.1x")
    ws.cell(row=12, column=8, value="12.9x")
    ws.cell(row=13, column=7, value="7.9x")
    ws.cell(row=13, column=8, value="12.8x")

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "04_comps_table.xlsx")
    print("Created: 04_comps_table.xlsx")


# =============================================================================
# Template 5: Time Series (with Chart)
# =============================================================================
def create_time_series():
    wb = Workbook()
    ws = wb.active
    ws.title = "Time_Series"

    ws['B2'] = "Share Price Performance"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "Indexed to 100 at start date"
    ws['B3'].font = SUBTITLE_FONT

    headers = ["Date", "Subject", "Benchmark 1", "Benchmark 2"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=5, column=col, value=header)
    apply_header_style(ws, 5, 2, 5)

    from datetime import date, timedelta
    base_date = date(2024, 1, 1)
    subject_values = [100, 105.2, 108.7, 112.3, 118.5, 115.2, 122.8, 128.5, 135.2, 142.1, 138.5, 145.2]
    bench1_values = [100, 102.8, 104.2, 107.5, 110.2, 108.5, 112.3, 115.8, 118.2, 122.5, 120.8, 125.1]
    bench2_values = [100, 101.5, 103.8, 106.2, 108.5, 107.2, 110.5, 113.2, 116.8, 119.5, 118.2, 121.5]

    for i, (subj, b1, b2) in enumerate(zip(subject_values, bench1_values, bench2_values)):
        row = i + 6
        ws.cell(row=row, column=2, value=base_date + timedelta(days=i*30))
        ws.cell(row=row, column=3, value=subj)
        ws.cell(row=row, column=4, value=b1)
        ws.cell(row=row, column=5, value=b2)

    # Create line chart
    chart = LineChart()
    chart.title = "Price Performance (Indexed)"
    chart.style = 10
    chart.y_axis.title = "Index"
    chart.x_axis.title = "Date"

    data_ref = Reference(ws, min_col=3, max_col=5, min_row=5, max_row=17)
    cats_ref = Reference(ws, min_col=2, min_row=6, max_row=17)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.height = 10
    chart.width = 15

    ws.add_chart(chart, "G5")

    # Summary table
    ws['G20'] = "Summary Returns"
    ws['G20'].font = HEADER_FONT
    ws['G21'] = "Metric"
    ws['H21'] = "Subject"
    ws['I21'] = "Bench 1"
    ws['J21'] = "Bench 2"
    apply_header_style(ws, 21, 7, 10)
    ws['G22'] = "Cumulative Return"
    ws['H22'] = "45.2%"
    ws['I22'] = "25.1%"
    ws['J22'] = "21.5%"

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "05_time_series.xlsx")
    print("Created: 05_time_series.xlsx")


# =============================================================================
# Template 7: Sources & Uses (Transaction Structure)
# =============================================================================
def create_sources_uses():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sources_Uses"

    ws['B2'] = "Sources & Uses of Funds"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "$ in millions"
    ws['B3'].font = SUBTITLE_FONT

    # Sources section
    ws['B5'] = "SOURCES"
    ws['B5'].font = WHITE_FONT
    ws['B5'].fill = NAVY_BLUE
    ws.merge_cells('B5:E5')

    headers = ["Source", "Amount", "% of Total", "Notes"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=6, column=col, value=header)
    apply_header_style(ws, 6, 2, 5)

    sources = [
        ("Senior Term Loan", 108, 0.50, "5.0x LTM EBITDA"),
        ("Sponsor Equity", 97, 0.45, ""),
        ("Management Rollover", 10, 0.05, "$10M commitment"),
        ("Total Sources", 215, 1.00, ""),
    ]

    for row_idx, row_data in enumerate(sources, 7):
        ws.cell(row=row_idx, column=2, value=row_data[0])
        cell_amt = ws.cell(row=row_idx, column=3, value=row_data[1])
        cell_amt.number_format = '$#,##0'
        cell_pct = ws.cell(row=row_idx, column=4, value=row_data[2])
        cell_pct.number_format = '0%'
        ws.cell(row=row_idx, column=5, value=row_data[3])
        if row_data[0] == "Total Sources":
            for col in range(2, 6):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT
                ws.cell(row=row_idx, column=col).border = Border(top=Side(style='double'))

    # Uses section
    ws['B13'] = "USES"
    ws['B13'].font = WHITE_FONT
    ws['B13'].fill = NAVY_BLUE
    ws.merge_cells('B13:E13')

    for col, header in enumerate(["Use", "Amount", "% of Total", "Notes"], 2):
        ws.cell(row=14, column=col, value=header)
    apply_header_style(ws, 14, 2, 5)

    uses = [
        ("Purchase Price", 206, 0.96, "11.0x LTM EBITDA"),
        ("Transaction Fees", 6, 0.03, "3% of EV"),
        ("Financing Fees", 3, 0.01, "4% of debt"),
        ("Total Uses", 215, 1.00, ""),
    ]

    for row_idx, row_data in enumerate(uses, 15):
        ws.cell(row=row_idx, column=2, value=row_data[0])
        cell_amt = ws.cell(row=row_idx, column=3, value=row_data[1])
        cell_amt.number_format = '$#,##0'
        cell_pct = ws.cell(row=row_idx, column=4, value=row_data[2])
        cell_pct.number_format = '0%'
        ws.cell(row=row_idx, column=5, value=row_data[3])
        if row_data[0] == "Total Uses":
            for col in range(2, 6):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT
                ws.cell(row=row_idx, column=col).border = Border(top=Side(style='double'))

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "07_sources_uses.xlsx")
    print("Created: 07_sources_uses.xlsx")


# =============================================================================
# Template 8: Scenario Analysis (Bull/Base/Bear)
# =============================================================================
def create_scenario_analysis():
    wb = Workbook()
    ws = wb.active
    ws.title = "Scenario_Analysis"

    ws['B2'] = "Scenario Analysis"
    ws['B2'].font = TITLE_FONT

    # Assumptions section
    ws['B4'] = "SCENARIO ASSUMPTIONS"
    ws['B4'].font = WHITE_FONT
    ws['B4'].fill = NAVY_BLUE
    ws.merge_cells('B4:E4')

    headers = ["Assumption", "Downside", "Base", "Upside"]
    for col, header in enumerate(headers, 2):
        cell = ws.cell(row=5, column=col, value=header)
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center')

    # Color code scenario headers
    ws.cell(row=5, column=3).fill = BEAR_FILL
    ws.cell(row=5, column=4).fill = BASE_FILL
    ws.cell(row=5, column=5).fill = BULL_FILL

    assumptions = [
        ("Revenue CAGR (%)", "5.0%", "7.5%", "11.8%"),
        ("Exit EBITDA Margin (%)", "12%", "14%", "16%"),
        ("Exit Multiple (x)", "8.0x", "9.5x", "11.0x"),
        ("Probability (%)", "25%", "50%", "25%"),
    ]

    for row_idx, row_data in enumerate(assumptions, 6):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 3:
                cell.fill = PatternFill(start_color="FFF5F5", end_color="FFF5F5", fill_type="solid")
            elif col_idx == 4:
                cell.fill = PatternFill(start_color="F5F9FF", end_color="F5F9FF", fill_type="solid")
            elif col_idx == 5:
                cell.fill = PatternFill(start_color="F5FFF5", end_color="F5FFF5", fill_type="solid")

    # Outputs section
    ws['B12'] = "CALCULATED OUTPUTS"
    ws['B12'].font = WHITE_FONT
    ws['B12'].fill = GREEN_FILL
    ws.merge_cells('B12:E12')

    outputs = [
        ("Exit EBITDA ($M)", "$32", "$42", "$55"),
        ("Exit EV ($M)", "$256", "$399", "$605"),
        ("Exit Equity ($M)", "$165", "$310", "$515"),
        ("", "", "", ""),
        ("Gross MOIC (x)", "1.7x", "3.2x", "5.3x"),
        ("Gross IRR (%)", "11%", "26%", "40%"),
    ]

    for row_idx, row_data in enumerate(outputs, 13):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if row_data[0] in ["Gross MOIC (x)", "Gross IRR (%)"]:
                cell.font = HEADER_FONT

    # Probability-weighted returns
    ws['B21'] = "PROBABILITY-WEIGHTED RETURNS"
    ws['B21'].font = HEADER_FONT
    ws['B22'] = "Expected Gross MOIC"
    ws['C22'] = "3.1x"
    ws['C22'].font = Font(bold=True, size=14, color="00A651")
    ws['B23'] = "Expected Gross IRR"
    ws['C23'] = "24%"
    ws['C23'].font = Font(bold=True, size=14, color="00A651")

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "08_scenario_analysis.xlsx")
    print("Created: 08_scenario_analysis.xlsx")


# =============================================================================
# Template 11: Heat Map (Performance Matrix)
# =============================================================================
def create_heat_map():
    wb = Workbook()
    ws = wb.active
    ws.title = "Heat_Map"

    ws['B2'] = "Annual Returns by Strategy"
    ws['B2'].font = TITLE_FONT

    headers = ["Strategy", "2020", "2021", "2022", "2023", "2024", "5-Yr IRR"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 8)

    data = [
        ("Core Value-Add", 0.171, 0.213, 0.314, 0.130, 0.124, 0.158),
        ("Opportunistic", 0.149, 0.188, 0.203, 0.125, 0.108, 0.154),
        ("Core Plus", 0.098, 0.112, 0.145, 0.095, 0.088, 0.107),
        ("Distressed", 0.071, -0.028, 0.121, 0.080, -0.082, 0.079),
    ]

    # Color fills for heat map
    dark_green = PatternFill(start_color="1B5E20", end_color="1B5E20", fill_type="solid")
    green = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
    light_green = PatternFill(start_color="A5D6A7", end_color="A5D6A7", fill_type="solid")
    red = PatternFill(start_color="E53935", end_color="E53935", fill_type="solid")

    for row_idx, row_data in enumerate(data, 5):
        ws.cell(row=row_idx, column=2, value=row_data[0])
        for col_idx, value in enumerate(row_data[1:], 3):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.number_format = '0.0%'
            cell.alignment = Alignment(horizontal='center')
            # Apply conditional color
            if value > 0.20:
                cell.fill = dark_green
                cell.font = Font(color="FFFFFF", bold=True)
            elif value > 0.10:
                cell.fill = green
                cell.font = Font(color="FFFFFF")
            elif value > 0:
                cell.fill = light_green
            else:
                cell.fill = red
                cell.font = Font(color="FFFFFF")

    # Legend
    ws['B11'] = "Color Scale:"
    ws['C11'] = "> 20%"
    ws['C11'].fill = dark_green
    ws['C11'].font = Font(color="FFFFFF")
    ws['D11'] = "10-20%"
    ws['D11'].fill = green
    ws['D11'].font = Font(color="FFFFFF")
    ws['E11'] = "0-10%"
    ws['E11'].fill = light_green
    ws['F11'] = "< 0%"
    ws['F11'].fill = red
    ws['F11'].font = Font(color="FFFFFF")

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "11_heat_map.xlsx")
    print("Created: 11_heat_map.xlsx")


# =============================================================================
# Template 16: Precedent Transactions (M&A Comps)
# =============================================================================
def create_precedent_transactions():
    wb = Workbook()
    ws = wb.active
    ws.title = "Precedent_Transactions"

    ws['B2'] = "Precedent Transaction Analysis"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "Selected M&A Transactions in Sector"
    ws['B3'].font = SUBTITLE_FONT

    headers = ["#", "Date", "Target", "Acquirer", "Deal Type", "EV ($M)", "LTM Rev", "LTM EBITDA", "EBITDA %", "EV/Rev", "EV/EBITDA"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=5, column=col, value=header)
    apply_header_style(ws, 5, 2, 12)

    data = [
        (1, "Oct-24", "Company A", "Strategic Buyer", "Strategic", 500, 380, 50, 0.132, 1.32, 10.0),
        (2, "Jun-24", "Company B", "PE Sponsor", "LBO", 425, 340, 42, 0.124, 1.25, 10.1),
        (3, "Mar-24", "Company C", "Strategic Buyer", "Strategic", 240, 180, 25, 0.139, 1.33, 9.6),
        (4, "Aug-23", "Company D", "PE Sponsor", "LBO", 340, 280, 30, 0.107, 1.21, 11.3),
        (5, "Dec-22", "Company E", "PE Sponsor", "LBO", 485, 400, 55, 0.138, 1.21, 8.8),
    ]

    for row_idx, row_data in enumerate(data, 6):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [7, 8, 9]:  # Financial columns
                cell.number_format = '#,##0'
            elif col_idx == 10:  # EBITDA %
                cell.number_format = '0.0%'
            elif col_idx in [11, 12]:  # Multiples
                cell.number_format = '0.0"x"'
            cell.border = THIN_BORDER

    # Summary statistics
    ws.cell(row=12, column=2, value="Mean").font = HEADER_FONT
    ws.cell(row=13, column=2, value="Median").font = HEADER_FONT
    ws.cell(row=14, column=2, value="25th Percentile").font = HEADER_FONT
    ws.cell(row=15, column=2, value="75th Percentile").font = HEADER_FONT

    # Formulas for summary
    ws['L12'] = "=AVERAGE(L6:L10)"
    ws['L13'] = "=MEDIAN(L6:L10)"
    ws['L14'] = "=PERCENTILE(L6:L10,0.25)"
    ws['L15'] = "=PERCENTILE(L6:L10,0.75)"

    for row in range(12, 16):
        ws.cell(row=row, column=12).number_format = '0.0"x"'

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "16_precedent_transactions.xlsx")
    print("Created: 16_precedent_transactions.xlsx")


# =============================================================================
# Template 19: Value Creation Waterfall (MOIC + IRR Bridge)
# =============================================================================
def create_value_creation_waterfall():
    """
    Creates waterfall charts for MOIC and IRR bridges.
    Uses stacked column chart technique with 4 series:
    - Base (invisible) - creates floating effect
    - Increase (green) - positive contributions
    - Decrease (red) - negative contributions
    - Total (navy) - final total bar
    Based on BCI 2026 Case Study Slide 18 format.
    """
    from openpyxl.chart.series import DataPoint
    from openpyxl.drawing.fill import PatternFillProperties, ColorChoice

    wb = Workbook()
    ws = wb.active
    ws.title = "Value_Creation"

    ws['B2'] = "VALUE CREATION ANALYSIS"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "Key Return Drivers | Base Case"
    ws['B3'].font = SUBTITLE_FONT

    # =========================================================================
    # MOIC BRIDGE DATA (for waterfall chart)
    # =========================================================================
    ws['H2'] = "MOIC Bridge Chart Data"
    ws['H2'].font = HEADER_FONT

    # Categories and waterfall data structure
    moic_headers = ["Category", "Base", "Increase", "Decrease", "Total"]
    for col, header in enumerate(moic_headers, 8):
        ws.cell(row=3, column=col, value=header)
    apply_header_style(ws, 3, 8, 12)

    # Waterfall data: [Category, Base (invisible), Increase (green), Decrease (red), Total (navy)]
    # Base stacks to create floating effect
    moic_waterfall = [
        ("Initial Investment", 0, 97, 0, 0),       # Starting bar
        ("Revenue Growth", 97, 173, 0, 0),          # +173 from 97
        ("Multiple Contraction", 270, 0, 45, 0),    # -45 from 270
        ("Debt Paydown", 225, 65, 0, 0),            # +65 from 225
        ("Exit Value", 0, 0, 0, 290),               # Final total
    ]

    for row_idx, row_data in enumerate(moic_waterfall, 4):
        for col_idx, value in enumerate(row_data, 8):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Create MOIC waterfall chart
    moic_chart = BarChart()
    moic_chart.type = "col"
    moic_chart.grouping = "stacked"
    moic_chart.overlap = 100
    moic_chart.title = "MOIC Value Bridge ($M)"
    moic_chart.y_axis.title = "Value ($M)"
    moic_chart.legend = None

    # Add data series
    cats = Reference(ws, min_col=8, min_row=4, max_row=8)
    base_data = Reference(ws, min_col=9, min_row=3, max_row=8)
    increase_data = Reference(ws, min_col=10, min_row=3, max_row=8)
    decrease_data = Reference(ws, min_col=11, min_row=3, max_row=8)
    total_data = Reference(ws, min_col=12, min_row=3, max_row=8)

    moic_chart.add_data(base_data, titles_from_data=True)
    moic_chart.add_data(increase_data, titles_from_data=True)
    moic_chart.add_data(decrease_data, titles_from_data=True)
    moic_chart.add_data(total_data, titles_from_data=True)
    moic_chart.set_categories(cats)

    # Style series
    # Base - invisible (no fill)
    moic_chart.series[0].graphicalProperties.noFill = True
    moic_chart.series[0].graphicalProperties.line.noFill = True
    # Increase - green
    moic_chart.series[1].graphicalProperties.solidFill = "00A651"
    # Decrease - red
    moic_chart.series[2].graphicalProperties.solidFill = "C00000"
    # Total - navy
    moic_chart.series[3].graphicalProperties.solidFill = "01395D"

    moic_chart.width = 15
    moic_chart.height = 10
    ws.add_chart(moic_chart, "B5")

    # =========================================================================
    # IRR BRIDGE DATA (for waterfall chart)
    # =========================================================================
    ws['H12'] = "IRR Bridge Chart Data"
    ws['H12'].font = HEADER_FONT

    irr_headers = ["Category", "Base", "Increase", "Decrease", "Total"]
    for col, header in enumerate(irr_headers, 8):
        ws.cell(row=13, column=col, value=header)
    apply_header_style(ws, 13, 8, 12)

    # IRR waterfall data (percentages)
    irr_waterfall = [
        ("Base (0%)", 0, 0, 0, 0),
        ("Revenue Growth", 0, 35, 0, 0),            # +35%
        ("Multiple Contraction", 35, 0, 14, 0),     # -14%
        ("Series D Dilution", 21, 0, 1, 0),         # -1%
        ("Net IRR", 0, 0, 0, 20),                   # Final: 20%
    ]

    for row_idx, row_data in enumerate(irr_waterfall, 14):
        for col_idx, value in enumerate(row_data, 8):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Create IRR waterfall chart
    irr_chart = BarChart()
    irr_chart.type = "col"
    irr_chart.grouping = "stacked"
    irr_chart.overlap = 100
    irr_chart.title = "IRR Attribution Bridge (%)"
    irr_chart.y_axis.title = "IRR (%)"
    irr_chart.legend = None

    cats2 = Reference(ws, min_col=8, min_row=14, max_row=18)
    base_data2 = Reference(ws, min_col=9, min_row=13, max_row=18)
    increase_data2 = Reference(ws, min_col=10, min_row=13, max_row=18)
    decrease_data2 = Reference(ws, min_col=11, min_row=13, max_row=18)
    total_data2 = Reference(ws, min_col=12, min_row=13, max_row=18)

    irr_chart.add_data(base_data2, titles_from_data=True)
    irr_chart.add_data(increase_data2, titles_from_data=True)
    irr_chart.add_data(decrease_data2, titles_from_data=True)
    irr_chart.add_data(total_data2, titles_from_data=True)
    irr_chart.set_categories(cats2)

    # Style series
    irr_chart.series[0].graphicalProperties.noFill = True
    irr_chart.series[0].graphicalProperties.line.noFill = True
    irr_chart.series[1].graphicalProperties.solidFill = "00A651"  # Green
    irr_chart.series[2].graphicalProperties.solidFill = "C00000"  # Red
    irr_chart.series[3].graphicalProperties.solidFill = "01395D"  # Navy

    irr_chart.width = 15
    irr_chart.height = 10
    ws.add_chart(irr_chart, "B22")

    # =========================================================================
    # SUMMARY TABLE
    # =========================================================================
    ws['H22'] = "Summary"
    ws['H22'].font = HEADER_FONT

    summary_data = [
        ("Metric", "Value"),
        ("Entry Equity", "$97M"),
        ("Exit Equity", "$290M"),
        ("Implied MOIC", "3.0x"),
        ("Net IRR", "20%"),
        ("Hold Period", "5 years"),
    ]

    for row_idx, (label, value) in enumerate(summary_data, 23):
        ws.cell(row=row_idx, column=8, value=label)
        ws.cell(row=row_idx, column=9, value=value)
        if row_idx == 23:
            ws.cell(row=row_idx, column=8).fill = NAVY_BLUE
            ws.cell(row=row_idx, column=8).font = WHITE_FONT
            ws.cell(row=row_idx, column=9).fill = NAVY_BLUE
            ws.cell(row=row_idx, column=9).font = WHITE_FONT

    # Target check
    ws['H30'] = "Target IRR (20%)"
    ws['I30'] = "Met"
    ws['I30'].fill = TOP_QUARTILE
    ws['I30'].font = HEADER_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "19_value_creation_waterfall.xlsx")
    print("Created: 19_value_creation_waterfall.xlsx")


# =============================================================================
# Template 22: Sensitivity Table (Entry vs Exit Multiple)
# =============================================================================
def create_sensitivity_table():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sensitivity"

    ws['C3'] = "SENSITIVITY ANALYSIS"
    ws['C3'].font = TITLE_FONT

    # Input summary
    ws['C5'] = "Inputs"
    ws['C5'].font = HEADER_FONT
    inputs = [
        ("Entry EBITDA ($M)", 19.5),
        ("Exit EBITDA ($M)", 42.0),
        ("Exit Debt ($M)", 20.0),
        ("Sponsor Ownership", "91%"),
        ("Hold Period (years)", 5),
        ("Sponsor Equity ($M)", 97.0),
    ]
    for row_idx, (label, value) in enumerate(inputs, 6):
        ws.cell(row=row_idx, column=3, value=value)
        ws.cell(row=row_idx, column=4, value=label)

    # IRR Sensitivity Table
    ws['C14'] = "Gross IRR: Entry Multiple vs Exit Multiple"
    ws['C14'].font = HEADER_FONT

    ws['D16'] = "Exit Multiple"
    ws['D16'].font = HEADER_FONT

    exit_multiples = [7.5, 8.5, 9.5, 10.5, 11.5]
    entry_multiples = [9.0, 10.0, 11.0, 12.0, 13.0]

    # Exit multiple headers
    for col_idx, mult in enumerate(exit_multiples, 4):
        cell = ws.cell(row=17, column=col_idx, value=f"{mult}x")
        cell.fill = NAVY_BLUE
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal='center')

    # Entry multiple row headers and IRR values
    ws.cell(row=17, column=3, value="Entry\nMultiple").fill = NAVY_BLUE
    ws.cell(row=17, column=3).font = WHITE_FONT

    # Sample IRR matrix (would normally be calculated)
    irr_matrix = [
        [0.35, 0.32, 0.29, 0.26, 0.24],
        [0.30, 0.27, 0.24, 0.21, 0.19],
        [0.26, 0.23, 0.20, 0.17, 0.15],
        [0.22, 0.19, 0.16, 0.13, 0.11],
        [0.18, 0.15, 0.12, 0.09, 0.07],
    ]

    for row_idx, (entry_mult, irr_row) in enumerate(zip(entry_multiples, irr_matrix), 18):
        ws.cell(row=row_idx, column=3, value=f"{entry_mult}x")
        ws.cell(row=row_idx, column=3).fill = NAVY_BLUE
        ws.cell(row=row_idx, column=3).font = WHITE_FONT

        for col_idx, irr in enumerate(irr_row, 4):
            cell = ws.cell(row=row_idx, column=col_idx, value=irr)
            cell.number_format = '0%'
            cell.alignment = Alignment(horizontal='center')
            # Color based on IRR threshold
            if irr >= 0.25:
                cell.fill = TOP_QUARTILE
            elif irr >= 0.20:
                cell.fill = THIRD_QUARTILE
            elif irr >= 0.15:
                cell.fill = SECOND_QUARTILE
            else:
                cell.fill = BOTTOM_QUARTILE

    # MOIC Sensitivity Table
    ws['C26'] = "Gross MOIC: Entry Multiple vs Exit Multiple"
    ws['C26'].font = HEADER_FONT

    for col_idx, mult in enumerate(exit_multiples, 4):
        cell = ws.cell(row=28, column=col_idx, value=f"{mult}x")
        cell.fill = NAVY_BLUE
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal='center')

    ws.cell(row=28, column=3, value="Entry\nMultiple").fill = NAVY_BLUE
    ws.cell(row=28, column=3).font = WHITE_FONT

    moic_matrix = [
        [4.3, 3.8, 3.4, 3.0, 2.7],
        [3.6, 3.2, 2.8, 2.5, 2.2],
        [3.1, 2.7, 2.4, 2.1, 1.9],
        [2.7, 2.4, 2.1, 1.8, 1.6],
        [2.3, 2.0, 1.8, 1.6, 1.4],
    ]

    for row_idx, (entry_mult, moic_row) in enumerate(zip(entry_multiples, moic_matrix), 29):
        ws.cell(row=row_idx, column=3, value=f"{entry_mult}x")
        ws.cell(row=row_idx, column=3).fill = NAVY_BLUE
        ws.cell(row=row_idx, column=3).font = WHITE_FONT

        for col_idx, moic in enumerate(moic_row, 4):
            cell = ws.cell(row=row_idx, column=col_idx, value=moic)
            cell.number_format = '0.0"x"'
            cell.alignment = Alignment(horizontal='center')
            if moic >= 3.0:
                cell.fill = TOP_QUARTILE
            elif moic >= 2.5:
                cell.fill = THIRD_QUARTILE
            elif moic >= 2.0:
                cell.fill = SECOND_QUARTILE
            else:
                cell.fill = BOTTOM_QUARTILE

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "22_sensitivity_table.xlsx")
    print("Created: 22_sensitivity_table.xlsx")


# =============================================================================
# Template 23: Debt Schedule with Credit Metrics
# =============================================================================
def create_debt_schedule():
    wb = Workbook()
    ws = wb.active
    ws.title = "Debt_Schedule"

    ws['B2'] = "DEBT SCHEDULE"
    ws['B2'].font = TITLE_FONT
    ws['B3'] = "$ in Millions"
    ws['B3'].font = SUBTITLE_FONT

    headers = ["", "Entry", "2025E", "2026E", "2027E", "2028E", "2029E"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=5, column=col, value=header)
    apply_header_style(ws, 5, 2, 8)

    # Senior Term Loan section
    ws['B6'] = "SENIOR TERM LOAN"
    ws['B6'].font = HEADER_FONT

    debt_data = [
        ("Beginning Balance", "", 108.0, 89.3, 79.3, 65.5, 45.6),
        ("(-) Mandatory Amortization", "", 0, 0, 0, 0, 0),
        ("(-) Cash Sweep Paydown", "", -18.7, -10.0, -13.8, -19.9, -25.1),
        ("Ending Balance", 108.0, 89.3, 79.3, 65.5, 45.6, 20.5),
    ]

    for row_idx, row_data in enumerate(debt_data, 7):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if isinstance(value, (int, float)) and value != "":
                cell.number_format = '$#,##0.0'
        if row_data[0] == "Ending Balance":
            for col in range(2, 9):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT

    # Credit Metrics section
    ws['B13'] = "CREDIT METRICS"
    ws['B13'].font = WHITE_FONT
    ws['B13'].fill = NAVY_BLUE
    ws.merge_cells('B13:H13')

    credit_data = [
        ("EBITDA", 19.5, 28.0, 32.0, 36.0, 40.0, 42.0),
        ("Leverage (Debt / EBITDA)", "5.5x", "3.2x", "2.5x", "1.8x", "1.1x", "0.5x"),
        ("Covenant (Max)", "6.0x", "6.0x", "6.0x", "6.0x", "6.0x", "6.0x"),
        ("Cushion", "0.5x", "2.8x", "3.5x", "4.2x", "4.9x", "5.5x"),
        ("Covenant Test", "PASS", "PASS", "PASS", "PASS", "PASS", "PASS"),
    ]

    for row_idx, row_data in enumerate(credit_data, 14):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if row_data[0] == "EBITDA" and isinstance(value, (int, float)):
                cell.number_format = '$#,##0.0'
            if value == "PASS":
                cell.fill = TOP_QUARTILE
                cell.font = Font(bold=True)
            elif value == "FAIL":
                cell.fill = BOTTOM_QUARTILE
                cell.font = Font(bold=True, color="FFFFFF")

    # Debt Paydown Summary
    ws['B21'] = "DEBT PAYDOWN SUMMARY"
    ws['B21'].font = HEADER_FONT
    ws['B22'] = "Entry Debt"
    ws['C22'] = 108.0
    ws['C22'].number_format = '$#,##0.0'
    ws['B23'] = "(-) Exit Debt"
    ws['C23'] = -20.5
    ws['C23'].number_format = '$#,##0.0'
    ws['B24'] = "Total Paydown"
    ws['C24'] = 87.5
    ws['C24'].number_format = '$#,##0.0'
    ws['C24'].font = HEADER_FONT
    ws['B25'] = "% Repaid"
    ws['C25'] = "81%"
    ws['C25'].font = Font(bold=True, color="00A651")

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "23_debt_schedule.xlsx")
    print("Created: 23_debt_schedule.xlsx")


# =============================================================================
# Template 25: Returns Analysis (Gross vs Net with Fee Waterfall)
# =============================================================================
def create_returns_analysis():
    wb = Workbook()
    ws = wb.active
    ws.title = "Returns_Analysis"

    ws['B2'] = "RETURNS ANALYSIS"
    ws['B2'].font = TITLE_FONT

    headers = ["", "Entry", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 8)

    # Entry section
    ws['B5'] = "ENTRY"
    ws['B5'].font = HEADER_FONT
    entry_data = [
        ("Sponsor Equity Invested ($M)", -97, "", "", "", "", ""),
        ("Exit EBITDA ($M)", "", "", "", "", "", 42.0),
        ("Exit Multiple (x)", "", "", "", "", "", "9.5x"),
        ("Exit Enterprise Value ($M)", "", "", "", "", "", 399),
        ("(-) Net Debt at Exit ($M)", "", "", "", "", "", -20),
        ("Exit Equity Value ($M)", "", "", "", "", "", 379),
        ("Sponsor Ownership at Exit", "", "", "", "", "", "91%"),
        ("Sponsor Proceeds ($M)", "", "", "", "", "", 345),
    ]

    for row_idx, row_data in enumerate(entry_data, 6):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if isinstance(value, (int, float)) and value != "":
                cell.number_format = '$#,##0'
        if row_data[0] in ["Exit Equity Value ($M)", "Sponsor Proceeds ($M)"]:
            ws.cell(row=row_idx, column=2).font = HEADER_FONT

    # Gross Returns
    ws['B16'] = "GROSS RETURNS"
    ws['B16'].font = WHITE_FONT
    ws['B16'].fill = NAVY_BLUE
    ws.merge_cells('B16:H16')

    ws['B17'] = "Cash Flow ($M)"
    ws['C17'] = -97
    ws['H17'] = 345
    ws['B18'] = "Gross MOIC (x)"
    ws['C18'] = "3.6x"
    ws['C18'].font = Font(bold=True, size=14, color="00A651")
    ws['B19'] = "Gross IRR (%)"
    ws['C19'] = "29%"
    ws['C19'].font = Font(bold=True, size=14, color="00A651")

    # Net Returns
    ws['B22'] = "NET RETURNS (After Fees)"
    ws['B22'].font = WHITE_FONT
    ws['B22'].fill = GREEN_FILL
    ws.merge_cells('B22:H22')

    net_data = [
        ("(-) Management Fees (2% x 5yr)", -9.7),
        ("Preferred Return (8% hurdle)", 51.3),
        ("Profits Above Hurdle", 186.7),
        ("(-) Carried Interest (20%)", -37.3),
        ("Net Proceeds to LP ($M)", 298.0),
    ]

    for row_idx, row_data in enumerate(net_data, 23):
        ws.cell(row=row_idx, column=2, value=row_data[0])
        cell = ws.cell(row=row_idx, column=3, value=row_data[1])
        cell.number_format = '$#,##0.0'
        if row_data[0] == "Net Proceeds to LP ($M)":
            cell.font = HEADER_FONT

    ws['B29'] = "Net MOIC (x)"
    ws['C29'] = "3.1x"
    ws['C29'].font = Font(bold=True, size=14, color="01395D")
    ws['B30'] = "Net IRR (%)"
    ws['C30'] = "25%"
    ws['C30'].font = Font(bold=True, size=14, color="01395D")

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "25_returns_analysis.xlsx")
    print("Created: 25_returns_analysis.xlsx")


# =============================================================================
# Remaining templates (simplified versions)
# =============================================================================

def create_before_after():
    wb = Workbook()
    ws = wb.active
    ws.title = "Before_After"

    ws['B2'] = "Value-Add Analysis"
    ws['B2'].font = TITLE_FONT

    headers = ["Metric", "Before", "After", "Change %", "Change $"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 6)

    data = [
        ("Revenue", 2780, 5087, 0.83, 2307),
        ("Rent per Unit", 2780, 3395, 0.22, 615),
        ("Care Revenue", 0, 1692, None, 1692),
        ("Occupancy", 0.85, 0.94, 0.11, 0.09),
        ("NOI Margin", 0.35, 0.42, 0.20, 0.07),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [3, 4, 6] and isinstance(value, (int, float)) and value and value > 100:
                cell.number_format = '$#,##0'
            elif col_idx == 5 and value:
                cell.number_format = '0%'

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "06_before_after.xlsx")
    print("Created: 06_before_after.xlsx")


def create_horizontal_bar_pie():
    wb = Workbook()
    ws = wb.active
    ws.title = "Rankings"

    ws['B2'] = "Market Ranking Analysis"
    ws['B2'].font = TITLE_FONT

    headers = ["Category", "Value", "Annotation", "Is_Subject"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 5)

    data = [
        ("Market A", 0.237, "#1 in Region", False),
        ("Market B", 0.213, "", False),
        ("Market C", 0.195, "", True),
        ("Market D", 0.183, "#1 in Province", False),
        ("Market E", 0.172, "", False),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 3:
                cell.number_format = '0.0%'
        if row_data[3]:  # Is_Subject
            for col in range(2, 6):
                ws.cell(row=row_idx, column=col).fill = LIGHT_GREEN_FILL

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "09_horizontal_bar_pie.xlsx")
    print("Created: 09_horizontal_bar_pie.xlsx")


def create_gantt_chart():
    wb = Workbook()
    ws = wb.active
    ws.title = "Timeline"

    ws['B2'] = "Transaction Timeline"
    ws['B2'].font = TITLE_FONT

    headers = ["Workstream", "Start", "End", "Duration (Weeks)", "Is_Milestone"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 6)

    from datetime import date
    data = [
        ("Planning", date(2025, 1, 1), date(2025, 3, 31), 13, False),
        ("Due Diligence", date(2025, 2, 1), date(2025, 5, 31), 17, False),
        ("Financing", date(2025, 4, 1), date(2025, 6, 30), 13, False),
        ("Documentation", date(2025, 5, 1), date(2025, 7, 31), 13, False),
        ("Closing", date(2025, 8, 1), date(2025, 8, 1), 0, True),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            ws.cell(row=row_idx, column=col_idx, value=value)
        if row_data[4]:  # Is_Milestone
            for col in range(2, 7):
                ws.cell(row=row_idx, column=col).fill = GREEN_FILL
                ws.cell(row=row_idx, column=col).font = WHITE_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "10_gantt_chart.xlsx")
    print("Created: 10_gantt_chart.xlsx")


def create_portfolio_valuations():
    wb = Workbook()
    ws = wb.active
    ws.title = "Portfolio_Valuations"

    ws['B2'] = "Portfolio Company Summary"
    ws['B2'].font = TITLE_FONT

    headers = ["Company", "Invested ($M)", "Current MOIC", "Current IRR", "Exit Date", "Exit MOIC Range", "Exit IRR Range"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 8)

    data = [
        ("Company A", 28.6, "2.0x", "39.7%", "H1'27", "2.5-3.0x", "28-34%"),
        ("Company B", 27.2, "1.6x", "87.5%", "2028", "2.5-3.0x", "26-32%"),
        ("Company C", 42.1, "1.85x", "25.3%", "H2'26", "2.2-2.8x", "22-28%"),
        ("Company D", 35.5, "1.45x", "18.5%", "2027", "2.0-2.5x", "20-25%"),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 3:
                cell.number_format = '$#,##0.0'

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "12_portfolio_valuations.xlsx")
    print("Created: 12_portfolio_valuations.xlsx")


def create_debt_benchmarking():
    wb = Workbook()
    ws = wb.active
    ws.title = "Debt_Benchmarking"

    ws['B2'] = "Debt Structure Comparison"
    ws['B2'].font = TITLE_FONT

    headers = ["Debt Type", "Company A ($M)", "% Total", "Company B ($M)", "% Total", "Subject ($M)", "% Total"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 8)

    data = [
        ("Senior Term Loan", 150, 0.60, 200, 0.67, 108, 0.50),
        ("Revolver", 25, 0.10, 30, 0.10, 0, 0),
        ("Subordinated Debt", 75, 0.30, 70, 0.23, 0, 0),
        ("Total Debt", 250, 1.00, 300, 1.00, 108, 0.50),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [3, 5, 7] and isinstance(value, (int, float)):
                cell.number_format = '$#,##0'
            elif col_idx in [4, 6, 8]:
                cell.number_format = '0%'
        if row_data[0] == "Total Debt":
            for col in range(2, 9):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "14_debt_benchmarking.xlsx")
    print("Created: 14_debt_benchmarking.xlsx")


def create_track_record():
    wb = Workbook()
    ws = wb.active
    ws.title = "Track_Record"

    ws['B2'] = "Historical FFO Per Unit"
    ws['B2'].font = TITLE_FONT

    headers = ["Year", "FFO/Unit", "Distribution"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 4)

    years = list(range(2015, 2026))
    ffo = [1.20, 1.35, 1.52, 1.71, 1.92, 2.10, 2.28, 2.48, 2.65, 2.85, 3.10]
    dist = [1.00, 1.12, 1.26, 1.42, 1.60, 1.75, 1.90, 2.07, 2.21, 2.38, 2.58]

    for i, (y, f, d) in enumerate(zip(years, ffo, dist)):
        ws.cell(row=i+5, column=2, value=y)
        cell_ffo = ws.cell(row=i+5, column=3, value=f)
        cell_ffo.number_format = '$#,##0.00'
        cell_dist = ws.cell(row=i+5, column=4, value=d)
        cell_dist.number_format = '$#,##0.00'

    # Summary
    ws['F4'] = "CAGR"
    ws['F4'].font = HEADER_FONT
    ws['F5'] = "10.0%"
    ws['F5'].fill = GREEN_FILL
    ws['F5'].font = Font(bold=True, color="FFFFFF", size=16)

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "17_track_record.xlsx")
    print("Created: 17_track_record.xlsx")


def create_deal_showcase():
    wb = Workbook()
    ws = wb.active
    ws.title = "Deal_Showcase"

    ws['B2'] = "Recent Transactions"
    ws['B2'].font = TITLE_FONT

    headers = ["Deal", "Sector", "Type", "EV ($M)", "Close Date"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 6)

    data = [
        ("Deal A", "Midstream", "Value-based", 9100, "Jul 2025"),
        ("Deal B", "Data", "Platform", 6900, "Sep 2025"),
        ("Deal C", "Transport", "Partnership", 5300, "Q1 2026"),
        ("Deal D", "Utilities", "Carve-out", 1000, "Q4 2025"),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 5:
                cell.number_format = '$#,##0'

    # Total
    ws['B10'] = "TOTAL"
    ws['B10'].font = HEADER_FONT
    ws['E10'] = "=SUM(E5:E8)"
    ws['E10'].number_format = '$#,##0'
    ws['E10'].font = HEADER_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "27_deal_showcase.xlsx")
    print("Created: 27_deal_showcase.xlsx")


def create_cost_of_capital():
    wb = Workbook()
    ws = wb.active
    ws.title = "Cost_of_Capital"

    ws['B2'] = "Cost of Capital Spectrum"
    ws['B2'].font = TITLE_FONT

    headers = ["Funding Source", "Cost Low", "Cost High", "Constraints", "Position"]
    for col, header in enumerate(headers, 2):
        ws.cell(row=4, column=col, value=header)
    apply_header_style(ws, 4, 2, 6)

    data = [
        ("Corporate Debt", 0.035, 0.045, "BBB+ rating limit", 1),
        ("Preferred Equity", 0.055, 0.065, "-", 2),
        ("Asset Sales", 0.09, 0.11, "Target range", 3),
        ("Common Equity", 0.12, 0.15, "Dilution concerns", 4),
    ]

    for row_idx, row_data in enumerate(data, 5):
        for col_idx, value in enumerate(row_data, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [3, 4]:
                cell.number_format = '0.0%'
        if row_data[0] == "Asset Sales":
            for col in range(2, 7):
                ws.cell(row=row_idx, column=col).fill = GREEN_FILL
                ws.cell(row=row_idx, column=col).font = WHITE_FONT

    auto_column_width(ws)
    wb.save(OUTPUT_DIR / "28_cost_of_capital.xlsx")
    print("Created: 28_cost_of_capital.xlsx")


# =============================================================================
# Main execution
# =============================================================================
def main():
    print(f"Generating Excel templates in: {OUTPUT_DIR}")
    print("-" * 60)

    # Professional templates based on BCI/Northleaf
    create_peer_benchmarking()          # Template 3 - SaaS benchmarking with quartiles
    create_comps_table()                # Template 4 - Trading comps
    create_time_series()                # Template 5 - Price performance
    create_before_after()               # Template 6 - Value-add
    create_sources_uses()               # Template 7 - S&U
    create_scenario_analysis()          # Template 8 - Bull/Base/Bear
    create_horizontal_bar_pie()         # Template 9 - Rankings
    create_gantt_chart()                # Template 10 - Timeline
    create_heat_map()                   # Template 11 - Returns matrix
    create_portfolio_valuations()       # Template 12 - Portfolio summary
    create_debt_benchmarking()          # Template 14 - Debt comparison
    create_precedent_transactions()     # Template 16 - M&A precedents
    create_track_record()               # Template 17 - Historical performance
    create_value_creation_waterfall()   # Template 19 - MOIC/IRR bridge
    create_sensitivity_table()          # Template 22 - Entry vs Exit matrix
    create_debt_schedule()              # Template 23 - Debt with credit metrics
    create_returns_analysis()           # Template 25 - Gross vs Net returns
    create_deal_showcase()              # Template 27 - Transaction highlights
    create_cost_of_capital()            # Template 28 - Funding spectrum

    print("-" * 60)
    print("All professional templates created successfully!")
    print("\nFormatting based on:")
    print("  - BCI 2026 Case Study (Growth Equity/SaaS)")
    print("  - Northleaf 2026 Model (LBO)")


if __name__ == "__main__":
    main()
