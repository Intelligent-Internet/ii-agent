import os
import asyncio
import logging
from copy import deepcopy
from typing import Optional, List, Dict, Any
from ii_agent.llm.base import LLMClient
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.tools.image_search_tool import ImageSearchTool
from ii_agent.tools.base import LLMTool
from ii_agent.llm.base import ToolCallParameters
from ii_agent.tools.memory.compactify_memory import CompactifyMemoryTool
from ii_agent.tools.memory.simple_memory import SimpleMemoryTool
from ii_agent.tools.slide_deck_tool import SlideDeckInitTool, SlideDeckCompleteTool
from ii_agent.tools.web_search_tool import WebSearchTool
from ii_agent.tools.visit_webpage_tool import VisitWebpageTool
from ii_agent.tools.str_replace_tool_relative import StrReplaceEditorTool
from ii_agent.tools.static_deploy_tool import StaticDeployTool
from ii_agent.tools.sequential_thinking_tool import SequentialThinkingTool
from ii_agent.tools.message_tool import MessageTool
from ii_agent.tools.complete_tool import (
    CompleteTool, 
    ReturnControlToUserTool, 
    CompleteToolReviewer, 
    ReturnControlToGeneralAgentTool
)
from ii_agent.tools.bash_tool import create_bash_tool, create_docker_bash_tool
from ii_agent.browser.browser import Browser
from ii_agent.utils import WorkspaceManager
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
from ii_agent.core.logger import logger
from ii_agent.events.action import (
    Action, MessageAction, CompleteAction,
    FileReadAction, FileWriteAction, FileEditAction,
    CmdRunAction, IPythonRunCellAction,
    BrowseURLAction, BrowseInteractiveAction, AgentThinkAction
)
from ii_agent.events.action.mcp import MCPAction
from ii_agent.events.observation import (
    Observation, SystemObservation, ErrorObservation,
    FileReadObservation, FileWriteObservation, FileEditObservation,
    CmdOutputObservation, BrowseObservation, BrowseInteractiveObservation,
    MCPObservation, NullObservation, IPythonRunCellObservation, AgentThinkObservation
)
from ii_agent.events.event import EventSource


