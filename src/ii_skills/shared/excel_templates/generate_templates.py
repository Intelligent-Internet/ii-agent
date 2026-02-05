"""
Generate Excel backup templates for slide generation.
Creates 18 template files with sample data and charts.
"""

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.chart import BarChart, LineChart, PieChart, Reference
from openpyxl.chart.series import DataPoint
from openpyxl.chart.label import DataLabelList
from openpyxl.utils import get_column_letter
from pathlib import Path

# Color constants
GREEN_FILL = PatternFill(start_color="00A651", end_color="00A651", fill_type="solid")
GRAY_FILL = PatternFill(start_color="4A4A4A", end_color="4A4A4A", fill_type="solid")
LIGHT_GRAY_FILL = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
WHITE_FONT = Font(color="FFFFFF", bold=True)
HEADER_FONT = Font(bold=True)
THIN_BORDER = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)

OUTPUT_DIR = Path(__file__).parent


def style_header_row(ws, row=1, max_col=None):
    """Apply header styling to first row."""
    if max_col is None:
        max_col = ws.max_column
    for col in range(1, max_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = GRAY_FILL
        cell.font = WHITE_FONT
        cell.alignment = Alignment(horizontal='center')


def style_data_rows(ws, start_row=2, max_row=None, max_col=None):
    """Apply alternating row styling."""
    if max_row is None:
        max_row = ws.max_row
    if max_col is None:
        max_col = ws.max_column
    for row in range(start_row, max_row + 1):
        for col in range(1, max_col + 1):
            cell = ws.cell(row=row, column=col)
            cell.border = THIN_BORDER
            if row % 2 == 0:
                cell.fill = LIGHT_GRAY_FILL


def auto_column_width(ws):
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
        adjusted_width = min(max_length + 2, 30)
        ws.column_dimensions[column_letter].width = adjusted_width


# =============================================================================
# Template 3: Peer Benchmarking
# =============================================================================
def create_peer_benchmarking():
    wb = Workbook()
    ws = wb.active
    ws.title = "Peer_Benchmarking"

    # Headers
    headers = ["Company", "Logo_Path", "Metric_Value", "Is_Subject"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)

    # Sample data
    data = [
        ("Peer A", "logos/peer_a.png", 23.8, False),
        ("Peer B", "logos/peer_b.png", 22.4, False),
        ("Peer C", "logos/peer_c.png", 20.2, False),
        ("Subject Company", "logos/subject.png", 18.2, True),
        ("Peer D", "logos/peer_d.png", 16.7, False),
        ("Peer E", "logos/peer_e.png", 13.8, False),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    style_header_row(ws)
    style_data_rows(ws)
    auto_column_width(ws)

    # Create bar chart
    chart = BarChart()
    chart.type = "bar"
    chart.style = 10
    chart.title = "Peer Benchmarking"
    chart.y_axis.title = "Multiple (x)"

    data_ref = Reference(ws, min_col=3, min_row=1, max_row=7)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=7)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)
    chart.shape = 4

    ws.add_chart(chart, "F2")

    # Instructions sheet
    ws2 = wb.create_sheet("Instructions")
    ws2['A1'] = "PEER BENCHMARKING TEMPLATE"
    ws2['A1'].font = Font(bold=True, size=14)
    ws2['A3'] = "Columns:"
    ws2['A4'] = "- Company: Peer company name"
    ws2['A5'] = "- Logo_Path: Optional path to company logo"
    ws2['A6'] = "- Metric_Value: The metric being compared (multiple, %, etc.)"
    ws2['A7'] = "- Is_Subject: TRUE for your company (will be highlighted green)"
    ws2['A9'] = "Chart will show horizontal bars sorted by value."
    ws2['A10'] = "Subject company bar will be green, peers gray."

    wb.save(OUTPUT_DIR / "03_peer_benchmarking.xlsx")
    print("Created: 03_peer_benchmarking.xlsx")


