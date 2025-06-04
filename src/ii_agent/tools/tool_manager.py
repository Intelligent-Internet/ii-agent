import os
import asyncio
import logging
from copy import deepcopy
from typing import Optional, List, Dict, Any
from ii_agent.llm.base import LLMClient
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.tools.advanced_tools.image_search_tool import ImageSearchTool
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
from ii_agent.tools.complete_tool import CompleteTool, ReturnControlToUserTool
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
from ii_agent.tools.advanced_tools.audio_tool import (
    AudioTranscribeTool,
    AudioGenerateTool,
)
from ii_agent.tools.advanced_tools.video_gen_tool import (
    VideoGenerateFromTextTool,
    VideoGenerateFromImageTool,
    LongVideoGenerateFromTextTool,
    LongVideoGenerateFromImageTool,
)
from ii_agent.tools.advanced_tools.image_gen_tool import ImageGenerateTool
from ii_agent.tools.advanced_tools.pdf_tool import PdfTextExtractTool
from ii_agent.tools.deep_research_tool import DeepResearchTool
from ii_agent.tools.list_html_links_tool import ListHtmlLinksTool


def get_system_tools(
    client: LLMClient,
    workspace_manager: WorkspaceManager,
    message_queue: asyncio.Queue,
    container_id: Optional[str] = None,
    ask_user_permission: bool = False,
    tool_args: Dict[str, Any] = None,
) -> list[LLMTool]:
    """
    Retrieves a list of all system tools.

    Returns:
        list[LLMTool]: A list of all system tools.
    """
    if container_id is not None:
        bash_tool = create_docker_bash_tool(
            container=container_id, ask_user_permission=ask_user_permission
        )
    else:
        bash_tool = create_bash_tool(
            ask_user_permission=ask_user_permission, cwd=workspace_manager.root
        )

    logger = logging.getLogger("presentation_context_manager")
    context_manager = LLMSummarizingContextManager(
        client=client,
        token_counter=TokenCounter(),
        logger=logger,
        token_budget=120_000,
    )

    tools = [
        MessageTool(),
        WebSearchTool(),
        VisitWebpageTool(),
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
    image_search_tool = ImageSearchTool()
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
        if tool_args.get("media_generation", False) and (
            os.environ.get("MEDIA_GCP_PROJECT_ID")
            and os.environ.get("MEDIA_GCP_LOCATION")
        ):
            tools.append(ImageGenerateTool(workspace_manager=workspace_manager))
            if tool_args.get("video_generation", False):
                tools.extend([
                    VideoGenerateFromTextTool(workspace_manager=workspace_manager), 
                    VideoGenerateFromImageTool(workspace_manager=workspace_manager),
                    LongVideoGenerateFromTextTool(workspace_manager=workspace_manager),
                    LongVideoGenerateFromImageTool(workspace_manager=workspace_manager)
                ])
        if tool_args.get("audio_generation", False) and (
            os.environ.get("OPEN_API_KEY") and os.environ.get("AZURE_OPENAI_ENDPOINT")
        ):
            tools.extend(
                [
                    AudioTranscribeTool(workspace_manager=workspace_manager),
                    AudioGenerateTool(workspace_manager=workspace_manager),
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

    def __init__(self, tools: List[LLMTool], logger_for_agent_logs: logging.Logger, interactive_mode: bool = True):
        self.logger_for_agent_logs = logger_for_agent_logs
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

    def run_tool(self, tool_params: ToolCallParameters, history: MessageHistory):
        """
        Executes a llm tool.

        Args:
            tool (LLMTool): The tool to execute.
            history (MessageHistory): The history of the conversation.
        Returns:
            ToolResult: The result of the tool execution.
        """
        llm_tool = self.get_tool(tool_params.tool_name)
        tool_name = tool_params.tool_name
        tool_input = tool_params.tool_input
        self.logger_for_agent_logs.info(f"Running tool: {tool_name}")
        self.logger_for_agent_logs.info(f"Tool input: {tool_input}")
        result = llm_tool.run(tool_input, history)

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
