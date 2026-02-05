"""
Financial Pattern Matching for PDF Extraction

Regex patterns and label matching for identifying financial line items,
statement headers, year columns, and numeric values in CIM PDFs.
"""

import re
from typing import Dict, List, Optional, Tuple


# ============================================================
# FINANCIAL STATEMENT DETECTION
# ============================================================

STATEMENT_HEADERS = {
    "income_statement": [
        r"(?:Consolidated\s+)?(?:Statements?\s+of\s+)?(?:Income|Operations|Earnings)",
        r"Income\s+Statement",
        r"Profit\s+(?:and|&)\s+Loss",
        r"P\s*&\s*L",
        r"Operating\s+Results",
    ],
    "balance_sheet": [
        r"(?:Consolidated\s+)?Balance\s+Sheet",
        r"(?:Consolidated\s+)?Statements?\s+of\s+Financial\s+Position",
        r"Assets\s+(?:and|&)\s+Liabilities",
    ],
    "cash_flow": [
        r"(?:Consolidated\s+)?(?:Statements?\s+of\s+)?Cash\s+Flow",
        r"Cash\s+Flow\s+Statement",
    ],
}


# ============================================================
# LINE ITEM PATTERNS
# ============================================================

INCOME_STATEMENT_LABELS = {
    # Revenue
    "revenue": [
        r"(?:Net\s+)?Revenue",
        r"(?:Total\s+)?Sales",
        r"Net\s+Sales",
        r"Total\s+Revenue",
        r"Gross\s+Revenue",
    ],
    # COGS
    "cogs": [
        r"Cost\s+of\s+(?:Goods\s+)?(?:Sold|Sales|Revenue)",
        r"COGS",
        r"Cost\s+of\s+Products\s+Sold",
    ],
    # Gross Profit
    "gross_profit": [
        r"Gross\s+Profit",
        r"Gross\s+Margin",
        r"Gross\s+Income",
    ],
    # Operating expenses
    "sg_and_a": [
        r"(?:Selling,?\s+)?General\s+(?:and|&)\s+Administrative",
        r"SG&A",
        r"SG\s*&\s*A",
    ],
    "rd_expense": [
        r"Research\s+(?:and|&)\s+Development",
        r"R\s*&\s*D",
    ],
    "total_opex": [
        r"Total\s+Operating\s+Expenses",
        r"Total\s+Expenses",
        r"Operating\s+Expenses",
    ],
    # EBITDA
    "ebitda": [
        r"(?:Adjusted\s+)?EBITDA",
    ],
    # D&A
    "depreciation": [
        r"Depreciation\s+(?:and|&)\s+Amortization",
        r"D\s*&\s*A",
        r"Depreciation",
        r"Amortization",
    ],
    # Net Income (must come before EBIT to avoid false matches)
    "net_income": [
        r"Net\s+(?:Income|Profit|Loss|Earnings)",
    ],
    # Operating Income / EBIT
    "ebit": [
        r"Operating\s+(?:Income|Profit|Loss)",
        r"(?:Income|Profit|Loss)\s+from\s+Operations",
        r"EBIT(?:\b)",
    ],
    # Interest
    "interest_expense": [
        r"Interest\s+Expense",
        r"Net\s+Interest\s+(?:Expense|Income)",
        r"Interest,?\s+net",
    ],
    # Tax
    "income_tax": [
        r"(?:Income\s+)?Tax(?:es)?\s*(?:Expense|Provision)?",
        r"Provision\s+for\s+Income\s+Taxes",
    ],
}

BALANCE_SHEET_LABELS = {
    "cash": [r"Cash\s+(?:and|&)\s+(?:Cash\s+)?Equivalents", r"Cash"],
    "accounts_receivable": [r"Accounts?\s+Receivable", r"Trade\s+Receivables", r"AR"],
    "inventory": [r"(?:Total\s+)?Inventor(?:y|ies)"],
    "total_current_assets": [r"Total\s+Current\s+Assets"],
    "ppe": [r"Property,?\s+Plant\s+(?:and|&)\s+Equipment", r"PP&E", r"Fixed\s+Assets"],
    "goodwill": [r"Goodwill"],
    "total_assets": [r"Total\s+Assets"],
    "accounts_payable": [r"Accounts?\s+Payable", r"Trade\s+Payables", r"AP"],
    "total_current_liabilities": [r"Total\s+Current\s+Liabilities"],
    "long_term_debt": [r"Long[\s-]Term\s+Debt", r"Total\s+Debt"],
    "total_liabilities": [r"Total\s+Liabilities"],
    "total_equity": [r"Total\s+(?:Shareholders?'?\s+)?Equity", r"Total\s+Stockholders"],
    "total_liab_equity": [r"Total\s+Liabilities\s+(?:and|&)\s+(?:Shareholders?'?\s+)?Equity"],
}