# =============================================================================
# Template 4: Comps Table
# =============================================================================
def create_comps_table():
    wb = Workbook()
    ws = wb.active
    ws.title = "Trading_Comps"

    headers = ["Company", "Ticker", "Price", "Mkt_Cap_M", "EV_M", "PE_CY", "PE_NY", "EV_EBITDA_CY", "EV_EBITDA_NY", "Is_Subject"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)

    data = [
        ("Peer A", "PEER.TO", 45.50, 2450, 3100, 18.5, 16.2, 12.3, 11.1, False),
        ("Peer B", "PB.TO", 32.25, 1890, 2350, 21.2, 18.7, 14.1, 12.8, False),
        ("Peer C", "PC.TO", 58.75, 3200, 4100, 19.8, 17.5, 13.2, 11.9, False),
        ("Subject Co", "SUBJ.TO", 28.00, 1450, 1850, 15.8, 14.1, 10.5, 9.8, True),
        ("Peer D", "PD.TO", 41.20, 2100, 2800, 17.2, 15.3, 11.8, 10.5, False),
        ("Average", "-", None, None, None, 18.5, 16.4, 12.4, 11.2, False),
        ("Median", "-", None, None, None, 18.5, 16.2, 12.3, 11.1, False),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [3] and value:  # Price column
                cell.number_format = '$#,##0.00'
            elif col_idx in [4, 5] and value:  # Market cap, EV
                cell.number_format = '#,##0'
            elif col_idx in [6, 7, 8, 9] and value:  # Multiples
                cell.number_format = '0.0"x"'

    style_header_row(ws)
    style_data_rows(ws)

    # Highlight subject row
    for col in range(1, 11):
        ws.cell(row=5, column=col).fill = GREEN_FILL
        ws.cell(row=5, column=col).font = WHITE_FONT

    auto_column_width(ws)

    # Instructions
    ws2 = wb.create_sheet("Instructions")
    ws2['A1'] = "TRADING COMPS TABLE TEMPLATE"
    ws2['A1'].font = Font(bold=True, size=14)
    ws2['A3'] = "Add peer companies with their trading multiples."
    ws2['A4'] = "Set Is_Subject=TRUE for your company (row will be highlighted green)."
    ws2['A5'] = "Include Average and Median rows at the bottom."

    wb.save(OUTPUT_DIR / "04_comps_table.xlsx")
    print("Created: 04_comps_table.xlsx")


# =============================================================================
# Template 5: Time Series
# =============================================================================
def create_time_series():
    wb = Workbook()
    ws = wb.active
    ws.title = "Time_Series"

    headers = ["Date", "Subject", "Benchmark_1", "Benchmark_2"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)

    from datetime import date, timedelta
    base_date = date(2024, 1, 1)
    subject_values = [100, 105.2, 108.7, 112.3, 118.5, 115.2, 122.8, 128.5, 135.2, 142.1, 138.5, 145.2]
    bench1_values = [100, 102.8, 104.2, 107.5, 110.2, 108.5, 112.3, 115.8, 118.2, 122.5, 120.8, 125.1]
    bench2_values = [100, 101.5, 103.8, 106.2, 108.5, 107.2, 110.5, 113.2, 116.8, 119.5, 118.2, 121.5]

    for i, (subj, b1, b2) in enumerate(zip(subject_values, bench1_values, bench2_values)):
        row = i + 2
        ws.cell(row=row, column=1, value=base_date + timedelta(days=i*30))
        ws.cell(row=row, column=2, value=subj)
        ws.cell(row=row, column=3, value=b1)
        ws.cell(row=row, column=4, value=b2)

    style_header_row(ws)
    auto_column_width(ws)

    # Create line chart
    chart = LineChart()
    chart.title = "Performance Comparison"
    chart.style = 10
    chart.y_axis.title = "Indexed Value"
    chart.x_axis.title = "Date"

    data_ref = Reference(ws, min_col=2, max_col=4, min_row=1, max_row=13)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=13)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)

    ws.add_chart(chart, "F2")

    # Summary table
    ws['F16'] = "Summary"
    ws['F16'].font = HEADER_FONT
    ws['F17'] = "Metric"
    ws['G17'] = "Subject"
    ws['H17'] = "Benchmark 1"
    ws['I17'] = "Benchmark 2"
    ws['F18'] = "Cumulative Return"
    ws['G18'] = "45.2%"
    ws['H18'] = "25.1%"
    ws['I18'] = "21.5%"

    wb.save(OUTPUT_DIR / "05_time_series.xlsx")
    print("Created: 05_time_series.xlsx")


