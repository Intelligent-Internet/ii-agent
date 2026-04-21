"""Browser-extension defaults.

The wire payload's ``core_tools`` / ``core_skills`` / ``connector`` IS
the user's request and is taken as-is. These ``BROWSER_EXTENSION_*``
sets are the **fallback defaults** the factory uses only when the
request leaves the matching key empty/null. They keep a sane baseline
for silent requests; populate them deliberately as needed.
"""

from __future__ import annotations

#: Fallback for ``requested_capabilities.core_tools`` (names from
#: :data:`TOOL_CLASS_MAP`) when the request doesn't specify any.
BROWSER_EXTENSION_DEFAULT_CORE_TOOLS: set[str] = set()

#: Fallback for ``requested_capabilities.core_skills`` (names from the
#: user's persisted ``SkillTool`` registry) when the request doesn't
#: specify any.
BROWSER_EXTENSION_DEFAULT_CORE_SKILLS: set[str] = set()

#: Fallback for ``requested_capabilities.connector`` (e.g. ``"github"``,
#: ``"google_drive"``) when the request doesn't specify one. The
#: connector still requires a wired ``connector_tool`` to instantiate.
BROWSER_EXTENSION_DEFAULT_CONNECTORS: set[str] = set()

#: Fallback system prompt — used only when the request doesn't ship its own.
DEFAULT_SYSTEM_PROMPT = (
    "You are an in-browser assistant running inside the ii-browser Chrome "
    "extension. All tool execution happens inside the extension; pause and "
    "wait after each tool call until the result is delivered."
)

#: Heading for the client-defined skill catalog appended to the system prompt.
CLIENT_SKILL_HEADING = "Skills available in the ii-browser extension runtime:"

#: Tag used by the shared capability helpers when emitting warnings.
LOG_PREFIX = "browser_extension"
