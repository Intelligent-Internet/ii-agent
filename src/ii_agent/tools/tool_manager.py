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
from ii_agent.llm.message_history import ToolCallParameters
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
from ii_agent.core.logger import logger
from ii_agent.events.action import (
    Action, ToolCallAction, MessageAction, CompleteAction,
    FileReadAction, FileWriteAction, FileEditAction,
    CmdRunAction, IPythonRunCellAction,
    BrowseURLAction, BrowseInteractiveAction
)
from ii_agent.events.observation import (
    UserMessageObservation, SystemObservation, 
    FileReadObservation, FileWriteObservation, FileEditObservation,
    CmdOutputObservation, BrowseObservation
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
        StrReplaceEditorTool(
            workspace_manager=workspace_manager, message_queue=message_queue
        ),
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

    def __init__(self, tools: List[LLMTool], interactive_mode: bool = True, reviewer_mode: bool = False):
        if reviewer_mode:
            self.complete_tool = ReturnControlToGeneralAgentTool() if interactive_mode else CompleteToolReviewer()
        else:
            self.complete_tool = ReturnControlToUserTool() if interactive_mode else CompleteTool()
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
        logger.info(f"Running tool: {tool_name}")
        logger.info(f"Tool input: {tool_input}")
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

        logger.info(log_message)

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

    async def handle_action(self, action):
        """
        Handle different types of actions and return appropriate observations.
        Similar to OpenHands Runtime._handle_action method.

        Args:
            action: The action to execute (from events.action)

        Returns:
            Observation: The result of the action execution
        """
        try:
            # Handle different action types
            if isinstance(action, ToolCallAction):
                return await self._handle_tool_call_action(action)
            elif isinstance(action, MessageAction):
                return await self._handle_message_action(action)
            elif isinstance(action, CompleteAction):
                return await self._handle_complete_action(action)
            elif isinstance(action, FileReadAction):
                return await self._handle_file_read_action(action)
            elif isinstance(action, FileWriteAction):
                return await self._handle_file_write_action(action)
            elif isinstance(action, FileEditAction):
                return await self._handle_file_edit_action(action)
            elif isinstance(action, CmdRunAction):
                return await self._handle_cmd_run_action(action)
            elif isinstance(action, IPythonRunCellAction):
                return await self._handle_ipython_action(action)
            elif isinstance(action, BrowseURLAction):
                return await self._handle_browse_url_action(action)
            elif isinstance(action, BrowseInteractiveAction):
                return await self._handle_browse_interactive_action(action)
            else:
                # Unknown action type
                error_msg = f"Unknown action type: {type(action).__name__}"
                logger.error(error_msg)
                return SystemObservation(
                    content=f"ERROR: {error_msg}",
                    cause=action.id
                )

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return SystemObservation(
                content=f"ERROR: Action execution error: {e}",
                cause=action.id
            )

    async def _handle_tool_call_action(self, action):
        """Handle ToolCallAction by executing the tool."""
        # Convert action to ToolCallParameters for compatibility
        tool_params = ToolCallParameters(
            tool_call_id=action.tool_call_id,
            tool_name=action.tool_name,
            tool_input=action.tool_input
        )

        try:
            # Use existing run_tool method
            result = await self.run_tool(tool_params, None)  # MessageHistory not needed in new pattern
            
            # Convert result to observation
            return ToolResultObservation(
                tool_name=action.tool_name,
                tool_call_id=action.tool_call_id,
                tool_output=result,
                content=str(result),
                success=True,
                cause=action.id
            )
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return SystemObservation(
                content=f"Tool execution error: {e}",
                event_type="tool_error",
                cause=action.id
            )

    async def _handle_message_action(self, action):
        """Handle MessageAction by creating a UserMessageObservation."""
        return UserMessageObservation(
            content=action.content,
            cause=action.id
        )

    async def _handle_complete_action(self, action):
        """Handle CompleteAction by creating a SystemObservation."""
        return SystemObservation(
            content=f"Task completed: {action.final_answer}",
            cause=action.id
        )

    async def _handle_file_read_action(self, action):
        """Handle FileReadAction by delegating to file_read tool."""
        try:
            # Find the file read tool and execute it
            tool_params = {
                'tool_call_id': getattr(action, 'tool_call_id', ''),
                'tool_name': 'str_replace_editor',
                'tool_input': {
                    'command': 'view',
                    'path': action.path,
                    'view_range': [action.start, action.end] if action.end != -1 else None
                }
            }
            
            tool_call = ToolCallParameters(**tool_params)
            result = await self.run_tool(tool_call, None)
            
            return FileReadObservation(
                path=action.path,
                content=str(result),
                success=True,
                lines_read=len(str(result).splitlines()) if result else 0,
                cause=action.id
            )
        except Exception as e:
            logger.error(f"File read failed: {e}")
            return SystemObservation(
                content=f"ERROR: File read error: {e}",
                cause=action.id
            )

    async def _handle_file_write_action(self, action):
        """Handle FileWriteAction by delegating to file write tool."""
        try:
            # Find the file write tool and execute it
            tool_params = {
                'tool_call_id': getattr(action, 'tool_call_id', ''),
                'tool_name': 'str_replace_editor',
                'tool_input': {
                    'command': 'create',
                    'path': action.path,
                    'file_text': action.content
                }
            }
            
            tool_call = ToolCallParameters(**tool_params)
            result = await self.run_tool(tool_call, None)
            
            return FileWriteObservation(
                path=action.path,
                content=str(result),
                success=True,
                bytes_written=len(action.content.encode('utf-8')) if hasattr(action, 'content') else 0,
                cause=action.id
            )
        except Exception as e:
            logger.error(f"File write failed: {e}")
            return SystemObservation(
                content=f"ERROR: File write error: {e}",
                cause=action.id
            )

    async def _handle_file_edit_action(self, action):
        """Handle FileEditAction by delegating to file edit tool."""
        try:
            # Find the file edit tool and execute it
            tool_params = {
                'tool_call_id': getattr(action, 'tool_call_id', ''),
                'tool_name': 'str_replace_editor',
                'tool_input': {
                    'command': 'str_replace',
                    'path': action.path,
                    'old_str': action.old_str,
                    'new_str': action.new_str
                }
            }
            
            tool_call = ToolCallParameters(**tool_params)
            result = await self.run_tool(tool_call, None)
            
            return FileEditObservation(
                path=action.path,
                content=str(result),
                success=True,
                prev_exist=True,  # Assume file exists for edit
                cause=action.id
            )
        except Exception as e:
            logger.error(f"File edit failed: {e}")
            return SystemObservation(
                content=f"ERROR: File edit error: {e}",
                cause=action.id
            )

    async def _handle_cmd_run_action(self, action):
        """Handle CmdRunAction by delegating to bash tool."""
        try:
            # Find the bash tool and execute it
            tool_params = {
                'tool_call_id': getattr(action, 'tool_call_id', ''),
                'tool_name': 'bash',
                'tool_input': {
                    'command': action.command
                }
            }
            
            tool_call = ToolCallParameters(**tool_params)
            result = await self.run_tool(tool_call, None)
            
            return CmdOutputObservation(
                command=action.command,
                content=str(result),
                exit_code=0,  # Assume success if no exception
                cause=action.id
            )
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return SystemObservation(
                content=f"ERROR: Command execution error: {e}",
                cause=action.id
            )

    async def _handle_ipython_action(self, action):
        """Handle IPythonRunCellAction - not implemented yet."""
        return SystemObservation(
            content="ERROR: IPython execution not yet implemented in tool manager",
            cause=action.id
        )

    async def _handle_browse_url_action(self, action):
        """Handle BrowseURLAction by delegating to browser tool."""
        try:
            # Find the browser tool and execute it
            tool_params = {
                'tool_call_id': getattr(action, 'tool_call_id', ''),
                'tool_name': 'visit_webpage',
                'tool_input': {
                    'url': action.url
                }
            }
            
            tool_call = ToolCallParameters(**tool_params)
            result = await self.run_tool(tool_call, None)
            
            return BrowseObservation(
                url=action.url,
                content=str(result),
                success=True,
                cause=action.id
            )
        except Exception as e:
            logger.error(f"Browse URL failed: {e}")
            return SystemObservation(
                content=f"ERROR: Browse URL error: {e}",
                cause=action.id
            )

    async def _handle_browse_interactive_action(self, action):
        """Handle BrowseInteractiveAction - delegate to browser tools."""
        return SystemObservation(
            content="ERROR: Interactive browsing not yet fully implemented in tool manager",
            cause=action.id
        )

    # Legacy method for backward compatibility
    async def run_tool_action(self, action):
        """
        Legacy method for backward compatibility.
        Use handle_action instead.
        """
        return await self.handle_action(action)
