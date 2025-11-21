"""REPL styling with ANSI colors - symbolic prefixes instead of graphical noise."""

from enum import Enum
from typing import List

class Color:
    """ANSI color codes."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Foreground colors
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'

    # Background colors
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'

    # High contrast combinations - color on black or black on color
    HIGH_CONTRAST = {
        'warning': '\033[1;33;40m',      # Bold yellow on black
        'info': '\033[1;37;40m',          # Bold white on black
        'command': '\033[1;36;40m',       # Bold cyan on black
        'accent': '\033[1;35;40m',        # Bold magenta on black
        'reverse_warning': '\033[1;30;43m',  # Black on yellow
        'reverse_info': '\033[1;30;47m',      # Black on white
        'reverse_command': '\033[1;30;46m',   # Black on cyan
        'reverse_accent': '\033[1;30;45m',    # Black on magenta
    }

class Symbol:
    """Symbolic prefixes for different contexts."""
    PROMPT = "▶"
    SUCCESS = "+"
    ERROR = "!"
    WARNING = "~"
    INFO = "•"
    QUESTION = "?"

    # Provider symbols
    AVAILABLE = "●"
    UNAVAILABLE = "○"

    # Status symbols
    RUNNING = "▸"
    COMPLETE = "✓"
    FAILED = "✗"

class Section:
    """Section headers with high contrast colors."""
    CHAT = f"{Color.BOLD}◆ CHAT{Color.RESET}"
    FILES = f"{Color.BOLD}◆ FILES{Color.RESET}"
    SESSION = f"{Color.BOLD}◆ SESSION{Color.RESET}"
    PROVIDERS = f"{Color.BOLD}◆ PROVIDERS{Color.RESET}"
    EXAMPLES = f"{Color.BOLD}◆ EXAMPLES{Color.RESET}"
    OTHER = f"{Color.BOLD}◆ OTHER{Color.RESET}"

def format_prompt(text: str) -> str:
    """Format prompt with symbol and color."""
    return f"{Color.BLUE}{Symbol.PROMPT}{Color.RESET} {text}"

def format_success(text: str) -> str:
    """Format success message."""
    return f"{Color.GREEN}{Symbol.SUCCESS}{Color.RESET} {text}"

def format_error(text: str) -> str:
    """Format error message."""
    return f"{Color.RED}{Symbol.ERROR}{Color.RESET} {text}"

def format_warning(text: str) -> str:
    """Format warning message."""
    return f"{Color.WHITE}{Symbol.WARNING}{Color.RESET} {text}"

def format_info(text: str) -> str:
    """Format info message."""
    return f"{Color.WHITE}{Symbol.INFO}{Color.RESET} {text}"

def format_provider(name: str, available: bool) -> str:
    """Format provider with symbol."""
    if available:
        return f"{Color.GREEN}{Symbol.AVAILABLE}{Color.RESET} {name}"
    else:
        return f"{Color.DIM}{Symbol.UNAVAILABLE}{Color.RESET} {name}"

def format_section_header(title: str, color: str = Color.WHITE) -> str:
    """Format section header with color hint."""
    return f"{color}{Color.BOLD}◆ {title.upper()}{Color.RESET}"

def format_status(status: str, success: bool = True) -> str:
    """Format status with symbol."""
    if success:
        return f"{Color.GREEN}{Symbol.COMPLETE}{Color.RESET} {status}"
    else:
        return f"{Color.RED}{Symbol.FAILED}{Color.RESET} {status}"

def format_model_status(provider: str, model: str, available: bool) -> str:
    """Format model status with color coding."""
    if available:
        return f"{Color.GREEN}{provider}/{model}{Color.RESET}"
    else:
        return f"{Color.DIM}{provider}/{model}{Color.RESET}"

def format_env_var(var_name: str) -> str:
    """Format environment variable hint."""
    return f"{Color.WHITE}{var_name}{Color.RESET}"

def format_command(cmd: str) -> str:
    """Format command with subtle highlighting."""
    return f"{Color.WHITE}{cmd}{Color.RESET}"

def format_file(filepath: str) -> str:
    """Format file path."""
    return f"{Color.GREEN}{filepath}{Color.RESET}"

def format_workspace(workspace: str) -> str:
    """Format workspace path."""
    return f"{Color.BLUE}{workspace}{Color.RESET}"

def create_status_line(prefix: str, content: str, color: str = Color.WHITE) -> str:
    """Create a status line with prefix and content."""
    return f"{color}{prefix}:{Color.RESET} {content}"

def create_header_line(title: str, subtitle: str = "", color: str = Color.BLUE) -> str:
    """Create header line with title and optional subtitle."""
    if subtitle:
        return f"{color}{Color.BOLD}{title}{Color.RESET} {Color.DIM}({subtitle}){Color.RESET}"
    else:
        return f"{color}{Color.BOLD}{title}{Color.RESET}"

def strip_ansi(text: str) -> str:
    """Remove ANSI codes from text."""
    import re
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def is_color_enabled() -> bool:
    """Check if color output should be enabled."""
    import os
    return os.environ.get('NO_COLOR') is None and os.isatty(2)

# Compatibility wrapper for Rich console
class ANSIConsole:
    """Console wrapper that uses ANSI colors instead of Rich panels."""

    def __init__(self):
        self.color_enabled = is_color_enabled()

    def print(self, text: str, style: str = "", end: str = "\n"):
        """Print with optional styling."""
        if not self.color_enabled:
            # Strip ANSI codes if color disabled
            text = strip_ansi(text)
        print(text, end=end)

    def print_header(self, title: str, workspace: str, model: str):
        """Print REPL header with ANSI colors."""
        lines = [
            create_header_line("ii-agent Interactive REPL", "v0.1.0", Color.BLUE),
            "",
            create_status_line("Workspace", format_workspace(workspace), Color.BLUE),
            create_status_line("Model", format_model_status(model.split('/')[0], '/'.join(model.split('/')[1:]), True), Color.GREEN),
            "",
            format_info("Type /help for commands, /exit to quit"),
            ""
        ]
        self.print("\n".join(lines))

    def print_section(self, title: str, items: List[str], color: str = Color.WHITE):
        """Print a section with items."""
        self.print("")
        self.print(format_section_header(title, color))
        for item in items:
            self.print(f"  {item}")

    def print_success(self, text: str):
        """Print success message."""
        self.print(format_success(text))

    def print_error(self, text: str):
        """Print error message."""
        self.print(format_error(text))

    def print_warning(self, text: str):
        """Print warning message."""
        self.print(format_warning(text))

    def print_info(self, text: str):
        """Print info message."""
        self.print(format_info(text))

# Export the console instance
console = ANSIConsole() if is_color_enabled() else None
if console is None:
    # Fallback to basic print if colors disabled
    console = type('Console', (), {'print': print,
                                   'print_success': print,
                                   'print_error': print,
                                   'print_warning': print,
                                   'print_info': print})()

# Export symbols for easy import
__all__ = [
    'Color', 'Symbol', 'Section',
    'format_prompt', 'format_success', 'format_error', 'format_warning', 'format_info',
    'format_provider', 'format_section_header', 'format_status', 'format_model_status',
    'format_env_var', 'format_command', 'format_file', 'format_workspace',
    'create_status_line', 'create_header_line', 'strip_ansi', 'is_color_enabled',
    'ANSIConsole', 'console'
]

# Test the styles
if __name__ == "__main__":
    console.print_header("Test REPL", "/tmp/test", "nvidia/qwen/test")
    console.print_success("Storage initialized")
    console.print_error("File not found")
    console.print_warning("API key missing")
    console.print_info("Using hashtable storage")

    console.print_section("Providers", [
        format_provider("nvidia", True),
        format_provider("anthropic", False)
    ], Color.BLUE)

    console.print(format_prompt("Enter command"))
    console.print(format_command("/help"))
    console.print(format_file("test.txt"))
    console.print(format_env_var("NVIDIA_API_KEY"))