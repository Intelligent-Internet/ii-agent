"""Terminal UI components for ii-agent CLI."""

import asyncio
import threading
import time
import sys
from typing import Optional, Generator
from dataclasses import dataclass

from prompt_toolkit import print_formatted_text, PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.shortcuts import prompt
from prompt_toolkit.application import get_app
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.keys import Keys
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.styles import Style

from ii_agent.core.config.ii_agent_config import IIAgentConfig
from ii_agent.events.event import Event
from ii_agent.events.action import Action
from ii_agent.events.observation import Observation
from ii_agent.controller.state import AgentState


# Color and styling constants
COLOR_GOLD = '#FFD700'
COLOR_GREY = '#808080'
DEFAULT_STYLE = Style.from_dict(
    {
        'gold': COLOR_GOLD,
        'grey': COLOR_GREY,
        'prompt': f'{COLOR_GOLD} bold',
    }
)

COMMANDS = {
    '/exit': 'Exit the application',
    '/help': 'Display available commands',
    '/new': 'Create a new conversation',
    '/status': 'Display conversation details and usage metrics',
    '/settings': 'Display and modify current settings',
    '/sessions': 'List all sessions',
    '/resume': 'Resume a previous session',
    '/clear': 'Clear the terminal screen',
}

@dataclass
class UsageMetrics:
    """Track usage metrics for the CLI session."""
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0
    session_init_time: float = 0.0
    
    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def display_banner(session_id: str):
    """Display the II-Agent banner."""
    banner = f"""
<b><cyan>
 _____   _____        _                    _   
|_   _| |_   _|      / \\   __ _  ___ _ __ | |_ 
  | |     | |       / _ \\ / _` |/ _ \\ '_ \\| __|
  | |     | |      / ___ \\ (_| |  __/ | | | |_ 
 _| |_   _| |_    /_/   \\_\\__, |\\___|_| |_|\\__|
|_____|_|_____|           |___/                
</cyan></b>

<grey>Intelligent Agent Platform</grey>
<grey>Session ID: {session_id}</grey>
<grey>Type /help for available commands</grey>
"""
    print_formatted_text(HTML(banner))


def display_welcome_message(message: str = '') -> None:
    print_formatted_text(
        HTML("<gold>Let's start building!</gold>\n"), style=DEFAULT_STYLE
    )
    if message:
        print_formatted_text(
            HTML(f'{message} <grey>Type /help for help</grey>'),
            style=DEFAULT_STYLE,
        )
    else:
        print_formatted_text(
            HTML('What do you want to build? <grey>Type /help for help</grey>'),
            style=DEFAULT_STYLE,
        )


def display_initialization_animation(text: str, is_loaded: asyncio.Event) -> None:
    ANIMATION_FRAMES = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']

    i = 0
    while not is_loaded.is_set():
        sys.stdout.write('\n')
        sys.stdout.write(
            f'\033[s\033[J\033[38;2;255;215;0m[{ANIMATION_FRAMES[i % len(ANIMATION_FRAMES)]}] {text}\033[0m\033[u\033[1A'
        )
        sys.stdout.flush()
        time.sleep(0.1)
        i += 1

    sys.stdout.write('\r' + ' ' * (len(text) + 10) + '\r')
    sys.stdout.flush()



def display_agent_running_message():
    """Display message when agent is running."""
    print_formatted_text(HTML('<yellow>🤖 Agent is thinking...</yellow>'))

def display_input_processing_message():
    """Display message when processing input."""
    print_formatted_text(HTML('<cyan>⚙️ Processing your input...</cyan>'))

def display_agent_response_message():
    """Display message when agent is generating response."""
    print_formatted_text(HTML('<yellow>💭 Agent is generating response...</yellow>'))

def display_tool_calling_message(tool_name: str):
    """Display message when agent is calling a tool."""
    print_formatted_text(HTML(f'<magenta>🔧 Agent is using tool: {tool_name}</magenta>'))


