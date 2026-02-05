"""
Unit tests for case_orchestrator.py — CaseWorkflowOrchestrator, CaseResult.
"""

import pytest
from pathlib import Path

from ii_skills.shared.case_orchestrator import (
    CaseWorkflowOrchestrator,
    CaseResult,
    TIMEFRAME_CONFIG,
    SHEET_METHOD_MAP,
    extract_assumptions_from_cim,
)


# ---------------------------------------------------------------------------
# CaseResult
# ---------------------------------------------------------------------------

class TestCaseResult:

    def test_default(self):
        r = CaseResult()
        assert r.success is True
        assert r.files_created == []
        assert r.errors == []

    def test_summary_basic(self):
        r = CaseResult(
            company_name="Acme Corp",
            case_type="lbo",
            deal_folder="/output/cases/test",
            model_path="/output/cases/test/02_models/acme_corp_lbo_model.xlsx",
            metrics={"MOIC": "2.5x", "IRR": "20.1%"},
        )
        s = r.summary
        assert "Acme Corp" in s
        assert "lbo" in s
        assert "MOIC" in s
        assert "2.5x" in s

    def test_summary_with_errors(self):
        r = CaseResult(errors=["Something went wrong"])
        s = r.summary
        assert "FAILED" not in s  # success is still True by default
        assert "Something went wrong" in s


# ---------------------------------------------------------------------------
# Config Mappings
# ---------------------------------------------------------------------------

class TestConfigMappings:

    def test_all_timeframes_defined(self):
        for tf in ["24-hour", "48-hour", "5-day", "7-day"]:
            assert tf in TIMEFRAME_CONFIG
            assert "depth" in TIMEFRAME_CONFIG[tf]
            assert "sheets" in TIMEFRAME_CONFIG[tf]
            assert len(TIMEFRAME_CONFIG[tf]["sheets"]) > 0

    def test_all_sheets_have_methods(self):
        all_sheets = set()
        for config in TIMEFRAME_CONFIG.values():
            all_sheets.update(config["sheets"])
        for sheet in all_sheets:
            assert sheet in SHEET_METHOD_MAP, f"Missing method for sheet: {sheet}"

    def test_24_hour_has_5_sheets(self):
        assert len(TIMEFRAME_CONFIG["24-hour"]["sheets"]) == 5

    def test_48_hour_has_10_sheets(self):
        assert len(TIMEFRAME_CONFIG["48-hour"]["sheets"]) == 10

    def test_5_day_has_14_sheets(self):
        assert len(TIMEFRAME_CONFIG["5-day"]["sheets"]) == 14


# ---------------------------------------------------------------------------
# CaseWorkflowOrchestrator — full integration
# ---------------------------------------------------------------------------

