"""
Custom markdown renderer for II Agent CLI.

This module provides a custom markdown renderer that ensures proper text alignment
and handles emoji headers correctly.
"""

from typing import Optional, Union, Iterator
from rich.console import Console, ConsoleOptions, RenderResult
from rich.text import Text
from rich.style import Style
from rich.rule import Rule
import re


class SimpleMarkdownRenderer:
    """Simple markdown renderer that ensures left alignment and proper formatting."""
    
    def __init__(self, content: str):
        self.content = content
        self.lines = content.split('\n')
    
    def render(self, console: Console) -> None:
        """Render the markdown content with left alignment."""
        in_code_block = False
        code_block_content = []
        code_block_lang = ""
        
        for i, line in enumerate(self.lines):
            # Handle code blocks
            if line.strip().startswith('```'):
                if not in_code_block:
                    # Start of code block
                    in_code_block = True
                    code_block_lang = line.strip()[3:].strip() or "text"
                    code_block_content = []
                else:
                    # End of code block
                    in_code_block = False
                    self._render_code_block(console, code_block_content, code_block_lang)
                    code_block_content = []
                continue
            
            if in_code_block:
                code_block_content.append(line)
                continue
            
            # Handle headers
            if line.strip().startswith('#'):
                self._render_header(console, line)
            # Handle horizontal rules
            elif line.strip() in ['---', '***', '___'] and len(line.strip()) >= 3:
                console.print(Rule(style="dim"))
            # Handle lists
            elif self._is_list_item(line):
                self._render_list_item(console, line)
            # Handle blockquotes
            elif line.strip().startswith('>'):
                self._render_blockquote(console, line)
            # Handle inline code and regular text
            else:
                self._render_paragraph(console, line)
    
    def _render_header(self, console: Console, line: str) -> None:
        """Render a header with proper formatting and LEFT alignment."""
        # Count the number of # symbols
        level = len(line) - len(line.lstrip('#'))
        text = line.lstrip('#').strip()
        
        # Style based on header level
        styles = {
            1: "bold bright_blue",
            2: "bold blue", 
            3: "bold cyan",
            4: "bold bright_cyan",
            5: "cyan",
            6: "bright_cyan"
        }
        
        style = styles.get(level, "bold")
        
        # Create text with explicit left justification
        header_text = Text(text, style=style, justify="left")
        
        # Add spacing
        if level <= 2:
            console.print()  # Extra space for h1 and h2
        
        console.print(header_text)
        
        if level <= 2:
            console.print()  # Extra space after h1 and h2
    
    def _render_paragraph(self, console: Console, line: str) -> None:
        """Render a paragraph with inline formatting."""
        if not line.strip():
            console.print()  # Empty line
            return
        
        # Process inline formatting
        text = self._process_inline_formatting(line)
        console.print(text)
    
    def _render_list_item(self, console: Console, line: str) -> None:
        """Render a list item."""
        # Detect list type and extract content
        match = re.match(r'^(\s*)([-*+]|\d+\.)\s+(.*)$', line)
        if match:
            indent, marker, content = match.groups()
            indent_level = len(indent) // 2  # Assuming 2 spaces per indent level
            
            # Create indentation
            prefix = "  " * indent_level
            
            # Style the marker
            if marker in ['-', '*', '+']:
                styled_marker = Text("•", style="cyan")
            else:
                styled_marker = Text(marker, style="cyan")
            
            # Process inline formatting in content
            formatted_content = self._process_inline_formatting(content)
            
            # Combine and print
            result = Text()
            result.append(prefix)
            result.append(styled_marker)
            result.append(" ")
            result.append(formatted_content)
            
            console.print(result)
    
    def _render_blockquote(self, console: Console, line: str) -> None:
        """Render a blockquote."""
        content = line.lstrip('>').strip()
        text = Text()
        text.append("│ ", style="dim cyan")
        text.append(self._process_inline_formatting(content))
        console.print(text)
    
    def _render_code_block(self, console: Console, lines: list, language: str) -> None:
        """Render a code block."""
        from rich.syntax import Syntax
        code = '\n'.join(lines)
        try:
            syntax = Syntax(code, language, theme="monokai", line_numbers=True)
            console.print(syntax)
        except Exception:
            # Fallback to plain text
            for line in lines:
                console.print(f"    {line}", style="dim green")
        console.print()  # Add space after code block
    
    def _process_inline_formatting(self, text: str) -> Text:
        """Process inline markdown formatting."""
        result = Text()
        
        # Simple regex patterns for inline formatting
        patterns = [
            (r'\*\*(.+?)\*\*', 'bold'),           # **bold**
            (r'\*(.+?)\*', 'italic'),             # *italic*
            (r'`(.+?)`', 'bold cyan on grey15'),  # `code`
            (r'\[(.+?)\]\((.+?)\)', 'link'),      # [text](url)
        ]
        
        # Process the text
        remaining = text
        position = 0
        
        while remaining:
            earliest_match = None
            earliest_pos = len(remaining)
            matched_pattern = None
            
            # Find the earliest match
            for pattern, style in patterns:
                match = re.search(pattern, remaining)
                if match and match.start() < earliest_pos:
                    earliest_match = match
                    earliest_pos = match.start()
                    matched_pattern = style
            
            if earliest_match:
                # Add text before match
                if earliest_pos > 0:
                    result.append(remaining[:earliest_pos])
                
                # Add formatted text
                if matched_pattern == 'link':
                    link_text = earliest_match.group(1)
                    link_url = earliest_match.group(2)
                    result.append(link_text, style="blue underline")
                else:
                    result.append(earliest_match.group(1), style=matched_pattern)
                
                # Update remaining text
                remaining = remaining[earliest_match.end():]
            else:
                # No more matches, add remaining text
                result.append(remaining)
                break
        
        return result
    
    def _is_list_item(self, line: str) -> bool:
        """Check if a line is a list item."""
        return bool(re.match(r'^\s*([-*+]|\d+\.)\s+', line))


