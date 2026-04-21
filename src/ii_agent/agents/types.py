"""Cross-cutting engine enums.

These enums are used across engine, realtime, integrations, and billing
layers. Keeping them here avoids dependency direction violations from
reaching into v1 sub-packages.
"""

from enum import StrEnum


class AgentType(StrEnum):
    """Enumeration of available agent types.

    Single source of truth — imported by server models, realtime handlers,
    agent engine, and any module that needs agent type discrimination.
    """

    GENERAL = "general"
    MEDIA = "media"
    BROWSER = "browser"
    SLIDE = "slide"
    SLIDE_NANO_BANANA = "slide_nano_banana"
    RESEARCHER = "researcher"
    WEBSITE_BUILD = "website_build"
    TASK_AGENT = "task_agent"
    DESIGN_DOCUMENT = "design_document"
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"
    DEEP_RESEARCH = "deep_research"
    FAST_RESEARCH = "fast_research"
    RESEARCH_TO_WEBSITE = "research_to_website"
    MOBILE_APP = "mobile_app"
    COWORK = "cowork"


__all__ = ["AgentType"]