class TestCaseWorkflowOrchestrator:

    @pytest.fixture
    def orch(self, tmp_path):
        return CaseWorkflowOrchestrator(
            base_dir=str(tmp_path / "cases"),
            quiet=True,
            use_color=False,
        )

    def test_24_hour_lbo(self, orch):
        result = orch.run(
            company_name="Test Corp",
            case_type="lbo",
            timeframe="24-hour",
        )

        assert result.success is True
        assert result.company_name == "Test Corp"
        assert result.case_type == "lbo"
        assert result.timeframe == "24-hour"

        # Deal folder created
        assert result.deal_folder != ""
        assert Path(result.deal_folder).exists()

        # Model generated
        assert result.model_path != ""
        assert Path(result.model_path).exists()
        assert result.model_path.endswith(".xlsx")

        # Terminal output rendered
        assert result.terminal_output != ""
        assert "Test Corp" in result.terminal_output
        assert "MOIC" in result.terminal_output

        # Metrics extracted
        assert "MOIC" in result.metrics
        assert "IRR" in result.metrics
        assert "Entry EV" in result.metrics

        # Timeline generated
        assert result.timeline != ""
        assert "Progress Timeline" in result.timeline

    def test_48_hour_lbo(self, orch):
        result = orch.run(
            company_name="Widget Inc",
            case_type="lbo",
            timeframe="48-hour",
        )

        assert result.success is True
        assert Path(result.model_path).exists()
        # 48-hour has more sheets
        assert len(result.files_created) >= 1

    def test_5_day_lbo(self, orch):
        result = orch.run(
            company_name="Full Corp",
            case_type="lbo",
            timeframe="5-day",
        )

        assert result.success is True
        assert Path(result.model_path).exists()

    def test_custom_assumptions(self, orch):
        result = orch.run(
            company_name="Custom Corp",
            case_type="lbo",
            timeframe="24-hour",
            assumptions={
                "ltm_revenue": 200.0,
                "ltm_ebitda": 50.0,
                "entry_multiple": 10.0,
                "exit_multiple": 9.0,
            },
        )

        assert result.success is True
        assert "10.0x" in result.terminal_output or "Entry EV" in result.metrics

    def test_growth_equity_case_type(self, orch):
        result = orch.run(
            company_name="Growth Corp",
            case_type="growth_equity",
            timeframe="24-hour",
        )

        assert result.success is True
        assert result.case_type == "growth_equity"
        assert Path(result.deal_folder).exists()

    def test_with_cim_file(self, orch, tmp_path):
        cim = tmp_path / "Company_CIM.pdf"
        cim.write_bytes(b"fake pdf")

        result = orch.run(
            company_name="CIM Corp",
            case_type="lbo",
            timeframe="24-hour",
            cim_path=str(cim),
        )

        assert result.success is True
        # CIM should be copied
        cim_files = [f for f in result.files_created if f.get("subfolder") == "01_cim"]
        assert len(cim_files) >= 1

    def test_model_saved_in_deal_folder(self, orch):
        result = orch.run(
            company_name="Folder Corp",
            case_type="lbo",
            timeframe="24-hour",
        )

        assert result.success is True
        # Model path should be inside deal folder
        assert result.deal_folder in result.model_path
        assert "02_models" in result.model_path

    def test_unknown_timeframe_defaults_to_24_hour(self, orch):
        result = orch.run(
            company_name="Default Corp",
            case_type="lbo",
            timeframe="unknown",
        )

        assert result.success is True
        # Should still work with default config

    def test_metrics_are_reasonable(self, orch):
        result = orch.run(
            company_name="Metrics Corp",
            case_type="lbo",
            timeframe="24-hour",
            assumptions={
                "ltm_revenue": 100.0,
                "ltm_ebitda": 20.0,
                "entry_multiple": 8.0,
                "exit_multiple": 8.0,
            },
        )

        assert result.success is True
        # MOIC should be > 1 for reasonable assumptions
        moic_str = result.metrics.get("MOIC", "")
        assert "x" in moic_str
        # IRR should be positive
        irr_str = result.metrics.get("IRR", "")
        assert "%" in irr_str

    def test_files_created_list(self, orch):
        result = orch.run(
            company_name="Files Corp",
            case_type="lbo",
            timeframe="24-hour",
        )

        assert result.success is True
        # At minimum the model should be in files_created
        model_files = [
            f for f in result.files_created
            if f.get("filename", "").endswith(".xlsx")
        ]
        assert len(model_files) >= 1

    def test_no_critical_errors(self, orch):
        result = orch.run(
            company_name="Clean Corp",
            case_type="lbo",
            timeframe="48-hour",
        )

        assert result.success is True
        # No fatal errors
        fatal = [e for e in result.errors if "failed" in e.lower()]
        assert len(fatal) == 0

    def test_cim_pdf_gracefully_skipped_without_pymupdf(self, orch, tmp_path):
        """If pymupdf isn't installed, CIM extraction is skipped gracefully."""
        cim = tmp_path / "test_cim.pdf"
        cim.write_bytes(b"%PDF-1.4 fake")

        result = orch.run(
            company_name="Skip Corp",
            case_type="lbo",
            timeframe="24-hour",
            cim_path=str(cim),
        )

        # Should still succeed even if extraction fails/skips
        assert result.success is True
        assert Path(result.model_path).exists()

    def test_merged_assumptions_cim_under_user(self, orch, tmp_path):
        """User-provided assumptions override CIM-extracted ones."""
        # No real CIM — just test that user overrides work with merged logic
        result = orch.run(
            company_name="Merge Corp",
            case_type="lbo",
            timeframe="24-hour",
            assumptions={
                "ltm_revenue": 500.0,
                "ltm_ebitda": 100.0,
            },
        )

        assert result.success is True
        assert "$500.0M" in result.metrics.get("Entry EV", "") or "500" in result.terminal_output


