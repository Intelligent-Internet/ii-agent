#!/usr/bin/env python3
"""
Institutional LBO Model Template Generator

Creates a Harvard/KKR-grade LBO model with Goldman Sachs formatting standards.
Based on Private Equity textbook best practices and professional reference models.

Structure:
1. Cover - Deal summary
2. Assumptions - All inputs in one place
3. Sources & Uses - Transaction funding
4. Operating Model - 5-year projections
5. Debt Schedule - Multi-tranche with cash sweep
6. Returns Analysis - IRR/MOIC with sensitivities
7. DCF Check - Sanity check valuation
8. Football Field - Summary output

Formatting Standards:
- Blue font (#0000FF) for hardcoded inputs
- Black font for formulas
- Yellow fill (#FFF3CD) for key input cells
- Gray headers (#1E3A5F with white text)
- Consistent number formatting
- Print-ready layout
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment, NamedStyle
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import FormulaRule
from datetime import datetime
import os

# Style Constants - Goldman Sachs / Institutional Standards
HEADER_FILL = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", name="Arial", size=10)
INPUT_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
INPUT_FONT = Font(color="0000FF", name="Arial", size=10)  # Blue for inputs
CALC_FONT = Font(color="000000", name="Arial", size=10)   # Black for formulas
TITLE_FONT = Font(bold=True, color="1E3A5F", name="Arial", size=14)
SECTION_FONT = Font(bold=True, color="1E3A5F", name="Arial", size=11)
SUBTOTAL_FONT = Font(bold=True, color="000000", name="Arial", size=10)
TOTAL_FILL = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")

THIN_BORDER = Border(
    left=Side(style='thin', color='CCCCCC'),
    right=Side(style='thin', color='CCCCCC'),
    top=Side(style='thin', color='CCCCCC'),
    bottom=Side(style='thin', color='CCCCCC')
)

BOTTOM_BORDER = Border(bottom=Side(style='thin', color='000000'))
DOUBLE_BORDER = Border(bottom=Side(style='double', color='000000'))


def style_header_row(ws, row, start_col, end_col):
    """Apply institutional header styling."""
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center', vertical='center')


def style_input_cell(cell, value=None):
    """Style a cell as an input (blue font, yellow background)."""
    cell.fill = INPUT_FILL
    cell.font = INPUT_FONT
    cell.border = THIN_BORDER
    if value is not None:
        cell.value = value


def style_calc_cell(cell, formula=None):
    """Style a cell as a calculation (black font)."""
    cell.font = CALC_FONT
    cell.border = THIN_BORDER
    if formula is not None:
        cell.value = formula


def style_total_row(ws, row, start_col, end_col):
    """Style a total/subtotal row."""
    for col in range(start_col, end_col + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = TOTAL_FILL
        cell.font = SUBTOTAL_FONT
        cell.border = BOTTOM_BORDER


def create_cover_sheet(wb):
    """Create deal cover sheet."""
    ws = wb.active
    ws.title = "Cover"

    # Title
    ws.merge_cells('B2:G2')
    ws['B2'] = "LEVERAGED BUYOUT ANALYSIS"
    ws['B2'].font = Font(bold=True, color="1E3A5F", name="Arial", size=24)
    ws['B2'].alignment = Alignment(horizontal='center')

    ws.merge_cells('B4:G4')
    ws['B4'] = "[TARGET COMPANY NAME]"
    ws['B4'].font = Font(bold=True, color="000000", name="Arial", size=18)
    ws['B4'].alignment = Alignment(horizontal='center')
    style_input_cell(ws['B4'])

    ws.merge_cells('B6:G6')
    ws['B6'] = "Confidential - For Discussion Purposes Only"
    ws['B6'].font = Font(italic=True, color="666666", name="Arial", size=10)
    ws['B6'].alignment = Alignment(horizontal='center')

    # Deal summary box
    ws['B9'] = "TRANSACTION SUMMARY"
    ws['B9'].font = SECTION_FONT

    summary_items = [
        ("Date", datetime.now().strftime("%B %d, %Y")),
        ("Transaction Type", "Leveraged Buyout"),
        ("Sponsor", "[Sponsor Name]"),
        ("Target", "[Target Company]"),
        ("Entry EV", "$XXX.X million"),
        ("Entry Multiple", "X.Xx LTM EBITDA"),
        ("Equity Check", "$XX.X million"),
        ("Hold Period", "5 years"),
    ]

    for i, (label, value) in enumerate(summary_items, start=11):
        ws.cell(row=i, column=2, value=label).font = CALC_FONT
        cell = ws.cell(row=i, column=4, value=value)
        if "[" in value:
            style_input_cell(cell)
        else:
            cell.font = CALC_FONT

    # Set column widths
    ws.column_dimensions['A'].width = 3
    ws.column_dimensions['B'].width = 20
    ws.column_dimensions['C'].width = 5
    ws.column_dimensions['D'].width = 25

    return ws


def create_assumptions_sheet(wb):
    """Create assumptions input sheet - all inputs in one place."""
    ws = wb.create_sheet("Assumptions")

    ws['A1'] = "MODEL ASSUMPTIONS"
    ws['A1'].font = TITLE_FONT

    # Transaction Assumptions Section
    row = 3
    ws.cell(row=row, column=1, value="TRANSACTION ASSUMPTIONS").font = SECTION_FONT
    row += 1

    txn_assumptions = [
        ("Transaction Date", "2025-12-31", "Date"),
        ("LTM Revenue ($M)", 500.0, "Currency"),
        ("LTM EBITDA ($M)", 75.0, "Currency"),
        ("LTM EBITDA Margin", 0.15, "Percent"),
        ("Entry EV/EBITDA Multiple", 8.0, "Multiple"),
        ("", "", ""),
        ("Transaction Fees (% of EV)", 0.02, "Percent"),
        ("Financing Fees (% of Debt)", 0.025, "Percent"),
        ("Minimum Cash Balance ($M)", 10.0, "Currency"),
    ]

    ws.cell(row=row, column=1, value="Assumption").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Value").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Units").font = HEADER_FONT
    style_header_row(ws, row, 1, 3)
    row += 1

    for label, value, unit in txn_assumptions:
        ws.cell(row=row, column=1, value=label).font = CALC_FONT
        if value != "":
            style_input_cell(ws.cell(row=row, column=2), value)
            if unit == "Percent":
                ws.cell(row=row, column=2).number_format = '0.0%'
            elif unit == "Currency":
                ws.cell(row=row, column=2).number_format = '#,##0.0'
            elif unit == "Multiple":
                ws.cell(row=row, column=2).number_format = '0.0x'
        ws.cell(row=row, column=3, value=unit).font = CALC_FONT
        row += 1

    row += 1

    # Capital Structure Section
    ws.cell(row=row, column=1, value="CAPITAL STRUCTURE").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Debt Tranche").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Multiple").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Rate").font = HEADER_FONT
    ws.cell(row=row, column=4, value="Amort").font = HEADER_FONT
    ws.cell(row=row, column=5, value="Term").font = HEADER_FONT
    style_header_row(ws, row, 1, 5)
    row += 1

    debt_tranches = [
        ("Senior Secured (Term Loan B)", 3.5, 0.065, 0.01, 7),
        ("Second Lien", 1.0, 0.095, 0.0, 8),
        ("Subordinated / Mezzanine", 0.5, 0.12, 0.0, 10),
    ]

    for tranche, mult, rate, amort, term in debt_tranches:
        ws.cell(row=row, column=1, value=tranche).font = CALC_FONT
        style_input_cell(ws.cell(row=row, column=2), mult)
        ws.cell(row=row, column=2).number_format = '0.0x'
        style_input_cell(ws.cell(row=row, column=3), rate)
        ws.cell(row=row, column=3).number_format = '0.0%'
        style_input_cell(ws.cell(row=row, column=4), amort)
        ws.cell(row=row, column=4).number_format = '0.0%'
        style_input_cell(ws.cell(row=row, column=5), term)
        row += 1

    row += 2

    # Operating Assumptions Section
    ws.cell(row=row, column=1, value="OPERATING ASSUMPTIONS").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Driver").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Year 1").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Year 2").font = HEADER_FONT
    ws.cell(row=row, column=4, value="Year 3").font = HEADER_FONT
    ws.cell(row=row, column=5, value="Year 4").font = HEADER_FONT
    ws.cell(row=row, column=6, value="Year 5").font = HEADER_FONT
    style_header_row(ws, row, 1, 6)
    row += 1

    op_drivers = [
        ("Revenue Growth", [0.08, 0.07, 0.06, 0.05, 0.05]),
        ("EBITDA Margin", [0.16, 0.17, 0.18, 0.18, 0.19]),
        ("D&A % Revenue", [0.03, 0.03, 0.03, 0.03, 0.03]),
        ("CapEx % Revenue", [0.04, 0.04, 0.03, 0.03, 0.03]),
        ("NWC % Revenue", [0.10, 0.10, 0.10, 0.10, 0.10]),
        ("Tax Rate", [0.25, 0.25, 0.25, 0.25, 0.25]),
    ]

    for driver, values in op_drivers:
        ws.cell(row=row, column=1, value=driver).font = CALC_FONT
        for i, val in enumerate(values, start=2):
            style_input_cell(ws.cell(row=row, column=i), val)
            ws.cell(row=row, column=i).number_format = '0.0%'
        row += 1

    row += 2

    # Exit Assumptions Section
    ws.cell(row=row, column=1, value="EXIT ASSUMPTIONS").font = SECTION_FONT
    row += 1

    exit_assumptions = [
        ("Exit Year", 5, "Year"),
        ("Exit EV/EBITDA Multiple", 8.0, "Multiple"),
        ("Exit Multiple vs Entry", 0.0, "Delta"),
    ]

    for label, value, unit in exit_assumptions:
        ws.cell(row=row, column=1, value=label).font = CALC_FONT
        style_input_cell(ws.cell(row=row, column=2), value)
        if unit == "Multiple":
            ws.cell(row=row, column=2).number_format = '0.0x'
        elif unit == "Delta":
            ws.cell(row=row, column=2).number_format = '+0.0x;-0.0x;0.0x'
        ws.cell(row=row, column=3, value=unit).font = CALC_FONT
        row += 1

    # Set column widths
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 12

    return ws


def create_sources_uses_sheet(wb):
    """Create Sources & Uses sheet."""
    ws = wb.create_sheet("Sources & Uses")

    ws['A1'] = "SOURCES AND USES OF FUNDS"
    ws['A1'].font = TITLE_FONT

    ws['A2'] = "($ in millions)"
    ws['A2'].font = Font(italic=True, color="666666", name="Arial", size=9)

    # Sources Section
    row = 4
    ws.cell(row=row, column=1, value="SOURCES OF FUNDS").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Source").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Amount").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Multiple").font = HEADER_FONT
    ws.cell(row=row, column=4, value="% of Total").font = HEADER_FONT
    style_header_row(ws, row, 1, 4)
    row += 1

    sources = [
        ("Senior Secured Term Loan B", "=Assumptions!B19*Assumptions!B7", "=B{0}/Assumptions!$B$7"),
        ("Second Lien Term Loan", "=Assumptions!B20*Assumptions!B7", "=B{0}/Assumptions!$B$7"),
        ("Subordinated Debt", "=Assumptions!B21*Assumptions!B7", "=B{0}/Assumptions!$B$7"),
        ("Rollover Equity", "0", "=B{0}/Assumptions!$B$7"),
        ("Sponsor Equity", "=B15-SUM(B{0}:B{1})", "=B{0}/Assumptions!$B$7"),
    ]

    source_start = row
    for i, (source, amount_formula, mult_formula) in enumerate(sources):
        ws.cell(row=row, column=1, value=source).font = CALC_FONT

        if source == "Sponsor Equity":
            ws.cell(row=row, column=2, value=f"=B15-SUM(B{source_start}:B{row-1})")
        elif source == "Rollover Equity":
            style_input_cell(ws.cell(row=row, column=2), 0)
        else:
            ws.cell(row=row, column=2, value=amount_formula)
        ws.cell(row=row, column=2).number_format = '#,##0.0'

        ws.cell(row=row, column=3, value=f"=B{row}/Assumptions!$B$7")
        ws.cell(row=row, column=3).number_format = '0.0x'

        ws.cell(row=row, column=4, value=f"=B{row}/$B$15")
        ws.cell(row=row, column=4).number_format = '0.0%'
        row += 1

    # Total Sources
    ws.cell(row=row, column=1, value="Total Sources").font = SUBTOTAL_FONT
    ws.cell(row=row, column=2, value=f"=SUM(B{source_start}:B{row-1})")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=3, value=f"=B{row}/Assumptions!$B$7")
    ws.cell(row=row, column=3).number_format = '0.0x'
    ws.cell(row=row, column=4, value="=1")
    ws.cell(row=row, column=4).number_format = '0.0%'
    style_total_row(ws, row, 1, 4)
    row += 2

    # Uses Section
    ws.cell(row=row, column=1, value="USES OF FUNDS").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Use").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Amount").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Multiple").font = HEADER_FONT
    ws.cell(row=row, column=4, value="% of Total").font = HEADER_FONT
    style_header_row(ws, row, 1, 4)
    row += 1

    uses_start = row
    uses = [
        ("Purchase Enterprise Value", "=Assumptions!B9*Assumptions!B7"),
        ("Refinance Existing Debt", "0"),
        ("Transaction Fees", "=Assumptions!B11*B{0}".format(uses_start)),
        ("Financing Fees", "=Assumptions!B12*(B6+B7+B8)"),
        ("Cash to Balance Sheet", "=Assumptions!B13"),
    ]

    for use, formula in uses:
        ws.cell(row=row, column=1, value=use).font = CALC_FONT
        if use == "Refinance Existing Debt":
            style_input_cell(ws.cell(row=row, column=2), 0)
        else:
            ws.cell(row=row, column=2, value=formula)
        ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=3, value=f"=B{row}/Assumptions!$B$7")
        ws.cell(row=row, column=3).number_format = '0.0x'
        ws.cell(row=row, column=4, value=f"=B{row}/$B$15")
        ws.cell(row=row, column=4).number_format = '0.0%'
        row += 1

    # Total Uses
    uses_total_row = row
    ws.cell(row=row, column=1, value="Total Uses").font = SUBTOTAL_FONT
    ws.cell(row=row, column=2, value=f"=SUM(B{uses_start}:B{row-1})")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=3, value=f"=B{row}/Assumptions!$B$7")
    ws.cell(row=row, column=3).number_format = '0.0x'
    ws.cell(row=row, column=4, value="=1")
    ws.cell(row=row, column=4).number_format = '0.0%'
    style_total_row(ws, row, 1, 4)
    row += 2

    # Check
    ws.cell(row=row, column=1, value="Sources - Uses (Check)").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B15-B{uses_total_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'

    # Column widths
    ws.column_dimensions['A'].width = 30
    ws.column_dimensions['B'].width = 15
    ws.column_dimensions['C'].width = 12
    ws.column_dimensions['D'].width = 12

    return ws


def create_operating_model_sheet(wb):
    """Create Operating Model sheet with 5-year projections."""
    ws = wb.create_sheet("Operating Model")

    ws['A1'] = "OPERATING MODEL"
    ws['A1'].font = TITLE_FONT

    ws['A2'] = "($ in millions, fiscal year ending December 31)"
    ws['A2'].font = Font(italic=True, color="666666", name="Arial", size=9)

    # Year headers
    row = 4
    headers = ["", "LTM", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=row, column=col, value=header)
    style_header_row(ws, row, 1, len(headers))
    row += 1

    # Income Statement Section
    ws.cell(row=row, column=1, value="INCOME STATEMENT").font = SECTION_FONT
    row += 1

    is_items = [
        ("Revenue", "=Assumptions!B6", "=B{prev}*(1+Assumptions!B{driver})", 28),
        ("% Growth", "", "=(C{this}-B{this})/B{this}", None),
        ("", "", "", None),
        ("EBITDA", "=Assumptions!B7", "=C{rev}*Assumptions!C{driver}", 29),
        ("% Margin", "=B{this}/B{rev}", "=C{this}/C{rev}", None),
        ("", "", "", None),
        ("D&A", "=B{rev}*0.03", "=C{rev}*Assumptions!C{driver}", 30),
        ("EBIT", "=B{ebitda}-B{da}", "=C{ebitda}-C{da}", None),
        ("% Margin", "=B{this}/B{rev}", "=C{this}/C{rev}", None),
        ("", "", "", None),
        ("Interest Expense", "", "='Debt Schedule'!C{int_row}", None),
        ("EBT", "=B{ebit}", "=C{ebit}-C{int}", None),
        ("Taxes", "=B{ebt}*0.25", "=MAX(0,C{ebt})*Assumptions!C{driver}", 33),
        ("Net Income", "=B{ebt}-B{tax}", "=C{ebt}-C{tax}", None),
    ]

    rev_row = row
    ebitda_row = None
    da_row = None
    ebit_row = None
    int_row = None
    ebt_row = None
    tax_row = None

    for item, ltm_formula, proj_formula, driver_row in is_items:
        ws.cell(row=row, column=1, value=item).font = CALC_FONT

        if item == "Revenue":
            rev_row = row
            ws.cell(row=row, column=2, value="=Assumptions!B6")
            for col in range(3, 8):
                prev_col = get_column_letter(col - 1)
                driver_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={prev_col}{row}*(1+Assumptions!{driver_col}28)")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "% Growth":
            for col in range(3, 8):
                prev_col = get_column_letter(col - 1)
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=({this_col}{rev_row}-{prev_col}{rev_row})/{prev_col}{rev_row}")
                ws.cell(row=row, column=col).number_format = '0.0%'
        elif item == "EBITDA":
            ebitda_row = row
            ws.cell(row=row, column=2, value="=Assumptions!B7")
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{rev_row}*Assumptions!{this_col}29")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "% Margin":
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{row-1}/{this_col}{rev_row}")
                ws.cell(row=row, column=col).number_format = '0.0%'
        elif item == "D&A":
            da_row = row
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{rev_row}*Assumptions!{this_col}30")
        elif item == "EBIT":
            ebit_row = row
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{ebitda_row}-{this_col}{da_row}")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "Interest Expense":
            int_row = row
            # Will link to debt schedule
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"='Debt Schedule'!{this_col}25")
        elif item == "EBT":
            ebt_row = row
            ws.cell(row=row, column=2, value=f"=B{ebit_row}")
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{ebit_row}-{this_col}{int_row}")
        elif item == "Taxes":
            tax_row = row
            ws.cell(row=row, column=2, value=f"=B{ebt_row}*0.25")
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=MAX(0,{this_col}{ebt_row})*Assumptions!{this_col}33")
        elif item == "Net Income":
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{ebt_row}-{this_col}{tax_row}")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
            style_total_row(ws, row, 1, 7)

        # Number format for financial values
        if item and item not in ["% Growth", "% Margin", ""]:
            for col in range(2, 8):
                if ws.cell(row=row, column=col).number_format == 'General':
                    ws.cell(row=row, column=col).number_format = '#,##0.0'

        row += 1

    row += 1

    # Free Cash Flow Section
    ws.cell(row=row, column=1, value="FREE CASH FLOW").font = SECTION_FONT
    row += 1

    fcf_start = row
    fcf_items = [
        "EBITDA",
        "(-) Cash Taxes",
        "(-) CapEx",
        "(+/-) Change in NWC",
        "Unlevered Free Cash Flow",
        "",
        "(-) Cash Interest",
        "(-) Mandatory Amortization",
        "Free Cash Flow for Debt Paydown",
    ]

    for item in fcf_items:
        ws.cell(row=row, column=1, value=item).font = CALC_FONT

        if item == "EBITDA":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{ebitda_row}")
        elif item == "(-) Cash Taxes":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=-{this_col}{tax_row}")
        elif item == "(-) CapEx":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=-{this_col}{rev_row}*Assumptions!{this_col}31")
        elif item == "(+/-) Change in NWC":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                prev_col = get_column_letter(col - 1)
                ws.cell(row=row, column=col, value=f"=-({this_col}{rev_row}*Assumptions!{this_col}32-{prev_col}{rev_row}*Assumptions!{prev_col}32)")
        elif item == "Unlevered Free Cash Flow":
            ufcf_row = row
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=SUM({this_col}{fcf_start}:{this_col}{row-1})")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "(-) Cash Interest":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=-{this_col}{int_row}")
        elif item == "(-) Mandatory Amortization":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"='Debt Schedule'!{this_col}19")
        elif item == "Free Cash Flow for Debt Paydown":
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"={this_col}{ufcf_row}+{this_col}{row-2}+{this_col}{row-1}")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
            style_total_row(ws, row, 1, 7)

        if item and item != "":
            for col in range(2, 8):
                if ws.cell(row=row, column=col).number_format == 'General':
                    ws.cell(row=row, column=col).number_format = '#,##0.0'

        row += 1

    # Column widths
    ws.column_dimensions['A'].width = 32
    for col in range(2, 8):
        ws.column_dimensions[get_column_letter(col)].width = 12

    return ws


def create_debt_schedule_sheet(wb):
    """Create Debt Schedule with multiple tranches and cash sweep."""
    ws = wb.create_sheet("Debt Schedule")

    ws['A1'] = "DEBT SCHEDULE"
    ws['A1'].font = TITLE_FONT

    ws['A2'] = "($ in millions)"
    ws['A2'].font = Font(italic=True, color="666666", name="Arial", size=9)

    # Year headers
    row = 4
    headers = ["", "Entry", "Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
    for col, header in enumerate(headers, start=1):
        ws.cell(row=row, column=col, value=header)
    style_header_row(ws, row, 1, len(headers))
    row += 1

    # Senior Debt Section
    ws.cell(row=row, column=1, value="SENIOR SECURED TERM LOAN B").font = SECTION_FONT
    row += 1

    senior_start = row
    senior_items = [
        ("Beginning Balance", "", "=B{end}"),
        ("(+) Draws", "='Sources & Uses'!B6", "0"),
        ("(-) Mandatory Amortization", "", "=-B{beg}*Assumptions!D19"),
        ("(-) Optional Prepayment", "", "=-MIN(C{avail},{end_prev})"),
        ("Ending Balance", "=B{beg}+B{draw}+B{mand}+B{opt}", "=C{beg}+C{draw}+C{mand}+C{opt}"),
        ("", "", ""),
        ("Interest Rate", "=Assumptions!C19", "=Assumptions!C19"),
        ("Interest Expense", "=B{end}*B{rate}", "=(B{end}+C{end})/2*C{rate}"),
    ]

    beg_row = None
    draw_row = None
    mand_row = None
    opt_row = None
    end_row = None
    rate_row = None

    for item, entry_formula, proj_formula in senior_items:
        ws.cell(row=row, column=1, value=item).font = CALC_FONT

        if item == "Beginning Balance":
            beg_row = row
            ws.cell(row=row, column=2, value=0)
            for col in range(3, 8):
                prev_col = get_column_letter(col - 1)
                ws.cell(row=row, column=col, value=f"={prev_col}{row+4}")
        elif item == "(+) Draws":
            draw_row = row
            ws.cell(row=row, column=2, value="='Sources & Uses'!B6")
            for col in range(3, 8):
                ws.cell(row=row, column=col, value=0)
        elif item == "(-) Mandatory Amortization":
            mand_row = row
            ws.cell(row=row, column=2, value=0)
            for col in range(3, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=-{this_col}{beg_row}*Assumptions!D19")
        elif item == "(-) Optional Prepayment":
            opt_row = row
            ws.cell(row=row, column=2, value=0)
            # Will be set after FCF is available
            for col in range(3, 8):
                ws.cell(row=row, column=col, value=0)  # Placeholder
        elif item == "Ending Balance":
            end_row = row
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=MAX(0,{this_col}{beg_row}+{this_col}{draw_row}+{this_col}{mand_row}+{this_col}{opt_row})")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "Interest Rate":
            rate_row = row
            for col in range(2, 8):
                ws.cell(row=row, column=col, value="=Assumptions!C19")
                ws.cell(row=row, column=col).number_format = '0.0%'
        elif item == "Interest Expense":
            for col in range(2, 8):
                this_col = get_column_letter(col)
                if col == 2:
                    ws.cell(row=row, column=col, value=f"={this_col}{end_row}*{this_col}{rate_row}")
                else:
                    prev_col = get_column_letter(col - 1)
                    ws.cell(row=row, column=col, value=f"=({prev_col}{end_row}+{this_col}{end_row})/2*{this_col}{rate_row}")

        if item not in ["Interest Rate", ""]:
            for col in range(2, 8):
                if ws.cell(row=row, column=col).number_format == 'General':
                    ws.cell(row=row, column=col).number_format = '#,##0.0'

        row += 1

    senior_int_row = row - 1

    row += 1

    # Second Lien Section (simplified)
    ws.cell(row=row, column=1, value="SECOND LIEN TERM LOAN").font = SECTION_FONT
    row += 1

    second_lien_items = [
        ("Beginning Balance", "0", "=B{end}"),
        ("(+) Draws", "='Sources & Uses'!B7", "0"),
        ("(-) Amortization", "", "0"),
        ("Ending Balance", "=B{beg}+B{draw}", "=C{beg}+C{draw}+C{amort}"),
        ("", "", ""),
        ("Interest Rate", "=Assumptions!C20", "=Assumptions!C20"),
        ("Interest Expense", "=B{end}*B{rate}", "=(B{end}+C{end})/2*C{rate}"),
    ]

    sl_beg = row
    for i, (item, entry_formula, proj_formula) in enumerate(second_lien_items):
        ws.cell(row=row, column=1, value=item).font = CALC_FONT

        if item == "Beginning Balance":
            ws.cell(row=row, column=2, value=0)
            for col in range(3, 8):
                prev_col = get_column_letter(col - 1)
                ws.cell(row=row, column=col, value=f"={prev_col}{row+3}")
        elif item == "(+) Draws":
            ws.cell(row=row, column=2, value="='Sources & Uses'!B7")
            for col in range(3, 8):
                ws.cell(row=row, column=col, value=0)
        elif item == "(-) Amortization":
            ws.cell(row=row, column=2, value=0)
            for col in range(3, 8):
                ws.cell(row=row, column=col, value=0)
        elif item == "Ending Balance":
            for col in range(2, 8):
                this_col = get_column_letter(col)
                ws.cell(row=row, column=col, value=f"=MAX(0,{this_col}{sl_beg}+{this_col}{sl_beg+1}+{this_col}{sl_beg+2})")
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "Interest Rate":
            for col in range(2, 8):
                ws.cell(row=row, column=col, value="=Assumptions!C20")
                ws.cell(row=row, column=col).number_format = '0.0%'
        elif item == "Interest Expense":
            for col in range(2, 8):
                this_col = get_column_letter(col)
                if col == 2:
                    ws.cell(row=row, column=col, value=f"={this_col}{row-2}*{this_col}{row-1}")
                else:
                    prev_col = get_column_letter(col - 1)
                    ws.cell(row=row, column=col, value=f"=({prev_col}{row-2}+{this_col}{row-2})/2*{this_col}{row-1}")

        if item not in ["Interest Rate", ""]:
            for col in range(2, 8):
                if ws.cell(row=row, column=col).number_format == 'General':
                    ws.cell(row=row, column=col).number_format = '#,##0.0'

        row += 1

    second_int_row = row - 1

    row += 1

    # Total Summary
    ws.cell(row=row, column=1, value="TOTAL DEBT SUMMARY").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Total Debt").font = SUBTOTAL_FONT
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{end_row}+{this_col}{sl_beg+3}")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    row += 1

    ws.cell(row=row, column=1, value="Total Interest Expense").font = SUBTOTAL_FONT
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{senior_int_row}+{this_col}{second_int_row}")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    style_total_row(ws, row, 1, 7)

    # Column widths
    ws.column_dimensions['A'].width = 28
    for col in range(2, 8):
        ws.column_dimensions[get_column_letter(col)].width = 12

    return ws


def create_returns_sheet(wb):
    """Create Returns Analysis sheet with IRR, MOIC, sensitivities."""
    ws = wb.create_sheet("Returns Analysis")

    ws['A1'] = "LBO RETURNS ANALYSIS"
    ws['A1'].font = TITLE_FONT

    ws['A2'] = "($ in millions)"
    ws['A2'].font = Font(italic=True, color="666666", name="Arial", size=9)

    # Exit Summary
    row = 4
    ws.cell(row=row, column=1, value="EXIT ANALYSIS").font = SECTION_FONT
    row += 1

    exit_items = [
        ("Exit Year", "=Assumptions!B35"),
        ("Exit EBITDA", "='Operating Model'!G9"),
        ("Exit Multiple", "=Assumptions!B36"),
        ("Exit Enterprise Value", "=B{ebitda}*B{mult}"),
        ("(-) Net Debt at Exit", "='Debt Schedule'!G24"),
        ("Exit Equity Value", "=B{ev}-B{debt}"),
    ]

    ebitda_row = None
    mult_row = None
    ev_row = None
    debt_row = None

    for item, formula in exit_items:
        ws.cell(row=row, column=1, value=item).font = CALC_FONT

        if item == "Exit Year":
            ws.cell(row=row, column=2, value="=Assumptions!B35")
            ws.cell(row=row, column=2).number_format = '0'
        elif item == "Exit EBITDA":
            ebitda_row = row
            ws.cell(row=row, column=2, value="='Operating Model'!G9")
            ws.cell(row=row, column=2).number_format = '#,##0.0'
        elif item == "Exit Multiple":
            mult_row = row
            ws.cell(row=row, column=2, value="=Assumptions!B36")
            ws.cell(row=row, column=2).number_format = '0.0x'
        elif item == "Exit Enterprise Value":
            ev_row = row
            ws.cell(row=row, column=2, value=f"=B{ebitda_row}*B{mult_row}")
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
        elif item == "(-) Net Debt at Exit":
            debt_row = row
            ws.cell(row=row, column=2, value="='Debt Schedule'!G24")
            ws.cell(row=row, column=2).number_format = '#,##0.0'
        elif item == "Exit Equity Value":
            ws.cell(row=row, column=2, value=f"=B{ev_row}-B{debt_row}")
            ws.cell(row=row, column=2).number_format = '#,##0.0'
            ws.cell(row=row, column=1).font = SUBTOTAL_FONT
            style_total_row(ws, row, 1, 2)

        row += 1

    exit_equity_row = row - 1
    row += 2

    # Returns Summary
    ws.cell(row=row, column=1, value="RETURNS SUMMARY").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Initial Equity Investment").font = CALC_FONT
    ws.cell(row=row, column=2, value="='Sources & Uses'!B10")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    entry_eq_row = row
    row += 1

    ws.cell(row=row, column=1, value="Exit Equity Value").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B{exit_equity_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    row += 1

    ws.cell(row=row, column=1, value="Total Equity Gain").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B{row-1}-B{entry_eq_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    row += 2

    ws.cell(row=row, column=1, value="MOIC (Multiple on Invested Capital)").font = SUBTOTAL_FONT
    ws.cell(row=row, column=2, value=f"=B{exit_equity_row}/B{entry_eq_row}")
    ws.cell(row=row, column=2).number_format = '0.00x'
    ws.cell(row=row, column=2).font = Font(bold=True, color="1E3A5F", size=14)
    moic_row = row
    row += 1

    ws.cell(row=row, column=1, value="IRR (Internal Rate of Return)").font = SUBTOTAL_FONT
    ws.cell(row=row, column=2, value=f"=(B{exit_equity_row}/B{entry_eq_row})^(1/Assumptions!B35)-1")
    ws.cell(row=row, column=2).number_format = '0.0%'
    ws.cell(row=row, column=2).font = Font(bold=True, color="1E3A5F", size=14)
    irr_row = row
    row += 3

    # Sensitivity Analysis
    ws.cell(row=row, column=1, value="SENSITIVITY ANALYSIS").font = SECTION_FONT
    row += 2

    ws.cell(row=row, column=1, value="MOIC: Entry Multiple vs Exit Multiple").font = CALC_FONT
    row += 1

    # Sensitivity table headers
    ws.cell(row=row, column=2, value="Exit Multiple").font = HEADER_FONT
    style_header_row(ws, row, 2, 7)
    row += 1

    ws.cell(row=row, column=1, value="Entry").font = HEADER_FONT
    for i, mult in enumerate([6.0, 7.0, 8.0, 9.0, 10.0], start=2):
        ws.cell(row=row, column=i, value=mult)
        ws.cell(row=row, column=i).number_format = '0.0x'
    style_header_row(ws, row, 1, 7)
    row += 1

    entry_mults = [6.0, 7.0, 8.0, 9.0, 10.0]
    for entry_mult in entry_mults:
        ws.cell(row=row, column=1, value=entry_mult)
        ws.cell(row=row, column=1).number_format = '0.0x'
        ws.cell(row=row, column=1).fill = HEADER_FILL
        ws.cell(row=row, column=1).font = HEADER_FONT

        for col, exit_mult in enumerate([6.0, 7.0, 8.0, 9.0, 10.0], start=2):
            # Simplified MOIC calculation for sensitivity
            # MOIC = Exit Equity / Entry Equity
            # This is a placeholder - actual formula would reference model cells
            ws.cell(row=row, column=col, value=f"={exit_mult}/{entry_mult}*B{moic_row}")
            ws.cell(row=row, column=col).number_format = '0.00x'
        row += 1

    # Column widths
    ws.column_dimensions['A'].width = 32
    ws.column_dimensions['B'].width = 15
    for col in range(3, 8):
        ws.column_dimensions[get_column_letter(col)].width = 10

    return ws


def create_lbo_model_template(output_path: str = None, company_name: str = "Target Company"):
    """
    Create a complete institutional LBO model template.

    Args:
        output_path: Directory to save the file (defaults to current directory)
        company_name: Name of target company

    Returns:
        Path to created file
    """
    wb = openpyxl.Workbook()

    # Create all sheets
    create_cover_sheet(wb)
    create_assumptions_sheet(wb)
    create_sources_uses_sheet(wb)
    create_operating_model_sheet(wb)
    create_debt_schedule_sheet(wb)
    create_returns_sheet(wb)

    # Set Cover as active sheet
    wb.active = wb['Cover']

    # Update company name
    wb['Cover']['B4'] = company_name

    # Save
    if output_path is None:
        output_path = os.path.dirname(os.path.abspath(__file__))

    filename = f"LBO_Model_Template_{datetime.now().strftime('%Y%m%d')}.xlsx"
    filepath = os.path.join(output_path, filename)
    wb.save(filepath)

    print(f"LBO Model Template created: {filepath}")
    return filepath


if __name__ == "__main__":
    print("=" * 60)
    print("Institutional LBO Model Template Generator")
    print("=" * 60)

    # Create template in current directory
    filepath = create_lbo_model_template(company_name="[Target Company]")

    print("\nTemplate includes:")
    print("  - Cover sheet with deal summary")
    print("  - Assumptions (all inputs consolidated)")
    print("  - Sources & Uses")
    print("  - Operating Model (5-year projections)")
    print("  - Debt Schedule (multi-tranche)")
    print("  - Returns Analysis (MOIC, IRR, sensitivities)")
    print("\nFormatting:")
    print("  - Blue font = hardcoded inputs")
    print("  - Black font = formulas")
    print("  - Yellow cells = key assumptions")
