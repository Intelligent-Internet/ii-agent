"""
DataStore Governance — QueryContext, AuditLogger, and PermissionGuard.

Provides:
- QueryContext: Tracks who is querying what and why
- AuditLogger: Append-only JSONL audit log of DataStore access
- PermissionGuard: Skill-level access control for DataStore operations

Usage:
    from ii_skills.shared.datastore_governance import (
        QueryContext, AuditLogger, PermissionGuard
    )

    ctx = QueryContext(source_skill="ib_toolkit", reason="deal_analysis")
    guard = PermissionGuard()
    guard.require(ctx, "write", "deal_analyses")  # OK
    guard.require(ctx, "write", "portfolio_holdings")  # raises PermissionError

    audit = AuditLogger()
    audit.log_access(ctx, "read", "portfolio_holdings", result_count=42)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# QueryContext
# ---------------------------------------------------------------------------

@dataclass
class QueryContext:
    """Metadata attached to DataStore operations for audit and permission checks."""
    source_skill: str
    source_action: Optional[str] = None
    session_id: Optional[str] = None
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_skill": self.source_skill,
            "source_action": self.source_action,
            "session_id": self.session_id,
            "correlation_id": self.correlation_id,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------

class AuditLogger:
    """Append-only log of DataStore access.

    Writes JSONL files to: log_dir/YYYY-MM-DD.jsonl
    """

    def __init__(self, log_dir: Optional[str] = None):
        """Initialize AuditLogger.

        Args:
            log_dir: Directory for audit log files. Defaults to "logs/audit".
        """
        self._log_dir = Path(log_dir) if log_dir else Path("logs/audit")

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def log_access(
        self,
        context: QueryContext,
        operation: str,
        entity_type: str,
        result_count: int = 0,
        denied: bool = False,
        error: Optional[str] = None,
    ) -> None:
        """Log a DataStore access event.

        Args:
            context: The QueryContext for this operation.
            operation: The operation type (read, write, create, delete).
            entity_type: The data entity accessed (portfolio_holdings, etc.).
            result_count: Number of results returned.
            denied: Whether the operation was denied by PermissionGuard.
            error: Optional error message.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_skill": context.source_skill,
            "source_action": context.source_action,
            "session_id": context.session_id,
            "correlation_id": context.correlation_id,
            "reason": context.reason,
            "operation": operation,
            "entity_type": entity_type,
            "result_count": result_count,
            "denied": denied,
        }
        if error:
            entry["error"] = error

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            filepath = self._log_dir / f"{date_str}.jsonl"

            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, default=str) + "\n")

        except Exception as e:
            logger.warning(f"Failed to write audit log: {e}")

    def get_recent(
        self,
        skill_name: Optional[str] = None,
        limit: int = 100,
        days: int = 7,
    ) -> List[Dict[str, Any]]:
        """Get recent audit log entries.

        Args:
            skill_name: Optional filter by source skill.
            limit: Maximum entries to return.
            days: Number of days to look back.

        Returns:
            List of audit log entries.
        """
        results = []
        today = datetime.now()

        for day_offset in range(days):
            date = today - __import__("datetime").timedelta(days=day_offset)
            date_str = date.strftime("%Y-%m-%d")
            filepath = self._log_dir / f"{date_str}.jsonl"

            if not filepath.exists():
                continue

            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        entry = json.loads(line)
                        if skill_name and entry.get("source_skill") != skill_name:
                            continue
                        results.append(entry)
                        if len(results) >= limit:
                            return results
            except Exception as e:
                logger.warning(f"Failed to read audit log {filepath}: {e}")

        return results[:limit]


# ---------------------------------------------------------------------------
# PermissionGuard
# ---------------------------------------------------------------------------

