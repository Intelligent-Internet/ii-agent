"""Main CLI entry point for ii-agent."""

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Optional

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import clear

from ii_agent.agents.base import BaseAgent
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.controller.agent_controller import AgentController
from ii_agent.core.logger import logger
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.core.storage.models.settings import Settings
from ii_agent.db.manager import Sessions
from ii_agent.db.models import Session
from ii_agent.utils.workspace_manager import WorkspaceManager
from ii_agent.controller.state import State, AgentState
from ii_agent.events.event import EventSource
from ii_agent.events.action import MessageAction

from ii_agent.core.config import parse_arguments, IIAgentConfig, LLMConfig, AgentConfig, CLIConfig, setup_config_from_args

from ii_agent.cli.commands import handle_commands
from ii_agent.cli.settings import modify_llm_settings_basic
from ii_agent.cli.tui import (
    display_banner,
    display_welcome_message,
    display_initialization_animation,
    display_agent_running_message,
    display_event,
    display_initial_user_prompt,
    read_prompt_input,
    read_confirmation_input,
    start_pause_listener,
    stop_pause_listener,
    UsageMetrics,
    update_streaming_output,
)
from ii_agent.cli.utils import update_usage_metrics, generate_sid


async def cleanup_session(
    loop: asyncio.AbstractEventLoop,
    agent: BaseAgent,
    controller: AgentController,
    workspace_manager: WorkspaceManager,
) -> None:
    """Clean up all resources from the current session."""
    try:
        current_task = asyncio.current_task(loop)
        pending = [task for task in asyncio.all_tasks(loop) if task is not current_task]

        if pending:
            done, pending_set = await asyncio.wait(set(pending), timeout=2.0)
            pending = list(pending_set)

        for task in pending:
            task.cancel()

    except Exception as e:
        logger.error(f'Error during session cleanup: {e}')


async def run_session(
    loop: asyncio.AbstractEventLoop,
    config: IIAgentConfig,
    llm_config: LLMConfig,
    agent_config: AgentConfig,
    settings_store: FileSettingsStore,
    settings: Optional[Settings] = None,
    task_content: Optional[str] = None,
    session_name: Optional[str] = None,
    skip_banner: bool = False,
) -> bool:
    """Run a CLI session with the agent."""
    new_session_requested = False
    
    # Generate session ID
    session_id = uuid.uuid4()
    if session_name:
        session_id = uuid.uuid5(uuid.NAMESPACE_URL, session_name)
    
    is_loaded = asyncio.Event()
    is_paused = asyncio.Event()
    always_confirm_mode = False
    
    # Show initialization animation
    loop.run_in_executor(
        None, display_initialization_animation, 'Initializing agent...', is_loaded
    )
    
    # Initialize components
    workspace_path = Path(config.workspace_root) / str(session_id)
    workspace_path.mkdir(parents=True, exist_ok=True)
    workspace_manager = WorkspaceManager(
        root=workspace_path,
        container_workspace=None
    )
    
    # Create LLM client
    from ii_agent.llm import get_client
    from ii_agent.prompts.system_prompt import SYSTEM_PROMPT
    from ii_agent.tools.tool_manager import get_system_tools, AgentToolManager
    
    llm_client = get_client(llm_config)
    system_prompt = SYSTEM_PROMPT
    
    # Create message queue for CLI communication
    message_queue = asyncio.Queue()
    
    # Get system tools with all required parameters
    tool_args = {
        'interactive_mode': True,
        'sequential_thinking': True,
        'deep_research': False,
        'pdf': True,
        'memory_tool': 'simple',
    }
    
    # Use settings if available, otherwise create empty settings
    if settings is None:
        settings = Settings()
    
    available_tools = get_system_tools(
        client=llm_client,
        workspace_manager=workspace_manager,
        message_queue=message_queue,
        settings=settings,
        container_id=None,
        tool_args=tool_args
    )
    
    # Convert tools to ToolParam format for agent
    tool_params = [tool.get_tool_param() for tool in available_tools]
    
    # Create agent
    agent = FunctionCallAgent(
        llm=llm_client,
        config=agent_config,
        system_prompt=system_prompt,
        available_tools=tool_params,
    )
    
    # Create tool manager with the actual tools
    tool_manager = AgentToolManager(tools=available_tools)
    
    # Create controller
    controller = AgentController(
        agent=agent,
        tool_manager=tool_manager,
        workspace_manager=workspace_manager,
        message_queue=message_queue,
        max_turns=config.max_turns,
        session_id=session_id,
        interactive_mode=True,
    )
    
    # Create and save session
    workspace_path = workspace_manager.root
    Sessions.create_session(
        session_uuid=session_id,
        workspace_path=workspace_path,
        device_id=None,
    )
    if session_name:
        Sessions.update_session_name(session_id, session_name)
    
    usage_metrics = UsageMetrics()
    
    async def prompt_for_next_task(agent_state: str) -> bool:
        """Prompt for next task and return whether session should continue."""
        nonlocal new_session_requested, session_active
        
        while True:
            next_message = await read_prompt_input(
                config, agent_state, multiline=config.cli.multiline_input
            )
            
            if not next_message.strip():
                continue
            
            # Handle commands first
            if next_message.startswith('/'):
                close_repl, new_session_requested = await handle_commands(
                    next_message,
                    usage_metrics,
                    session_id,
                    config,
                    settings_store,
                )
                
                if close_repl:
                    session_active = False
                    return False
                    
                if new_session_requested:
                    return False
                    
                # Continue the loop for other commands that don't end session
                continue
            
            # Process regular user message
            try:
                print_formatted_text(HTML('<cyan>⚙️ Processing your input...</cyan>'))
                
                result = await controller.run_async(next_message)
                print_formatted_text(HTML(f'<green>✓ {result.tool_result_message}</green>'))
                
                # Return True to continue session after processing one message
                return True
                
            except Exception as e:
                print_formatted_text(HTML(f'<red>✗ Error: {e}</red>'))
                # Return True to continue session even on error
                return True
    
    # Clear loading animation
    is_loaded.set()
    
    # Clear terminal
    clear()
    
    # Show banner if not skipped
    if not skip_banner:
        display_banner(session_id=str(session_id))
    
    welcome_message = 'What do you want to build?'
    initial_message = task_content or ''
    
    # Show welcome message
    display_welcome_message(welcome_message)
    
    # Process initial message if provided
    if initial_message:
        display_initial_user_prompt(initial_message)
        try:
            result = await controller.run_async(initial_message)
            print_formatted_text(HTML(f'<green>✓ {result.tool_result_message}</green>'))
        except Exception as e:
            print_formatted_text(HTML(f'<red>✗ Error: {e}</red>'))
    
    # Start main interactive session loop
    session_active = True
    
    while session_active and not new_session_requested:
        try:
            should_continue = await prompt_for_next_task('')
            
            if not should_continue:
                break
            
        except KeyboardInterrupt:
            print_formatted_text('\n⚠️ Session interrupted by user\n')
            session_active = False
        except Exception as e:
            print_formatted_text(f'\n⚠️ Error: {e}\n')
    
    await cleanup_session(loop, agent, controller, workspace_manager)
    
    print_formatted_text('✅ Session terminated successfully.\n')
    return new_session_requested


