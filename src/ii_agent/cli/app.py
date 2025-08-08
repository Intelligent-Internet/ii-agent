"""
Main CLI application.

This module provides the main CLI application class that orchestrates
the AgentController with event stream for CLI usage.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional, Dict, Any
from fastmcp import Client
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.cli.subscribers.console_subscriber import ConsoleSubscriber
from ii_agent.cli.input.rich_prompt import create_rich_prompt
from ii_agent.cli.commands.command_handler import CommandHandler
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.moa_controller import MoAAgentController, create_moa_controller
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.agents.moa_agent import create_moa_agent
from ii_agent.core.config.moa_config import create_default_moa_config
from ii_agent.llm import get_client
from ii_agent.llm.base import LLMClient
from ii_agent.controller.state import State
from ii_agent.llm.context_manager import LLMCompact, TodoAwareContextManager
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.core.logger import logger
from ii_agent.prompts import get_system_prompt
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_agent.cli.state_persistence import (
    StateManager,
    restore_agent_state,
    restore_configs,
)
from ii_agent.cli.plan_state import PlanStateManager
from ii_agent.cli.components.session_selector import SessionSelector
from ii_agent.controller.tool_manager import AgentToolManager
from ii_agent.llm.base import ToolParam
from ii_tool.utils import load_tools_from_mcp
from ii_tool.tools.manager import get_default_tools
from ii_tool.core import WorkspaceManager
from ii_tool.core.config import (
    WebSearchConfig, 
    WebVisitConfig, 
    ImageSearchConfig, 
    VideoGenerateConfig, 
    ImageGenerateConfig, 
    FullStackDevConfig
)
from ii_tool.tools.agent import (
    TaskAgentTool, 
    TASK_AGENT_SYSTEM_PROMPT,
    WorkflowAgentTool,
    WORKFLOW_AGENT_SYSTEM_PROMPT
)


class CLIApp:
    """Main CLI application class."""

    def __init__(
        self,
        workspace_path: str,
        config: IIAgentConfig,
        llm_config: LLMConfig,
        web_search_config: WebSearchConfig,
        web_visit_config: WebVisitConfig,
        fullstack_dev_config: FullStackDevConfig,
        image_search_config: ImageSearchConfig | None = None,
        video_generate_config: VideoGenerateConfig | None = None,
        image_generate_config: ImageGenerateConfig | None = None,
        minimal: bool = False,
        enable_moa: bool = False,
        context_manager_type: str = "todo_aware",
    ):
        # config
        self.config = config
        self.llm_config = llm_config
        self.web_search_config = web_search_config
        self.web_visit_config = web_visit_config
        self.fullstack_dev_config = fullstack_dev_config
        self.image_search_config = image_search_config
        self.video_generate_config = video_generate_config
        self.image_generate_config = image_generate_config
        # workspace
        self.workspace_path = workspace_path
        self.workspace_manager = WorkspaceManager(workspace_path)
        # Create state manager - we'll update it with continue_session later
        self.state_manager = None
        # Create event stream
        self.event_stream = AsyncEventStream(logger=logger)
        
        # Create console subscriber with config and callback
        self.console_subscriber = ConsoleSubscriber(
            minimal=minimal,
            config=config,
            confirmation_callback=self._handle_tool_confirmation
        )
        
        # Subscribe to events
        self.event_stream.subscribe(self.console_subscriber.handle_event)

        # Create command handler first
        self.command_handler = CommandHandler(self.console_subscriber.console)

        # Create rich prompt with command handler
        self.rich_prompt = create_rich_prompt(
            workspace_path, self.console_subscriber.console, self.command_handler
        )

        # Store MoA preference
        self.enable_moa = enable_moa
        
        # Store context manager preference
        self.context_manager_type = context_manager_type
        
        # Agent controller will be created when needed
        self.agent_controller: Optional[AgentController] = None
        
        # Store for pending tool confirmations
        self._tool_confirmations: Dict[str, Dict[str, Any]] = {}
        
        # Initialize plan state manager
        self.plan_state_manager = PlanStateManager(workspace_path)
        
        # Ensure plans directory exists
        plans_dir = self.plan_state_manager.get_plans_directory()
        plans_dir.mkdir(exist_ok=True)
        logger.info(f"Plans directory initialized: {plans_dir}")
    
    def _create_context_manager(self, client: LLMClient, token_counter: TokenCounter) -> ContextManager:
        """Create a context manager based on configuration."""
        if self.context_manager_type == "todo_aware":
            return TodoAwareContextManager(
                client=client,
                token_counter=token_counter,
                token_budget=TOKEN_BUDGET,
            )
        elif self.context_manager_type == "compact":
            return LLMCompact(
                client=client,
                token_counter=token_counter,
                token_budget=TOKEN_BUDGET,
            )
        else:
            # Fallback to todo_aware as default
            return TodoAwareContextManager(
                client=client,
                token_counter=token_counter,
                token_budget=TOKEN_BUDGET,
            )
        
    def _handle_tool_confirmation(self, tool_call_id: str, tool_name: str, approved: bool, alternative_instruction: str) -> None:
        """Handle tool confirmation response from console subscriber."""
        # Store the confirmation response
        self._tool_confirmations[tool_call_id] = {
            "tool_name": tool_name,
            "approved": approved,
            "alternative_instruction": alternative_instruction
        }
        
        # If there's an agent controller, send the confirmation response to it
        if self.agent_controller:
            self.agent_controller.add_confirmation_response(tool_call_id, approved, alternative_instruction)
            logger.debug(f"Tool confirmation sent to agent controller: {tool_call_id} -> approved={approved}")
        else:
            logger.debug(f"Tool confirmation received but no agent controller: {tool_call_id} -> approved={approved}")
        
    async def initialize_agent(self, continue_from_state: bool = False, resume_session_data: Optional[Dict] = None) -> None:
        """Initialize the agent controller."""
        if self.agent_controller is not None:
            return

        # Create state manager now that we know if we're continuing
        if self.state_manager is None:
            self.state_manager = StateManager(
                Path(self.workspace_path), continue_session=continue_from_state
            )

        settings_store = await FileSettingsStore.get_instance(self.config, None)
        settings = await settings_store.load()
        
        # Ensure CLI config exists with defaults
        if not settings.cli_config:
            from ii_agent.core.config.cli_config import CliConfig
            settings.cli_config = CliConfig()
            await settings_store.store(settings)
        
        # Update console subscriber with settings
        self.console_subscriber.settings = settings

        # Load saved state - prioritize resume_session_data, then continue_from_state
        saved_state_data = None
        if resume_session_data:
            saved_state_data = resume_session_data
            self.console_subscriber.console.print(
                f"🔄 [cyan]Resuming session {saved_state_data.get('session_id', 'unknown')}...[/cyan]"
            )
        elif continue_from_state:
            saved_state_data = self.state_manager.load_state()
            if saved_state_data:
                self.console_subscriber.console.print(
                    "🔄 [cyan]Continuing from previous state...[/cyan]"
                )
            else:
                self.console_subscriber.console.print(
                    "⚠️ [yellow]No saved state found, starting fresh...[/yellow]"
                )
        
        # Update configurations from saved state if available
        if saved_state_data:
            config_data, llm_config_data = restore_configs(saved_state_data)
            if config_data:
                for key, value in config_data.items():
                    if hasattr(self.config, key):
                        setattr(self.config, key, value)
            if llm_config_data:
                for key, value in llm_config_data.items():
                    if hasattr(self.llm_config, key):
                        setattr(self.llm_config, key, value)

        # Create LLM client based on configuration
        llm_client = get_client(self.llm_config)

        # Create agent
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=get_system_prompt(self.workspace_manager.get_workspace_path()),
        )

        tool_manager = AgentToolManager()

        # Get core tools
        tool_manager.register_tools(
            get_default_tools(
                chat_session_id=self.config.session_id,
                workspace_path=self.workspace_path,
                web_search_config=self.web_search_config,
                web_visit_config=self.web_visit_config,
                fullstack_dev_config=self.fullstack_dev_config,
                image_search_config=self.image_search_config,
                video_generate_config=self.video_generate_config,
                image_generate_config=self.image_generate_config,
            )
        )

        if self.config.mcp_config:
            mcp_tools = await load_tools_from_mcp(self.config.mcp_config)
            tool_manager.register_tools(mcp_tools)

        # Add TaskAgent tool
        # ---------------------------------------------------------------------
        task_agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=TASK_AGENT_SYSTEM_PROMPT,
        )
        task_agent_list_tools = get_default_tools(
            chat_session_id=f"TASK-AGENT-{self.config.session_id}",
            workspace_path=self.workspace_path,
            web_search_config=self.web_search_config,
            web_visit_config=self.web_visit_config,
        )
        task_agent_tool = TaskAgentTool(
            agent=FunctionCallAgent(
                llm=llm_client,
                config=task_agent_config,
                tools=[ToolParam(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in task_agent_list_tools]
            ),
            tools=task_agent_list_tools,
            context_manager=self._create_context_manager(
                client=llm_client,
                token_counter=TokenCounter()
            ),
            event_stream=self.event_stream,
            workspace_manager=self.workspace_manager,
        )

        tool_manager.register_tools([task_agent_tool])
        
        # Add WorkflowAgent tool
        # ---------------------------------------------------------------------
        workflow_agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=WORKFLOW_AGENT_SYSTEM_PROMPT,
        )
        workflow_agent_list_tools = get_default_tools(
            chat_session_id=f"WORKFLOW-AGENT-{self.config.session_id}",
            workspace_path=self.workspace_path,
            web_search_config=self.web_search_config,
            web_visit_config=self.web_visit_config,
        )
        workflow_agent_tool = WorkflowAgentTool(
            agent=FunctionCallAgent(
                llm=llm_client,
                config=workflow_agent_config,
                tools=[ToolParam(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in workflow_agent_list_tools]
            ),
            tools=workflow_agent_list_tools,
            context_manager=self._create_context_manager(
                client=llm_client,
                token_counter=TokenCounter()
            ),
            event_stream=self.event_stream,
            workspace_manager=self.workspace_manager,
        )
        
        tool_manager.register_tools([workflow_agent_tool])
        # ---------------------------------------------------------------------

        # Get tools as ToolParam list
        tools = [ToolParam(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in tool_manager.get_tools()]
        
        # Create agent based on MoA preference
        if self.enable_moa:
            # For MoA, agent will be created by the MoA controller
            agent = None
        else:
            agent = FunctionCallAgent(
                llm=llm_client, 
                config=agent_config,
                tools=tools
            )
        
        # Create context manager
        token_counter = TokenCounter()
        context_manager = self._create_context_manager(
            client=llm_client,
            token_counter=token_counter
        )

        # Create message history - restore from saved state if available
        if saved_state_data:
            state = restore_agent_state(saved_state_data)
        else:
            state = State()

        # Create agent controller based on MoA preference
        if self.enable_moa:
            # Create MoA configuration
            moa_config = create_default_moa_config()
            
            # Update agent config with MoA
            agent_config.moa_config = moa_config
            
            # Create MoA agent controller
            self.agent_controller = create_moa_controller(
                tool_manager=tool_manager,
                tools=tools,
                init_history=state,
                workspace_manager=self.workspace_manager,
                event_stream=self.event_stream,
                context_manager=context_manager,
                moa_config=moa_config,
                agent_config=agent_config,
                interactive_mode=True,
                config=self.config,
            )
            
            # Print MoA activation message
            self.console_subscriber.console.print("[bold green]🚀 MoA (Mixture-of-Agents) enabled! Using Claude + GPT-4 + Gemini working together.[/bold green]")
            
        else:
            # Create standard agent controller
            self.agent_controller = AgentController(
                agent=agent,
                tool_manager=tool_manager,
                init_history=state,
                workspace_manager=self.workspace_manager,
                event_stream=self.event_stream,
                context_manager=context_manager,
                interactive_mode=True,
                config=self.config,
            )

        # Print configuration info
        self.console_subscriber.print_config_info(self.llm_config)
        self.console_subscriber.print_workspace_info(str(self.workspace_manager.get_workspace_path()))

        # Show previous conversation history if continuing from state
        if continue_from_state and saved_state_data:
            self.console_subscriber.render_conversation_history(
                self.agent_controller.history
            )

    async def run_interactive_mode(
        self,
        session_name: Optional[str] = None,
        resume: bool = False,
        continue_from_state: bool = False,
    ) -> int:
        """Run interactive chat mode."""
        try:
            # Handle resume flag - let user select session
            selected_session_data = None
            if resume:
                selected_session_data = await self._handle_resume_selection()
                if selected_session_data:
                    # Initialize agent with the selected session data
                    await self.initialize_agent(continue_from_state=False, resume_session_data=selected_session_data)
                else:
                    # User chose new session or selection failed
                    await self.initialize_agent(continue_from_state)
            else:
                await self.initialize_agent(continue_from_state)

            self.console_subscriber.print_welcome()
            self.console_subscriber.print_session_info(session_name)

            # Show session history if we resumed from a selected session
            if selected_session_data:
                self.console_subscriber.render_conversation_history(
                    self.agent_controller.history
                )

            while True:
                try:
                    # Get user input using rich prompt
                    user_input = await self.rich_prompt.get_input()

                    if not user_input:
                        continue

                    # Check if it's a slash command
                    if self.command_handler.is_command(user_input):
                        # Create command context
                        command_context = {
                            "app": self,
                            "config": self.config,
                            "agent_controller": self.agent_controller,
                            "workspace_manager": self.workspace_manager,
                            "plan_state_manager": self.plan_state_manager,
                            "session_name": session_name,
                            "should_exit": False,
                        }

                        # Execute command
                        result = await self.command_handler.execute_command(
                            user_input, command_context
                        )

                        # Check if we should exit
                        if (
                            command_context.get("should_exit", False)
                            or result == "EXIT_COMMAND"
                        ):
                            break

                        # Continue to next iteration for commands
                        continue

                    # Handle regular conversation input
                    if user_input.lower() in ["exit", "quit", "bye"]:
                        break

                    # Run agent
                    if self.agent_controller is None:
                        raise RuntimeError("Agent controller not initialized")
                    await self.agent_controller.run_agent_async(
                        instruction=user_input,
                        files=None,
                        resume=True,  # Always resume in interactive mode
                    )

                    # Save session if name provided
                    if session_name:
                        self._save_session(session_name)

                except KeyboardInterrupt:
                    self.console_subscriber.console.print("\n⚠️ [yellow]Interrupted by user[/yellow]")
                    if self.agent_controller is not None:
                        self.agent_controller.cancel()
                    continue
                except EOFError:
                    break

            # Save state before exit (always save so it can be restored with --continue)
            self._save_state_on_exit(True)

            self.console_subscriber.print_goodbye()
            return 0

        except Exception as e:
            logger.error(f"Error in interactive mode: {e}")
            # if self.config.debug:
            import traceback

            traceback.print_exc()
            return 1

    async def _handle_resume_selection(self) -> Optional[Dict[str, Any]]:
        """Handle session selection for --resume flag."""
        try:
            # Create a temporary state manager to list sessions
            temp_state_manager = StateManager(
                workspace_path=Path(self.workspace_path),
                continue_session=False
            )
            
            # Get available sessions
            available_sessions = temp_state_manager.list_available_sessions()
            
            if not available_sessions:
                self.console_subscriber.console.print("[yellow]No previous sessions found. Starting new session.[/yellow]")
                return None
            
            # Show session selector
            session_selector = SessionSelector(self.console_subscriber.console)
            selected_session_id = session_selector.select_session(available_sessions)
            
            if not selected_session_id:
                # User chose new session or cancelled
                return None
            
            # Load the selected session
            selected_session_data = temp_state_manager.load_specific_session(selected_session_id)
            
            if selected_session_data:
                # Display session info
                session_info = next((s for s in available_sessions if s["session_id"] == selected_session_id), None)
                if session_info:
                    session_selector.display_session_info(session_info)
            
            return selected_session_data
            
        except Exception as e:
            logger.error(f"Error handling resume selection: {e}")
            self.console_subscriber.console.print(f"[red]Error selecting session: {e}. Starting new session.[/red]")
            return None

    def _read_instruction_from_file(self, file_path: str) -> str:
        """Read instruction from file."""
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading instruction file: {e}")
            return ""

    def _save_output(self, result: str, output_file: str, output_format: str) -> None:
        """Save output to file."""
        try:
            if output_format == "json":
                data = {
                    "result": result,
                    "timestamp": str(asyncio.get_event_loop().time()),
                }
                with open(output_file, "w") as f:
                    json.dump(data, f, indent=2)
            elif output_format == "markdown":
                with open(output_file, "w") as f:
                    f.write(f"# Agent Result\n\n{result}\n")
            else:  # text
                with open(output_file, "w") as f:
                    f.write(result)

            print(f"Output saved to: {output_file}")
        except Exception as e:
            print(f"Error saving output: {e}")

    def _load_session(self, session_name: str) -> None:
        """Load session from file."""
        try:
            session_dir = self.config.get_session_dir()
            if not session_dir:
                return

            session_file = session_dir / f"{session_name}.json"
            if not session_file.exists():
                print(f"Session '{session_name}' not found")
                return

            with open(session_file, "r") as f:
                session_data = json.load(f)

            # Restore message history
            if self.agent_controller and "history" in session_data:
                # You'll need to implement history restoration based on your State class
                pass

            print(f"Session '{session_name}' loaded")

        except Exception as e:
            print(f"Error loading session: {e}")

    def _save_session(self, session_name: str) -> None:
        """Save session to file."""
        try:
            session_dir = self.config.get_session_dir()
            if not session_dir:
                return

            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / f"{session_name}.json"

            # Save message history
            session_data = {
                "name": session_name,
                "timestamp": str(asyncio.get_event_loop().time()),
                "config": self.config.get_llm_config(),
            }

            if self.agent_controller:
                # You'll need to implement history serialization based on your State class
                pass

            with open(session_file, "w") as f:
                json.dump(session_data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving session: {e}")

    def _save_state_on_exit(self, should_save: bool) -> None:
        """Save agent state when exiting if requested."""
        if not should_save or not self.agent_controller or not self.state_manager:
            return

        try:
            # Get the current state from agent controller
            current_state = self.agent_controller.history  # Access the state directly

            # Only save if there's conversation history
            if len(current_state.message_lists) == 0:
                return

            # Save the complete state
            self.state_manager.save_state(
                agent_state=current_state,
                config=self.config,
                llm_config=self.llm_config,
                workspace_path=str(self.workspace_manager.get_workspace_path()),
                session_name=None,  # For --continue, we don't use session names
            )

            self.console_subscriber.console.print(
                "💾 [green]State saved for next --continue[/green]"
            )

        except Exception as e:
            logger.error(f"Error saving state on exit: {e}")
            self.console_subscriber.console.print(
                f"⚠️ [yellow]Failed to save state: {e}[/yellow]"
            )

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.event_stream:
            self.event_stream.clear_subscribers()

        if self.rich_prompt:
            self.rich_prompt.cleanup()

        # Clean up console subscriber resources
        if self.console_subscriber:
            self.console_subscriber.cleanup()