class PermissionGuard:
    """Skill-level access control for DataStore operations.

    Enforces which skills can perform which operations on which entity types.
    Uses a policy dict mapping skill_name -> entity_type -> allowed_operations.
    """

    # Default policies: explicit grants per skill.
    # Unlisted skills get read-only on everything.
    DEFAULT_POLICIES: Dict[str, Dict[str, List[str]]] = {
        "ib_toolkit": {
            "deal_analyses": ["read", "write", "create"],
            "skill_memories": ["read", "write"],
            "company_profiles": ["read", "write"],
            "skill_outputs": ["read", "write", "create"],
            "portfolio_holdings": ["read"],
            "market_prices": ["read"],
        },
        "networth_newsletter": {
            "portfolio_holdings": ["read", "write"],
            "market_prices": ["read", "write"],
            "portfolio_snapshots": ["read", "write"],
            "skill_outputs": ["read", "write", "create"],
        },
        "market_newsletter": {
            "market_prices": ["read", "write"],
            "company_profiles": ["read"],
            "skill_outputs": ["read", "write", "create"],
        },
        "health_dashboard": {
            "skill_outputs": ["read", "write", "create"],
            "skill_memories": ["read", "write"],
        },
        "deal_memory": {
            "skill_memories": ["read", "write", "delete"],
            "deal_analyses": ["read", "write"],
            "company_profiles": ["read"],
        },
        "output_organizer": {
            "skill_outputs": ["read", "write", "create"],
            "deal_analyses": ["read"],
        },
        "pdf_extractor": {
            "skill_outputs": ["read", "write", "create"],
            "company_profiles": ["read"],
        },
    }

    def __init__(
        self,
        policies: Optional[Dict[str, Dict[str, List[str]]]] = None,
        audit_logger: Optional[AuditLogger] = None,
    ):
        """Initialize PermissionGuard.

        Args:
            policies: Custom policy dict. If None, uses DEFAULT_POLICIES.
            audit_logger: Optional AuditLogger for logging denied access.
        """
        self._policies = policies if policies is not None else dict(self.DEFAULT_POLICIES)
        self._audit_logger = audit_logger

    def check(
        self,
        context: QueryContext,
        operation: str,
        entity_type: str,
    ) -> bool:
        """Check if an operation is allowed.

        Args:
            context: The QueryContext identifying the caller.
            operation: The operation (read, write, create, delete).
            entity_type: The data entity type.

        Returns:
            True if allowed, False if denied.
        """
        skill = context.source_skill

        # Get skill's policy, or fall back to default read-only
        skill_policy = self._policies.get(skill)

        if skill_policy is None:
            # Unlisted skill: read-only on everything
            return operation == "read"

        # Get entity permissions
        entity_ops = skill_policy.get(entity_type)

        if entity_ops is None:
            # Entity not listed for this skill: read-only
            return operation == "read"

        return operation in entity_ops

    def require(
        self,
        context: QueryContext,
        operation: str,
        entity_type: str,
    ) -> None:
        """Require permission, raising PermissionError if denied.

        Args:
            context: The QueryContext identifying the caller.
            operation: The operation (read, write, create, delete).
            entity_type: The data entity type.

        Raises:
            PermissionError: If the operation is not allowed.
        """
        if not self.check(context, operation, entity_type):
            msg = (
                f"Permission denied: skill '{context.source_skill}' "
                f"cannot '{operation}' on '{entity_type}'"
            )

            # Log denied attempt
            if self._audit_logger:
                self._audit_logger.log_access(
                    context, operation, entity_type,
                    denied=True, error=msg,
                )

            logger.warning(msg)
            raise PermissionError(msg)

    def get_skill_permissions(self, skill_name: str) -> Dict[str, List[str]]:
        """Get the permission policy for a skill.

        Args:
            skill_name: The skill name.

        Returns:
            Dict mapping entity_type -> list of allowed operations.
        """
        return dict(self._policies.get(skill_name, {}))

    def set_skill_permissions(
        self,
        skill_name: str,
        entity_type: str,
        operations: List[str],
    ) -> None:
        """Set permissions for a skill on an entity type.

        Args:
            skill_name: The skill name.
            entity_type: The entity type.
            operations: List of allowed operations.
        """
        if skill_name not in self._policies:
            self._policies[skill_name] = {}
        self._policies[skill_name][entity_type] = list(operations)