def render_markdown(content: str, console: Optional[Console] = None, 
                   in_panel: bool = False) -> Union[str, 'SimpleMarkdownRenderer']:
    """
    Render markdown content with proper left alignment.
    
    Args:
        content: The markdown content to render
        console: Optional console to print to (if None, returns the content for panel)
        in_panel: Whether the content will be displayed inside a panel
        
    Returns:
        Empty string if console provided, otherwise the processed content
    """
    try:
        renderer = SimpleMarkdownRenderer(content)
        
        if console:
            # Direct rendering
            renderer.render(console)
            return ""
        else:
            # For panel rendering, we need to return a renderable that Rich can understand
            # Let's create a custom Text object with all the formatted content
            from io import StringIO
            from rich.console import Console as CaptureConsole
            from rich.capture import Capture
            
            # Capture the rendered output
            with Capture() as capture:
                capture_console = Console(file=StringIO(), force_jupyter=False)
                renderer.render(capture_console)
            
            # For now, let's just render directly and return the content
            # This is a simpler approach that should work in panels
            buffer_console = Console(file=StringIO(), force_terminal=True, width=80)
            renderer.render(buffer_console)
            
            # Return a simple wrapper that just renders the markdown
            class RenderableMarkdown:
                def __init__(self, renderer):
                    self.renderer = renderer
                
                def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
                    # Simply render using our custom renderer
                    self.renderer.render(console)
                    return
                    yield
            
            return RenderableMarkdown(renderer)
            
    except Exception as e:
        # Fallback to plain text if markdown parsing fails
        if console:
            console.print(content, style="white")
            return ""
        else:
            return content


def preprocess_markdown_content(content: str) -> str:
    """
    Preprocess markdown content to handle special cases.
    
    This function handles:
    - Lines that start with emojis and should be headers
    - Proper spacing around headers
    - List formatting
    
    Args:
        content: Raw markdown content
        
    Returns:
        Preprocessed markdown content
    """
    lines = content.split('\n')
    processed_lines = []
    
    for i, line in enumerate(lines):
        # Check if line starts with emoji followed by text (potential header)
        if line.strip() and _starts_with_emoji_header(line):
            # Add markdown header syntax if not already present
            if not line.strip().startswith('#'):
                # Make it a level 2 header
                processed_lines.append(f"## {line.strip()}")
            else:
                processed_lines.append(line)
        else:
            processed_lines.append(line)
    
    return '\n'.join(processed_lines)


def _starts_with_emoji_header(line: str) -> bool:
    """
    Check if a line starts with an emoji followed by header-like text.
    
    Args:
        line: The line to check
        
    Returns:
        True if line appears to be an emoji header
    """
    stripped = line.strip()
    if not stripped:
        return False
        
    # Check for common emoji header patterns
    emoji_headers = [
        '🚀', '🔮', '📊', '🎯', '💡', '⚡', '🔧', '📝', '✨',
        '🎨', '🛠️', '📦', '🔥', '⭐', '🌟', '💫', '🏆', '🎪'
    ]
    
    for emoji in emoji_headers:
        if stripped.startswith(emoji):
            # Check if it's followed by text that looks like a header
            rest = stripped[len(emoji):].strip()
            if rest and len(rest.split()) <= 5:  # Short phrases are likely headers
                return True
                
    return False