CASH_FLOW_LABELS = {
    "cfo": [r"(?:Net\s+)?Cash\s+(?:Provided\s+by|from)\s+Operating", r"Operating\s+Cash\s+Flow"],
    "capex": [r"Capital\s+Expenditures?", r"CapEx", r"Purchases?\s+of\s+Property"],
    "cfi": [r"(?:Net\s+)?Cash\s+(?:Used\s+in|from)\s+Investing", r"Investing\s+Cash\s+Flow"],
    "cff": [r"(?:Net\s+)?Cash\s+(?:from|Used\s+in)\s+Financing", r"Financing\s+Cash\s+Flow"],
    "fcf": [r"Free\s+Cash\s+Flow", r"FCF"],
}


# ============================================================
# KEY METRICS PATTERNS
# ============================================================

METRIC_PATTERNS = {
    "revenue_growth": r"Revenue\s+Growth[\s:]+([(\d]+[\d.]+)%?\)?",
    "ebitda_margin": r"EBITDA\s+Margin[\s:]+([(\d]+[\d.]+)%?\)?",
    "gross_margin": r"Gross\s+Margin[\s:]+([(\d]+[\d.]+)%?\)?",
    "net_margin": r"Net\s+(?:Income\s+)?Margin[\s:]+([(\d]+[\d.]+)%?\)?",
    "capex_pct": r"CapEx\s+(?:as\s+)?%?\s*(?:of\s+)?Revenue[\s:]+([(\d]+[\d.]+)%?\)?",
    "leverage": r"(?:Net\s+)?Leverage[\s:]+([(\d]+[\d.]+)x?\)?",
    "debt_to_ebitda": r"(?:Total\s+)?Debt\s*/\s*EBITDA[\s:]+([(\d]+[\d.]+)x?\)?",
}


# ============================================================
# YEAR DETECTION
# ============================================================

YEAR_PATTERNS = [
    r"(?:FY\s*)?20[1-3]\d(?:A|E|P|F)?",  # FY2024A, 2025E, etc.
    r"(?:FYE?\s+)?(?:Dec|Jan|Mar|Jun|Sep)[\s-]?(?:20)?[1-3]\d",  # Dec-24, FYE Mar-25
    r"LTM",  # Last Twelve Months
    r"NTM",  # Next Twelve Months
    r"TTM",  # Trailing Twelve Months
]


# ============================================================
# NUMBER PARSING
# ============================================================

# Matches financial numbers: $1,234.5, (1,234.5), $1.2M, 1,234, 12.5%
NUMBER_PATTERN = re.compile(
    r"""
    \(?\$?\s*                       # Optional opening paren and dollar sign
    (\d{1,3}(?:,\d{3})*(?:\.\d+)?) # Number with optional commas and decimals
    \s*(?:[MmBbKk])?               # Optional magnitude suffix
    \s*%?\)?                       # Optional percent and closing paren
    """,
    re.VERBOSE,
)


def parse_number(text: str) -> Optional[float]:
    """Parse a financial number string into a float.

    Handles: $1,234.5, (1,234.5), 1.2M, 1,234, 12.5%, --
    Returns None if not parseable.
    """
    text = text.strip()

    # Skip dashes, blanks, N/A
    if text in ("", "-", "--", "—", "n/a", "N/A", "nm", "NM"):
        return None

    is_negative = "(" in text and ")" in text

    # Remove formatting characters
    cleaned = text.replace("$", "").replace(",", "").replace("(", "").replace(")", "").replace("%", "").strip()

    # Handle magnitude suffixes
    multiplier = 1.0
    if cleaned.endswith(("M", "m")):
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith(("B", "b")):
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]
    elif cleaned.endswith(("K", "k")):
        multiplier = 1_000
        cleaned = cleaned[:-1]

    try:
        value = float(cleaned) * multiplier
        return -value if is_negative else value
    except (ValueError, TypeError):
        return None


def match_line_item(label: str, patterns_dict: Dict[str, List[str]]) -> Optional[str]:
    """Match a text label against known financial line item patterns.

    Returns the canonical name (dict key) or None.
    """
    label_clean = label.strip()
    for canonical_name, patterns in patterns_dict.items():
        for pattern in patterns:
            if re.search(pattern, label_clean, re.IGNORECASE):
                return canonical_name
    return None


def detect_years(text: str) -> List[str]:
    """Extract year labels from header text."""
    years = []
    for pattern in YEAR_PATTERNS:
        matches = re.findall(pattern, text)
        years.extend(matches)
    return years
