"""
Main CLI application.

This module provides the main CLI application class that orchestrates
the AgentController with event stream for CLI usage.
"""

import asyncio
import json
import signal
from pathlib import Path
from typing import Optional, Dict, Any
from uuid import UUID
from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.cli.subscribers.console_subscriber import ConsoleSubscriber
from ii_agent.cli.input.rich_prompt import create_rich_prompt
from ii_agent.cli.commands.command_handler import CommandHandler
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.controller.agent_controller import AgentController
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.llm import get_client
from ii_agent.controller.state import State
from ii_agent.llm.context_manager import LLMCompact
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.runtime.runtime_manager import RuntimeManager
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.core.logger import logger
from ii_agent.prompts.system_prompt import SYSTEM_PROMPT
from ii_agent.utils.constants import TOKEN_BUDGET
from ii_agent.cli.state_persistence import (
    StateManager,
    restore_agent_state,
    restore_configs,
)
from ii_agent.tools import AgentToolManager
from ii_agent.llm.base import ToolParam


class CLIApp:
    """Main CLI application class."""

    def __init__(
        self,
        config: IIAgentConfig,
        llm_config: LLMConfig,
        workspace_path: str,
        minimal: bool = False,
    ):
        self.config = config
        self.llm_config = llm_config
        self.workspace_manager = WorkspaceManager(Path(workspace_path))
        # Create state manager - we'll update it with continue_session later
        self.workspace_path = workspace_path
        # Create event stream
        self.event_stream = AsyncEventStream(logger=logger)
        
        # Create console subscriber with config and callback
        self.console_subscriber = ConsoleSubscriber(
            minimal=minimal,
            config=config,
            confirmation_callback=self._handle_tool_confirmation
        )
        self.session_config = None
        
        # Subscribe to events
        self.event_stream.subscribe(self.console_subscriber.handle_event)

        # Create command handler first
        self.command_handler = CommandHandler(self.console_subscriber.console)

        # Create rich prompt with command handler
        self.rich_prompt = create_rich_prompt(
            workspace_path, self.console_subscriber.console, self.command_handler
        )

        # Agent controller will be created when needed
        self.agent_controller: Optional[AgentController] = None
        
        # Store for pending tool confirmations
        self._tool_confirmations: Dict[str, Dict[str, Any]] = {}
        
        # Setup signal handlers
        self._setup_signal_handlers()
        
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
        
    async def initialize_agent(self) -> None:
        """Initialize the agent controller."""
        if self.agent_controller is not None:
            return

        if not self.session_config:
            raise ValueError("Session config not initialized")



        saved_state_data = None
        # Initialize with session continuation check
        is_valid_session = self.state_manager.is_valid_session(self.session_config.session_id)
        if is_valid_session:
            saved_state_data = self.state_manager.load_state(self.session_config.session_id)
            if saved_state_data:
                self.console_subscriber.console.print(
                    "🔄 [cyan]Continuing from previous state...[/cyan]"
                )
                # Update configurations from saved state if available
                config_data, llm_config_data = restore_configs(saved_state_data)
                if config_data:
                    for key, value in config_data.items():
                        if hasattr(self.config, key):
                            setattr(self.config, key, value)
                if llm_config_data:
                    for key, value in llm_config_data.items():
                        if hasattr(self.llm_config, key):
                            setattr(self.llm_config, key, value)
            else:
                self.console_subscriber.console.print(
                    "⚠️ [yellow]No saved state found, starting fresh...[/yellow]"
                )

        # Create LLM client based on configuration
        llm_client = get_client(self.llm_config)

        # Create agent
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=SYSTEM_PROMPT,
        )

        tool_manager = AgentToolManager()

        runtime_manager = RuntimeManager(
            session_config=self.session_config, settings=self.settings
        )
        if not self.state_manager.is_valid_session(self.session_config.session_id):
            await runtime_manager.start_runtime()
        else:
            await runtime_manager.connect_runtime()
        mcp_client = await runtime_manager.get_mcp_client(
            str(self.workspace_manager.root)
        )

        await tool_manager.register_mcp_tools(
            mcp_client=mcp_client,
            trust=True, # Trust the system MCP tools
        )

        if self.config.mcp_config:
            # Don't trust the custom MCP tools by default
            await tool_manager.register_mcp_tools(Client(self.config.mcp_config), trust=False)

        agent = FunctionCallAgent(
            llm=llm_client, 
            config=agent_config,
            tools=[ToolParam(name=tool.name, description=tool.description, input_schema=tool.input_schema) for tool in tool_manager.get_tools()]
        )
        
        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMCompact(
            client=llm_client,
            token_counter=token_counter,
            token_budget=TOKEN_BUDGET,  # Default token budget
        )

        # Create message history - restore from saved state if available
        if saved_state_data:
            state = restore_agent_state(saved_state_data)
        else:
            state = State()

        # Create agent controller
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
        self.console_subscriber.print_workspace_info(str(self.workspace_manager.root))

        # Show previous conversation history if continuing from state
        if is_valid_session and saved_state_data:
            self.console_subscriber.render_conversation_history(
                self.agent_controller.history
            )

    async def run_interactive_mode(self) -> int:
        """Run interactive chat mode."""
        try:
            #Initialize settings
            settings_store = await FileSettingsStore.get_instance(self.config, None)
            self.settings = await settings_store.load()
            
            # Ensure CLI config exists with defaults
            if not self.settings.cli_config:
                from ii_agent.core.config.cli_config import CliConfig
                self.settings.cli_config = CliConfig()
            await settings_store.store(self.settings)
            self.console_subscriber.settings = self.settings
            self.state_manager = StateManager(self.config, self.settings)

            self.session_config = await self.console_subscriber.select_session_config(self.state_manager)
            await self.initialize_agent()

            self.console_subscriber.print_welcome()
            self.console_subscriber.print_session_info(
                self.session_config.session_id if self.session_config else None,
                self.session_config.mode.value if self.session_config else None
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
                            "session_name": self.session_config.session_name
                            if self.session_config
                            else None,
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

    def _save_state_on_exit(self, should_save: bool) -> None:
        """Save agent state when exiting if requested."""
        if not should_save or not self.agent_controller or not self.state_manager or not self.session_config:
            return

        try:
            # Get the current state from agent controller
            current_state = self.agent_controller.history  # Access the state directly

            # Only save if there's conversation history
            if len(current_state.message_lists) == 0:
                return

            # Save the complete state
            self.state_manager.save_state(
                session_id=self.session_config.session_id,
                agent_state=current_state,
                config=self.config,
                llm_config=self.llm_config,
                workspace_path=str(self.workspace_manager.root),
            )

            self.console_subscriber.console.print(
                "💾 [green]State saved for next --continue[/green]"
            )

        except Exception as e:
            logger.error(f"Error saving state on exit: {e}")
            self.console_subscriber.console.print(
                f"⚠️ [yellow]Failed to save state: {e}[/yellow]"
            )

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTSTP"
            self.console_subscriber.console.print(f"\n\n🛑 [yellow]Received {signal_name}, saving state...[/yellow]")
            self._save_state_on_exit(True)
            self.console_subscriber.print_goodbye()
            exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        # Note: SIGTSTP (Ctrl+Z) cannot be caught in the same way as it suspends the process
        # We'll handle KeyboardInterrupt in the main loop instead

    def cleanup(self) -> None:
        """Clean up resources."""
        if self.event_stream:
            self.event_stream.clear_subscribers()

        if self.rich_prompt:
            self.rich_prompt.cleanup()

        # Clean up console subscriber resources
        if self.console_subscriber:
            self.console_subscriber.cleanup()