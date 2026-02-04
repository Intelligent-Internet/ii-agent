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

logger = logging.getLogger(__name__)

# Skill registry
_SKILLS: Dict[str, "BaseSkill"] = {}


class BaseSkill:
    """Base class for all ii-agent skills."""

    name: str = "base_skill"
    version: str = "0.0.0"
    description: str = "Base skill class"

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._initialized = False

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
