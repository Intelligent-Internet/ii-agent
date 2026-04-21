from __future__ import annotations

#: Fallback for ``requested_capabilities.core_tools`` (names from
#: :data:`TOOL_CLASS_MAP`) when the request doesn't specify any.
COWORK_DEFAULT_CORE_TOOLS: set[str] = set()

#: Fallback for ``requested_capabilities.core_skills`` (names from the
#: user's persisted ``SkillTool`` registry) when the request doesn't
#: specify any.
COWORK_DEFAULT_CORE_SKILLS: set[str] = set()

#: Fallback for ``requested_capabilities.connector`` (e.g. ``"github"``,
#: ``"google_drive"``) when the request doesn't specify one. The
#: connector still requires a wired ``connector_tool`` to instantiate.
COWORK_DEFAULT_CONNECTORS: set[str] = set()

#: Fallback system prompt — used only when the request doesn't ship its own.
DEFAULT_SYSTEM_PROMPT = (
    "You are the Cowork agent inside II Agent desktop. "
    "Help the user reason over local cowork context, use tools deliberately, and keep responses concise and actionable."
)

#: Heading for the client-defined skill catalog appended to the system prompt.
CLIENT_SKILL_HEADING = "Skills available in the cowork mode:"

#: Tag used by the shared capability helpers when emitting warnings.
LOG_PREFIX = "cowork"