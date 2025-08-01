"""
Plan command implementation.

This module provides the /plan command that analyzes feature requests and 
generates detailed implementation plans in markdown format.
"""

from typing import Optional, Any, Dict
from pathlib import Path
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from .base_command import BaseCommand
from ..plan_state import PlanStateManager
from ...prompts.plan_mode_prompt import get_plan_mode_system_prompt


class PlanCommand(BaseCommand):
    """Command to generate implementation plans for features."""

    @property
    def name(self) -> str:
        return "plan"

    @property
    def description(self) -> str:
        return "Generate detailed implementation plan for a feature or task (read-only analysis mode)"

    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the plan command."""
        # Handle special flags
        if args.strip() in ["--list", "-l"]:
            return await self._list_plans(context)
        
        if args.strip() in ["--help", "-h"]:
            self.console.print(self.get_help_text())
            return None
            
        if not args.strip():
            self.console.print("[red]Error: Please provide a feature description[/red]")
            self.console.print("Usage: /plan <feature_description>")
            self.console.print("Example: /plan Add user authentication with JWT tokens") 
            self.console.print("Use [cyan]/plan --list[/cyan] to see existing plans")
            return None

        # Get workspace and create plan state manager
        app = context.get("app")
        if not app:
            self.console.print("[red]Error: App context not available[/red]")
            return None

        workspace_path = app.workspace_path
        plan_manager = PlanStateManager(workspace_path)



        # Activate plan mode
        plan_manager.activate_plan_mode()

        # Generate plan without conflicting progress indicators
        try:
            # Get agent controller for analysis
            agent_controller = context.get("agent_controller")
            if not agent_controller:
                self.console.print("[red]Error: Agent controller not available[/red]")
                plan_manager.deactivate_plan_mode()
                return None

            # Show progress message without Rich Progress to avoid conflicts
            self.console.print("🔍 [cyan]Analyzing codebase and generating plan...[/cyan]")
            
            # Generate the plan using the agent
            await self._generate_comprehensive_plan(
                agent_controller, args, workspace_path
            )
            
            # Since the agent creates the plan file directly, we just need to verify it was created
            # The agent will have created the plan in the plans/ directory
            self.console.print("✅ [green]Plan generation process completed![/green]")
            self.console.print("\n[cyan]The agent has created your implementation plan.[/cyan]")
            self.console.print("[cyan]Check the plans/ directory for the generated plan file.[/cyan]")
            self.console.print("\n💡 [yellow]Tip:[/yellow] Use [cyan]/plan --list[/cyan] to see all available plans")
            self.console.print("💡 [yellow]Tip:[/yellow] Use [cyan]/implement <plan_id>[/cyan] to execute a plan")

        except Exception as e:
            self.console.print(f"[red]Error during plan generation: {e}[/red]")
            plan_manager.deactivate_plan_mode()
            return None

        # Deactivate plan mode after generation
        plan_manager.deactivate_plan_mode()

        return "PLAN_GENERATED"

    async def _list_plans(self, context: Dict[str, Any]) -> Optional[str]:
        """List all available implementation plans."""
        app = context.get("app")
        if not app:
            self.console.print("[red]Error: App context not available[/red]")
            return None

        workspace_path = app.workspace_path
        plan_manager = PlanStateManager(workspace_path)
        
        plans = plan_manager.list_plans()
        
        if not plans:
            self.console.print("[yellow]No implementation plans found.[/yellow]")
            self.console.print("Use [cyan]/plan <feature_description>[/cyan] to create a new plan.")
            return None

        # Create table for plans
        from rich.table import Table
        table = Table(title="Available Implementation Plans")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Status", style="green")
        table.add_column("Created", style="dim")
        table.add_column("Description", style="dim", max_width=50)

        for plan in plans:
            # Truncate description for display
            desc = plan.description[:47] + "..." if len(plan.description) > 50 else plan.description
            
            # Color status
            status_color = {
                "planning": "yellow",
                "ready": "green", 
                "in_progress": "blue",
                "completed": "green",
                "cancelled": "red",
                "error": "red"
            }.get(plan.status, "white")
            
            table.add_row(
                plan.plan_id,
                plan.name,
                f"[{status_color}]{plan.status}[/{status_color}]",
                plan.created_at.split('T')[0],  # Just the date
                desc
            )

        self.console.print(table)
        self.console.print(f"\nUse [cyan]/implement <plan_id>[/cyan] to execute a plan")
        
        return "PLANS_LISTED"

    async def _generate_comprehensive_plan(
        self, 
        agent_controller, 
        feature_description: str, 
        workspace_path: str
    ) -> None:
        """Generate comprehensive implementation plan using proper system prompt."""
        try:
            # Get the plan mode system prompt
            system_prompt = get_plan_mode_system_prompt(workspace_path, feature_description)
            
            # Create a temporary agent configuration for plan mode
            from ii_agent.core.config.agent_config import AgentConfig
            
            # Get max tokens from agent config or app config
            max_tokens = 8192  # Default fallback
            if hasattr(agent_controller, 'agent') and agent_controller.agent and hasattr(agent_controller.agent, 'config'):
                max_tokens = getattr(agent_controller.agent.config, 'max_tokens_per_turn', 8192)
            
            # Create plan mode agent config with the special system prompt
            plan_agent_config = AgentConfig(
                max_tokens_per_turn=max_tokens,
                system_prompt=system_prompt,
            )
            
            # Store original config
            original_config = agent_controller.agent.config if hasattr(agent_controller, 'agent') and agent_controller.agent else None
            
            # Temporarily update agent config for plan mode
            if hasattr(agent_controller, 'agent') and agent_controller.agent:
                agent_controller.agent.config = plan_agent_config
            
            # Create plan generation instruction
            plan_instruction = f"""Begin plan generation for: {feature_description}