# =============================================================================
# Template 6: Before/After
# =============================================================================
def create_before_after():
    wb = Workbook()
    ws = wb.active
    ws.title = "Before_After"

    headers = ["Metric", "Before_Value", "After_Value", "Change_Pct", "Change_Abs"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)

    data = [
        ("Revenue", 2780, 5087, 0.83, 2307),
        ("Rent per Unit", 2780, 3395, 0.22, 615),
        ("Care Revenue", 0, 1692, None, 1692),
        ("Occupancy", 0.85, 0.94, 0.11, 0.09),
        ("NOI Margin", 0.35, 0.42, 0.20, 0.07),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [2, 3, 5] and value and row_idx <= 4:
                cell.number_format = '$#,##0'
            elif col_idx == 4 and value:
                cell.number_format = '0%'

    style_header_row(ws)
    style_data_rows(ws)
    auto_column_width(ws)

    # KPI Summary section
    ws['G1'] = "KPI Summary"
    ws['G1'].font = Font(bold=True, size=12)
    ws['G2'] = "Cost"
    ws['H2'] = "$5,000"
    ws['G3'] = "Uplift"
    ws['H3'] = "+$400/month"
    ws['G4'] = "Payback"
    ws['H4'] = "1 Year"
    ws['G5'] = "ROI"
    ws['H5'] = "96%"

    wb.save(OUTPUT_DIR / "06_before_after.xlsx")
    print("Created: 06_before_after.xlsx")


# =============================================================================
# Template 7: Sources & Uses
# =============================================================================
def create_sources_uses():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sources_Uses"

    # Sources section
    ws['A1'] = "SOURCES"
    ws['A1'].font = Font(bold=True, size=12)
    ws['A1'].fill = GRAY_FILL
    ws['A1'].font = WHITE_FONT

    headers = ["Source_Item", "Low_Case", "Mid_Case", "High_Case"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=2, column=col, value=header)
    style_header_row(ws, row=2, max_col=4)

    sources = [
        ("Equity Issue", 125, 138, 150),
        ("Retained Interest", 142, 150, 157),
        ("Portfolio Debt", 282, 282, 282),
        ("Total Sources", 549, 569, 589),
    ]

    for row_idx, row_data in enumerate(sources, 3):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx > 1:
                cell.number_format = '$#,##0'
        if row_data[0] == "Total Sources":
            for col in range(1, 5):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT

    # Uses section
    ws['A8'] = "USES"
    ws['A8'].font = WHITE_FONT
    ws['A8'].fill = GRAY_FILL

    for col, header in enumerate(headers, 1):
        ws.cell(row=9, column=col, value=header.replace("Source", "Use"))
    style_header_row(ws, row=9, max_col=4)

    uses = [
        ("Purchase Price", 488, 507, 526),
        ("Transaction Costs", 14, 14, 15),
        ("Debt Repayment", 47, 47, 47),
        ("Total Uses", 549, 569, 589),
    ]

    for row_idx, row_data in enumerate(uses, 10):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx > 1:
                cell.number_format = '$#,##0'
        if row_data[0] == "Total Uses":
            for col in range(1, 5):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT

    # Valuation Summary
    ws['F1'] = "VALUATION SUMMARY"
    ws['F1'].font = WHITE_FONT
    ws['F1'].fill = GREEN_FILL

    val_headers = ["Metric", "Low", "Mid", "High"]
    for col, header in enumerate(val_headers, 6):
        ws.cell(row=2, column=col, value=header)

    valuation = [
        ("AFFO", 22.0, 22.0, 22.0),
        ("Multiple", "13.5x", "14.5x", "15.5x"),
        ("Equity Value", 297, 319, 341),
        ("+ Net Debt", 234, 234, 234),
        ("= Enterprise Value", 502, 521, 541),
    ]

    for row_idx, row_data in enumerate(valuation, 3):
        for col_idx, value in enumerate(row_data, 6):
            ws.cell(row=row_idx, column=col_idx, value=value)

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "07_sources_uses.xlsx")
    print("Created: 07_sources_uses.xlsx")


# =============================================================================
# Template 8: Scenario Analysis
# =============================================================================
def create_scenario_analysis():
    wb = Workbook()
    ws = wb.active
    ws.title = "Scenario_Analysis"

    # Assumptions
    ws['A1'] = "ASSUMPTIONS"
    ws['A1'].font = WHITE_FONT
    ws['A1'].fill = GRAY_FILL

    headers = ["Assumption", "Bear_Case", "Base_Case", "Bull_Case"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=2, column=col, value=header)
    style_header_row(ws, row=2, max_col=4)

    assumptions = [
        ("Revenue Growth", "2.0%", "5.0%", "8.0%"),
        ("EBITDA Margin", "18.0%", "22.0%", "25.0%"),
        ("Exit Multiple", "8.0x", "10.0x", "12.0x"),
        ("Debt Paydown", "50%", "75%", "100%"),
        ("Hold Period (Years)", 5, 5, 5),
    ]

    for row_idx, row_data in enumerate(assumptions, 3):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Outputs
    ws['A10'] = "OUTPUTS"
    ws['A10'].font = WHITE_FONT
    ws['A10'].fill = GREEN_FILL

    for col, header in enumerate(["Output_Metric", "Bear_Case", "Base_Case", "Bull_Case"], 1):
        ws.cell(row=11, column=col, value=header)
    style_header_row(ws, row=11, max_col=4)

    outputs = [
        ("Exit EV ($M)", 850, 1200, 1650),
        ("Equity Value ($M)", 520, 780, 1150),
        ("IRR", "12.5%", "18.5%", "24.0%"),
        ("MOIC", "1.8x", "2.4x", "3.2x"),
    ]

    for row_idx, row_data in enumerate(outputs, 12):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Probability weighting
    ws['F1'] = "PROBABILITY WEIGHTING"
    ws['F1'].font = HEADER_FONT
    ws['F2'] = "Scenario"
    ws['G2'] = "Probability"
    ws['H2'] = "Weighted IRR"
    ws['F3'] = "Bear"
    ws['G3'] = "25%"
    ws['H3'] = "3.1%"
    ws['F4'] = "Base"
    ws['G4'] = "50%"
    ws['H4'] = "9.3%"
    ws['F5'] = "Bull"
    ws['G5'] = "25%"
    ws['H5'] = "6.0%"
    ws['F6'] = "Expected"
    ws['G6'] = "100%"
    ws['H6'] = "18.4%"
    ws['F6'].font = HEADER_FONT
    ws['H6'].font = HEADER_FONT

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "08_scenario_analysis.xlsx")
    print("Created: 08_scenario_analysis.xlsx")


