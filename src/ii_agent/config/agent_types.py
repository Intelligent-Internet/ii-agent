"""Agent type configuration and enums."""

from enum import Enum
from typing import List, Optional
from ii_agent.utils.constants import is_gpt5_family, is_anthropic_family

# from ii_tool.mcp_integrations.playwright import SELECTED_TOOLS as PLAYWRIGHT_TOOLS
from ii_tool.tools.agent.message_user import MessageUserTool
from ii_tool.tools.shell import (
    ShellView,
    ShellInit,
    ShellList,
    ShellRunCommand,
    ShellWriteToProcessTool,
)
from ii_tool.tools.file_system import (
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    ApplyPatchTool,
)
from ii_tool.tools.browser import (
    BrowserClickTool,
    BrowserWaitTool,
    BrowserViewTool,
    BrowserScrollDownTool,
    BrowserScrollUpTool,
    BrowserSwitchTabTool,
    BrowserOpenNewTabTool,
    BrowserGetSelectOptionsTool,
    BrowserSelectDropdownOptionTool,
    BrowserNavigationTool,
    BrowserRestartTool,
    BrowserEnterTextTool,
    BrowserPressKeyTool,
    BrowserDragTool,
    BrowserEnterMultipleTextsTool,
)
from ii_tool.tools.media import VideoGenerateTool, ImageGenerateTool
from ii_tool.tools.dev import RegisterPort, FullStackInitTool, GetDatabaseConnection, SaveCheckpointTool
from ii_tool.tools.slide_system.slide_patch import SlideApplyPatchTool
from ii_tool.tools.web import WebSearchTool, WebVisitTool, WebVisitCompressTool
from ii_tool.tools.slide_system.slide_edit_tool import SlideEditTool
from ii_tool.tools.slide_system.slide_write_tool import SlideWriteTool
from ii_tool.tools.productivity import TodoReadTool, TodoWriteTool
from ii_tool.tools.web.image_search_tool import ImageSearchTool
from ii_tool.tools.web.web_batch_search_tool import WebBatchSearchTool
from ii_tool.tools.file_system.str_replace_editor import StrReplaceEditorTool
# from ii_tool.tools.codex import CodexExecuteTool  # Now using MCP stdio versions
from ii_tool.tools.sbll_knowledge_tool import SBLLKnowledgeTool


class AgentType(str, Enum):
    """Enumeration of available agent types."""

    GENERAL = "general"
    MEDIA = "media"
    BROWSER = "browser"
    SLIDE = "slide"
    RESEARCHER = "researcher"
    WEBSITE_BUILD = "website_build"
    TASK_AGENT = "task_agent"
    DESIGN_DOCUMENT = "design_document"
    CODEX = "codex"
    CLAUDE_CODE = "claude_code"