def get_system_tools(
    client: LLMClient,
    workspace_manager: WorkspaceManager,
    message_queue: asyncio.Queue,
    settings: Settings,
    container_id: Optional[str] = None,
    tool_args: Dict[str, Any] = None,
) -> list[LLMTool]:
    """
    Retrieves a list of all system tools.

    Returns:
        list[LLMTool]: A list of all system tools.
    """
    ask_user_permission = False # Not support
    if container_id is not None:
        bash_tool = create_docker_bash_tool(
            container=container_id, ask_user_permission=ask_user_permission
        )
    else:
        bash_tool = create_bash_tool(
            ask_user_permission=ask_user_permission, cwd=workspace_manager.root
        )

    context_manager = LLMSummarizingContextManager(
        client=client,
        token_counter=TokenCounter(),
        token_budget=TOKEN_BUDGET,
    )

    tools = [
        MessageTool(),
        WebSearchTool(settings=settings),
        VisitWebpageTool(settings=settings),
        StaticDeployTool(workspace_manager=workspace_manager),
        StrReplaceEditorTool(workspace_manager=workspace_manager),
        bash_tool,
        ListHtmlLinksTool(workspace_manager=workspace_manager),
        SlideDeckInitTool(
            workspace_manager=workspace_manager,
        ),
        SlideDeckCompleteTool(
            workspace_manager=workspace_manager,
        ),
        DisplayImageTool(workspace_manager=workspace_manager),
    ]
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
                if (settings.media_config.gcp_project_id and settings.media_config.gcp_location) or (settings.media_config.google_ai_studio_api_key):
                    has_media_config = True
                
            if has_media_config:
                tools.append(ImageGenerateTool(workspace_manager=workspace_manager, settings=settings))
                if tool_args.get("video_generation", True):
                    tools.extend([
                        VideoGenerateFromTextTool(workspace_manager=workspace_manager, settings=settings), 
                        VideoGenerateFromImageTool(workspace_manager=workspace_manager, settings=settings),
                        LongVideoGenerateFromTextTool(workspace_manager=workspace_manager, settings=settings),
                        LongVideoGenerateFromImageTool(workspace_manager=workspace_manager, settings=settings)
                    ])
                if settings.media_config.google_ai_studio_api_key:
                    tools.append(SingleSpeakerSpeechGenerationTool(workspace_manager=workspace_manager, settings=settings))
            else:
                logger.warning("Media generation tools not added due to missing configuration")
                raise Exception("Media generation tools not added due to missing configuration")
        if tool_args.get("audio_generation", False):
            # Check if audio config is available in settings
            has_audio_config = False
            if settings and settings.audio_config:
                if (settings.audio_config.openai_api_key and 
                    settings.audio_config.azure_endpoint):
                    has_audio_config = True
                
            if has_audio_config:
                tools.extend(
                    [
                        AudioTranscribeTool(workspace_manager=workspace_manager, settings=settings),
                        AudioGenerateTool(workspace_manager=workspace_manager, settings=settings),
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
            tools.append(CompactifyMemoryTool(context_manager=context_manager))
        elif memory_tool == "none":
            pass
        elif memory_tool == "simple":
            tools.append(SimpleMemoryTool())
            
        # Add complete tools based on mode
        interactive_mode = tool_args.get("interactive_mode", True)
        reviewer_mode = tool_args.get("reviewer_mode", False)
        
        if reviewer_mode:
            if interactive_mode:
                tools.append(ReturnControlToGeneralAgentTool())
            else:
                tools.append(CompleteToolReviewer())
        else:
            if interactive_mode:
                tools.append(ReturnControlToUserTool())
            else:
                tools.append(CompleteTool())

    return tools


class AgentToolManager:
    """
    Manages the execution of tools for the agent.

    This class is responsible for:
    - Managing all available tools
    - Providing access to tools by name
    - Executing tools with appropriate inputs
    - Converting actions to observations
    - Logging tool execution details

    The tool manager focuses solely on tool execution and does not
    manage agent completion state, which is handled by the agent itself.
    """

    def __init__(self, tools: List[LLMTool]):
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

    async def run_tool(self, tool_params: ToolCallParameters):
        """
        Executes a llm tool asynchronously.

        Args:
            tool_params (ToolCallParameters): The tool parameters.
        Returns:
            ToolResult: The result of the tool execution.
        """
        llm_tool = self.get_tool(tool_params.tool_name)
        tool_name = tool_params.tool_name
        tool_input = tool_params.tool_input
        logger.info(f"Running tool: {tool_name}")
        logger.info(f"Tool input: {tool_input}")
        result = await llm_tool.run_async(tool_input)

        tool_input_str = "\n".join([f" - {k}: {v}" for k, v in tool_input.items()])

        log_message = f"Calling tool {tool_name} with input:\n{tool_input_str}"
        if isinstance(result, str):
            log_message += f"\nTool output: \n{result}\n\n"
        elif isinstance(result, list):
            result_to_log = deepcopy(result)
            for i in range(len(result_to_log)):
                if isinstance(result_to_log[i], dict) and result_to_log[i].get("type") == "image":
                    result_to_log[i]["source"]["data"] = "[REDACTED]"
            log_message += f"\nTool output: \n{result_to_log}\n\n"
        else:
            log_message += f"\nTool output: \n{result}\n\n"

        logger.info(log_message)

        # Handle both ToolResult objects and tuples
        if isinstance(result, tuple):
            tool_result, _ = result
        else:
            tool_result = result

        return tool_result


    def get_tools(self) -> list[LLMTool]:
        """
        Retrieves a list of all available tools.

        Returns:
            list[LLMTool]: A list of all available tools.
        """
        return self.tools

    async def handle_action(self, action: Action) -> Observation:
        """
        Handle different types of actions and return appropriate observations.

        Args:
            action: The action to execute (from events.action)

        Returns:
            Observation: The result of the action execution
        """
        if not action.runnable:
            if isinstance(action, AgentThinkAction):
                return AgentThinkObservation(content="Your thought has been recorded")
            return NullObservation(content='') # TODO: not any yet

        try:
            # Unified tool execution
            return await self._execute_tool_action(action)

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return ErrorObservation(
                content=f"Action execution error: {e}",
                error_id="action_execution_error",
                cause=action.id
            )

    async def _execute_tool_action(self, action: Action) -> Observation:
        """
        Unified tool execution for all action types.
        
        Args:
            action: Action to execute (with or without tool_call_metadata)
            
        Returns:
            Observation: Result with metadata transferred if available
        """
        # Determine tool name and metadata
        metadata = action.tool_call_metadata
        if metadata:
            tool_name = metadata.function_name
        elif hasattr(action, 'name') and action.name:
            tool_name = action.name
        else:
            error_msg = f"Action {type(action).__name__} has no tool name or metadata"
            logger.error(error_msg)
            return ErrorObservation(
                content=error_msg,
                error_id="missing_tool_name",
                cause=action.id
            )
        
        # Extract tool arguments
        if hasattr(action, 'arguments'):
            tool_input = action.arguments
        elif hasattr(action, 'tool_input'):
            tool_input = action.tool_input
        else:
            tool_input = {}
        
        # Execute the tool
        try:
            tool = self.get_tool(tool_name)
            result = await tool.run_impl(tool_input)
            
            # Create appropriate observation based on action type
            if isinstance(action, MCPAction):
                observation = MCPObservation(
                    content=str(result.tool_output) if hasattr(result, 'tool_output') else str(result),
                    name=tool_name,
                    arguments=tool_input,
                    cause=action.id
                )
            else:
                raise NotImplementedError(f"Action type {type(action).__name__} not supported")
            
            # Transfer metadata if available
            observation.tool_call_metadata = metadata
                
            return observation
            
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {e}")
            observation = ErrorObservation(
                content=f"Tool execution error for {tool_name}: {e}",
                error_id="tool_execution_error",
                cause=action.id
            )
            observation.tool_call_metadata = metadata
            return observation