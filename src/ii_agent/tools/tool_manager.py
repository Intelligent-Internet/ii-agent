import asyncio
import logging
from copy import deepcopy
from typing import List, Dict, Any

from ii_agent.llm.base import LLMClient
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.prompts.system_prompt import SystemPromptBuilder
from ii_agent.tools.clients.str_replace_client import StrReplaceClient
from ii_agent.tools.deploy_tool import DeployTool
from ii_agent.tools.get_database_connection import DatabaseConnection
from ii_agent.tools.image_search_tool import ImageSearchTool
from ii_agent.tools.base import LLMTool
from ii_agent.llm.message_history import ToolCallParameters
from ii_agent.tools.openai_llm_tool import OpenAILLMTool
from ii_agent.tools.register_deployment import RegisterDeploymentTool
from ii_agent.tools.shell_tools import (
    ShellExecTool,
    ShellViewTool,
    ShellWaitTool,
    ShellKillProcessTool,
    ShellWriteToProcessTool,
)
from ii_agent.tools.static_deploy_tool import StaticDeployTool
from ii_agent.tools.clients.terminal_client import TerminalClient
from ii_agent.tools.memory.compactify_memory import CompactifyMemoryTool
from ii_agent.tools.memory.simple_memory import SimpleMemoryTool
from ii_agent.tools.slide_deck_tool import SlideDeckInitTool, SlideDeckCompleteTool
from ii_agent.tools.web_dev_tool import FullStackInitTool
from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.tools.str_replace_tool_relative import (
    StrReplaceEditorTool as StrReplaceEditorToolRelative,
)
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.message_tool import MessageTool
from ii_agent.tools.complete_tool import (
    CompleteTool,
    ReturnControlToUserTool,
    CompleteToolReviewer,
    ReturnControlToGeneralAgentTool,
)
from ii_agent.browser.browser import Browser
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.browser_tools import (
    BrowserNavigationTool,
    BrowserRestartTool,
    BrowserScrollDownTool,
    BrowserScrollUpTool,
    BrowserViewTool,
    BrowserWaitTool,
    BrowserSwitchTabTool,
    BrowserOpenNewTabTool,
    BrowserClickTool,
    BrowserEnterTextTool,
    BrowserPressKeyTool,
    BrowserGetSelectOptionsTool,
    BrowserSelectDropdownOptionTool,
)
from ii_agent.tools.visualizer import DisplayImageTool
from ii_agent.tools.audio_tool import (
    AudioTranscribeTool,
    AudioGenerateTool,
)
from ii_agent.tools.video_gen_tool import (
    VideoGenerateFromTextTool,
    VideoGenerateFromImageTool,
    LongVideoGenerateFromTextTool,
    LongVideoGenerateFromImageTool,
)
from ii_agent.tools.image_gen_tool import ImageGenerateTool
from ii_agent.tools.speech_gen_tool import SingleSpeakerSpeechGenerationTool
from ii_agent.tools.pdf_tool import PdfTextExtractTool
from ii_agent.tools.deep_research_tool import DeepResearchTool
from ii_agent.tools.list_html_links_tool import ListHtmlLinksTool
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_agent.core.storage.models.settings import Settings
from ii_agent.utils.sandbox_manager import SandboxManager


