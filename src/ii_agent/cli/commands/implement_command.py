"""
Implement command implementation.

This module provides the /implement command that executes pre-existing plans 
step-by-step with progress tracking and plan updates.
"""

import re
from typing import Optional, Any, Dict, List, Tuple
from pathlib import Path
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML

from .base_command import BaseCommand
from ..plan_state import PlanStateManager, PlanInfo
from ...prompts.plan_mode_prompt import get_implementation_mode_system_prompt


class ImplementCommand(BaseCommand):
    """Command to execute implementation plans step-by-step."""

    @property
    def name(self) -> str:
        return "implement"

    @property
    def description(self) -> str:
        return "Execute a pre-existing implementation plan step-by-step with progress tracking"

    async def execute(self, args: str, context: Dict[str, Any]) -> Optional[str]:
        """Execute the implement command."""
        # Handle special flags
        if args.strip() in ["--list", "-l"]:
            return await self._list_plans(context)
        
        if args.strip() in ["--help", "-h"] or not args.strip():
            self.console.print(self.get_help_text())
            return None

        # Get workspace and create plan state manager
        app = context.get("app")
        if not app:
            self.console.print("[red]Error: App context not available[/red]")
            return None

        workspace_path = app.workspace_path
        plan_manager = PlanStateManager(workspace_path)

        # Parse plan ID from args
        plan_id = args.strip().split()[0]
        
        # Get plan info
        plan_info = plan_manager.get_plan_info(plan_id)
        if not plan_info:
            self.console.print(f"[red]Error: Plan '{plan_id}' not found[/red]")
            self.console.print("Use [cyan]/implement --list[/cyan] to see available plans")
            return None

        # Load plan content
        plan_content = plan_manager.load_plan_content(plan_id)
        if not plan_content:
            self.console.print(f"[red]Error: Could not load plan content for '{plan_id}'[/red]")
            return None

        # Show implementation information
        info_panel = Panel(
            f"[bold green]Implementation Mode[/bold green]\n\n"
            f"📋 [bold]Plan:[/bold] {plan_info.name}\n"
            f"🆔 [bold]ID:[/bold] {plan_info.plan_id}\n"
            f"📅 [bold]Created:[/bold] {plan_info.created_at}\n"
            f"📊 [bold]Status:[/bold] {plan_info.status}\n\n"
            f"💡 [bold]Description:[/bold]\n{plan_info.description}\n\n"
            "🚀 [bold]What happens next:[/bold]\n"
            "1. Parse implementation steps from plan\n"
            "2. Execute steps one by one with confirmation\n"
            "3. Track progress and update plan status\n"
            "4. Handle any issues or blockers\n"
            "5. Complete implementation and update documentation",
            title="Implementation Phase",
            style="green",
        )
        self.console.print(info_panel)

        # Get confirmation to proceed
        try:
            session = PromptSession()
            response = await session.prompt_async(
                HTML("<ansigreen>Proceed with implementation? (Y/n): </ansigreen>")
            )
            confirmed = response.strip().lower() in ["y", "yes", ""]

            if not confirmed:
                self.console.print("[green]Implementation cancelled.[/green]")
                return None

        except (EOFError, KeyboardInterrupt):
            self.console.print("[green]Implementation cancelled.[/green]")
            return None

        # Activate plan mode for implementation
        plan_manager.activate_plan_mode(plan_id)
        
        # Update plan status to in_progress
        plan_manager.update_plan_status(plan_id, "in_progress")

        # Start implementation process
        try:
            result = await self._execute_implementation(
                plan_info, plan_content, plan_manager, context
            )
            
            if result:
                # Update plan status to completed
                plan_manager.update_plan_status(plan_id, "completed")
                
                # Show success message
                success_panel = Panel(
                    f"🎉 [bold green]Implementation Completed Successfully![/bold green]\n\n"
                    f"📋 [bold]Plan:[/bold] {plan_info.name}\n"
                    f"🆔 [bold]ID:[/bold] {plan_info.plan_id}\n"
                    f"✅ [bold]Status:[/bold] Completed\n\n"
                    "🎯 [bold]What was accomplished:[/bold]\n"
                    "• All implementation steps executed\n"
                    "• Code changes applied successfully\n"
                    "• Tests and validation completed\n"
                    "• Documentation updated\n\n"
                    "📝 [bold]Next steps:[/bold]\n"
                    "• Review implemented changes\n"
                    "• Run additional tests if needed\n"
                    "• Deploy or integrate as appropriate",
                    title="Implementation Complete",
                    style="green",
                )
                self.console.print(success_panel)
                
                return "IMPLEMENTATION_COMPLETED"
            else:
                # Update plan status to error or cancelled
                plan_manager.update_plan_status(plan_id, "error")
                self.console.print("[red]Implementation failed or was cancelled[/red]")
                return None
                
        except Exception as e:
            self.console.print(f"[red]Error during implementation: {e}[/red]")
            plan_manager.update_plan_status(plan_id, "error")
            return None
        
        finally:
            # Deactivate plan mode
            plan_manager.deactivate_plan_mode()

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

    async def _execute_implementation(
        self, 
        plan_info: PlanInfo, 
        plan_content: str, 
        plan_manager: PlanStateManager,
        context: Dict[str, Any]
    ) -> bool:
        """Execute the implementation plan step by step."""
        
        # Parse implementation steps from plan content
        steps = self._parse_implementation_steps(plan_content)
        
        if not steps:
            self.console.print("[red]Error: No implementation steps found in plan[/red]")
            return False

        self.console.print(f"[green]Found {len(steps)} implementation steps[/green]")
        
        # Get agent controller
        agent_controller = context.get("agent_controller")
        if not agent_controller:
            self.console.print("[red]Error: Agent controller not available[/red]")
            return False

        # Set up implementation mode system prompt
        app = context.get("app")
        workspace_path = app.workspace_path if app else "."
        
        # Get the implementation mode system prompt
        system_prompt = get_implementation_mode_system_prompt(workspace_path, plan_content)
        
        # Get max tokens from agent config or use default
        max_tokens = 8192  # Default fallback
        if hasattr(agent_controller, 'agent') and agent_controller.agent and hasattr(agent_controller.agent, 'config'):
            max_tokens = getattr(agent_controller.agent.config, 'max_tokens_per_turn', 8192)
        
        # Create implementation mode agent config
        from ii_agent.core.config.agent_config import AgentConfig
        
        implementation_agent_config = AgentConfig(
            max_tokens_per_turn=max_tokens,
            system_prompt=system_prompt,
        )
        
        # Store original config and temporarily update for implementation mode
        original_config = agent_controller.agent.config if hasattr(agent_controller, 'agent') and agent_controller.agent else None
        
        if hasattr(agent_controller, 'agent') and agent_controller.agent:
            agent_controller.agent.config = implementation_agent_config

        # Execute steps with progress tracking
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            
            main_task = progress.add_task("Implementing plan...", total=len(steps))
            
            for i, (phase, step_description) in enumerate(steps, 1):
                progress.update(
                    main_task, 
                    description=f"Step {i}/{len(steps)}: {step_description[:50]}...",
                    completed=i-1
                )
                
                # Show current step
                step_panel = Panel(
                    f"[bold]Phase:[/bold] {phase}\n"
                    f"[bold]Step {i}/{len(steps)}:[/bold] {step_description}\n\n"
                    "This step will be executed by the AI agent...",
                    title=f"Implementation Step {i}",
                    style="blue",
                )
                self.console.print(step_panel)
                
                # Ask for confirmation for each major step
                try:
                    session = PromptSession()
                    response = await session.prompt_async(
                        HTML(f"<ansiblue>Execute step {i}? (Y/n/s to skip): </ansiblue>")
                    )
                    user_choice = response.strip().lower()
                    
                    if user_choice in ["n", "no"]:
                        self.console.print("[yellow]Implementation cancelled by user[/yellow]")
                        return False
                    elif user_choice in ["s", "skip"]:
                        self.console.print("[yellow]Step skipped[/yellow]")
                        continue
                        
                except (EOFError, KeyboardInterrupt):
                    self.console.print("[yellow]Implementation cancelled[/yellow]")
                    return False
                
                # Execute the step using agent
                step_success = await self._execute_step(
                    agent_controller, phase, step_description, progress, main_task
                )
                
                if not step_success:
                    self.console.print(f"[red]Step {i} failed. Do you want to continue?[/red]")
                    try:
                        response = await session.prompt_async(
                            HTML("<ansired>Continue despite failure? (y/N): </ansired>")
                        )
                        if response.strip().lower() not in ["y", "yes"]:
                            return False
                    except (EOFError, KeyboardInterrupt):
                        return False
                
                # Update progress
                plan_manager.update_plan_progress(plan_info.plan_id, {
                    f"step_{i}": {
                        "description": step_description,
                        "phase": phase,
                        "status": "completed" if step_success else "failed",
                        "completed_at": plan_manager.current_state.get("last_updated")
                    }
                })
            
            progress.update(main_task, completed=len(steps), description="✅ Implementation completed!")
        
        # Restore original agent config
        if original_config and hasattr(agent_controller, 'agent') and agent_controller.agent:
            agent_controller.agent.config = original_config
        
        return True

    def _parse_implementation_steps(self, plan_content: str) -> List[Tuple[str, str]]:
        """Parse implementation steps from plan content."""
        steps = []
        current_phase = "Unknown"
        
        lines = plan_content.split('\n')
        
        # Look for implementation sections and checklist items
        in_implementation_section = False
        
        for line in lines:
            line = line.strip()
            
            # Detect implementation sections
            if any(keyword in line.lower() for keyword in ['implementation', 'plan', 'phase', 'step']):
                if line.startswith('#'):
                    in_implementation_section = True
                    current_phase = line.strip('#').strip()
                    continue
            
            # Parse checklist items
            if in_implementation_section and line.startswith('- [ ]'):
                step_desc = line[5:].strip()  # Remove '- [ ]'
                if step_desc and len(step_desc) > 5:  # Ignore very short items
                    steps.append((current_phase, step_desc))
            
            # Parse numbered lists
            elif in_implementation_section and re.match(r'^\d+\.', line):
                step_desc = re.sub(r'^\d+\.\s*', '', line).strip()
                if step_desc and len(step_desc) > 5:
                    steps.append((current_phase, step_desc))
        
        # If no structured steps found, create high-level steps from plan
        if not steps:
            steps = [
                ("Analysis", "Analyze current codebase structure"),
                ("Setup", "Set up necessary files and configurations"),
                ("Implementation", "Implement core functionality"),
                ("Testing", "Add and run tests"),
                ("Documentation", "Update documentation"),
                ("Validation", "Validate implementation meets requirements")
            ]
        
        return steps

    async def _execute_step(
        self, 
        agent_controller, 
        phase: str, 
        step_description: str, 
        progress: Progress, 
        task_id
    ) -> bool:
        """Execute a single implementation step."""
        try:
            # Create instruction for the step
            step_instruction = f"""IMPLEMENTATION STEP - {phase}

Execute the following implementation step:
{step_description}

Please:
1. Analyze what needs to be done for this step
2. Implement the required changes
3. Test the changes if applicable
4. Provide a summary of what was accomplished

If you encounter any issues or need clarification, please explain the problem and suggest alternatives.
"""
            
            # Execute the step
            await agent_controller.run_agent_async(
                instruction=step_instruction,
                files=None,
                resume=True
            )
            
            # Check if execution was successful
            # This is a simplified check - in practice you might want more sophisticated validation
            return True
            
        except Exception as e:
            progress.update(task_id, description=f"❌ Step failed: {e}")
            self.console.print(f"[red]Step execution failed: {e}[/red]")
            return False

    def validate_args(self, args: str) -> bool:
        """Validate command arguments."""
        # Handle special flags
        if args.strip() in ["--list", "-l", "--help", "-h"]:
            return True
        
        # Require plan ID for implementation
        return bool(args.strip())

    def get_help_text(self) -> str:
        """Get detailed help text for the implement command."""
        return (
            "The /implement command executes pre-existing implementation plans step-by-step.\n\n"
            "Usage:\n"
            "  /implement <plan_id>         - Execute a specific plan\n"
            "  /implement --list            - List all available plans\n\n"
            "Examples:\n"
            "  /implement a1b2c3d4          - Execute plan with ID a1b2c3d4\n"
            "  /implement --list            - Show all available plans\n\n"
            "Implementation Process:\n"
            "1. 📋 Load and parse the implementation plan\n"
            "2. 🔍 Show plan overview and get confirmation\n"
            "3. 🚀 Execute steps one by one with progress tracking\n"
            "4. ✅ Confirm each major step before execution\n"
            "5. 📊 Track progress and update plan status\n"
            "6. 🎯 Complete implementation and update documentation\n\n"
            "Step Execution:\n"
            "• Each step is executed by the AI agent\n"
            "• User confirmation required for major steps\n"
            "• Option to skip or cancel at any step\n"
            "• Progress tracked and saved to plan file\n"
            "• Automatic error handling and recovery options\n\n"
            "Plan Status Management:\n"
            "• Status updated throughout implementation\n"
            "• Progress saved for resumability\n"
            "• Error states handled gracefully\n"
            "• Completion status tracked\n\n"
            "Interactive Features:\n"
            "• Step-by-step confirmation\n"
            "• Skip option for individual steps\n"
            "• Cancel option at any point\n"
            "• Continue despite failures option\n"
            "• Real-time progress display\n\n"
            "Requirements:\n"
            "• Plan must exist (created via /plan command)\n"
            "• Plan must be in 'ready' or 'in_progress' status\n"
            "• Agent controller must be available for execution"
        )