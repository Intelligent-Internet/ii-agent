"""
PDF Extractor Skill

Extract financial data from CIM PDFs and other financial documents.
Uses PyMuPDF for text extraction with layout analysis, regex patterns
for financial line item matching, and openpyxl for Excel output.

Usage:
    skill = PDFExtractorSkill()
    skill.initialize()

    # Extract all financials from a CIM
    result = skill.execute("extract_financials",
        pdf_path="/path/to/cim.pdf",
        company_name="Acme Corp")

    # Export extracted data to Excel
    result = skill.execute("export_to_excel",
        extracted_data=result["extracted_data"],
        company_name="Acme Corp")
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from ii_skills import BaseSkill, register_skill

logger = logging.getLogger(__name__)

__version__ = "1.0.0"
__author__ = "II-Agent System"


@register_skill
class PDFExtractorSkill(BaseSkill):
    """Extract financial data from CIM PDFs into structured formats."""

    name = "pdf_extractor"
    version = __version__
    description = "Extract financials from CIMs and financial PDFs into Excel models"

    SKILL_DIR = Path(__file__).parent
    OUTPUT_DIR = SKILL_DIR / "output"

    def __init__(self, config: Optional[Dict] = None):
        super().__init__(config)
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def validate_config(self) -> List[str]:
        issues = []
        try:
            import fitz  # noqa: F401
        except ImportError:
            issues.append("pymupdf (fitz) is required but not installed")
        return issues

    def get_capabilities(self) -> List[str]:
        return [
            "extract_financials",
            "extract_income_statement",
            "extract_balance_sheet",
            "extract_key_metrics",
            "extract_text",
            "export_to_excel",
        ]

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a PDF extraction action."""
        actions = {
            "extract_financials": self._extract_financials,
            "extract_income_statement": self._extract_income_statement,
            "extract_balance_sheet": self._extract_balance_sheet,
            "extract_key_metrics": self._extract_key_metrics,
            "extract_text": self._extract_text,
            "export_to_excel": self._export_to_excel,
        }

        handler = actions.get(action)
        if not handler:
            raise NotImplementedError(f"Action '{action}' not implemented")
        return handler(**kwargs)

    # ------------------------------------------------------------------
    # Extraction Actions
    # ------------------------------------------------------------------

    def _extract_financials(
        self,
        pdf_path: str,
        company_name: str = "Company",
        **kwargs,
    ) -> Dict:
        """Extract all financial statements and metrics from a CIM PDF."""
        from .extractor import extract_all_financials

        pdf_path = str(Path(pdf_path).resolve())
        if not Path(pdf_path).exists():
            return {"success": False, "error": f"PDF not found: {pdf_path}"}

        result = extract_all_financials(pdf_path)

        # Save JSON output
        json_path = self.OUTPUT_DIR / f"{company_name.replace(' ', '_')}_extracted.json"
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2, default=str)

        return {
            "success": True,
            "extracted_data": result,
            "output_path": str(json_path),
            "summary": result.get("extraction_summary", ""),
        }

    def _extract_income_statement(
        self,
        pdf_path: str,
        **kwargs,
    ) -> Dict:
        """Extract just the income statement from a PDF."""
        from .extractor import extract_pages, extract_financial_statement

        pages = extract_pages(pdf_path)
        result = extract_financial_statement(pages, "income_statement")

        return {
            "success": True,
            "statement_type": "income_statement",
            "years": result.get("years", []),
            "line_items": result.get("line_items", {}),
            "rows_matched": result.get("rows_matched", 0),
        }

    def _extract_balance_sheet(
        self,
        pdf_path: str,
        **kwargs,
    ) -> Dict:
        """Extract just the balance sheet from a PDF."""
        from .extractor import extract_pages, extract_financial_statement

        pages = extract_pages(pdf_path)
        result = extract_financial_statement(pages, "balance_sheet")

        return {
            "success": True,
            "statement_type": "balance_sheet",
            "years": result.get("years", []),
            "line_items": result.get("line_items", {}),
            "rows_matched": result.get("rows_matched", 0),
        }

    def _extract_key_metrics(
        self,
        pdf_path: str,
        **kwargs,
    ) -> Dict:
        """Extract key financial metrics from unstructured text."""
        from .extractor import extract_pages, extract_metrics_from_text

        pages = extract_pages(pdf_path)
        full_text = "\n".join(p["text"] for p in pages)
        metrics = extract_metrics_from_text(full_text)

        return {
            "success": True,
            "metrics": metrics,
            "metrics_found": len(metrics),
        }

    def _extract_text(
        self,
        pdf_path: str,
        pages: Optional[List[int]] = None,
        **kwargs,
    ) -> Dict:
        """Extract raw text from a PDF (for non-financial documents).

        Args:
            pdf_path: Path to PDF file
            pages: Optional list of page numbers (0-indexed) to extract
        """
        from .extractor import extract_pages

        all_pages = extract_pages(pdf_path)

        if pages:
            selected = [p for p in all_pages if p["page_num"] in pages]
        else:
            selected = all_pages

        text_by_page = {p["page_num"]: p["text"] for p in selected}
        full_text = "\n\n".join(p["text"] for p in selected)

        return {
            "success": True,
            "text": full_text,
            "pages": text_by_page,
            "page_count": len(all_pages),
            "extracted_pages": len(selected),
        }

    # ------------------------------------------------------------------
    # Export Actions
    # ------------------------------------------------------------------

    def _export_to_excel(
        self,
        extracted_data: Dict[str, Any],
        company_name: str = "Company",
        output_path: Optional[str] = None,
        **kwargs,
    ) -> Dict:
        """Write extracted financial data to a formatted Excel workbook.

        Args:
            extracted_data: Output from extract_financials
            company_name: Company name for headers
            output_path: Optional custom output path
        """
        from .excel_writer import write_extraction_to_excel

        if not output_path:
            safe_name = company_name.replace(" ", "_").replace("/", "-")
            output_path = str(self.OUTPUT_DIR / f"{safe_name}_financials.xlsx")

        write_extraction_to_excel(extracted_data, output_path, company_name)

        return {
            "success": True,
            "output_path": output_path,
            "company_name": company_name,
            "sheets": _count_sheets(extracted_data),
        }


def _count_sheets(data: Dict) -> int:
    """Count how many sheets will be created."""
    count = 0
    if data.get("income_statement", {}).get("line_items"):
        count += 1
    if data.get("balance_sheet", {}).get("line_items"):
        count += 1
    if data.get("cash_flow", {}).get("line_items"):
        count += 1
    if data.get("metrics"):
        count += 1
    return max(count, 1)  # Always at least summary sheet


def get_pdf_extractor(config: Optional[Dict] = None) -> PDFExtractorSkill:
    """Get an instance of the PDF Extractor skill."""
    skill = PDFExtractorSkill(config)
    skill.initialize()
    return skill