class AgentTypeConfig:
    """Configuration for different agent types."""

    # Define toolsets for each agent type
    TOOLSETS = {
        AgentType.GENERAL: [
            # Shell tools
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            MessageUserTool.name,
            SBLLKnowledgeTool.name,
            # ShellStopCommand.name,
            ShellList.name,
            # File system tools
            # ASTGrepTool.name,
            # GrepTool.name,
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            FullStackInitTool.name,
            SaveCheckpointTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            # TodoReadTool.name,
            TodoWriteTool.name,
            RegisterPort.name,
            FullStackInitTool.name,
        ],
        AgentType.TASK_AGENT: [
            # Shell tools
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            # ShellStopCommand.name,
            MessageUserTool.name,
            ShellList.name,
            # File system tools
            # ASTGrepTool.name,
            # GrepTool.name,
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            FullStackInitTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            # TodoReadTool.name,
            TodoWriteTool.name,
        ],
        AgentType.BROWSER: [
            # Browser tools
            BrowserClickTool.name,
            BrowserWaitTool.name,
            BrowserViewTool.name,
            BrowserScrollDownTool.name,
            BrowserScrollUpTool.name,
            BrowserSwitchTabTool.name,
            BrowserOpenNewTabTool.name,
            BrowserGetSelectOptionsTool.name,
            BrowserSelectDropdownOptionTool.name,
            BrowserNavigationTool.name,
            BrowserRestartTool.name,
            BrowserEnterTextTool.name,
            BrowserPressKeyTool.name,
            BrowserDragTool.name,
            BrowserEnterMultipleTextsTool.name,
            MessageUserTool.name,
        ],
        AgentType.MEDIA: [
            # File system tools
            FileReadTool.name,
            # Media tools
            VideoGenerateTool.name,
            ImageGenerateTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            # Todo tools
            # TodoReadTool.name,
            TodoWriteTool.name,
            MessageUserTool.name,
        ],
        AgentType.SLIDE: [
            # TODO: Add slide-specific tools when available
            MessageUserTool.name,
            FileEditTool.name,
            FileReadTool.name,
            FileWriteTool.name,
            ImageGenerateTool.name,
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            # TodoReadTool.name,
            TodoWriteTool.name,
            SlideWriteTool.name,
            SlideEditTool.name,
        ],
        AgentType.WEBSITE_BUILD: [
            # Shell tools
            MessageUserTool.name,
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            # ShellStopCommand.name,
            ShellList.name,
            # File system tools
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            FullStackInitTool.name,
            SaveCheckpointTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            # Todo tools
            # TodoReadTool.name,
            TodoWriteTool.name,
            # common tools
            RegisterPort.name,
            GetDatabaseConnection.name,
        ],
        AgentType.RESEARCHER: [
            MessageUserTool.name,
            WebBatchSearchTool.name,
            WebVisitCompressTool.name,
            SBLLKnowledgeTool.name,
        ],
        AgentType.DESIGN_DOCUMENT: [
            # File system tools for creating design docs
            MessageUserTool.name,
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            # ShellStopCommand.name,
            ShellList.name,
            # File system tools
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            # TodoReadTool.name,
            TodoWriteTool.name,
        ],
        AgentType.CODEX: [
            MessageUserTool.name,
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            # ShellStopCommand.name,
            ShellList.name,
            # File system tools
            # ASTGrepTool.name,
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            TodoReadTool.name,
            TodoWriteTool.name,
            RegisterPort.name,
            FullStackInitTool.name,
            # Codex tools are now provided via MCP stdio transport
            # "mcp_codex_execute",  # MCP Codex execute tool
            # "mcp_codex_review",  # MCP Codex review tool
        ],
        AgentType.CLAUDE_CODE: [
            MessageUserTool.name,
            ShellInit.name,
            ShellRunCommand.name,
            ShellView.name,
            # ShellStopCommand.name,
            ShellList.name,
            # File system tools
            # ASTGrepTool.name,
            FileReadTool.name,
            FileWriteTool.name,
            FileEditTool.name,
            # Web tools
            WebSearchTool.name,
            WebVisitTool.name,
            ImageSearchTool.name,
            TodoReadTool.name,
            TodoWriteTool.name,
            RegisterPort.name,
            FullStackInitTool.name,
        ],
    }

    GENERAL_FORBIDDEN_TOOLS = [
        SlideEditTool.name,
        SlideWriteTool.name,
    ]

    @classmethod
    def get_allowed_toolset(
        cls, agent_type: AgentType, model_name: Optional[str] = None
    ) -> List[str]:
        """Get the allowed toolset for a specific agent type.

        Args:
            agent_type: The type of agent
            model_name: Optional model name to customize toolset (e.g., "gpt-5")

        Returns:
            List of allowed tool names
        """
        base_toolset = cls.TOOLSETS.get(
            agent_type, cls.TOOLSETS[AgentType.GENERAL]
        ).copy()
        # If model is GPT-5 family, replace FileWriteTool and FileEditTool with ApplyPatchTool
        if (
            model_name
            and is_gpt5_family(model_name)
            and (
                FileWriteTool.name in base_toolset or FileEditTool.name in base_toolset
            )
        ):
            # Remove FileWriteTool and FileEditTool if present
            gpt_5_forbidden_tools = [FileWriteTool.name, FileEditTool.name, ShellList.name, ShellWriteToProcessTool.name]
            base_toolset = [
                tool
                for tool in base_toolset
                if tool not in gpt_5_forbidden_tools
            ]

            # Add ApplyPatchTool if not already present
            if ApplyPatchTool.name not in base_toolset:
                # Find position where file tools are (after FileReadTool)
                try:
                    read_index = base_toolset.index(FileReadTool.name)
                    base_toolset.insert(read_index + 1, ApplyPatchTool.name)
                except ValueError:
                    # If FileReadTool not found, just append
                    base_toolset.append(ApplyPatchTool.name)

        # If slide write tools
        if (
            model_name
            and is_gpt5_family(model_name)
            and (
                SlideWriteTool.name in base_toolset
                or SlideEditTool.name in base_toolset
            )
        ):
            # Remove SlideWriteTool and SlideEditTool if present
            base_toolset = [
                tool
                for tool in base_toolset
                if tool not in [SlideWriteTool.name, SlideEditTool.name]
            ]

            # Add SlideApplyPatchTool if not already present
            if SlideApplyPatchTool.name not in base_toolset:
                # Find position where file tools are (after FileReadTool)
                base_toolset.append(SlideApplyPatchTool.name)

        if model_name and is_anthropic_family(model_name):
            anthropic_forbidden_tools = [FileWriteTool.name, FileEditTool.name, ShellList.name, ShellWriteToProcessTool.name]
            base_toolset = [
                tool
                for tool in base_toolset
                if tool not in anthropic_forbidden_tools
            ]
            base_toolset.append(StrReplaceEditorTool.name)

        return base_toolset

    @classmethod
    def is_valid_agent_type(cls, agent_type: str) -> bool:
        """Check if an agent type is valid."""
        try:
            AgentType(agent_type)
            return True
        except ValueError:
            return False

    @classmethod
    def get_all_agent_types(cls) -> List[str]:
        """Get all available agent types."""
        return [agent_type.value for agent_type in AgentType]
