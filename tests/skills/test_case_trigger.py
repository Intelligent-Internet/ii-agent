"""
Unit tests for case_trigger.py — CaseStudyTrigger, CaseSetupResult.
"""

import json
import pytest
from pathlib import Path

from ii_skills.shared.case_trigger import (
    CaseStudyTrigger,
    CaseSetupResult,
    DEAL_FOLDER_TEMPLATES,
)


# ---------------------------------------------------------------------------
# CaseSetupResult
# ---------------------------------------------------------------------------

class TestCaseSetupResult:

    def test_default_success(self):
        result = CaseSetupResult()
        assert result.success is True
        assert result.files_copied == []
        assert result.errors == []

    def test_summary_format(self):
        result = CaseSetupResult(
            company_name="Acme Corp",
            case_type="lbo",
            deal_folder="/output/cases/2026-02-05_acme_corp_lbo",
            subfolders=["01_cim", "02_models"],
            created_at="2026-02-05 10:00 UTC",
        )
        text = result.summary
        assert "Acme Corp" in text
        assert "lbo" in text
        assert "01_cim" in text
        assert "02_models" in text

    def test_summary_with_errors(self):
        result = CaseSetupResult(errors=["File not found: test.pdf"])
        text = result.summary
        assert "File not found" in text
        assert "Warnings" in text

    def test_to_dict(self):
        result = CaseSetupResult(
            company_name="Test",
            case_type="lbo",
            deal_folder="/tmp/test",
        )
        d = result.to_dict()
        assert d["company_name"] == "Test"
        assert d["case_type"] == "lbo"
        assert d["deal_folder"] == "/tmp/test"


# ---------------------------------------------------------------------------
# CaseStudyTrigger
# ---------------------------------------------------------------------------

class TestCaseStudyTrigger:

    @pytest.fixture
    def trigger(self, tmp_path):
        return CaseStudyTrigger(base_dir=str(tmp_path / "cases"))

    def test_start_case_lbo(self, trigger, tmp_path):
        result = trigger.start_case("Acme Corp", case_type="lbo")

        assert result.success is True
        assert result.company_name == "Acme Corp"
        assert result.case_type == "lbo"
        assert Path(result.deal_folder).exists()
        assert len(result.subfolders) == 6  # LBO has 6 subfolders
        assert "01_cim" in result.subfolders
        assert "02_models" in result.subfolders
        assert "06_ic_materials" in result.subfolders

        # All subfolders should exist
        for sf in result.subfolders:
            assert Path(result.subfolder_paths[sf]).exists()

    def test_start_case_growth_equity(self, trigger):
        result = trigger.start_case("Widget Inc", case_type="growth_equity")
        assert result.success is True
        assert result.case_type == "growth_equity"
        assert len(result.subfolders) == 5

    def test_start_case_unknown_type_defaults_to_general(self, trigger):
        result = trigger.start_case("Unknown Corp", case_type="weird_type")
        assert result.success is True
        assert result.case_type == "general"

    def test_case_config_written(self, trigger):
        result = trigger.start_case("Config Corp", case_type="lbo")
        config_path = Path(result.deal_folder) / "case_config.json"
        assert config_path.exists()

        config = json.loads(config_path.read_text())
        assert config["company_name"] == "Config Corp"
        assert config["case_type"] == "lbo"
        assert config["status"] == "active"

    def test_cim_placed_in_correct_subfolder(self, trigger, tmp_path):
        # Create a fake CIM PDF
        cim_file = tmp_path / "Acme_CIM.pdf"
        cim_file.write_bytes(b"fake pdf content")

        result = trigger.start_case(
            "Acme Corp",
            case_type="lbo",
            cim_path=str(cim_file),
        )

        assert result.success is True
        assert len(result.files_copied) == 1
        assert result.files_copied[0]["subfolder"] == "01_cim"
        assert result.files_copied[0]["filename"] == "Acme_CIM.pdf"

        # File should actually exist in destination
        dest = Path(result.files_copied[0]["destination"])
        assert dest.exists()

    def test_model_placed_in_correct_subfolder(self, trigger, tmp_path):
        model_file = tmp_path / "Acme_Model.xlsx"
        model_file.write_bytes(b"fake excel data")

        result = trigger.start_case(
            "Acme Corp",
            case_type="lbo",
            model_path=str(model_file),
        )

        assert len(result.files_copied) == 1
        assert result.files_copied[0]["subfolder"] == "02_models"

    def test_both_files_placed(self, trigger, tmp_path):
        cim = tmp_path / "cim.pdf"
        cim.write_bytes(b"pdf")
        model = tmp_path / "model.xlsx"
        model.write_bytes(b"excel")

        result = trigger.start_case(
            "Both Corp",
            case_type="lbo",
            cim_path=str(cim),
            model_path=str(model),
        )

        assert len(result.files_copied) == 2

    def test_additional_files(self, trigger, tmp_path):
        pptx = tmp_path / "slides.pptx"
        pptx.write_bytes(b"pptx")
        doc = tmp_path / "memo.docx"
        doc.write_bytes(b"docx")

        result = trigger.start_case(
            "Files Corp",
            case_type="lbo",
            additional_files={
                "slides.pptx": str(pptx),
                "memo.docx": str(doc),
            },
        )

        assert len(result.files_copied) == 2
        # pptx -> presentations, docx -> cim
        subfolders_used = {f["subfolder"] for f in result.files_copied}
        assert "03_presentations" in subfolders_used
        assert "01_cim" in subfolders_used

    def test_missing_file_warning(self, trigger):
        result = trigger.start_case(
            "Missing Corp",
            case_type="lbo",
            cim_path="/nonexistent/file.pdf",
        )

        assert result.success is True  # Overall still succeeds
        assert len(result.errors) == 1
        assert "not found" in result.errors[0]

    def test_list_cases_empty(self, trigger):
        cases = trigger.list_cases()
        assert cases == []

    def test_list_cases_after_creation(self, trigger):
        trigger.start_case("Alpha Corp", case_type="lbo")
        trigger.start_case("Beta Corp", case_type="growth_equity")

        cases = trigger.list_cases()
        assert len(cases) == 2

    def test_folder_name_format(self, trigger):
        result = trigger.start_case("My Test Company", case_type="lbo")
        folder_name = Path(result.deal_folder).name

        # Should contain date, normalized company name, and case type
        assert "my_test_company" in folder_name
        assert "lbo" in folder_name

    def test_all_deal_types(self, trigger):
        """All known deal types should create successfully."""
        for deal_type in DEAL_FOLDER_TEMPLATES:
            result = trigger.start_case(f"Test {deal_type}", case_type=deal_type)
            assert result.success is True
            assert len(result.subfolders) > 0

    def test_timeframe_stored_in_config(self, trigger):
        result = trigger.start_case(
            "Timeframe Corp",
            case_type="lbo",
            timeframe="24-hour",
        )
        config_path = Path(result.deal_folder) / "case_config.json"
        config = json.loads(config_path.read_text())
        assert config["timeframe"] == "24-hour"
