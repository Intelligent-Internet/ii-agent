"""
Core PDF Text Extraction Engine

Uses PyMuPDF (fitz) for text extraction with layout preservation.
Groups text blocks into rows/columns to reconstruct tabular data.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .patterns import (
    STATEMENT_HEADERS,
    INCOME_STATEMENT_LABELS,
    BALANCE_SHEET_LABELS,
    CASH_FLOW_LABELS,
    METRIC_PATTERNS,
    match_line_item,
    parse_number,
    detect_years,
)

logger = logging.getLogger(__name__)

# Y-coordinate tolerance for grouping text into same row (points)
ROW_TOLERANCE = 4.0
# Minimum number of numeric columns to consider something a table
MIN_TABLE_COLUMNS = 2


def extract_pages(pdf_path: str) -> List[Dict[str, Any]]:
    """Extract text blocks from all pages of a PDF.

    Returns list of page dicts with:
        - page_num: 0-indexed page number
        - text: plain text of the page
        - blocks: list of (x0, y0, x1, y1, text, block_type, block_no) tuples
        - width, height: page dimensions
    """
    import fitz  # PyMuPDF

    doc = fitz.open(pdf_path)
    pages = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("blocks")  # Returns list of block tuples

        pages.append({
            "page_num": page_num,
            "text": page.get_text(),
            "blocks": blocks,
            "width": page.rect.width,
            "height": page.rect.height,
        })

    doc.close()
    return pages


def find_statement_pages(
    pages: List[Dict],
    statement_type: str,
) -> List[int]:
    """Find pages containing a specific financial statement.

    Args:
        pages: Output from extract_pages()
        statement_type: Key from STATEMENT_HEADERS (income_statement, balance_sheet, cash_flow)

    Returns:
        List of page numbers (0-indexed) containing the statement
    """
    patterns = STATEMENT_HEADERS.get(statement_type, [])
    found_pages = []

    for page in pages:
        for pattern in patterns:
            if re.search(pattern, page["text"], re.IGNORECASE):
                found_pages.append(page["page_num"])
                break

    return found_pages


def blocks_to_rows(blocks: List, row_tolerance: float = ROW_TOLERANCE) -> List[List[Dict]]:
    """Convert positioned text blocks into rows sorted by position.

    Groups blocks with similar Y-coordinates into rows,
    then sorts each row by X-coordinate (left to right).

    Returns list of rows, where each row is a list of:
        {"x": float, "y": float, "x2": float, "y2": float, "text": str}
    """
    if not blocks:
        return []

    # Filter to text blocks only (block_type == 0) and clean
    text_blocks = []
    for block in blocks:
        if len(block) >= 5 and block[4].strip():
            text_blocks.append({
                "x": block[0],
                "y": block[1],
                "x2": block[2],
                "y2": block[3],
                "text": block[4].strip().replace("\n", " "),
            })

    if not text_blocks:
        return []

    # Sort by Y position (top to bottom)
    text_blocks.sort(key=lambda b: b["y"])

    # Group into rows by Y-coordinate proximity
    rows = []
    current_row = [text_blocks[0]]
    current_y = text_blocks[0]["y"]

    for block in text_blocks[1:]:
        if abs(block["y"] - current_y) <= row_tolerance:
            current_row.append(block)
        else:
            rows.append(sorted(current_row, key=lambda b: b["x"]))
            current_row = [block]
            current_y = block["y"]

    if current_row:
        rows.append(sorted(current_row, key=lambda b: b["x"]))

    return rows


def extract_table_from_rows(
    rows: List[List[Dict]],
    label_patterns: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Extract a financial table from positioned rows.

    Identifies:
    1. Header row (containing year labels)
    2. Data rows (label + numbers)

    Returns:
        {
            "years": ["2022A", "2023A", "2024E", ...],
            "line_items": {
                "revenue": [100.0, 120.0, 150.0, ...],
                "cogs": [-60.0, -70.0, -85.0, ...],
                ...
            },
            "raw_labels": {"revenue": "Net Revenue", ...},
            "rows_matched": 5,
            "rows_unmatched": 2,
        }
    """
    result = {
        "years": [],
        "line_items": {},
        "raw_labels": {},
        "rows_matched": 0,
        "rows_unmatched": 0,
    }

    # Step 1: Find header row with year labels
    header_row_idx = None
    for i, row in enumerate(rows):
        row_text = " ".join(cell["text"] for cell in row)
        years = detect_years(row_text)
        if len(years) >= MIN_TABLE_COLUMNS:
            result["years"] = years
            header_row_idx = i
            break

    if header_row_idx is None:
        return result

    # Step 2: Determine column positions from header
    # The first column is labels, remaining are data
    num_cols = len(row) if header_row_idx is not None else 0

    # Step 3: Parse data rows
    for row in rows[header_row_idx + 1:]:
        if not row:
            continue

        # First cell is usually the label
        label_text = row[0]["text"]

        # Skip section headers (often bold/all caps with no numbers)
        data_cells = row[1:] if len(row) > 1 else []
        numbers = [parse_number(cell["text"]) for cell in data_cells]

        # If no parseable numbers, skip row
        if not any(n is not None for n in numbers):
            continue

        # Try to match the label
        canonical = match_line_item(label_text, label_patterns)

        if canonical:
            # Pad/trim numbers to match year count
            while len(numbers) < len(result["years"]):
                numbers.append(None)
            numbers = numbers[:len(result["years"])]

            result["line_items"][canonical] = numbers
            result["raw_labels"][canonical] = label_text
            result["rows_matched"] += 1
        else:
            result["rows_unmatched"] += 1

    return result