def get_system_tools(
    client: LLMClient,
    workspace_manager: WorkspaceManager,
    sandbox_manager: SandboxManager,
    message_queue: asyncio.Queue,
    system_prompt_builder: SystemPromptBuilder,
    settings: Settings,
    tool_args: Dict[str, Any] = None,
) -> list[LLMTool]:
    """
    Retrieves a list of all system tools.

    Returns:
        list[LLMTool]: A list of all system tools.
    """

    logger = logging.getLogger("tool_manager")

    terminal_client = TerminalClient(settings)
    str_replace_client = StrReplaceClient(settings)

    tools = []
    if workspace_manager.is_local_workspace():
        tools.extend(
            [
                StaticDeployTool(workspace_manager=workspace_manager),
                ListHtmlLinksTool(workspace_manager=workspace_manager),
            ]
        )  # Todo: Replace this with local mode of register deployment tool
    else:
        tools.extend(
            [
                RegisterDeploymentTool(sandbox_manager=sandbox_manager),
                FullStackInitTool(
                    workspace_manager=workspace_manager,
                    terminal_client=terminal_client,
                    system_prompt_builder=system_prompt_builder,
                ),
            ]
        )
        if settings.third_party_integration_config.vercel_api_key:
            tools.append(
                DeployTool(
                    terminal_client=terminal_client,
                    workspace_manager=workspace_manager,
                    settings=settings,
                )
            )
        if settings.third_party_integration_config.neon_db_api_key:
            tools.append(DatabaseConnection(settings=settings))
        if settings.third_party_integration_config.openai_api_key:
            tools.append(OpenAILLMTool(settings=settings))

    # Shell tools
    tools.extend(
        [
            ShellViewTool(terminal_client=terminal_client),
            ShellWaitTool(terminal_client=terminal_client),
            ShellWriteToProcessTool(terminal_client=terminal_client),
            ShellKillProcessTool(terminal_client=terminal_client),
            ShellExecTool(
                terminal_client=terminal_client, workspace_manager=workspace_manager
            ),
        ]
    )

    # Str replace tools
    tools.extend(
        [
            StrReplaceEditorToolRelative(
                workspace_manager=workspace_manager,
                message_queue=message_queue,
                str_replace_client=str_replace_client,
            ),
        ]
    )

    tools.extend(
        [
            MessageTool(),
            WebSearchTool(settings=settings),
            VisitWebpageTool(settings=settings),
            SlideDeckInitTool(
                workspace_manager=workspace_manager,
                terminal_client=terminal_client,
            ),
            SlideDeckCompleteTool(
                workspace_manager=workspace_manager,
                str_replace_client=str_replace_client,
            ),
            DisplayImageTool(workspace_manager=workspace_manager),
        ]
    )

    image_search_tool = ImageSearchTool(settings=settings)
    if image_search_tool.is_available():
        tools.append(image_search_tool)

    # Conditionally add tools based on tool_args
    if tool_args:
        if tool_args.get("sequential_thinking", False):
            tools.append(SequentialThinkingTool())
        if tool_args.get("deep_research", False):
            tools.append(DeepResearchTool())
        if tool_args.get("pdf", False):
            tools.append(PdfTextExtractTool(workspace_manager=workspace_manager))
        if tool_args.get("media_generation", False):
            # Check if media config is available in settings
            has_media_config = False
            if settings and settings.media_config:
                if (
                    settings.media_config.gcp_project_id
                    and settings.media_config.gcp_location
                ) or (settings.media_config.google_ai_studio_api_key):
                    has_media_config = True

            if has_media_config:
                tools.append(
                    ImageGenerateTool(
                        workspace_manager=workspace_manager, settings=settings
                    )
                )
                if tool_args.get("video_generation", True):
                    tools.extend(
                        [
                            VideoGenerateFromTextTool(
                                workspace_manager=workspace_manager, settings=settings
                            ),
                            VideoGenerateFromImageTool(
                                workspace_manager=workspace_manager, settings=settings
                            ),
                            LongVideoGenerateFromTextTool(
                                workspace_manager=workspace_manager, settings=settings
                            ),
                            LongVideoGenerateFromImageTool(
                                workspace_manager=workspace_manager, settings=settings
                            ),
                        ]
                    )
                if settings.media_config.google_ai_studio_api_key:
                    tools.append(
                        SingleSpeakerSpeechGenerationTool(
                            workspace_manager=workspace_manager, settings=settings
                        )
                    )
            else:
                logger.warning(
                    "Media generation tools not added due to missing configuration"
                )
                raise Exception(
                    "Media generation tools not added due to missing configuration"
                )
        if tool_args.get("audio_generation", False):
            # Check if audio config is available in settings
            has_audio_config = False
            if settings and settings.audio_config:
                if (
                    settings.audio_config.openai_api_key
                    and settings.audio_config.azure_endpoint
                ):
                    has_audio_config = True

            if has_audio_config:
                tools.extend(
                    [
                        AudioTranscribeTool(
                            workspace_manager=workspace_manager, settings=settings
                        ),
                        AudioGenerateTool(
                            workspace_manager=workspace_manager, settings=settings
                        ),
                    ]
                )

        # Browser tools
        if tool_args.get("browser", False):
            browser = Browser()
            tools.extend(
                [
                    BrowserNavigationTool(browser=browser),
                    BrowserRestartTool(browser=browser),
                    BrowserScrollDownTool(browser=browser),
                    BrowserScrollUpTool(browser=browser),
                    BrowserViewTool(browser=browser),
                    BrowserWaitTool(browser=browser),
                    BrowserSwitchTabTool(browser=browser),
                    BrowserOpenNewTabTool(browser=browser),
                    BrowserClickTool(browser=browser),
                    BrowserEnterTextTool(browser=browser),
                    BrowserPressKeyTool(browser=browser),
                    BrowserGetSelectOptionsTool(browser=browser),
                    BrowserSelectDropdownOptionTool(browser=browser),
                ]
            )

        memory_tool = tool_args.get("memory_tool")
        if memory_tool == "compactify-memory":
            context_manager = LLMSummarizingContextManager(
                client=client,
                token_counter=TokenCounter(),
                logger=logger,
                token_budget=TOKEN_BUDGET,
            )
            tools.append(CompactifyMemoryTool(context_manager=context_manager))
        elif memory_tool == "none":
            pass
        elif memory_tool == "simple":
            tools.append(SimpleMemoryTool())

    return tools


