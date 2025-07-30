"""
Enhanced message rendering components.

This module provides components for rendering different types of messages
with better structure and formatting.
"""

from typing import Optional, Dict, Any
from enum import Enum
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.markdown import Markdown


class MessageType(Enum):
    """Message types for different rendering styles."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    ERROR = "error"
    THINKING = "thinking"


class MessageRenderer:
    """Enhanced message renderer with structured formatting."""
    
    def __init__(self, console: Console, minimal: bool = False):
        self.console = console
        self.minimal = minimal
        self.language_detector = LanguageDetector()
    
    def render_message(self, 
                      message_type: MessageType,
                      content: str,
                      metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render a message with appropriate formatting."""
        
        if message_type == MessageType.USER:
            self._render_user_message(content, metadata)
        elif message_type == MessageType.ASSISTANT:
            self._render_assistant_message(content, metadata)
        elif message_type == MessageType.TOOL_CALL:
            self._render_tool_call_message(content, metadata)
        elif message_type == MessageType.TOOL_RESULT:
            self._render_tool_result_message(content, metadata)
        elif message_type == MessageType.ERROR:
            self._render_error_message(content, metadata)
        elif message_type == MessageType.THINKING:
            self._render_thinking_message(content, metadata)
        else:
            self._render_system_message(content, metadata)
    
    def _render_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render user message."""
        if self.minimal:
            self.console.print(f"👤 [blue]{content}[/blue]")
        else:
            panel = Panel(
                content,
                title="👤 User",
                style="blue",
                border_style="blue"
            )
            self.console.print(panel)
    
    def _render_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render assistant message with enhanced formatting and markdown support."""
        if self.minimal:
            # For minimal mode, try to render markdown without panel
            try:
                markdown_content = Markdown(content, justify="left")
                self.console.print(f"🤖 [green]Assistant:[/green]")
                self.console.print(markdown_content)
            except Exception:
                # Fallback to plain text
                self.console.print(f"🤖 [green]{content}[/green]")
        else:
            # Always try to render as markdown first
            try:
                rendered_content = Markdown(content, justify="left")
            except Exception:
                # Fallback to plain text if markdown parsing fails
                rendered_content = content
            
            # Add metadata if available
            title = "🤖 Assistant"
            if metadata:
                cost = metadata.get("cost_usd")
                duration = metadata.get("duration_ms")
                if cost or duration:
                    title += " ("
                    if cost:
                        title += f"${cost:.4f}"
                    if duration:
                        title += f", {duration}ms" if cost else f"{duration}ms"
                    title += ")"
            
            panel = Panel(
                rendered_content,
                title=title,
                style="green",
                border_style="green"
            )
            self.console.print(panel)
    
    def _render_tool_call_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render tool call message."""
        if self.minimal:
            tool_name = metadata.get("tool_name", "unknown") if metadata else "unknown"
            self.console.print(f"🔧 [blue]Using tool:[/blue] [bold]{tool_name}[/bold]")
        else:
            self._render_tool_call_detailed(content, metadata)
    
    def _render_tool_call_detailed(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render detailed tool call information."""
        tool_name = metadata.get("tool_name", "unknown") if metadata else "unknown"
        tool_input = metadata.get("tool_input", {}) if metadata else {}
        
        table = Table(title=f"🔧 Tool Call: {tool_name}", style="blue")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="white")
        
        if tool_input:
            for key, value in tool_input.items():
                # Truncate long values
                if isinstance(value, str) and len(value) > 200:
                    value = value[:200] + "..."
                table.add_row(key, str(value))
        
        self.console.print(table)
    
    def _render_tool_result_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render tool result message."""
        tool_name = metadata.get("tool_name", "unknown") if metadata else "unknown"
        
        if self.minimal:
            self.console.print(f"✅ [green]Tool completed:[/green] [bold]{tool_name}[/bold]")
        else:
            self._render_tool_result_detailed(content, tool_name)
    
    def _render_tool_result_detailed(self, content: str, tool_name: str) -> None:
        """Render detailed tool result."""
        # Truncate long results
        if len(content) > 1000:
            content = content[:1000] + "\\n... (truncated)"
        
        # Enhanced code detection and syntax highlighting
        if self.language_detector.contains_code(content):
            language = self.language_detector.detect_language(content)
            try:
                syntax = Syntax(content, language, theme="monokai", line_numbers=True)
                panel = Panel(syntax, title=f"✅ Tool Result: {tool_name}", style="green")
            except Exception:
                panel = Panel(content, title=f"✅ Tool Result: {tool_name}", style="green")
        else:
            panel = Panel(content, title=f"✅ Tool Result: {tool_name}", style="green")
        
        self.console.print(panel)
    
    def _render_error_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render error message."""
        panel = Panel(
            f"❌ Error: {content}",
            title="Error",
            style="red",
            border_style="red"
        )
        self.console.print(panel)
    
    def _render_thinking_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render thinking message."""
        if not self.minimal:
            panel = Panel(
                content,
                title="🤔 Thinking",
                style="yellow",
                border_style="yellow"
            )
            self.console.print(panel)
    
    def _render_system_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Render system message."""
        if not self.minimal:
            panel = Panel(
                content,
                title="ℹ️ System",
                style="cyan",
                border_style="cyan"
            )
            self.console.print(panel)