def extract_metrics_from_text(text: str) -> Dict[str, Optional[float]]:
    """Extract key financial metrics from unstructured text.

    Looks for patterns like "EBITDA Margin: 25.3%" or "Revenue Growth of 12%".
    """
    metrics = {}

    for metric_name, pattern in METRIC_PATTERNS.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = parse_number(match.group(1))
            if value is not None:
                metrics[metric_name] = value

    return metrics


def extract_financial_statement(
    pages: List[Dict],
    statement_type: str,
) -> Dict[str, Any]:
    """Extract a specific financial statement from PDF pages.

    Args:
        pages: Output from extract_pages()
        statement_type: 'income_statement', 'balance_sheet', or 'cash_flow'

    Returns:
        Extracted table data dict
    """
    label_map = {
        "income_statement": INCOME_STATEMENT_LABELS,
        "balance_sheet": BALANCE_SHEET_LABELS,
        "cash_flow": CASH_FLOW_LABELS,
    }
    labels = label_map.get(statement_type, INCOME_STATEMENT_LABELS)

    # Find relevant pages
    statement_pages = find_statement_pages(pages, statement_type)

    if not statement_pages:
        logger.warning(f"No pages found for {statement_type}")
        return {"years": [], "line_items": {}, "raw_labels": {}, "rows_matched": 0, "rows_unmatched": 0}

    # Try each page until we get a good extraction
    best_result = None
    best_match_count = 0

    for page_num in statement_pages:
        page = pages[page_num]
        rows = blocks_to_rows(page["blocks"])
        result = extract_table_from_rows(rows, labels)

        if result["rows_matched"] > best_match_count:
            best_result = result
            best_match_count = result["rows_matched"]

    # If single page didn't work well, try combining consecutive pages
    if best_match_count < 3 and len(statement_pages) >= 2:
        for i in range(len(statement_pages) - 1):
            p1 = pages[statement_pages[i]]
            p2 = pages[statement_pages[i] + 1] if statement_pages[i] + 1 < len(pages) else None

            if p2:
                combined_blocks = p1["blocks"] + p2["blocks"]
                rows = blocks_to_rows(combined_blocks)
                result = extract_table_from_rows(rows, labels)

                if result["rows_matched"] > best_match_count:
                    best_result = result
                    best_match_count = result["rows_matched"]

    return best_result or {"years": [], "line_items": {}, "raw_labels": {}, "rows_matched": 0, "rows_unmatched": 0}


def extract_all_financials(pdf_path: str) -> Dict[str, Any]:
    """Extract all financial statements and metrics from a CIM PDF.

    Returns:
        {
            "income_statement": {...},
            "balance_sheet": {...},
            "cash_flow": {...},
            "metrics": {...},
            "page_count": int,
            "extraction_summary": str,
        }
    """
    pages = extract_pages(pdf_path)

    result = {
        "income_statement": extract_financial_statement(pages, "income_statement"),
        "balance_sheet": extract_financial_statement(pages, "balance_sheet"),
        "cash_flow": extract_financial_statement(pages, "cash_flow"),
        "metrics": {},
        "page_count": len(pages),
        "extraction_summary": "",
    }

    # Extract metrics from full text
    full_text = "\n".join(p["text"] for p in pages)
    result["metrics"] = extract_metrics_from_text(full_text)

    # Summary
    is_items = len(result["income_statement"].get("line_items", {}))
    bs_items = len(result["balance_sheet"].get("line_items", {}))
    cf_items = len(result["cash_flow"].get("line_items", {}))
    metric_count = len(result["metrics"])

    result["extraction_summary"] = (
        f"Extracted {is_items} P&L items, {bs_items} BS items, "
        f"{cf_items} CF items, {metric_count} metrics from {len(pages)} pages"
    )

    return result