def display_event(event: Event, config: IIAgentConfig):
    """Display an event in the terminal."""
    
    if isinstance(event, Action):
        if hasattr(event, 'content') and event.content:
            print_formatted_text(HTML(f'<blue>🤖 {event.content}</blue>'))
        elif hasattr(event, 'name'):
            print_formatted_text(HTML(f'<blue>🔧 Using tool: {event.name}</blue>'))
    
    elif isinstance(event, Observation):
        if hasattr(event, 'content') and event.content:
            # Limit output length for readability
            content = event.content
            if len(content) > 1000:
                content = content[:1000] + '... (truncated)'
            print_formatted_text(HTML(f'<green>📋 {content}</green>'))


def display_initial_user_prompt(message: str):
    """Display the initial user prompt."""
    print_formatted_text(HTML(f'<b><cyan>User:</cyan></b> {message}\n'))


class CommandCompleter(Completer):
    """Custom completer for commands."""

    def __init__(self, agent_state: str) -> None:
        super().__init__()
        self.agent_state = agent_state

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Generator[Completion, None, None]:
        text = document.text_before_cursor.lstrip()
        if text.startswith('/'):
            available_commands = dict(COMMANDS)
            # Note: Our AgentState doesn't have PAUSED, so we'll keep all commands
            # available_commands.pop('/resume', None)

            for command, description in available_commands.items():
                if command.startswith(text):
                    yield Completion(
                        command,
                        start_position=-len(text),
                        display_meta=description,
                        style='bg:ansidarkgray fg:gold',
                    )


def create_prompt_session(config: IIAgentConfig) -> PromptSession[str]:
    """Creates a prompt session with VI mode enabled if specified in the config."""
    # Note: vi_mode would need to be added to IIAgentConfig if needed
    return PromptSession(style=DEFAULT_STYLE)


async def read_prompt_input(
    config: IIAgentConfig,
    agent_state: str,
    multiline: bool = False
) -> str:
    """Read user input from the prompt."""
    
    try:
        prompt_session = create_prompt_session(config)
        prompt_session.completer = (
            CommandCompleter(agent_state) if not multiline else None
        )
        

        if multiline:
            kb = KeyBindings()

            @kb.add('c-d')
            def _(event: KeyPressEvent) -> None:
                event.current_buffer.validate_and_handle()

            with patch_stdout():
                print_formatted_text('')
                message = await prompt_session.prompt_async(
                    HTML(
                        '<gold>Enter your message and press Ctrl-D to finish:</gold>\n'
                    ),
                    multiline=True,
                    key_bindings=kb,
                )
        else:
            with patch_stdout():
                print_formatted_text('')
                message = await prompt_session.prompt_async(
                    HTML('<gold>> </gold>'),
                )
        
        return message if message is not None else ''
    except (KeyboardInterrupt, EOFError) as e:
        return '/exit'


async def prompt_multiline(prompt_text: str) -> str:
    """Prompt for multiline input."""
    # This function is now integrated into read_prompt_input
    # Keeping for backward compatibility
    return await read_prompt_input(
        IIAgentConfig(), '', multiline=True
    )


async def read_confirmation_input(config: IIAgentConfig) -> str:
    """Read confirmation input from user."""
    try:
        prompt_session = create_prompt_session(config)

        while True:
            with patch_stdout():
                print_formatted_text('')
                confirmation: str = await prompt_session.prompt_async(
                    HTML('<gold>Proceed with action? (y)es/(n)o/(a)lways > </gold>'),
                )

                confirmation = (
                    '' if confirmation is None else confirmation.strip().lower()
                )

                if confirmation in ['y', 'yes']:
                    return 'yes'
                elif confirmation in ['n', 'no']:
                    return 'no'
                elif confirmation in ['a', 'always']:
                    return 'always'
                else:
                    # Display error message for invalid input
                    print_formatted_text('')
                    print_formatted_text(
                        HTML(
                            '<ansired>Invalid input. Please enter (y)es, (n)o, or (a)lways.</ansired>'
                        )
                    )
                    # Continue the loop to re-prompt
    except (KeyboardInterrupt, EOFError):
        return 'no'


