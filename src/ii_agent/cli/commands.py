"""CLI commands handler for ii-agent."""

import uuid
from typing import Tuple

from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import HTML

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.core.storage.settings.file_settings_store import FileSettingsStore
from ii_agent.db.manager import Sessions

from .tui import UsageMetrics
from .settings import modify_llm_settings_basic


async def handle_commands(
    message: str,
    usage_metrics: UsageMetrics,
    session_id: uuid.UUID,
    config: IIAgentConfig,
    settings_store: FileSettingsStore,
) -> Tuple[bool, bool]:
    """Handle CLI commands.
    
    Args:
        message: The user message to process
        usage_metrics: Usage metrics tracker
        session_id: Current session ID
        config: II Agent configuration
        settings_store: Settings store
        
    Returns:
        Tuple of (close_repl, new_session_requested)
    """
    if not message.startswith('/'):
        return False, False
    
    command = message[1:].strip().lower()
    
    if command == 'help':
        await handle_help()
        return False, False
    
    elif command == 'exit' or command == 'quit':
        return await handle_exit()
    
    elif command == 'new':
        return await handle_new_session()
    
    elif command == 'status':
        await handle_status(usage_metrics, session_id)
        return False, False
    
    elif command == 'settings':
        await handle_settings(config, settings_store)
        return False, False
    
    elif command == 'sessions':
        await handle_sessions()
        return False, False
    
    elif command.startswith('resume'):
        return await handle_resume(command)
    
    elif command == 'clear':
        await handle_clear()
        return False, False
    
    else:
        print_formatted_text(HTML(f'<red>Unknown command: {command}</red>'))
        print_formatted_text(HTML('<grey>Type /help for available commands</grey>'))
        return False, False


async def handle_help():
    """Display help information."""
    help_text = """
<b>Available Commands:</b>

<cyan>/help</cyan>     - Show this help message
<cyan>/exit</cyan>     - Exit the CLI
<cyan>/new</cyan>      - Start a new session
<cyan>/status</cyan>   - Show current session status
<cyan>/settings</cyan> - Configure LLM and agent settings
<cyan>/sessions</cyan> - List all sessions
<cyan>/resume</cyan>   - Resume a previous session
<cyan>/clear</cyan>    - Clear the terminal screen

<b>Usage:</b>
- Type your task or question directly (without /)
- Use commands starting with / for CLI functions
- Press Ctrl+C to interrupt agent execution
- Use multiline input for complex instructions
"""
    print_formatted_text(HTML(help_text))


async def handle_exit() -> Tuple[bool, bool]:
    """Handle exit command."""
    print_formatted_text(HTML('<yellow>Exiting CLI...</yellow>'))
    return True, False


async def handle_new_session() -> Tuple[bool, bool]:
    """Handle new session command."""
    print_formatted_text(HTML('<green>Starting new session...</green>'))
    return True, True


async def handle_status(usage_metrics: UsageMetrics, session_id: uuid.UUID):
    """Handle status command."""
    status_text = f"""
<b>Session Status:</b>

<cyan>Session ID:</cyan> {session_id}
<cyan>Input tokens:</cyan> {usage_metrics.input_tokens:,}
<cyan>Output tokens:</cyan> {usage_metrics.output_tokens:,}
<cyan>Total tokens:</cyan> {usage_metrics.total_tokens:,}
<cyan>Total cost:</cyan> ${usage_metrics.total_cost:.4f}
"""
    print_formatted_text(HTML(status_text))


async def handle_settings(config: IIAgentConfig, settings_store: FileSettingsStore):
    """Handle settings command."""
    print_formatted_text(HTML('<yellow>Opening settings configuration...</yellow>'))
    await modify_llm_settings_basic(config, settings_store)


async def handle_sessions():
    """Handle sessions command."""
    try:
        # For now, we'll use device_id=None to get all sessions
        # This could be enhanced to use a proper device identification
        sessions = Sessions.get_sessions_by_device_id("")
        if not sessions:
            print_formatted_text(HTML('<yellow>No sessions found</yellow>'))
            return
        
        print_formatted_text(HTML('<b>Available Sessions:</b>'))
        for session in sessions:
            session_name = session.get('name', 'Unnamed Session')
            print_formatted_text(HTML(
                f'<green>• {session_name}</green> '
                f'(ID: {session["id"]}) '
                f'- Created: {session["created_at"]}'
            ))
    except Exception as e:
        print_formatted_text(HTML(f'<red>Error listing sessions: {e}</red>'))


async def handle_resume(command: str) -> Tuple[bool, bool]:
    """Handle resume command."""
    parts = command.split()
    if len(parts) < 2:
        print_formatted_text(HTML('<red>Usage: /resume <session_id></red>'))
        return False, False
    
    session_id = parts[1]
    try:
        session = Sessions.get_session_by_id(uuid.UUID(session_id))
        if not session:
            print_formatted_text(HTML(f'<red>Session not found: {session_id}</red>'))
            return False, False
        
        session_name = session.name or 'Unnamed Session'
        print_formatted_text(HTML(f'<green>Resuming session: {session_name}</green>'))
        # TODO: Implement session resumption
        return True, False
    except ValueError:
        print_formatted_text(HTML(f'<red>Invalid session ID: {session_id}</red>'))
        return False, False
    except Exception as e:
        print_formatted_text(HTML(f'<red>Error resuming session: {e}</red>'))
        return False, False


async def handle_clear():
    """Handle clear command."""
    from prompt_toolkit.shortcuts import clear
    clear()
    print_formatted_text(HTML('<green>Terminal cleared</green>'))


def check_folder_security_agreement(config: IIAgentConfig, folder_path: str) -> bool:
    """Check if user agrees to work in the specified folder."""
    print_formatted_text(HTML(
        f'<yellow>II-Agent will work in folder: {folder_path}</yellow>\n'
        f'<yellow>This may involve reading, writing, and executing files.</yellow>\n'
        f'<yellow>Do you agree to proceed? (y/n): </yellow>'
    ), end='')
    
    try:
        response = input().strip().lower()
        return response in ['y', 'yes']
    except KeyboardInterrupt:
        print_formatted_text('\n<red>Operation cancelled by user</red>')
        return False
    except Exception:
        return False