class AgentToolManager:
    """
    Manages the creation and execution of tools for the agent.

    This class is responsible for:
    - Initializing and managing all available tools
    - Providing access to tools by name
    - Executing tools with appropriate inputs
    - Logging tool execution details

    Tools include bash commands, browser interactions, file operations,
    search capabilities, and task completion functionality.
    """

    def __init__(
        self,
        tools: List[LLMTool],
        logger_for_agent_logs: logging.Logger,
        interactive_mode: bool = True,
        reviewer_mode: bool = False,
    ):
        self.logger_for_agent_logs = logger_for_agent_logs
        if reviewer_mode:
            self.complete_tool = (
                ReturnControlToGeneralAgentTool()
                if interactive_mode
                else CompleteToolReviewer()
            )
        else:
            self.complete_tool = (
                ReturnControlToUserTool() if interactive_mode else CompleteTool()
            )
        self.tools = tools

    def get_tool(self, tool_name: str) -> LLMTool:
        """
        Retrieves a tool by its name.

        Args:
            tool_name (str): The name of the tool to retrieve.

        Returns:
            LLMTool: The tool object corresponding to the given name.

        Raises:
            ValueError: If the tool with the specified name is not found.
        """
        try:
            tool: LLMTool = next(t for t in self.get_tools() if t.name == tool_name)
            return tool
        except StopIteration:
            raise ValueError(f"Tool with name {tool_name} not found")

    async def run_tool(self, tool_params: ToolCallParameters, history: MessageHistory):
        """
        Executes a llm tool asynchronously.

        Args:
            tool_params (ToolCallParameters): The tool parameters.
            history (MessageHistory): The history of the conversation.
        Returns:
            ToolResult: The result of the tool execution.
        """
        llm_tool = self.get_tool(tool_params.tool_name)
        tool_name = tool_params.tool_name
        tool_input = tool_params.tool_input
        self.logger_for_agent_logs.info(f"Running tool: {tool_name}")
        self.logger_for_agent_logs.info(f"Tool input: {tool_input}")
        result = await llm_tool.run_async(tool_input, history)

        tool_input_str = "\n".join([f" - {k}: {v}" for k, v in tool_input.items()])

        log_message = f"Calling tool {tool_name} with input:\n{tool_input_str}"
        if isinstance(result, str):
            log_message += f"\nTool output: \n{result}\n\n"
        else:
            result_to_log = deepcopy(result)
            for i in range(len(result_to_log)):
                if result_to_log[i].get("type") == "image":
                    result_to_log[i]["source"]["data"] = "[REDACTED]"
            log_message += f"\nTool output: \n{result_to_log}\n\n"

        self.logger_for_agent_logs.info(log_message)

        # Handle both ToolResult objects and tuples
        if isinstance(result, tuple):
            tool_result, _ = result
        else:
            tool_result = result

        return tool_result

    def should_stop(self):
        """
        Checks if the agent should stop based on the completion tool.

        Returns:
            bool: True if the agent should stop, False otherwise.
        """
        return self.complete_tool.should_stop

    def get_final_answer(self):
        """
        Retrieves the final answer from the completion tool.

        Returns:
            str: The final answer from the completion tool.
        """
        return self.complete_tool.answer

    def reset(self):
        """
        Resets the completion tool.
        """
        self.complete_tool.reset()

    def get_tools(self) -> list[LLMTool]:
        """
        Retrieves a list of all available tools.

        Returns:
            list[LLMTool]: A list of all available tools.
        """
        return self.tools + [self.complete_tool]