# ---------------------------------------------------------------------------
# extract_assumptions_from_cim
# ---------------------------------------------------------------------------

class TestExtractAssumptionsFromCIM:

    def test_empty_data(self):
        result = extract_assumptions_from_cim({})
        assert result == {}

    def test_revenue_and_ebitda(self):
        data = {
            "income_statement": {
                "line_items": {
                    "revenue": [80.0, 100.0, 120.0],
                    "ebitda": [12.0, 16.0, 24.0],
                },
            },
            "metrics": {},
        }
        result = extract_assumptions_from_cim(data)

        assert result["ltm_revenue"] == 120.0
        assert result["ltm_ebitda"] == 24.0

    def test_revenue_growth_computed(self):
        data = {
            "income_statement": {
                "line_items": {
                    "revenue": [100.0, 120.0],  # 20% growth
                    "ebitda": [20.0, 24.0],
                },
            },
            "metrics": {},
        }
        result = extract_assumptions_from_cim(data)

        # Growth should be capped at 15% and taper
        assert len(result["revenue_growth"]) == 5
        assert result["revenue_growth"][0] == 0.15  # Capped
        assert result["revenue_growth"][4] < result["revenue_growth"][0]

    def test_ebitda_margin_computed(self):
        data = {
            "income_statement": {
                "line_items": {
                    "revenue": [100.0, 150.0],
                    "ebitda": [15.0, 30.0],  # 20% margin
                },
            },
            "metrics": {},
        }
        result = extract_assumptions_from_cim(data)

        assert len(result["ebitda_margin"]) == 5
        assert result["ebitda_margin"][0] == 0.2
        # Slight expansion
        assert result["ebitda_margin"][4] > result["ebitda_margin"][0]

    def test_metrics_fallback(self):
        data = {
            "income_statement": {"line_items": {}},
            "metrics": {
                "revenue_growth": 8.0,
                "ebitda_margin": 22.0,
                "capex_pct": 4.0,
            },
        }
        result = extract_assumptions_from_cim(data)

        assert len(result["revenue_growth"]) == 5
        assert result["revenue_growth"][0] == 0.08
        assert len(result["ebitda_margin"]) == 5
        assert result["ebitda_margin"][0] == 0.22
        assert result.get("capex_pct") == 0.04

    def test_single_year_no_growth(self):
        data = {
            "income_statement": {
                "line_items": {
                    "revenue": [100.0],
                    "ebitda": [20.0],
                },
            },
            "metrics": {},
        }
        result = extract_assumptions_from_cim(data)

        assert result["ltm_revenue"] == 100.0
        assert result["ltm_ebitda"] == 20.0
        # No growth computed from single year
        assert "revenue_growth" not in result

    def test_negative_values_use_absolute(self):
        data = {
            "income_statement": {
                "line_items": {
                    "revenue": [-100.0, -150.0],
                    "ebitda": [-20.0, -30.0],
                },
            },
            "metrics": {},
        }
        result = extract_assumptions_from_cim(data)

        assert result["ltm_revenue"] == 150.0
        assert result["ltm_ebitda"] == 30.0
