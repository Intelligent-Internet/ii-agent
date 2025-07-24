"""
Compact command implementation.

This module provides the /compact command that truncates the conversation
context to save memory while preserving important information.
"""

from typing import Optional, Any, Dict
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from .base_command import BaseCommand


class CompactCommand(BaseCommand):
    """Command to compact conversation context."""

    @property
    def name(self) -> str:
        return "compact"

    @property
    def description(self) -> str:
        return "Truncate context to save memory while preserving important information"

    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the compact command."""
        # Show information about what compacting does
        info_panel = Panel(
            "Context compacting will intelligently reduce the conversation history\n"
            "while preserving the most important information.\n\n"
            "This is useful when:\n"
            "• The conversation is getting very long\n"
            "• You're approaching token limits\n"
            "• Performance is slowing down due to large context\n\n"
            "💡 [bold]Tip:[/bold] This is safer than /clear as it preserves context.",
            title="Context Compacting",
            style="cyan",
        )
        self.console.print(info_panel)

        try:
            # Get confirmation using async prompt
            session = PromptSession()
            response = await session.prompt_async(
                HTML("<ansigreen>Continue with context compacting? (Y/n): </ansigreen>")
            )
            confirmed = response.strip().lower() in ["y", "yes", ""]

            if confirmed:
                # Show progress indicator
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=self.console,
                ) as progress:
                    task = progress.add_task("Compacting context...", total=None)

                    # Perform the compacting operation
                    app = context.get("app")
                    if (
                        app
                        and hasattr(app, "agent_controller")
                        and app.agent_controller
                    ):
                        try:
                            # Use the agent controller's compact method
                            result = app.agent_controller.compact_context()

                            if result.get("success"):
                                tokens_saved = result.get("tokens_saved", 0)
                                progress.update(
                                    task,
                                    description=f"Context compacted! Saved {tokens_saved} tokens",
                                )
                            else:
                                error_msg = result.get("error", "Unknown error")
                                progress.update(
                                    task,
                                    description=f"Error during compacting: {error_msg}",
                                )
                                self.console.print(
                                    f"[red]Error during context compacting: {error_msg}[/red]"
                                )
                                return None
                        except Exception as e:
                            progress.update(
                                task, description=f"Error during compacting: {e}"
                            )
                            self.console.print(
                                f"[red]Error during context compacting: {e}[/red]"
                            )
                            return None
                    else:
                        progress.update(
                            task, description="Agent controller not available"
                        )
                        self.console.print(
                            "[yellow]Agent controller not available for compacting[/yellow]"
                        )
                        return None

                # Show success message
                success_panel = Panel(
                    "✅ [bold green]Context compacted successfully![/bold green]\n\n"
                    "• Conversation history has been intelligently reduced\n"
                    "• Important context has been preserved\n"
                    "• Token usage has been optimized\n"
                    "• Performance should be improved\n\n"
                    "You can continue your conversation normally.",
                    title="Context Compacted",
                    style="green",
                )
                self.console.print(success_panel)

                return "COMPACT_COMMAND"
            else:
                self.console.print(
                    "[green]Compacting cancelled. Context preserved.[/green]"
                )
                return None

        except (EOFError, KeyboardInterrupt):
            # User pressed Ctrl+C during confirmation
            self.console.print(
                "[green]Compacting cancelled. Context preserved.[/green]"
            )
            return None

    def get_help_text(self) -> str:
        """Get detailed help text for the compact command."""
        return (
            "The /compact command intelligently reduces conversation context to save memory.\n\n"
            "Usage:\n"
            "  /compact    - Compact context with confirmation\n"
            "What happens during compacting:\n"
            "• Recent messages are kept in full detail\n"
            "• Older messages are summarized or compressed\n"
            "• Important context and decisions are preserved\n"
            "• Token usage is significantly reduced\n"
            "• Performance is improved\n\n"
            "When to use /compact:\n"
            "• When the conversation is getting very long\n"
            "• When you're approaching token limits\n"
            "• When performance is slowing down\n"
            "• When you want to optimize without losing context\n\n"
            "Advantages over /clear:\n"
            "• Preserves important conversation context\n"
            "• Maintains continuity in your work\n"
            "• Keeps recent messages intact\n"
            "• Safer option for long conversations\n\n"
            "💡 Tip: Use /compact regularly during long sessions to maintain optimal performance."
        )