class LanguageDetector:
    """Enhanced language detection for code highlighting."""
    
    def __init__(self):
        self.code_indicators = [
            "{", "[", "<", "def ", "class ", "import ", "function", "const ", "let ", "var ",
            "#!/", "<?php", "<html", "SELECT", "CREATE", "INSERT", "UPDATE", "DELETE",
            "public ", "private ", "protected ", "static ", "void ", "int ", "String ",
            "package ", "using ", "namespace ", "struct ", "enum ", "trait ", "impl "
        ]
    
    def contains_code(self, text: str) -> bool:
        """Check if text contains code."""
        return any(indicator in text for indicator in self.code_indicators)
    
    def detect_language(self, code: str) -> str:
        """Detect programming language from code content."""
        code_lower = code.lower()
        
        # Python
        if any(keyword in code for keyword in ["def ", "import ", "class ", "from ", "elif "]):
            return "python"
        
        # JavaScript/TypeScript
        if any(keyword in code for keyword in ["function", "const ", "let ", "var ", "=>", "console.log"]):
            return "javascript"
        
        # Java
        if any(keyword in code for keyword in ["public ", "private ", "protected ", "static ", "void ", "String "]):
            return "java"
        
        # C/C++
        if any(keyword in code for keyword in ["#include", "int main", "printf", "cout", "std::"]):
            return "cpp"
        
        # C#
        if any(keyword in code for keyword in ["using ", "namespace ", "Console.WriteLine"]):
            return "csharp"
        
        # Go
        if any(keyword in code for keyword in ["package ", "func ", "import ", "var ", "fmt.Print"]):
            return "go"
        
        # Rust
        if any(keyword in code for keyword in ["fn ", "let ", "mut ", "struct ", "enum ", "impl ", "trait "]):
            return "rust"
        
        # PHP
        if "<?php" in code:
            return "php"
        
        # HTML
        if any(tag in code_lower for tag in ["<html", "<div", "<span", "<head", "<body"]):
            return "html"
        
        # CSS
        if any(pattern in code for pattern in [":", "{", "}", "px", "em", "rem", "#", "."]):
            return "css"
        
        # SQL
        if any(keyword in code.upper() for keyword in ["SELECT", "CREATE", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE"]):
            return "sql"
        
        # JSON
        if code.strip().startswith(("{", "[")) and code.strip().endswith(("}", "]")):
            return "json"
        
        # XML
        if code.strip().startswith("<") and code.strip().endswith(">"):
            return "xml"
        
        # Shell/Bash
        if any(indicator in code for indicator in ["#!/bin/bash", "#!/bin/sh", "echo ", "grep ", "awk ", "sed "]):
            return "bash"
        
        # Default to text
        return "text"