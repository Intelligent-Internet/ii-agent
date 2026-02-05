"""Shared fixtures for integration tests.

These fixtures provide pre-configured skill instances, mock data,
and test utilities for end-to-end testing.
"""

import pytest
from pathlib import Path
from typing import Dict


# ============================================================
# Paths
# ============================================================

@pytest.fixture
def test_output_dir(tmp_path):
    """Temporary output directory for test-generated files."""
    output = tmp_path / "test_output"
    output.mkdir()
    return output


@pytest.fixture
def workspace_path(tmp_path):
    """Simulated workspace path (like ~/.ii_agent/workspace)."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    return str(ws)


# ============================================================
# Skills
# ============================================================

@pytest.fixture
def ib_toolkit():
    """Get an initialized IB Toolkit skill instance."""
    from ii_skills import get_skill

    skill = get_skill("ib_toolkit")
    if skill is None:
        pytest.skip("ib_toolkit skill not available")
    skill.initialize()
    return skill


@pytest.fixture
def ir_toolkit():
    """Get an initialized IR Toolkit skill instance."""
    from ii_skills import get_skill

    skill = get_skill("ir_toolkit")
    if skill is None:
        pytest.skip("ir_toolkit skill not available")
    skill.initialize()
    return skill


# ============================================================
# Bridge
# ============================================================

@pytest.fixture
def skill_tool_ib(ib_toolkit, workspace_path):
    """Get a SkillTool wrapping the IB Toolkit."""
    from ii_skills.bridge import SkillTool

    return SkillTool(ib_toolkit, workspace_path=workspace_path)


@pytest.fixture
def all_skill_tools(workspace_path):
    """Get all available skill tools."""
    from ii_skills.bridge import get_skill_tools

    return get_skill_tools(workspace_path=workspace_path)


# ============================================================
# Sample Data
# ============================================================

@pytest.fixture
def sample_lbo_params() -> Dict:
    """Standard LBO analysis parameters for testing."""
    return {
        "ebitda": 50.0,
        "entry_multiple": 8.0,
        "exit_multiple": 9.0,
        "leverage": 4.0,
        "hold_years": 5,
        "ebitda_growth": 0.08,
    }


@pytest.fixture
def sample_company_params() -> Dict:
    """Standard company parameters for testing."""
    return {
        "company_name": "Test Corp",
        "ticker": "TEST",
        "entry_multiple": 8.0,
        "exit_multiple": 8.0,
        "hold_period": 5,
    }


@pytest.fixture
def sample_capital_structure_params() -> Dict:
    """Standard capital structure parameters for testing."""
    return {
        "ebitda": 50.0,
        "revenue": 200.0,
        "capex": 15.0,
        "industry": "industrials",
        "existing_debt": 0,
        "revenue_volatility": "moderate",
    }


@pytest.fixture
def sample_qoe_params() -> Dict:
    """Standard quality of earnings parameters for testing."""
    return {
        "revenue": 200.0,
        "reported_ebitda": 50.0,
        "company_name": "Test Corp",
        "period": "LTM",
        "adjustments": [
            {
                "description": "One-time restructuring",
                "amount": 5.0,
                "category": "ONE_TIME",
                "risk": "LOW",
            },
            {
                "description": "Related party lease adjustment",
                "amount": 2.0,
                "category": "RELATED_PARTY",
                "risk": "HIGH",
            },
        ],
    }
