"""Todo Panel Component for beautiful todo visualization."""

from typing import List, Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, MofNCompleteColumn
from rich.text import Text
from rich.box import ROUNDED
from rich import box

class TodoPanel:
    """Beautiful todo panel visualization component."""
    
    STATUS_ICONS = {
        "pending": "⏳",
        "in_progress": "🔄", 
        "completed": "✅"
    }
    
    PRIORITY_COLORS = {
        "high": "bold red",
        "medium": "bold yellow", 
        "low": "bold green"
    }
    
    def __init__(self, console: Optional[Console] = None):
        """Initialize the TodoPanel component.
        
        Args:
            console: Rich console instance
        """
        self.console = console or Console()
    
    def render(self, todos: List[Dict[str, Any]], title: str = "📋 Todo List") -> None:
        """Render the todo list as a beautiful panel.
        
        Args:
            todos: List of todo items
            title: Panel title
        """
        if not todos:
            self._render_empty_state(title)
            return
            
        # Calculate statistics
        total = len(todos)
        completed = sum(1 for todo in todos if todo.get("status") == "completed")
        in_progress = sum(1 for todo in todos if todo.get("status") == "in_progress")
        pending = sum(1 for todo in todos if todo.get("status") == "pending")
        completion_percentage = (completed / total * 100) if total > 0 else 0
        
        # Create table
        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=box.SIMPLE_HEAD,
            padding=(0, 1),
            expand=True
        )
        
        # Add columns
        table.add_column("", width=3, justify="center")  # Status icon
        table.add_column("Task", style="white", ratio=3)
        table.add_column("Priority", justify="center", width=10)
        table.add_column("ID", style="dim", width=8)
        
        # Sort todos by status and priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        status_order = {"in_progress": 0, "pending": 1, "completed": 2}
        
        sorted_todos = sorted(
            todos,
            key=lambda x: (
                status_order.get(x.get("status", "pending"), 3),
                priority_order.get(x.get("priority", "medium"), 3)
            )
        )
        
        # Add rows
        for todo in sorted_todos:
            status = todo.get("status", "pending")
            priority = todo.get("priority", "medium")
            
            status_icon = self.STATUS_ICONS.get(status, "❓")
            priority_text = Text(priority.upper(), style=self.PRIORITY_COLORS.get(priority, "white"))
            
            # Apply styling based on status
            content_style = ""
            if status == "completed":
                content_style = "dim strike"
            elif status == "in_progress":
                content_style = "bold cyan"
                
            table.add_row(
                status_icon,
                Text(todo.get("content", ""), style=content_style),
                priority_text,
                f"#{todo.get('id', 'N/A')}"
            )
        
        # Create header with statistics
        header = self._create_header(total, completed, in_progress, pending, completion_percentage)
        
        # Create progress bar
        progress_bar = self._create_progress_bar(completion_percentage)
        
        # Combine everything in a panel
        panel_content = Text()
        panel_content.append(header)
        panel_content.append("\n\n")
        panel_content.append(progress_bar)
        panel_content.append("\n\n")
        
        self.console.print(panel_content)
        self.console.print(table)
        
    def _render_empty_state(self, title: str) -> None:
        """Render empty state when no todos exist."""
        empty_panel = Panel(
            Text("No tasks in the todo list", style="dim italic", justify="center"),
            title=title,
            box=ROUNDED,
            padding=(1, 2),
            style="dim"
        )
        self.console.print(empty_panel)
    
    def _create_header(self, total: int, completed: int, in_progress: int, 
                      pending: int, completion_percentage: float) -> Text:
        """Create header with statistics."""
        header = Text()
        
        # Title
        header.append("📊 Overview\n", style="bold blue")
        header.append(f"Total Tasks: {total} | ", style="white")
        header.append(f"✅ Completed: {completed} | ", style="green")
        header.append(f"🔄 In Progress: {in_progress} | ", style="cyan")
        header.append(f"⏳ Pending: {pending}", style="yellow")
        
        return header
    
    def _create_progress_bar(self, percentage: float) -> str:
        """Create a visual progress bar."""
        filled = int(percentage / 100 * 30)
        empty = 30 - filled
        
        bar = Text()
        bar.append("Progress: [", style="white")
        bar.append("█" * filled, style="green")
        bar.append("░" * empty, style="dim white")
        bar.append(f"] {percentage:.1f}%", style="white")
        
        return bar
    
    def render_compact(self, todos: List[Dict[str, Any]]) -> None:
        """Render a compact version of the todo list."""
        if not todos:
            self.console.print("[dim]No tasks[/dim]")
            return
            
        # Group by status
        by_status = {"completed": [], "in_progress": [], "pending": []}
        for todo in todos:
            status = todo.get("status", "pending")
            by_status[status].append(todo)
        
        # Create compact display
        summary = Text()
        summary.append(f"✅ {len(by_status['completed'])} ", style="green")
        summary.append(f"🔄 {len(by_status['in_progress'])} ", style="cyan")
        summary.append(f"⏳ {len(by_status['pending'])}", style="yellow")
        
        self.console.print(Panel(summary, title="📋 Tasks", box=ROUNDED, padding=(0, 1)))