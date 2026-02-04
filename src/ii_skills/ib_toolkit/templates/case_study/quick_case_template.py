#!/usr/bin/env python3
"""
Quick Case Template Generator

A streamlined model for timed PE/IB interview case studies.
Designed to be completed in 30-60 minutes with essential analysis only.

Structure (single sheet for speed):
- Transaction Inputs
- Quick Sources & Uses
- 5-Year Projections (simplified)
- Returns Calculator
- Key Sensitivities

Usage:
- All inputs at top for fast data entry
- Formulas pre-built for instant results
- Print on 1-2 pages for presentation
"""

import openpyxl
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.utils import get_column_letter
from datetime import datetime
import os

# Style Constants
HEADER_FILL = PatternFill(start_color="1E3A5F", end_color="1E3A5F", fill_type="solid")
HEADER_FONT = Font(bold=True, color="FFFFFF", name="Arial", size=9)
INPUT_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
INPUT_FONT = Font(color="0000FF", name="Arial", size=9)
CALC_FONT = Font(color="000000", name="Arial", size=9)
SECTION_FONT = Font(bold=True, color="1E3A5F", name="Arial", size=10)
RESULT_FONT = Font(bold=True, color="1E3A5F", name="Arial", size=12)
TOTAL_FILL = PatternFill(start_color="E8E8E8", end_color="E8E8E8", fill_type="solid")

THIN_BORDER = Border(
    left=Side(style='thin', color='CCCCCC'),
    right=Side(style='thin', color='CCCCCC'),
    top=Side(style='thin', color='CCCCCC'),
    bottom=Side(style='thin', color='CCCCCC')
)


def style_input(cell, value=None):
    cell.fill = INPUT_FILL
    cell.font = INPUT_FONT
    cell.border = THIN_BORDER
    if value is not None:
        cell.value = value


def style_header(ws, row, start, end):
    for col in range(start, end + 1):
        cell = ws.cell(row=row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal='center')


