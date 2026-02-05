#!/usr/bin/env python3
"""
Formula Builder - Cell reference and Excel formula utilities.

Provides helper methods for constructing Excel formulas programmatically,
used by ExcelModelGenerator to write real formulas instead of hardcoded values.
"""

from openpyxl.utils import get_column_letter


class FormulaBuilder:
    """Utility class for building Excel formula strings."""

    @staticmethod
    def col_letter(col: int) -> str:
        """Convert 1-based column number to letter. col_letter(2) → 'B'"""
        return get_column_letter(col)

    @staticmethod
    def ref(row: int, col: int, abs_row: bool = False, abs_col: bool = False) -> str:
        """Cell reference: ref(5, 2) → 'B5', ref(5, 2, True, True) → '$B$5'"""
        c = get_column_letter(col)
        c_str = f"${c}" if abs_col else c
        r_str = f"${row}" if abs_row else str(row)
        return f"{c_str}{r_str}"

    @staticmethod
    def sheet_ref(sheet: str, row: int, col: int, abs_row: bool = False, abs_col: bool = False) -> str:
        """Cross-sheet reference: sheet_ref('Operating Model', 10, 3) → \"'Operating Model'!C10\""""
        c = get_column_letter(col)
        c_str = f"${c}" if abs_col else c
        r_str = f"${row}" if abs_row else str(row)
        return f"'{sheet}'!{c_str}{r_str}"

    @staticmethod
    def sum_range(start_row: int, end_row: int, col: int) -> str:
        """SUM formula: sum_range(4, 6, 2) → '=SUM(B4:B6)'"""
        c = get_column_letter(col)
        return f"=SUM({c}{start_row}:{c}{end_row})"

    @staticmethod
    def sum_row_range(row: int, start_col: int, end_col: int) -> str:
        """SUM across columns: sum_row_range(18, 2, 6) → '=SUM(B18:F18)'"""
        sc = get_column_letter(start_col)
        ec = get_column_letter(end_col)
        return f"=SUM({sc}{row}:{ec}{row})"

    @staticmethod
    def avg_cells(row1: int, col1: int, row2: int, col2: int) -> str:
        """Average of two cells: avg_cells(5, 2, 8, 2) → '=(B5+B8)/2'"""
        r1 = f"{get_column_letter(col1)}{row1}"
        r2 = f"{get_column_letter(col2)}{row2}"
        return f"=({r1}+{r2})/2"

    @staticmethod
    def pct(numerator_row: int, denominator_row: int, col: int) -> str:
        """Division formula: pct(13, 10, 3) → '=C13/C10'"""
        c = get_column_letter(col)
        return f"={c}{numerator_row}/{c}{denominator_row}"

    @staticmethod
    def iferror(formula: str, fallback: str = "0") -> str:
        """Wrap formula in IFERROR: iferror('B5/B3', '0') → '=IFERROR(B5/B3,0)'
        If formula starts with '=', the '=' is stripped from the inner formula."""
        inner = formula.lstrip("=")
        return f"=IFERROR({inner},{fallback})"

    @staticmethod
    def max_zero(formula: str) -> str:
        """Wrap formula in MAX(0,...): max_zero('C10+C11') → '=MAX(0,C10+C11)'"""
        inner = formula.lstrip("=")
        return f"=MAX(0,{inner})"