def start_pause_listener(loop: asyncio.AbstractEventLoop, is_paused: asyncio.Event, event_stream):
    """Start listening for pause commands."""
    def pause_listener():
        try:
            input()  # Wait for Enter key
            is_paused.set()
            print_formatted_text(HTML('<yellow>⏸️ Agent paused. Press Enter to resume.</yellow>'))
        except:
            pass
    
    thread = threading.Thread(target=pause_listener, daemon=True)
    thread.start()


async def stop_pause_listener():
    """Stop the pause listener."""
    # In a real implementation, this would clean up the pause listener
    pass


def update_streaming_output(output: str):
    """Update streaming output in the terminal."""
    if output.strip():
        print_formatted_text(HTML(f'<grey>{output}</grey>'), end='')


def display_runtime_initialization_message(runtime_type: str):
    """Display runtime initialization message."""
    print_formatted_text(HTML(f'<yellow>Initializing {runtime_type} runtime...</yellow>'))


def display_session_restored_message(session_name: str):
    """Display session restored message."""
    print_formatted_text(HTML(f'<green>✅ Session restored: {session_name}</green>'))


def display_error_message(message: str):
    """Display error message."""
    print_formatted_text(HTML(f'<red>❌ Error: {message}</red>'))


def display_success_message(message: str):
    """Display success message."""
    print_formatted_text(HTML(f'<green>✅ {message}</green>'))


def display_warning_message(message: str):
    """Display warning message."""
    print_formatted_text(HTML(f'<yellow>⚠️ {message}</yellow>'))


def display_info_message(message: str):
    """Display info message."""
    print_formatted_text(HTML(f'<cyan>ℹ️ {message}</cyan>'))


def display_session_summary(session_id: str, metrics: UsageMetrics):
    """Display session summary."""
    summary = f"""
<b>Session Summary:</b>

<cyan>Session ID:</cyan> {session_id}
<cyan>Total tokens:</cyan> {metrics.total_tokens:,}
<cyan>Input tokens:</cyan> {metrics.input_tokens:,}
<cyan>Output tokens:</cyan> {metrics.output_tokens:,}
<cyan>Total cost:</cyan> ${metrics.total_cost:.4f}
"""
    print_formatted_text(HTML(summary))


def display_tool_execution_start(tool_name: str):
    """Display tool execution start message."""
    print_formatted_text(HTML(f'<yellow>🔧 Executing {tool_name}...</yellow>'))


def display_tool_execution_end(tool_name: str, success: bool):
    """Display tool execution end message."""
    if success:
        print_formatted_text(HTML(f'<green>✅ {tool_name} completed successfully</green>'))
    else:
        print_formatted_text(HTML(f'<red>❌ {tool_name} failed</red>'))


def display_thinking_indicator():
    """Display thinking indicator."""
    print_formatted_text(HTML('<yellow>🤔 Thinking...</yellow>'))


def display_typing_indicator():
    """Display typing indicator."""
    print_formatted_text(HTML('<blue>⌨️ Typing response...</blue>'))


def get_console_width() -> int:
    """Get console width for formatting."""
    try:
        import os
        return os.get_terminal_size().columns
    except:
        return 80  # Default width


def format_output_for_console(text: str, max_width: Optional[int] = None) -> str:
    """Format output text for console display."""
    if max_width is None:
        max_width = get_console_width() - 4  # Leave some margin
    
    lines = text.split('\n')
    formatted_lines = []
    
    for line in lines:
        if len(line) <= max_width:
            formatted_lines.append(line)
        else:
            # Wrap long lines
            words = line.split(' ')
            current_line = ''
            for word in words:
                if len(current_line + word) <= max_width:
                    current_line += word + ' '
                else:
                    if current_line:
                        formatted_lines.append(current_line.rstrip())
                    current_line = word + ' '
            if current_line:
                formatted_lines.append(current_line.rstrip())
    
    return '\n'.join(formatted_lines)