def create_quick_case_template(output_path: str = None):
    """Create quick case template for timed interviews."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Quick LBO"

    # Title
    ws['A1'] = "QUICK LBO CASE MODEL"
    ws['A1'].font = Font(bold=True, color="1E3A5F", name="Arial", size=14)
    ws.merge_cells('A1:H1')

    ws['A2'] = "Company: "
    ws['A2'].font = CALC_FONT
    style_input(ws['B2'], "[Enter Company Name]")
    ws.merge_cells('B2:D2')

    # ========== SECTION 1: INPUTS ==========
    row = 4
    ws.cell(row=row, column=1, value="1. TRANSACTION INPUTS").font = SECTION_FONT
    row += 1

    # Input table headers
    ws.cell(row=row, column=1, value="Input").font = HEADER_FONT
    ws.cell(row=row, column=2, value="Value").font = HEADER_FONT
    ws.cell(row=row, column=3, value="Unit").font = HEADER_FONT
    style_header(ws, row, 1, 3)
    row += 1

    inputs = [
        ("LTM Revenue", 500, "$M", "B6"),
        ("LTM EBITDA", 75, "$M", "B7"),
        ("Entry Multiple", 8.0, "x EBITDA", "B8"),
        ("Total Leverage", 5.0, "x EBITDA", "B9"),
        ("Senior Debt Rate", 0.07, "%", "B10"),
        ("Revenue Growth (Y1-5)", 0.06, "% avg", "B11"),
        ("EBITDA Margin (Exit)", 0.18, "%", "B12"),
        ("Exit Multiple", 8.0, "x EBITDA", "B13"),
        ("Hold Period", 5, "years", "B14"),
        ("Tax Rate", 0.25, "%", "B15"),
    ]

    input_cells = {}
    for label, value, unit, cell_ref in inputs:
        ws.cell(row=row, column=1, value=label).font = CALC_FONT
        style_input(ws.cell(row=row, column=2), value)
        if "%" in unit:
            ws.cell(row=row, column=2).number_format = '0.0%'
        elif "x" in unit:
            ws.cell(row=row, column=2).number_format = '0.0x'
        else:
            ws.cell(row=row, column=2).number_format = '#,##0.0'
        ws.cell(row=row, column=3, value=unit).font = CALC_FONT
        input_cells[label] = f"B{row}"
        row += 1

    row += 1

    # ========== SECTION 2: SOURCES & USES ==========
    ws.cell(row=row, column=1, value="2. SOURCES & USES").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Sources").font = HEADER_FONT
    ws.cell(row=row, column=2, value="$M").font = HEADER_FONT
    ws.cell(row=row, column=3, value="%").font = HEADER_FONT
    ws.cell(row=row, column=5, value="Uses").font = HEADER_FONT
    ws.cell(row=row, column=6, value="$M").font = HEADER_FONT
    ws.cell(row=row, column=7, value="%").font = HEADER_FONT
    style_header(ws, row, 1, 3)
    style_header(ws, row, 5, 7)
    row += 1

    # Sources
    sources_start = row
    ws.cell(row=row, column=1, value="Senior Debt").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"={input_cells['LTM EBITDA']}*{input_cells['Total Leverage']}*0.7")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=3, value=f"=B{row}/$B${row+3}")
    ws.cell(row=row, column=3).number_format = '0.0%'

    ws.cell(row=row, column=5, value="Enterprise Value").font = CALC_FONT
    ws.cell(row=row, column=6, value=f"={input_cells['LTM EBITDA']}*{input_cells['Entry Multiple']}")
    ws.cell(row=row, column=6).number_format = '#,##0.0'
    ws.cell(row=row, column=7, value=f"=F{row}/$F${row+3}")
    ws.cell(row=row, column=7).number_format = '0.0%'
    row += 1

    ws.cell(row=row, column=1, value="Sub Debt").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"={input_cells['LTM EBITDA']}*{input_cells['Total Leverage']}*0.3")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=3, value=f"=B{row}/$B${row+2}")
    ws.cell(row=row, column=3).number_format = '0.0%'

    ws.cell(row=row, column=5, value="Fees (2%)").font = CALC_FONT
    ws.cell(row=row, column=6, value=f"=F{row-1}*0.02")
    ws.cell(row=row, column=6).number_format = '#,##0.0'
    ws.cell(row=row, column=7, value=f"=F{row}/$F${row+2}")
    ws.cell(row=row, column=7).number_format = '0.0%'
    row += 1

    ws.cell(row=row, column=1, value="Sponsor Equity").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B{row+1}-B{sources_start}-B{sources_start+1}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=3, value=f"=B{row}/$B${row+1}")
    ws.cell(row=row, column=3).number_format = '0.0%'
    equity_row = row

    ws.cell(row=row, column=5, value="Cash to BS").font = CALC_FONT
    ws.cell(row=row, column=6, value=10)
    style_input(ws.cell(row=row, column=6), 10)
    ws.cell(row=row, column=6).number_format = '#,##0.0'
    ws.cell(row=row, column=7, value=f"=F{row}/$F${row+1}")
    ws.cell(row=row, column=7).number_format = '0.0%'
    row += 1

    # Totals
    ws.cell(row=row, column=1, value="Total Sources").font = Font(bold=True, name="Arial", size=9)
    ws.cell(row=row, column=2, value=f"=SUM(B{sources_start}:B{row-1})")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=2).fill = TOTAL_FILL

    ws.cell(row=row, column=5, value="Total Uses").font = Font(bold=True, name="Arial", size=9)
    ws.cell(row=row, column=6, value=f"=SUM(F{sources_start}:F{row-1})")
    ws.cell(row=row, column=6).number_format = '#,##0.0'
    ws.cell(row=row, column=6).fill = TOTAL_FILL

    ws.cell(row=row, column=8, value="Check:")
    ws.cell(row=row, column=9, value=f"=B{row}-F{row}")
    ws.cell(row=row, column=9).number_format = '#,##0.0'
    sources_total_row = row
    row += 2

    # ========== SECTION 3: PROJECTIONS ==========
    ws.cell(row=row, column=1, value="3. OPERATING PROJECTIONS").font = SECTION_FONT
    row += 1

    years = ["", "LTM", "Y1", "Y2", "Y3", "Y4", "Y5"]
    for col, yr in enumerate(years, start=1):
        ws.cell(row=row, column=col, value=yr)
    style_header(ws, row, 1, 7)
    row += 1

    proj_start = row
    # Revenue
    ws.cell(row=row, column=1, value="Revenue").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"={input_cells['LTM Revenue']}")
    for col in range(3, 8):
        prev_col = get_column_letter(col - 1)
        ws.cell(row=row, column=col, value=f"={prev_col}{row}*(1+{input_cells['Revenue Growth (Y1-5)']})")
    for col in range(2, 8):
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    rev_row = row
    row += 1

    # EBITDA
    ws.cell(row=row, column=1, value="EBITDA").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"={input_cells['LTM EBITDA']}")
    # Interpolate margin from LTM to exit
    ltm_margin = f"{input_cells['LTM EBITDA']}/{input_cells['LTM Revenue']}"
    exit_margin = input_cells['EBITDA Margin (Exit)']
    for col in range(3, 8):
        year_num = col - 2
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{rev_row}*(({ltm_margin})+({exit_margin}-{ltm_margin})*{year_num}/5)")
    for col in range(2, 8):
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    ebitda_row = row
    row += 1

    # EBITDA Margin
    ws.cell(row=row, column=1, value="% Margin").font = CALC_FONT
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{ebitda_row}/{this_col}{rev_row}")
        ws.cell(row=row, column=col).number_format = '0.0%'
    row += 1

    # D&A (3% of revenue)
    ws.cell(row=row, column=1, value="D&A").font = CALC_FONT
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{rev_row}*0.03")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    da_row = row
    row += 1

    # CapEx (4% of revenue)
    ws.cell(row=row, column=1, value="CapEx").font = CALC_FONT
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"=-{this_col}{rev_row}*0.04")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    capex_row = row
    row += 1

    # NWC Change
    ws.cell(row=row, column=1, value="Δ NWC").font = CALC_FONT
    ws.cell(row=row, column=2, value="")
    for col in range(3, 8):
        this_col = get_column_letter(col)
        prev_col = get_column_letter(col - 1)
        ws.cell(row=row, column=col, value=f"=-({this_col}{rev_row}-{prev_col}{rev_row})*0.10")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
    nwc_row = row
    row += 1

    # Unlevered FCF
    ws.cell(row=row, column=1, value="Unlevered FCF").font = Font(bold=True, name="Arial", size=9)
    for col in range(2, 8):
        this_col = get_column_letter(col)
        ws.cell(row=row, column=col, value=f"={this_col}{ebitda_row}*(1-{input_cells['Tax Rate']})+{this_col}{da_row}+{this_col}{capex_row}+{this_col}{nwc_row}")
        ws.cell(row=row, column=col).number_format = '#,##0.0'
        ws.cell(row=row, column=col).fill = TOTAL_FILL
    ufcf_row = row
    row += 2

    # ========== SECTION 4: RETURNS ==========
    ws.cell(row=row, column=1, value="4. RETURNS ANALYSIS").font = SECTION_FONT
    row += 1

    # Exit Calculation
    ws.cell(row=row, column=1, value="Exit EBITDA (Y5)").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=G{ebitda_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    exit_ebitda_row = row
    row += 1

    ws.cell(row=row, column=1, value="Exit EV").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B{exit_ebitda_row}*{input_cells['Exit Multiple']}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    exit_ev_row = row
    row += 1

    # Simplified debt paydown (assume 50% paid down)
    ws.cell(row=row, column=1, value="Exit Debt (est.)").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=(B{sources_start}+B{sources_start+1})*0.5")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    exit_debt_row = row
    row += 1

    ws.cell(row=row, column=1, value="Exit Equity").font = Font(bold=True, name="Arial", size=9)
    ws.cell(row=row, column=2, value=f"=B{exit_ev_row}-B{exit_debt_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    ws.cell(row=row, column=2).fill = TOTAL_FILL
    exit_equity_row = row
    row += 2

    # Key Returns
    ws.cell(row=row, column=1, value="Entry Equity").font = CALC_FONT
    ws.cell(row=row, column=2, value=f"=B{equity_row}")
    ws.cell(row=row, column=2).number_format = '#,##0.0'
    entry_eq_row = row
    row += 1

    ws.cell(row=row, column=1, value="MOIC").font = RESULT_FONT
    ws.cell(row=row, column=2, value=f"=B{exit_equity_row}/B{entry_eq_row}")
    ws.cell(row=row, column=2).number_format = '0.00x'
    ws.cell(row=row, column=2).font = RESULT_FONT
    moic_row = row
    row += 1

    ws.cell(row=row, column=1, value="IRR").font = RESULT_FONT
    ws.cell(row=row, column=2, value=f"=(B{exit_equity_row}/B{entry_eq_row})^(1/{input_cells['Hold Period']})-1")
    ws.cell(row=row, column=2).number_format = '0.0%'
    ws.cell(row=row, column=2).font = RESULT_FONT
    irr_row = row
    row += 2

    # ========== SECTION 5: QUICK SENSITIVITY ==========
    ws.cell(row=row, column=1, value="5. EXIT MULTIPLE SENSITIVITY").font = SECTION_FONT
    row += 1

    ws.cell(row=row, column=1, value="Exit Mult").font = HEADER_FONT
    mults = [6.0, 7.0, 8.0, 9.0, 10.0]
    for i, m in enumerate(mults, start=2):
        ws.cell(row=row, column=i, value=m)
        ws.cell(row=row, column=i).number_format = '0.0x'
    style_header(ws, row, 1, 6)
    row += 1

    ws.cell(row=row, column=1, value="MOIC").font = CALC_FONT
    for i, m in enumerate(mults, start=2):
        ws.cell(row=row, column=i, value=f"=(B{exit_ebitda_row}*{m}-B{exit_debt_row})/B{entry_eq_row}")
        ws.cell(row=row, column=i).number_format = '0.00x'
    row += 1

    ws.cell(row=row, column=1, value="IRR").font = CALC_FONT
    for i, m in enumerate(mults, start=2):
        this_col = get_column_letter(i)
        ws.cell(row=row, column=i, value=f"=({this_col}{row-1})^(1/{input_cells['Hold Period']})-1")
        ws.cell(row=row, column=i).number_format = '0.0%'

    # Column widths
    ws.column_dimensions['A'].width = 22
    for col in range(2, 10):
        ws.column_dimensions[get_column_letter(col)].width = 10

    # Save
    if output_path is None:
        output_path = os.path.dirname(os.path.abspath(__file__))

    filename = f"Quick_Case_Template_{datetime.now().strftime('%Y%m%d')}.xlsx"
    filepath = os.path.join(output_path, filename)
    wb.save(filepath)

    print(f"Quick Case Template created: {filepath}")
    return filepath


if __name__ == "__main__":
    print("=" * 60)
    print("Quick Case Template Generator")
    print("=" * 60)
    create_quick_case_template()
    print("\nDesigned for 30-60 minute timed cases")
    print("All inputs at top, instant results below")
