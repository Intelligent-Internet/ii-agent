"""
Unit tests for datastore_governance.py — QueryContext, AuditLogger, PermissionGuard.
"""

import json
import pytest
from pathlib import Path

from ii_skills.shared.datastore_governance import (
    QueryContext,
    AuditLogger,
    PermissionGuard,
)


# ---------------------------------------------------------------------------
# QueryContext
# ---------------------------------------------------------------------------

class TestQueryContext:

    def test_defaults(self):
        ctx = QueryContext(source_skill="ib_toolkit")
        assert ctx.source_skill == "ib_toolkit"
        assert ctx.source_action is None
        assert ctx.session_id is None
        assert ctx.correlation_id != ""
        assert ctx.reason == ""

    def test_full_construction(self):
        ctx = QueryContext(
            source_skill="ib_toolkit",
            source_action="quick_lbo_analysis",
            session_id="sess-123",
            reason="deal_analysis",
        )
        assert ctx.source_action == "quick_lbo_analysis"
        assert ctx.session_id == "sess-123"

    def test_to_dict(self):
        ctx = QueryContext(source_skill="test", reason="testing")
        d = ctx.to_dict()
        assert d["source_skill"] == "test"
        assert d["reason"] == "testing"
        assert "correlation_id" in d

    def test_unique_correlation_ids(self):
        ctx1 = QueryContext(source_skill="a")
        ctx2 = QueryContext(source_skill="b")
        assert ctx1.correlation_id != ctx2.correlation_id


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_audit_dir(tmp_path):
    return tmp_path / "audit"


@pytest.fixture
def audit_logger(tmp_audit_dir):
    return AuditLogger(log_dir=str(tmp_audit_dir))


class TestAuditLogger:

    def test_log_access_creates_file(self, audit_logger, tmp_audit_dir):
        ctx = QueryContext(source_skill="ib_toolkit", reason="test")
        audit_logger.log_access(ctx, "read", "portfolio_holdings", result_count=5)

        # Check file was created
        files = list(tmp_audit_dir.glob("*.jsonl"))
        assert len(files) == 1

        # Check content
        with open(files[0]) as f:
            entry = json.loads(f.readline())
        assert entry["source_skill"] == "ib_toolkit"
        assert entry["operation"] == "read"
        assert entry["entity_type"] == "portfolio_holdings"
        assert entry["result_count"] == 5
        assert entry["denied"] is False

    def test_log_access_appends(self, audit_logger, tmp_audit_dir):
        ctx = QueryContext(source_skill="test")
        audit_logger.log_access(ctx, "read", "a")
        audit_logger.log_access(ctx, "write", "b")

        files = list(tmp_audit_dir.glob("*.jsonl"))
        assert len(files) == 1

        with open(files[0]) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_log_denied_access(self, audit_logger, tmp_audit_dir):
        ctx = QueryContext(source_skill="pdf_extractor")
        audit_logger.log_access(
            ctx, "write", "portfolio_holdings",
            denied=True, error="Permission denied",
        )

        files = list(tmp_audit_dir.glob("*.jsonl"))
        with open(files[0]) as f:
            entry = json.loads(f.readline())
        assert entry["denied"] is True
        assert "Permission denied" in entry["error"]

    def test_get_recent_empty(self, audit_logger):
        results = audit_logger.get_recent()
        assert results == []

    def test_get_recent_with_filter(self, audit_logger):
        ctx_a = QueryContext(source_skill="skill_a")
        ctx_b = QueryContext(source_skill="skill_b")
        audit_logger.log_access(ctx_a, "read", "data")
        audit_logger.log_access(ctx_b, "read", "data")

        results = audit_logger.get_recent(skill_name="skill_a")
        assert len(results) == 1
        assert results[0]["source_skill"] == "skill_a"

    def test_get_recent_with_limit(self, audit_logger):
        ctx = QueryContext(source_skill="test")
        for i in range(10):
            audit_logger.log_access(ctx, "read", f"entity_{i}")

        results = audit_logger.get_recent(limit=3)
        assert len(results) == 3


# ---------------------------------------------------------------------------
# PermissionGuard
# ---------------------------------------------------------------------------

class TestPermissionGuard:

    def test_ib_toolkit_read_holdings(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="ib_toolkit")
        assert guard.check(ctx, "read", "portfolio_holdings") is True

    def test_ib_toolkit_write_holdings_denied(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="ib_toolkit")
        assert guard.check(ctx, "write", "portfolio_holdings") is False

    def test_ib_toolkit_write_deals_allowed(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="ib_toolkit")
        assert guard.check(ctx, "write", "deal_analyses") is True

    def test_networth_write_holdings_allowed(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="networth_newsletter")
        assert guard.check(ctx, "write", "portfolio_holdings") is True

    def test_unknown_skill_read_only(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="unknown_skill")
        assert guard.check(ctx, "read", "anything") is True
        assert guard.check(ctx, "write", "anything") is False
        assert guard.check(ctx, "delete", "anything") is False

    def test_unlisted_entity_read_only(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="ib_toolkit")
        # 'alerts' is not in ib_toolkit's policy
        assert guard.check(ctx, "read", "alerts") is True
        assert guard.check(ctx, "write", "alerts") is False

    def test_require_raises_on_deny(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="pdf_extractor")
        with pytest.raises(PermissionError, match="pdf_extractor"):
            guard.require(ctx, "write", "portfolio_holdings")

    def test_require_passes_on_allow(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="ib_toolkit")
        guard.require(ctx, "read", "company_profiles")  # Should not raise

    def test_require_logs_to_audit(self, tmp_path):
        audit = AuditLogger(log_dir=str(tmp_path / "audit"))
        guard = PermissionGuard(audit_logger=audit)
        ctx = QueryContext(source_skill="unknown")

        with pytest.raises(PermissionError):
            guard.require(ctx, "write", "data")

        # Check audit log has the denied entry
        entries = audit.get_recent()
        assert len(entries) == 1
        assert entries[0]["denied"] is True

    def test_custom_policies(self):
        policies = {
            "custom_skill": {
                "custom_entity": ["read", "write", "delete"],
            }
        }
        guard = PermissionGuard(policies=policies)
        ctx = QueryContext(source_skill="custom_skill")
        assert guard.check(ctx, "delete", "custom_entity") is True

    def test_get_skill_permissions(self):
        guard = PermissionGuard()
        perms = guard.get_skill_permissions("ib_toolkit")
        assert "deal_analyses" in perms
        assert "read" in perms["deal_analyses"]

    def test_set_skill_permissions(self):
        guard = PermissionGuard()
        guard.set_skill_permissions("new_skill", "new_entity", ["read", "write"])
        ctx = QueryContext(source_skill="new_skill")
        assert guard.check(ctx, "write", "new_entity") is True

    def test_deal_memory_delete_memories(self):
        guard = PermissionGuard()
        ctx = QueryContext(source_skill="deal_memory")
        assert guard.check(ctx, "delete", "skill_memories") is True
        assert guard.check(ctx, "read", "company_profiles") is True