# =============================================================================
# Template 9: Horizontal Bar + Pie
# =============================================================================
def create_horizontal_bar_pie():
    wb = Workbook()
    ws = wb.active
    ws.title = "Rankings"

    # Bar chart data
    ws['A1'] = "BAR CHART DATA"
    ws['A1'].font = HEADER_FONT

    headers = ["Category", "Value", "Annotation", "Is_Subject"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=2, column=col, value=header)
    style_header_row(ws, row=2, max_col=4)

    bar_data = [
        ("City A", 23.7, "#1 in Region", False),
        ("City B", 21.3, "", False),
        ("City C", 19.5, "", True),
        ("City D", 18.3, "#1 in Province", False),
        ("City E", 18.3, "", False),
        ("City F", 17.3, "", False),
        ("City G", 16.9, "", False),
        ("City H", 16.9, "#4 in Ontario", False),
        ("City I", 16.5, "", False),
    ]

    for row_idx, row_data in enumerate(bar_data, 3):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 2:
                cell.number_format = '0.0%'

    # Pie chart data
    ws['F1'] = "PIE CHART DATA"
    ws['F1'].font = HEADER_FONT
    ws['F2'] = "Segment"
    ws['G2'] = "Percentage"
    style_header_row(ws, row=2, max_col=7)

    pie_data = [
        ("Top Markets", 0.15),
        ("Other Markets", 0.85),
    ]

    for row_idx, row_data in enumerate(pie_data, 3):
        ws.cell(row=row_idx, column=6, value=row_data[0])
        cell = ws.cell(row=row_idx, column=7, value=row_data[1])
        cell.number_format = '0%'

    # Create bar chart
    chart = BarChart()
    chart.type = "bar"
    chart.style = 10
    chart.title = "Market Ranking"

    data_ref = Reference(ws, min_col=2, min_row=2, max_row=11)
    cats_ref = Reference(ws, min_col=1, min_row=3, max_row=11)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)

    ws.add_chart(chart, "A14")

    # Create pie chart
    pie = PieChart()
    pie.title = "Exposure Breakdown"
    data_ref = Reference(ws, min_col=7, min_row=2, max_row=4)
    cats_ref = Reference(ws, min_col=6, min_row=3, max_row=4)
    pie.add_data(data_ref, titles_from_data=True)
    pie.set_categories(cats_ref)

    ws.add_chart(pie, "I14")

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "09_horizontal_bar_pie.xlsx")
    print("Created: 09_horizontal_bar_pie.xlsx")


