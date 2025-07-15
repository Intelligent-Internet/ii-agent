"""
Main CLI application.

This module provides the main CLI application class that orchestrates
the AgentController with event stream for CLI usage.
"""

import asyncio
import json
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.config.agent_config import AgentConfig
from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.cli.subscribers.console_subscriber import ConsoleSubscriber
from ii_agent.core.event_stream import AsyncEventStream
from ii_agent.controller.agent_controller import AgentController
from ii_agent.controller.agent import Agent
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.llm import get_client
from ii_agent.controller.state import State
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.tools import get_system_tools
from ii_agent.core.logger import logger
from ii_agent.prompts.system_prompt import SYSTEM_PROMPT
from ii_agent.utils.constants import TOKEN_BUDGET


class CLIApp:
    """Main CLI application class."""
    
    def __init__(self, config: IIAgentConfig, llm_config: LLMConfig, workspace_path: str, minimal: bool = False):
        self.config = config
        self.llm_config = llm_config
        self.workspace_manager = WorkspaceManager(Path(workspace_path))
        # Create event stream
        self.event_stream = AsyncEventStream(logger=logger)
        
        # Create console subscriber
        self.console_subscriber = ConsoleSubscriber(
            minimal=minimal
        )
        
        # Subscribe to events
        self.event_stream.subscribe(self.console_subscriber.handle_event)
        
        # Agent controller will be created when needed
        self.agent_controller: Optional[AgentController] = None
        
    async def initialize_agent(self) -> None:
        """Initialize the agent controller."""
        if self.agent_controller is not None:
            return

        settings_store = await FileSettingsStore.get_instance(self.config, None)
        settings = await settings_store.load()

        
        # Create LLM client based on configuration
        llm_client = get_client(self.llm_config)
        
        # Create agent
        agent_config = AgentConfig(
            max_tokens_per_turn=self.config.max_output_tokens_per_turn,
            system_prompt=SYSTEM_PROMPT,
        )
        
        
        # Get system tools
        tools = get_system_tools(
            client=llm_client,
            settings=settings,
            workspace_manager=self.workspace_manager,
        )

        agent = FunctionCallAgent(
            llm_client, 
            agent_config,
            tools
        )
        
        
        # Create context manager
        token_counter = TokenCounter()
        context_manager = LLMSummarizingContextManager(
            client=llm_client,
            token_counter=token_counter,
            token_budget=TOKEN_BUDGET,  # Default token budget
        )
        
        # Create message history
        state = State(context_manager)
        
        # Create agent controller
        self.agent_controller = AgentController(
            agent=agent,
            tools=tools,
            init_history=state,
            workspace_manager=self.workspace_manager,
            event_stream=self.event_stream,
            interactive_mode=True,
        )
        
        # Print configuration info
        self.console_subscriber.print_config_info(self.llm_config)
        self.console_subscriber.print_workspace_info(str(self.workspace_manager.root))
    
    async def run_interactive_mode(
        self, 
        session_name: Optional[str] = None,
        resume: bool = False
    ) -> int:
        """Run interactive chat mode."""
        try:
            await self.initialize_agent()
            
            self.console_subscriber.print_welcome()
            self.console_subscriber.print_session_info(session_name)
            
            # Load session if resuming
            if resume and session_name:
                self._load_session(session_name)
            
            while True:
                try:
                    # Get user input
                    user_input = input("\n👤 You: ").strip()
                    
                    if user_input.lower() in ['exit', 'quit', 'bye']:
                        break
                    
                    if not user_input:
                        continue
                    
                    # Run agent
                    await self.agent_controller.run_agent_async(
                        instruction=user_input,
                        files=None,
                        resume=True  # Always resume in interactive mode
                    )
                    
                    # Save session if name provided
                    if session_name:
                        self._save_session(session_name)
                
                except KeyboardInterrupt:
                    print("\n⚠️ Interrupted by user")
                    self.agent_controller.cancel()
                    continue
                except EOFError:
                    break
            
            self.console_subscriber.print_goodbye()
            return 0
            
        except Exception as e:
            logger.error(f"Error in interactive mode: {e}")
            # if self.config.debug:
            import traceback
            traceback.print_exc()
            return 1
    
    async def run_single_instruction(
        self,
        instruction: Optional[str] = None,
        file_path: Optional[str] = None,
        attachments: List[str] = None,
        output_file: Optional[str] = None,
        output_format: str = "text"
    ) -> int:
        """Run a single instruction."""
        try:
            await self.initialize_agent()
            
            # Get instruction
            if file_path:
                instruction = self._read_instruction_from_file(file_path)
            
            if not instruction:
                print("Error: No instruction provided")
                return 1
            
            # Process attachments
            processed_attachments = []
            if attachments:
                for attachment in attachments:
                    attachment_path = Path(attachment)
                    if attachment_path.exists():
                        processed_attachments.append(str(attachment_path.resolve()))
                    else:
                        print(f"Warning: Attachment not found: {attachment}")
            
            # Run agent
            result = await self.agent_controller.run_agent_async(
                instruction=instruction,
                files=processed_attachments,
                resume=False
            )
            
            # Handle output
            if output_file:
                self._save_output(result, output_file, output_format)
            
            return 0
            
        except Exception as e:
            logger.error(f"Error running instruction: {e}")
            if self.config.debug:
                import traceback
                traceback.print_exc()
            return 1
    
    def _read_instruction_from_file(self, file_path: str) -> str:
        """Read instruction from file."""
        try:
            with open(file_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading instruction file: {e}")
            return ""
    
    def _save_output(self, result: str, output_file: str, output_format: str) -> None:
        """Save output to file."""
        try:
            if output_format == "json":
                data = {"result": result, "timestamp": str(asyncio.get_event_loop().time())}
                with open(output_file, 'w') as f:
                    json.dump(data, f, indent=2)
            elif output_format == "markdown":
                with open(output_file, 'w') as f:
                    f.write(f"# Agent Result\n\n{result}\n")
            else:  # text
                with open(output_file, 'w') as f:
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
            
            with open(session_file, 'r') as f:
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
            
            with open(session_file, 'w') as f:
                json.dump(session_data, f, indent=2)
            
        except Exception as e:
            logger.error(f"Error saving session: {e}")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        if self.event_stream:
            self.event_stream.clear_subscribers()