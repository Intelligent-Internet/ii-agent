"""
Skill Manifest Types — Strict Tool Contract + Plugin Lifecycle

Provides structured capability manifests that replace the flat
get_capabilities() -> List[str] pattern with typed schemas.

Core types:
- RiskLevel: READ_ONLY / WRITE / DESTRUCTIVE per action
- PermissionScope: NETWORK, STORAGE, FILESYSTEM, etc.
- ActionSchema: Per-action I/O schema, risk level, examples
- SkillManifest: Full skill capability declaration
- HealthReport / SkillStatus: Runtime health and state

Backward compatible — SkillManifest.from_capabilities() auto-generates
a minimal manifest from legacy get_capabilities() strings.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RiskLevel(Enum):
    """Risk classification for individual skill actions."""
    READ_ONLY = "read_only"       # Data retrieval, search, recall
    WRITE = "write"               # File creation, data storage
    DESTRUCTIVE = "destructive"   # Deletion, overwrite, irreversible


class PermissionScope(Enum):
    """Resource scopes a skill or action may require."""
    NETWORK = "network"
    STORAGE = "storage"
    DATABASE = "database"
    FILESYSTEM = "filesystem"
    CREDENTIALS = "credentials"
    EXTERNAL_API = "external_api"


class SkillState(Enum):
    """Lifecycle state of a skill instance."""
    CREATED = "created"
    INITIALIZING = "initializing"
    ACTIVE = "active"
    DEACTIVATING = "deactivating"
    DEACTIVATED = "deactivated"
    ERROR = "error"


class HealthStatus(Enum):
    """Health check result."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Action Schema
# ---------------------------------------------------------------------------

@dataclass
class ActionSchema:
    """Schema for a single skill action.

    Describes the action's inputs, outputs, risk level, and required
    permissions so the bridge layer can generate richer tool descriptions,
    validate params before dispatch, and gate destructive operations.
    """
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.READ_ONLY
    required_permissions: List[PermissionScope] = field(default_factory=list)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["risk_level"] = self.risk_level.value
        d["required_permissions"] = [p.value for p in self.required_permissions]
        return d

    @classmethod
    def from_capability_string(cls, capability: str) -> "ActionSchema":
        """Create a minimal ActionSchema from a legacy capability string."""
        return cls(
            name=capability,
            description=f"Execute '{capability}' action",
            input_schema={"type": "object", "additionalProperties": True},
            output_schema={"type": "object", "additionalProperties": True},
            risk_level=RiskLevel.READ_ONLY,
        )


# ---------------------------------------------------------------------------
# Health Report
# ---------------------------------------------------------------------------

@dataclass
class HealthReport:
    """Result of a skill health check."""
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


# ---------------------------------------------------------------------------
# Skill Status
# ---------------------------------------------------------------------------

@dataclass
class SkillStatus:
    """Aggregated runtime status of a skill."""
    state: SkillState
    health: HealthReport
    uptime_seconds: float = 0.0
    action_count: int = 0
    last_action: Optional[str] = None
    last_action_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        d["health"] = self.health.to_dict()
        return d


# ---------------------------------------------------------------------------
# Skill Manifest
# ---------------------------------------------------------------------------

@dataclass
class SkillManifest:
    """Structured capability declaration for a skill.

    Replaces the flat List[str] from get_capabilities() with rich,
    typed action schemas that the bridge layer uses for:
    - Richer LLM tool descriptions (per-action parameter docs)
    - Risk-based confirmation gating (DESTRUCTIVE actions prompt user)
    - Lightweight param validation before dispatch
    - Manifest-aware introspection / skill listing
    """
    name: str
    version: str
    description: str
    actions: Dict[str, ActionSchema] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    resource_requirements: List[PermissionScope] = field(default_factory=list)

    @classmethod
    def from_capabilities(cls, skill) -> "SkillManifest":
        """Auto-generate a minimal manifest from a legacy skill.

        Wraps each capability string as an ActionSchema with open
        input/output schemas. Skills that override get_manifest() bypass
        this entirely.

        Args:
            skill: A BaseSkill instance with name, version, description,
                   and get_capabilities().
        """
        capabilities = skill.get_capabilities()
        actions = {
            cap: ActionSchema.from_capability_string(cap)
            for cap in capabilities
        }
        return cls(
            name=skill.name,
            version=skill.version,
            description=skill.description,
            actions=actions,
        )

    def get_action(self, action_name: str) -> Optional[ActionSchema]:
        """Look up an action by name."""
        return self.actions.get(action_name)

    def get_action_names(self) -> List[str]:
        """Return sorted list of action names."""
        return sorted(self.actions.keys())

    def get_destructive_actions(self) -> List[str]:
        """Return names of actions classified as DESTRUCTIVE."""
        return [
            name for name, schema in self.actions.items()
            if schema.risk_level == RiskLevel.DESTRUCTIVE
        ]

    def get_write_actions(self) -> List[str]:
        """Return names of actions classified as WRITE."""
        return [
            name for name, schema in self.actions.items()
            if schema.risk_level == RiskLevel.WRITE
        ]

    def get_all_permissions(self) -> List[PermissionScope]:
        """Aggregate all unique permissions across manifest + actions."""
        perms = set(self.resource_requirements)
        for action in self.actions.values():
            perms.update(action.required_permissions)
        return sorted(perms, key=lambda p: p.value)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "actions": {
                name: schema.to_dict()
                for name, schema in self.actions.items()
            },
            "dependencies": self.dependencies,
            "resource_requirements": [p.value for p in self.resource_requirements],
        }

    def build_action_docs(self) -> str:
        """Generate human-readable action documentation for LLM prompts.

        Returns a formatted string describing each action with its
        parameters, risk level, and examples.
        """
        if not self.actions:
            return "No actions available."

        lines = []
        for name in sorted(self.actions.keys()):
            schema = self.actions[name]
            risk_tag = f"[{schema.risk_level.value}]"
            lines.append(f"- {name} {risk_tag}: {schema.description}")

            # Document input params if schema has properties
            props = schema.input_schema.get("properties", {})
            required = schema.input_schema.get("required", [])
            if props:
                for param, param_schema in props.items():
                    req_marker = " (required)" if param in required else ""
                    param_type = param_schema.get("type", "any")
                    param_desc = param_schema.get("description", "")
                    lines.append(
                        f"    {param} ({param_type}{req_marker}): {param_desc}"
                    )

            # Include examples if present
            if schema.examples:
                lines.append(f"    Example: {schema.examples[0]}")

        return "\n".join(lines)
