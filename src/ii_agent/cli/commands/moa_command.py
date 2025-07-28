import logging
from typing import Optional, Dict, Any, List
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from ii_agent.cli.commands.base_command import BaseCommand
from ii_agent.controller.moa_controller import MoAAgentController
from ii_agent.core.config.moa_config import MoAConfig, create_default_moa_config
from ii_agent.core.config.llm_config import LLMConfig, APITypes

logger = logging.getLogger(__name__)


class MoACommand(BaseCommand):
    """Command to manage Mixture-of-Agents (MoA) functionality."""
    
    def __init__(self, console: Console):
        super().__init__(console)
    
    @property
    def name(self) -> str:
        return "moa"
    
    @property 
    def description(self) -> str:
        return "Manage Mixture-of-Agents (MoA) functionality"
    
    async def execute(self, args: str, app_context: Dict[str, Any]) -> Optional[str]:
        """Execute the MoA command.
        
        Args:
            args: Command arguments as a string
            app_context: Application context containing controller reference
            
        Returns:
            Optional response message or None to continue normal flow
        """
        # Parse arguments
        arg_parts = args.strip().split() if args.strip() else []
        
        if not arg_parts:
            return self._show_help()
        
        # Get controller from app context
        controller = app_context.get("controller")
        if not isinstance(controller, MoAAgentController):
            self.console.print("[red]Error: MoA commands require a MoA-enabled controller[/red]")
            return None
        
        subcommand = arg_parts[0].lower()
        
        if subcommand == "status":
            return self._show_status(controller)
        elif subcommand == "enable":
            return self._enable_moa(controller, arg_parts[1:])
        elif subcommand == "disable":
            return self._disable_moa(controller)
        elif subcommand == "config":
            return self._configure_moa(controller, arg_parts[1:])
        elif subcommand == "stats":
            return self._show_stats(controller)
        else:
            self.console.print(f"[red]Unknown MoA subcommand: {subcommand}[/red]")
            return self._show_help()
    
    def _show_help(self) -> None:
        """Show help for the MoA command."""
        help_text = """
[bold cyan]MoA (Mixture-of-Agents) Command[/bold cyan]

[bold]Usage:[/bold]
  moa status           - Show current MoA status and configuration
  moa enable           - Enable MoA with default configuration
  moa disable          - Disable MoA and use single model
  moa config           - Show detailed configuration
  moa stats            - Show performance statistics

[bold]Examples:[/bold]
  moa status           # Check if MoA is enabled
  moa enable           # Enable with Claude, OpenAI, and Gemini
  moa disable          # Switch back to single model
  moa stats            # View performance metrics

[bold]About MoA:[/bold]
Mixture-of-Agents leverages multiple LLMs (Claude, GPT-4, Gemini) working together
to generate higher-quality responses through collaborative synthesis.
"""
        self.console.print(Panel(help_text, title="MoA Help", border_style="cyan"))
        return None
    
    def _show_status(self, controller: MoAAgentController) -> None:
        """Show the current MoA status."""
        try:
            status = controller.get_moa_status()
            
            # Create status table
            table = Table(title="MoA Status", show_header=True, header_style="bold magenta")
            table.add_column("Property", style="cyan", no_wrap=True)
            table.add_column("Value", style="green")
            
            # Basic status
            table.add_row("MoA Enabled", "✅ Yes" if status.get("moa_enabled", False) else "❌ No")
            
            if status.get("moa_enabled", False):
                table.add_row("Type", status.get("type", "Unknown"))
                table.add_row("Layers", str(status.get("num_layers", "Unknown")))
                table.add_row("Parallel Execution", "✅ Yes" if status.get("parallel_execution", False) else "❌ No")
                table.add_row("Max Concurrent", str(status.get("max_concurrent_requests", "Unknown")))
                
                # Reference models
                ref_models = status.get("reference_models", [])
                if ref_models:
                    table.add_row("Reference Models", ", ".join(ref_models))
                
                # Aggregator model
                agg_model = status.get("aggregator_model")
                if agg_model:
                    table.add_row("Aggregator Model", agg_model)
            
            self.console.print(table)
            
            # Show performance stats if available
            perf_stats = status.get("performance_stats")
            if perf_stats:
                self._display_performance_stats(perf_stats)
            
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error getting MoA status: {str(e)}[/red]")
            return None
    
    def _enable_moa(self, controller: MoAAgentController, args: List[str]) -> None:
        """Enable MoA with optional configuration."""
        try:
            # For now, use default configuration
            # In the future, we could parse args for custom config
            result = controller.enable_moa()
            
            if result["success"]:
                self.console.print("[green]✅ MoA enabled successfully![/green]")
                
                # Show configuration summary
                moa_info = result.get("moa_info", {})
                ref_models = moa_info.get("reference_models", [])
                agg_model = moa_info.get("aggregator_model", "Unknown")
                
                summary = f"""
[bold cyan]MoA Configuration Summary:[/bold cyan]
• Reference Models: {', '.join(ref_models)}
• Aggregator Model: {agg_model}
• Parallel Execution: {'Enabled' if moa_info.get('parallel_execution') else 'Disabled'}

Your agent is now powered by multiple AI models working together! 🚀
"""
                self.console.print(Panel(summary, title="MoA Enabled", border_style="green"))
            else:
                self.console.print(f"[red]❌ Failed to enable MoA: {result.get('error', 'Unknown error')}[/red]")
            
            return result["success"]
            
        except Exception as e:
            self.console.print(f"[red]Error enabling MoA: {str(e)}[/red]")
            return None
    
    def _disable_moa(self, controller: MoAAgentController) -> None:
        """Disable MoA."""
        try:
            result = controller.disable_moa()
            
            if result["success"]:
                self.console.print("[yellow]MoA disabled. Using standard single-model behavior.[/yellow]")
            else:
                self.console.print(f"[red]❌ Failed to disable MoA: {result.get('error', 'Unknown error')}[/red]")
            
            return result["success"]
            
        except Exception as e:
            self.console.print(f"[red]Error disabling MoA: {str(e)}[/red]")
            return None
    
    def _configure_moa(self, controller: MoAAgentController, args: List[str]) -> None:
        """Show detailed MoA configuration."""
        try:
            status = controller.get_moa_status()
            
            if not status.get("moa_enabled", False):
                self.console.print("[yellow]MoA is not currently enabled. Use 'moa enable' to activate it.[/yellow]")
                return None
            
            # Create detailed configuration display
            config_text = f"""
[bold cyan]MoA Configuration Details[/bold cyan]

[bold]Architecture:[/bold]
• Type: {status.get('type', 'Unknown')}
• Layers: {status.get('num_layers', 'Unknown')}
• Parallel Execution: {status.get('parallel_execution', False)}
• Max Concurrent Requests: {status.get('max_concurrent_requests', 'Unknown')}

[bold]Models:[/bold]
• Reference Models: {', '.join(status.get('reference_models', []))}
• Aggregator Model: {status.get('aggregator_model', 'Unknown')}

[bold]Performance:[/bold]
"""
            
            # Add performance stats if available
            perf_stats = status.get("performance_stats")
            if perf_stats:
                config_text += f"""• Total Requests: {perf_stats.get('total_requests', 0)}
• Success Rate: {perf_stats.get('success_rate', 0):.2%}
• Average Time: {perf_stats.get('average_time_per_request', 0):.2f}s
"""
            else:
                config_text += "• No performance data available yet"
            
            self.console.print(Panel(config_text, title="MoA Configuration", border_style="cyan"))
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error showing MoA configuration: {str(e)}[/red]")
            return None
    
    def _show_stats(self, controller: MoAAgentController) -> None:
        """Show detailed performance statistics."""
        try:
            status = controller.get_moa_status()
            
            if not status.get("moa_enabled", False):
                self.console.print("[yellow]MoA is not currently enabled. No statistics available.[/yellow]")
                return None
            
            perf_stats = status.get("performance_stats")
            if not perf_stats:
                self.console.print("[yellow]No performance statistics available yet. Use MoA to generate some data![/yellow]")
                return None
            
            self._display_performance_stats(perf_stats)
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error showing MoA statistics: {str(e)}[/red]")
            return None
    
    def _display_performance_stats(self, stats: Dict[str, Any]):
        """Display performance statistics in a formatted table."""
        table = Table(title="MoA Performance Statistics", show_header=True, header_style="bold magenta")
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="green")
        
        # Format statistics
        total_requests = stats.get("total_requests", 0)
        failed_requests = stats.get("failed_requests", 0)
        success_rate = stats.get("success_rate", 0)
        total_time = stats.get("total_time", 0)
        avg_time = stats.get("average_time_per_request", 0)
        max_workers = stats.get("max_workers", 0)
        
        table.add_row("Total Requests", str(total_requests))
        table.add_row("Failed Requests", str(failed_requests))
        table.add_row("Success Rate", f"{success_rate:.2%}")
        table.add_row("Total Processing Time", f"{total_time:.2f}s")
        table.add_row("Average Time per Request", f"{avg_time:.2f}s")
        table.add_row("Max Concurrent Workers", str(max_workers))
        
        self.console.print(table)
    
    def get_completions(self, args: List[str]) -> List[str]:
        """Get command completions for tab completion."""
        if len(args) == 0:
            return ["status", "enable", "disable", "config", "stats"]
        elif len(args) == 1:
            subcommands = ["status", "enable", "disable", "config", "stats"]
            return [cmd for cmd in subcommands if cmd.startswith(args[0].lower())]
        else:
            return []