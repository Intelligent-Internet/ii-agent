"""
II-Agent Skills Plugin System

A modular skill framework for extending ii-agent capabilities.
Skills are self-contained modules that provide domain-specific functionality.

Available Skills:
- ib_toolkit: Investment banking presentations, Excel models, and analysis frameworks
- market_newsletter: Daily market news and price tracking with NewsAPI
- health_dashboard: WHOOP health metrics integration (recovery, sleep, strain)
- networth_newsletter: Daily net worth tracking and portfolio analysis
- daily_investment_newsletter: Canadian investment news aggregation
- memory: Long-term context and memory management (coming soon)
"""

from typing import Dict, List, Optional, Type
from pathlib import Path
import importlib
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Skill registry
_SKILLS: Dict[str, "BaseSkill"] = {}


class BaseSkill:
    """Base class for all ii-agent skills.

    Provides default implementations for the plugin lifecycle:
    - get_manifest(): Structured capability declaration (auto-generated from get_capabilities())
    - teardown(): Cleanup resources on shutdown
    - health_check(): Runtime health status
    - on_activate() / on_deactivate(): Lifecycle transitions
    - get_status(): Aggregated runtime state
    """

    name: str = "base_skill"
    version: str = "0.0.0"
    description: str = "Base skill class"

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._initialized = False
        # Lifecycle tracking
        self._state = "created"  # Use string to avoid import cycle; maps to SkillState
        self._activated_at: Optional[str] = None
        self._action_count: int = 0
        self._last_action: Optional[str] = None
        self._last_action_at: Optional[str] = None

    def initialize(self) -> bool:
        """Initialize the skill. Override in subclasses."""
        self._initialized = True
        return True

    def validate_config(self) -> List[str]:
        """Validate configuration. Returns list of missing/invalid items."""
        return []

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this skill provides."""
        return []

    def execute(self, action: str, **kwargs) -> Dict:
        """Execute a skill action. Override in subclasses."""
        raise NotImplementedError(f"Action '{action}' not implemented")

    @property
    def is_ready(self) -> bool:
        """Check if skill is ready to use."""
        return self._initialized and len(self.validate_config()) == 0

    # ------------------------------------------------------------------
    # Plugin Lifecycle (Goose-inspired)
    # ------------------------------------------------------------------

    def get_manifest(self):
        """Return a SkillManifest for this skill.

        Default implementation auto-generates from get_capabilities().
        Override in subclasses to provide rich typed schemas.

        Returns:
            SkillManifest instance
        """
        from ii_skills.shared.skill_manifest import SkillManifest
        return SkillManifest.from_capabilities(self)

    def teardown(self) -> None:
        """Release resources held by this skill. Override for cleanup."""
        pass

    def health_check(self):
        """Check runtime health of this skill.

        Default returns HEALTHY if initialized, UNHEALTHY otherwise.

        Returns:
            HealthReport instance
        """
        from ii_skills.shared.skill_manifest import HealthReport, HealthStatus
        if self._initialized:
            return HealthReport(
                status=HealthStatus.HEALTHY,
                message=f"{self.name} is initialized and ready",
            )
        return HealthReport(
            status=HealthStatus.UNHEALTHY,
            message=f"{self.name} is not initialized",
        )

    def on_activate(self) -> None:
        """Called when the skill is registered and ready for use.

        Sets state to ACTIVE and records activation timestamp.
        Override for custom activation logic (call super first).
        """
        self._state = "active"
        self._activated_at = datetime.now(timezone.utc).isoformat()
        logger.debug(f"Skill '{self.name}' activated")

    def on_deactivate(self) -> None:
        """Called during graceful shutdown.

        Calls teardown() and sets state to DEACTIVATED.
        Override for custom deactivation logic (call super last).
        """
        self._state = "deactivating"
        try:
            self.teardown()
        except Exception as e:
            logger.warning(f"Skill '{self.name}' teardown error: {e}")
            self._state = "error"
            return
        self._state = "deactivated"
        logger.debug(f"Skill '{self.name}' deactivated")

    def get_status(self):
        """Return aggregated runtime status.

        Returns:
            SkillStatus instance with state, health, uptime, action stats.
        """
        from ii_skills.shared.skill_manifest import (
            SkillStatus, SkillState, HealthReport, HealthStatus,
        )

        # Map string state to enum
        state_map = {
            "created": SkillState.CREATED,
            "initializing": SkillState.INITIALIZING,
            "active": SkillState.ACTIVE,
            "deactivating": SkillState.DEACTIVATING,
            "deactivated": SkillState.DEACTIVATED,
            "error": SkillState.ERROR,
        }
        state = state_map.get(self._state, SkillState.CREATED)

        # Calculate uptime
        uptime = 0.0
        if self._activated_at:
            try:
                activated = datetime.fromisoformat(self._activated_at)
                uptime = (datetime.now(timezone.utc) - activated).total_seconds()
            except (ValueError, TypeError):
                pass

        health = self.health_check()

        return SkillStatus(
            state=state,
            health=health,
            uptime_seconds=uptime,
            action_count=self._action_count,
            last_action=self._last_action,
            last_action_at=self._last_action_at,
        )


def register_skill(skill_class: Type[BaseSkill]) -> Type[BaseSkill]:
    """Decorator to register a skill."""
    _SKILLS[skill_class.name] = skill_class
    logger.info(f"Registered skill: {skill_class.name} v{skill_class.version}")
    return skill_class


def get_skill(name: str, config: Optional[Dict] = None) -> Optional[BaseSkill]:
    """Get a skill instance by name."""
    if name in _SKILLS:
        return _SKILLS[name](config)
    return None


def list_skills() -> List[Dict]:
    """List all registered skills."""
    return [
        {
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
        }
        for skill in _SKILLS.values()
    ]


def discover_skills():
    """Auto-discover and register skills from the ii_skills package."""
    skills_dir = Path(__file__).parent

    for skill_path in skills_dir.iterdir():
        if skill_path.is_dir() and not skill_path.name.startswith("_"):
            try:
                module = importlib.import_module(f"ii_skills.{skill_path.name}")
                logger.info(f"Loaded skill module: {skill_path.name}")
            except ImportError as e:
                logger.warning(f"Failed to load skill {skill_path.name}: {e}")


# Auto-discover skills on import
discover_skills()