async def run_setup_flow(config: IIAgentConfig, settings_store: FileSettingsStore):
    """Run the setup flow to configure initial settings."""
    # Display the banner
    display_banner(session_id='setup')
    
    print_formatted_text(
        HTML('<grey>No settings found. Starting initial setup...</grey>\n')
    )
    
    # Use the existing settings modification function
    await modify_llm_settings_basic(config, settings_store)


async def main_with_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Main CLI entry point with event loop."""
    args = parse_arguments()

    # Setup config from args
    config = setup_config_from_args(args)
     
    # Load settings from store
    settings_store = await FileSettingsStore.get_instance(config=config, user_id=None)
    settings = await settings_store.load()
    
    banner_shown = False
    
    # If no settings exist, run setup flow
    if not settings:
        clear()
        await run_setup_flow(config, settings_store)
        banner_shown = True
        settings = await settings_store.load()
    
    # Create LLM and agent configs from settings
    llm_config = LLMConfig()
    agent_config = AgentConfig()
    
    if settings and settings.llm_configs:
        # Get the default LLM config if it exists
        default_llm_config = settings.llm_configs.get('default')
        if default_llm_config:
            llm_config = default_llm_config
    
    # Override with CLI arguments
    if args.model:
        llm_config.model = args.model
    if args.api_key:
        from pydantic import SecretStr
        llm_config.api_key = SecretStr(args.api_key)
    if args.base_url:
        llm_config.base_url = args.base_url
    if args.temperature is not None:
        llm_config.temperature = args.temperature
    if args.agent:
        agent_config.name = args.agent
    
    # Read task from args
    task_str = None
    if args.task:
        task_str = args.task
    elif args.file:
        with open(args.file, 'r', encoding='utf-8') as f:
            file_content = f.read()
        task_str = f"Please read and understand the following file content:\\n\\n```\\n{file_content}\\n```\\n\\nAfter reviewing the file, please ask me what I'd like to do with it."
    
    # Run the first session
    new_session_requested = await run_session(
        loop,
        config,
        llm_config,
        agent_config,
        settings_store,
        settings,
        task_str,
        session_name=args.name,
        skip_banner=banner_shown or args.no_banner,
    )
    
    # Handle new session requests
    while new_session_requested:
        new_session_requested = await run_session(
            loop,
            config,
            llm_config,
            agent_config,
            settings_store,
            settings,
            None,
        )


def main():
    """Main entry point for the CLI."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main_with_loop(loop))
    except KeyboardInterrupt:
        print_formatted_text('⚠️ Session was interrupted\\n')
    except Exception as e:
        print(f'An error occurred: {e}')
        sys.exit(1)
    finally:
        try:
            # Cancel all running tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Wait for all tasks to complete
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
        except Exception as e:
            print(f'Error during cleanup: {e}')
            sys.exit(1)


if __name__ == '__main__':
    main()