# =============================================================================
# Template 10: Gantt Chart
# =============================================================================
def create_gantt_chart():
    wb = Workbook()
    ws = wb.active
    ws.title = "Timeline"

    headers = ["Workstream", "Start_Date", "End_Date", "Duration_Weeks", "Is_Milestone"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    from datetime import date
    data = [
        ("Planning", date(2025, 1, 1), date(2025, 3, 31), 13, False),
        ("Appraisals", date(2025, 1, 15), date(2025, 6, 30), 24, False),
        ("Due Diligence", date(2025, 4, 1), date(2025, 9, 30), 26, False),
        ("Structuring", date(2025, 6, 1), date(2025, 9, 30), 17, False),
        ("Prospectus", date(2025, 8, 1), date(2025, 11, 30), 17, False),
        ("Marketing", date(2025, 10, 1), date(2025, 11, 30), 9, False),
        ("Filing", date(2025, 10, 15), date(2025, 11, 15), 4, False),
        ("Launch", date(2025, 12, 1), date(2025, 12, 1), 0, True),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Milestones section
    ws['G1'] = "MILESTONES"
    ws['G1'].font = HEADER_FONT
    ws['G2'] = "Milestone_Name"
    ws['H2'] = "Target_Date"
    ws['I2'] = "Description"
    style_header_row(ws, row=2, max_col=9)

    milestones = [
        ("Board Approval", date(2025, 3, 15), "Internal approval"),
        ("Prospectus Filed", date(2025, 10, 15), "Regulatory filing"),
        ("IPO Launch", date(2025, 12, 1), "Market debut"),
    ]

    for row_idx, row_data in enumerate(milestones, 3):
        ws.cell(row=row_idx, column=7, value=row_data[0])
        ws.cell(row=row_idx, column=8, value=row_data[1])
        ws.cell(row=row_idx, column=9, value=row_data[2])

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "10_gantt_chart.xlsx")
    print("Created: 10_gantt_chart.xlsx")


# =============================================================================
# Template 11: Heat Map
# =============================================================================
def create_heat_map():
    wb = Workbook()
    ws = wb.active
    ws.title = "Heat_Map"

    headers = ["Strategy", "2020", "2021", "2022", "2023", "2024", "5_Yr_IRR"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Strategy A", 0.171, 0.213, 0.314, 0.130, 0.124, 0.158),
        ("Strategy B", 0.149, 0.188, 0.203, 0.125, 0.108, 0.154),
        ("Strategy C", 0.071, -0.028, 0.121, 0.080, -0.082, 0.079),
        ("Strategy D", 0.185, 0.156, 0.178, 0.142, 0.135, 0.159),
        ("Strategy E", 0.098, 0.112, 0.145, 0.095, 0.088, 0.107),
    ]

    # Color fills for heat map
    dark_green = PatternFill(start_color="006400", end_color="006400", fill_type="solid")
    green = PatternFill(start_color="00A651", end_color="00A651", fill_type="solid")
    light_green = PatternFill(start_color="90EE90", end_color="90EE90", fill_type="solid")
    red = PatternFill(start_color="C00000", end_color="C00000", fill_type="solid")

    for row_idx, row_data in enumerate(data, 2):
        ws.cell(row=row_idx, column=1, value=row_data[0])
        for col_idx, value in enumerate(row_data[1:], 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            cell.number_format = '0.0%'
            # Apply conditional color
            if value > 0.20:
                cell.fill = dark_green
                cell.font = Font(color="FFFFFF")
            elif value > 0.10:
                cell.fill = green
                cell.font = Font(color="FFFFFF")
            elif value > 0:
                cell.fill = light_green
            else:
                cell.fill = red
                cell.font = Font(color="FFFFFF")

    auto_column_width(ws)

    # Legend
    ws['I1'] = "COLOR LEGEND"
    ws['I1'].font = HEADER_FONT
    ws['I2'] = "> 20%"
    ws['J2'] = "Dark Green"
    ws['I3'] = "10-20%"
    ws['J3'] = "Green"
    ws['I4'] = "0-10%"
    ws['J4'] = "Light Green"
    ws['I5'] = "< 0%"
    ws['J5'] = "Red"

    wb.save(OUTPUT_DIR / "11_heat_map.xlsx")
    print("Created: 11_heat_map.xlsx")


# =============================================================================
# Template 12: Portfolio Valuations
# =============================================================================
def create_portfolio_valuations():
    wb = Workbook()
    ws = wb.active
    ws.title = "Portfolio_Valuations"

    headers = ["Company", "Logo_Path", "Invested_M", "Current_MOIC", "Current_IRR",
               "Exit_Date", "Exit_MOIC_Low", "Exit_MOIC_High", "Exit_IRR_Low", "Exit_IRR_High"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Company A", "logos/a.png", 28.6, 2.00, 0.397, "H1'27", 2.5, 3.0, 0.28, 0.34),
        ("Company B", "logos/b.png", 27.2, 1.60, 0.875, "2028", 2.5, 3.0, 0.26, 0.32),
        ("Company C", "logos/c.png", 42.1, 1.85, 0.253, "H2'26", 2.2, 2.8, 0.22, 0.28),
        ("Company D", "logos/d.png", 35.5, 1.45, 0.185, "2027", 2.0, 2.5, 0.20, 0.25),
        ("Company E", "logos/e.png", 22.8, 2.25, 0.425, "H1'26", 2.8, 3.5, 0.30, 0.38),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 3:
                cell.number_format = '$#,##0.0"M"'
            elif col_idx in [4, 7, 8]:
                cell.number_format = '0.00"x"'
            elif col_idx in [5, 9, 10]:
                cell.number_format = '0.0%'

    style_data_rows(ws)
    auto_column_width(ws)

    # Summary row
    ws['A8'] = "PORTFOLIO TOTAL"
    ws['A8'].font = HEADER_FONT
    ws['C8'] = "=SUM(C2:C6)"
    ws['C8'].number_format = '$#,##0.0"M"'

    wb.save(OUTPUT_DIR / "12_portfolio_valuations.xlsx")
    print("Created: 12_portfolio_valuations.xlsx")


# =============================================================================
# Template 14: Debt Benchmarking
# =============================================================================
def create_debt_benchmarking():
    wb = Workbook()
    ws = wb.active
    ws.title = "Debt_Benchmarking"

    headers = ["Debt_Type", "Company_A_Value", "Company_A_Pct", "Company_B_Value", "Company_B_Pct",
               "Subject_Value", "Subject_Pct"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("CMHC Insured", 1631, 0.496, 598, 0.471, 30, 0.127),
        ("Non-CMHC Insured", 358, 0.109, 189, 0.149, 205, 0.873),
        ("Unsecured Debt", 950, 0.289, 450, 0.354, None, None),
        ("Term Loan", 149, 0.045, None, None, None, None),
        ("Credit Facility", 190, 0.058, 30, 0.024, None, None),
        ("Total Debt", 3286, 1.0, 1270, 1.0, 234, 1.0),
        ("Credit Capacity", 400, 0.122, 309, 0.243, 65, 0.277),
        ("Undrawn Capacity", 210, 0.064, 309, 0.243, 65, 0.277),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [2, 4, 6] and value:
                cell.number_format = '$#,##0'
            elif col_idx in [3, 5, 7] and value:
                cell.number_format = '0.0%'
        if row_data[0] == "Total Debt":
            for col in range(1, 8):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT

    style_data_rows(ws)
    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "14_debt_benchmarking.xlsx")
    print("Created: 14_debt_benchmarking.xlsx")


# =============================================================================
# Template 16: 4-Quadrant Achievement
# =============================================================================
def create_achievement_summary():
    wb = Workbook()
    ws = wb.active
    ws.title = "Achievement_Summary"

    headers = ["Quadrant", "Title", "Subtitle", "Target", "Actual", "Status"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        (1, "Executed strategic", "priorities", "4 initiatives", "4 completed", "Achieved"),
        (2, "Delivered record", "financial results", "$3.20 FFO", "$3.32 FFO", "Achieved"),
        (3, "Maintained strong", "balance sheet", "BBB+ rating", "BBB+ rating", "Achieved"),
        (4, "Advanced ESG", "priorities", "3 goals", "3 goals", "Achieved"),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 6:
                if value == "Achieved":
                    cell.fill = GREEN_FILL
                    cell.font = WHITE_FONT

    style_data_rows(ws)
    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "16_achievement_summary.xlsx")
    print("Created: 16_achievement_summary.xlsx")


# =============================================================================
# Template 17: Track Record CAGR
# =============================================================================
def create_track_record():
    wb = Workbook()
    ws = wb.active
    ws.title = "Track_Record"

    headers = ["Year", "FFO_Per_Unit", "Distribution"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    # Sample data showing growth from $0.42 to $3.32 over 16 years
    years = list(range(2009, 2026))
    ffo_values = [0.42, 0.51, 0.62, 0.75, 0.91, 1.10, 1.33, 1.61, 1.95, 2.10,
                  2.28, 2.48, 2.65, 2.82, 3.00, 3.15, 3.32]
    dist_values = [0.38, 0.45, 0.52, 0.62, 0.75, 0.90, 1.08, 1.30, 1.55, 1.65,
                   1.78, 1.92, 2.05, 2.15, 2.28, 2.38, 2.50]

    for i, (year, ffo, dist) in enumerate(zip(years, ffo_values, dist_values)):
        row = i + 2
        ws.cell(row=row, column=1, value=year)
        cell_ffo = ws.cell(row=row, column=2, value=ffo)
        cell_ffo.number_format = '$#,##0.00'
        cell_dist = ws.cell(row=row, column=3, value=dist)
        cell_dist.number_format = '$#,##0.00'

    # Summary metrics
    ws['E1'] = "SUMMARY METRICS"
    ws['E1'].font = HEADER_FONT
    ws['E2'] = "Start Value"
    ws['F2'] = "$0.42"
    ws['E3'] = "End Value"
    ws['F3'] = "$3.32"
    ws['E4'] = "CAGR"
    ws['F4'] = "14%"
    ws['F4'].fill = GREEN_FILL
    ws['F4'].font = WHITE_FONT
    ws['E5'] = "Period"
    ws['F5'] = "2009-2025"

    # Create line chart
    chart = LineChart()
    chart.title = "FFO Per Unit Track Record"
    chart.style = 10
    chart.y_axis.title = "FFO Per Unit ($)"
    chart.x_axis.title = "Year"

    data_ref = Reference(ws, min_col=2, min_row=1, max_row=18)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=18)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)

    ws.add_chart(chart, "E8")

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "17_track_record.xlsx")
    print("Created: 17_track_record.xlsx")


# =============================================================================
# Template 19: Exit Strategy Grid
# =============================================================================
def create_exit_summary():
    wb = Workbook()
    ws = wb.active
    ws.title = "Exit_Summary"

    headers = ["Transaction_Name", "Logo_Path", "Exit_Strategy", "Proceeds_M", "IRR", "MoC"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Deal A", "logos/a.png", "Full exit", 480, 0.17, 3.6),
        ("Deal B", "logos/b.png", "Partial sale", 430, 0.19, 7.5),
        ("Deal C", "logos/c.png", "Partial sale", 390, 0.18, 2.9),
        ("Deal D", "logos/d.png", "Staged exit", 580, 0.22, 3.8),
        ("Deal E", "logos/e.png", "Public market", 620, 0.25, 1.6),
        ("TOTAL", "-", "Various", 2500, 0.20, 4.0),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 4 and value:
                cell.number_format = '$#,##0"M"'
            elif col_idx == 5 and value:
                cell.number_format = '0%'
            elif col_idx == 6 and value:
                cell.number_format = '0.0"x"'
        if row_data[0] == "TOTAL":
            for col in range(1, 7):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT
                ws.cell(row=row_idx, column=col).fill = LIGHT_GRAY_FILL

    style_data_rows(ws, max_row=6)
    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "19_exit_summary.xlsx")
    print("Created: 19_exit_summary.xlsx")


# =============================================================================
# Template 22: Debt Maturity Profile
# =============================================================================
def create_debt_maturity():
    wb = Workbook()
    ws = wb.active
    ws.title = "Debt_Maturity"

    headers = ["Year", "Amount_B", "Facility_Type", "Rate"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        (2026, 0.3, "Corporate bonds", 0.045),
        (2027, 0.5, "Term loan", 0.052),
        (2028, 0.5, "Revolving credit", 0.055),
        (2029, 0.4, "Project finance", 0.048),
        ("2030+", 2.5, "Long-dated bonds", 0.050),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 2:
                cell.number_format = '$#,##0.0"B"'
            elif col_idx == 4:
                cell.number_format = '0.0%'

    # Summary metrics
    ws['F1'] = "SUMMARY METRICS"
    ws['F1'].font = HEADER_FONT
    ws['F2'] = "Outstanding"
    ws['G2'] = "~$4.2 billion"
    ws['F3'] = "Average Rate"
    ws['G3'] = "5.0%"
    ws['F4'] = "Average Term"
    ws['G4'] = "14 Years"

    # Create bar chart
    chart = BarChart()
    chart.title = "Debt Maturity Profile"
    chart.style = 10
    chart.y_axis.title = "Amount ($B)"

    data_ref = Reference(ws, min_col=2, min_row=1, max_row=6)
    cats_ref = Reference(ws, min_col=1, min_row=2, max_row=6)
    chart.add_data(data_ref, titles_from_data=True)
    chart.set_categories(cats_ref)

    ws.add_chart(chart, "F7")

    auto_column_width(ws)

    wb.save(OUTPUT_DIR / "22_debt_maturity.xlsx")
    print("Created: 22_debt_maturity.xlsx")


# =============================================================================
# Template 23: Value Creation Bridge
# =============================================================================
def create_value_bridge():
    wb = Workbook()
    ws = wb.active
    ws.title = "Value_Bridge"

    headers = ["Component", "Value_Low", "Value_High", "Is_Subtotal"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Inflation Pass-through", 0.03, 0.04, False),
        ("GDP Growth", 0.01, 0.02, False),
        ("Reinvested Capital", 0.02, 0.03, False),
        ("= Organic Growth", 0.06, 0.09, True),
        ("M&A Contribution", 0.02, 0.03, False),
        ("= Total FFO Growth", 0.08, 0.12, True),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [2, 3] and isinstance(value, float):
                cell.number_format = '0%'
        if row_data[3]:  # Is subtotal
            for col in range(1, 5):
                ws.cell(row=row_idx, column=col).font = HEADER_FONT
                ws.cell(row=row_idx, column=col).fill = GREEN_FILL
                if col > 1:
                    ws.cell(row=row_idx, column=col).font = Font(bold=True, color="FFFFFF")

    auto_column_width(ws)

    # Target box
    ws['F1'] = "TARGET"
    ws['F1'].font = HEADER_FONT
    ws['F2'] = "FFO per unit growth"
    ws['F3'] = "10%+"
    ws['F3'].fill = GREEN_FILL
    ws['F3'].font = Font(bold=True, color="FFFFFF", size=14)

    wb.save(OUTPUT_DIR / "23_value_bridge.xlsx")
    print("Created: 23_value_bridge.xlsx")


# =============================================================================
# Template 25: Deal Showcase Grid
# =============================================================================
def create_deal_showcase():
    wb = Workbook()
    ws = wb.active
    ws.title = "Deal_Showcase"

    headers = ["Deal_Name", "Logo_Path", "Sector", "Deal_Type", "Enterprise_Value", "Close_Date"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Deal A", "logos/a.png", "Midstream", "Value-based", 9100, "Jul 2025"),
        ("Deal B", "logos/b.png", "Data", "Platform", 6900, "Sep 2025"),
        ("Deal C", "logos/c.png", "Transport", "Partnership", 5300, "Q1 2026"),
        ("Deal D", "logos/d.png", "Utilities", "Carve-out", 1000, "Q4 2025"),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx == 5:
                cell.number_format = '$#,##0"M"'

    style_data_rows(ws)
    auto_column_width(ws)

    # Total row
    ws['A7'] = "TOTAL"
    ws['A7'].font = HEADER_FONT
    ws['E7'] = "=SUM(E2:E5)"
    ws['E7'].number_format = '$#,##0"M"'
    ws['E7'].font = HEADER_FONT

    wb.save(OUTPUT_DIR / "25_deal_showcase.xlsx")
    print("Created: 25_deal_showcase.xlsx")


# =============================================================================
# Template 27: Cost of Capital Spectrum
# =============================================================================
def create_cost_of_capital():
    wb = Workbook()
    ws = wb.active
    ws.title = "Cost_of_Capital"

    headers = ["Funding_Source", "Cost_Low", "Cost_High", "Constraints", "Position"]
    for col, header in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=header)
    style_header_row(ws)

    data = [
        ("Corporate Debt", 0.035, 0.045, "BBB+ rating limit", 1),
        ("Preferred Equity", 0.055, 0.065, "-", 2),
        ("Asset Sales", 0.09, 0.11, "Target range", 3),
        ("Common Equity", 0.12, 0.15, "Dilution concerns", 4),
    ]

    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if col_idx in [2, 3]:
                cell.number_format = '0.0%'
        # Highlight asset sales row (target)
        if row_data[0] == "Asset Sales":
            for col in range(1, 6):
                ws.cell(row=row_idx, column=col).fill = GREEN_FILL
                ws.cell(row=row_idx, column=col).font = WHITE_FONT

    style_data_rows(ws)
    auto_column_width(ws)

    # Spectrum visualization helper
    ws['G1'] = "SPECTRUM"
    ws['G1'].font = HEADER_FONT
    ws['G2'] = "Lowest Cost"
    ws['H2'] = "--->"
    ws['I2'] = "Highest Cost"
    ws['G3'] = "~4%"
    ws['H3'] = "9-11%"
    ws['I3'] = "12-15%+"
    ws['H3'].fill = GREEN_FILL
    ws['H3'].font = WHITE_FONT

    wb.save(OUTPUT_DIR / "27_cost_of_capital.xlsx")
    print("Created: 27_cost_of_capital.xlsx")


# =============================================================================
# Main execution
# =============================================================================
def main():
    print(f"Generating Excel templates in: {OUTPUT_DIR}")
    print("-" * 50)

    create_peer_benchmarking()      # Template 3
    create_comps_table()            # Template 4
    create_time_series()            # Template 5
    create_before_after()           # Template 6
    create_sources_uses()           # Template 7
    create_scenario_analysis()      # Template 8
    create_horizontal_bar_pie()     # Template 9
    create_gantt_chart()            # Template 10
    create_heat_map()               # Template 11
    create_portfolio_valuations()   # Template 12
    create_debt_benchmarking()      # Template 14
    create_achievement_summary()    # Template 16
    create_track_record()           # Template 17
    create_exit_summary()           # Template 19
    create_debt_maturity()          # Template 22
    create_value_bridge()           # Template 23
    create_deal_showcase()          # Template 25
    create_cost_of_capital()        # Template 27

    print("-" * 50)
    print("All 18 templates created successfully!")


if __name__ == "__main__":
    main()