Execute the complete plan mode workflow:
1. Investigate the codebase thoroughly using read-only tools
2. Analyze findings and document insights  
3. Create a comprehensive implementation plan
4. Save the plan as a markdown file in the plans/ directory

Focus on creating a detailed, actionable plan that another developer could follow step-by-step."""

            # Run the agent with plan mode system prompt
            await agent_controller.run_agent_async(
                instruction=plan_instruction,
                files=None,
                resume=False  # Fresh context for plan generation
            )
            
            # Restore original config
            if original_config and hasattr(agent_controller, 'agent') and agent_controller.agent:
                agent_controller.agent.config = original_config
            
        except Exception as e:
            self.console.print(f"[red]❌ Plan generation error: {e}[/red]")
            raise

    def validate_args(self, args: str) -> bool:
        """Validate command arguments."""
        # Handle special flags
        if args.strip() in ["--list", "-l", "--help", "-h"]:
            return True
        
        # Require feature description for plan generation
        return bool(args.strip())

    def get_help_text(self) -> str:
        """Get detailed help text for the plan command."""
        return (
            "The /plan command generates detailed implementation plans for features.\n\n"
            "Usage:\n"
            "  /plan <feature_description>  - Generate plan for a feature\n"
            "  /plan --list                 - List all existing plans\n\n"
            "Examples:\n"
            "  /plan Add user authentication with JWT tokens\n"
            "  /plan Implement real-time chat with WebSockets\n"
            "  /plan Add dark mode toggle to UI components\n\n"
            "Plan Mode Process:\n"
            "1. 🔍 Investigation Phase - Analyzes existing codebase (read-only)\n"
            "2. 📋 Planning Phase - Generates comprehensive implementation strategy\n"
            "3. 💾 Documentation Phase - Saves plan to plans/ directory\n"
            "4. 🚀 Ready for Implementation - Use /implement to execute the plan\n\n"
            "What's Included in Plans:\n"
            "• Detailed codebase analysis and findings\n"
            "• Step-by-step implementation strategy\n"
            "• Technical specifications and architecture changes\n"
            "• Risk assessment and mitigation strategies\n"
            "• Testing and validation approach\n"
            "• Timeline estimates and success criteria\n\n"
            "Benefits:\n"
            "• Thorough planning reduces implementation risks\n"
            "• Clear roadmap for complex features\n"
            "• Documentation of decisions and rationale\n"
            "• Enables review and collaboration before coding\n"
            "• Provides checkpoint for implementation progress\n\n"
            "Next Steps:\n"
            "• Review generated plan in plans/ directory\n"
            "• Use /implement <plan_id> to execute the plan\n"
            "• Modify plan file if adjustments are needed"
        )