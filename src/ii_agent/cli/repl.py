"""Interactive REPL for ii-agent - aider-style CLI interface."""
import os
import sys
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import WordCompleter, Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.document import Document
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

import anthropic
import openai
from google import genai

from ii_agent.core.config.ii_agent_config import config


class ModelCompleter(Completer):
    """Custom completer for /model command with provider and model suggestions."""

    def __init__(self, available_providers: Dict[str, bool]):
        self.available_providers = available_providers
        self.model_suggestions = {
            "anthropic": [
                "claude-sonnet-4",
                "claude-opus-4",
                "claude-sonnet-3.5",
            ],
            "openai": [
                "gpt-4",
                "gpt-4-turbo",
                "gpt-4o",
                "gpt-3.5-turbo",
            ],
            "gemini": [
                "gemini-2.0-flash-exp",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ],
            "nvidia": [
                "qwen/qwen3-coder-480b-a35b-instruct",
                "meta/llama-3.1-405b-instruct",
                "meta/llama-3.1-70b-instruct",
                "kimi/kimi2-0905",
                "nvidia/llama-3.1-nemotron-70b-instruct",
            ],
        }

    def get_completions(self, document: Document, complete_event):
        """Generate completions based on current input."""
        text = document.text_before_cursor
        words = text.split()

        # If we're at a command, offer commands
        if not text or text == "/":
            return

        # If text starts with /model
        if text.startswith("/model"):
            parts = text.split()

            # Just "/model" or "/model " -> suggest providers
            if len(parts) == 1 or (len(parts) == 2 and text.endswith(" ")):
                word = parts[1] if len(parts) == 2 else ""
                available = [p for p, avail in self.available_providers.items() if avail]

                for provider in available:
                    if provider.startswith(word.lower()):
                        yield Completion(
                            provider,
                            start_position=-len(word),
                            display=f"{provider} ✓",
                        )

            # "/model <provider>" or "/model <provider> " -> suggest models
            elif len(parts) >= 2:
                provider = parts[1]
                word = parts[2] if len(parts) >= 3 else ""

                if provider in self.model_suggestions:
                    models = self.model_suggestions[provider]
                    for model in models:
                        if model.lower().startswith(word.lower()):
                            yield Completion(
                                model,
                                start_position=-len(word),
                                display=model,
                            )


class LocalSession:
    """Local session manager without database."""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()
        self.history: List[Dict[str, Any]] = []
        self.context_files: List[Path] = []
        self.model = "qwen/qwen3-coder-480b-a35b-instruct"
        self.provider = "nvidia"
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"

    def add_message(self, role: str, content: str):
        """Add message to history."""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def add_file(self, filepath: str):
        """Add file to context."""
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {filepath}")
        if path not in self.context_files:
            self.context_files.append(path)

    def remove_file(self, filepath: str):
        """Remove file from context."""
        path = Path(filepath).resolve()
        if path in self.context_files:
            self.context_files.remove(path)

    def clear_files(self):
        """Clear all context files."""
        self.context_files.clear()

    def get_context(self) -> str:
        """Get context from files."""
        context_parts = []
        for path in self.context_files:
            try:
                with open(path, 'r') as f:
                    content = f.read()
                context_parts.append(f"File: {path}\n\n{content}\n")
            except Exception as e:
                context_parts.append(f"Error reading {path}: {e}\n")
        return "\n".join(context_parts)


class AgentREPL:
    """Interactive REPL for ii-agent."""

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.getcwd()
        self.session = LocalSession(self.workspace)
        self.console = Console()
        self.running = True

        # Check available providers
        self.available_providers = self._check_available_providers()

        # Commands - set this first before completer
        self.commands = {
            "/help": self.cmd_help,
            "/exit": self.cmd_exit,
            "/quit": self.cmd_exit,
            "/clear": self.cmd_clear,
            "/model": self.cmd_model,
            "/add": self.cmd_add,
            "/drop": self.cmd_drop,
            "/ls": self.cmd_ls,
            "/files": self.cmd_files,
            "/reset": self.cmd_reset,
        }

        # Prompt toolkit setup
        history_file = Path.home() / ".ii_agent" / "repl_history"
        history_file.parent.mkdir(parents=True, exist_ok=True)

        self.prompt_session = PromptSession(
            history=FileHistory(str(history_file)),
            completer=self._get_completer(),
            style=self._get_style(),
        )

    def _check_available_providers(self) -> Dict[str, bool]:
        """Check which providers have API keys set."""
        providers = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
        }
        return {
            provider: bool(os.getenv(env_var))
            for provider, env_var in providers.items()
        }

    def _get_completer(self) -> Completer:
        """Get custom completer with model completion support."""
        return ModelCompleter(self.available_providers)

    def _get_style(self) -> Style:
        """Get prompt style."""
        return Style.from_dict({
            'prompt': '#00aa00 bold',
        })

    async def cmd_help(self, args: str):
        """Show help."""
        # Build provider list with availability indicators
        provider_lines = []
        provider_info = {
            "anthropic": ("Claude models", "claude-sonnet-4, claude-opus-4"),
            "openai": ("GPT models", "gpt-4, gpt-4-turbo"),
            "gemini": ("Google models", "gemini-2.0-flash-exp"),
            "nvidia": ("NVIDIA models", "qwen/qwen3-coder-480b-a35b-instruct, kimi/kimi2-0905"),
        }

        for provider, (desc, examples) in provider_info.items():
            if self.available_providers.get(provider, False):
                status = "✓"
                provider_lines.append(f"- `{provider}` {status} - {desc} ({examples})")
            else:
                status = "✗"
                env_var = {
                    "anthropic": "ANTHROPIC_API_KEY",
                    "openai": "OPENAI_API_KEY",
                    "gemini": "GOOGLE_API_KEY",
                    "nvidia": "NVIDIA_API_KEY",
                }[provider]
                provider_lines.append(f"- ~~`{provider}`~~ {status} - {desc} (set `{env_var}`)")

        providers_text = "\n".join(provider_lines)

        help_text = f"""
# ii-agent REPL Commands

**Chat Commands:**
- Just type your message to chat with the agent
- Multi-line: End with empty line or Ctrl+D

**File Management:**
- `/add <file>` - Add file to context
- `/drop <file>` - Remove file from context
- `/files` - List files in context
- `/ls` - List files in workspace

**Session:**
- `/clear` - Clear chat history
- `/reset` - Reset session (clear history and files)
- `/model [provider] [model]` - Change model

**Providers:**
{providers_text}

**Examples:**
- `/model anthropic claude-sonnet-4`
- `/model nvidia qwen/qwen3-coder-480b-a35b-instruct`
- `/model openai gpt-4`

**Other:**
- `/help` - Show this help
- `/exit` or `/quit` - Exit REPL
"""
        self.console.print(Markdown(help_text))

    async def cmd_exit(self, args: str):
        """Exit REPL."""
        self.running = False
        self.console.print("[yellow]Goodbye![/yellow]")

    async def cmd_clear(self, args: str):
        """Clear history."""
        self.session.history.clear()
        self.console.print("[green]Chat history cleared[/green]")

    async def cmd_model(self, args: str):
        """Change model."""
        parts = args.strip().split()
        if not parts:
            # Show current model and available providers
            self.console.print(f"[cyan]Current: {self.session.provider}/{self.session.model}[/cyan]")

            available = [p for p, avail in self.available_providers.items() if avail]
            if available:
                self.console.print(f"[green]Available providers: {', '.join(available)}[/green]")

            unavailable = [p for p, avail in self.available_providers.items() if not avail]
            if unavailable:
                self.console.print(f"[dim]Unavailable (no API key): {', '.join(unavailable)}[/dim]")
            return

        # Parse provider and model
        if len(parts) == 1:
            new_model = parts[0]
            new_provider = self.session.provider
        elif len(parts) == 2:
            new_provider = parts[0]
            new_model = parts[1]
        else:
            self.console.print("[red]Usage: /model [provider] <model>[/red]")
            return

        # Check if provider has API key
        if not self.available_providers.get(new_provider, False):
            env_var = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "gemini": "GOOGLE_API_KEY",
                "nvidia": "NVIDIA_API_KEY",
            }.get(new_provider, f"{new_provider.upper()}_API_KEY")

            self.console.print(f"[red]Error: Provider '{new_provider}' not available[/red]")
            self.console.print(f"[yellow]Set API key: export {env_var}=your_key_here[/yellow]")
            return

        # Set the model
        self.session.provider = new_provider
        self.session.model = new_model
        self.console.print(f"[green]Model set to: {self.session.provider}/{self.session.model}[/green]")

    async def cmd_add(self, args: str):
        """Add file to context."""
        filepath = args.strip()
        if not filepath:
            self.console.print("[red]Usage: /add <file>[/red]")
            return

        try:
            self.session.add_file(filepath)
            self.console.print(f"[green]Added: {filepath}[/green]")
        except FileNotFoundError as e:
            self.console.print(f"[red]{e}[/red]")

    async def cmd_drop(self, args: str):
        """Remove file from context."""
        filepath = args.strip()
        if not filepath:
            self.console.print("[red]Usage: /drop <file>[/red]")
            return

        self.session.remove_file(filepath)
        self.console.print(f"[green]Removed: {filepath}[/green]")

    async def cmd_files(self, args: str):
        """List context files."""
        if not self.session.context_files:
            self.console.print("[yellow]No files in context[/yellow]")
            return

        self.console.print("[cyan]Files in context:[/cyan]")
        for path in self.session.context_files:
            self.console.print(f"  - {path}")

    async def cmd_ls(self, args: str):
        """List workspace files."""
        try:
            files = sorted(Path(self.workspace).iterdir())
            self.console.print(f"[cyan]Workspace: {self.workspace}[/cyan]")
            for f in files:
                if f.is_dir():
                    self.console.print(f"  [blue]{f.name}/[/blue]")
                else:
                    self.console.print(f"  {f.name}")
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")

    async def cmd_reset(self, args: str):
        """Reset session."""
        self.session.history.clear()
        self.session.clear_files()
        self.console.print("[green]Session reset[/green]")

    async def process_command(self, text: str) -> bool:
        """Process command. Returns True if command was handled."""
        text = text.strip()
        if not text.startswith("/"):
            return False

        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd in self.commands:
            await self.commands[cmd](args)
            return True

        self.console.print(f"[red]Unknown command: {cmd}[/red]")
        self.console.print("[yellow]Type /help for available commands[/yellow]")
        return True

    def _check_api_key(self) -> bool:
        """Check if API key is set for current provider."""
        env_vars = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "nvidia": "NVIDIA_API_KEY",
        }

        env_var = env_vars.get(self.session.provider)
        if not env_var:
            return True  # Unknown provider, let it fail naturally

        if not os.getenv(env_var):
            self.console.print(f"[red]Error: {env_var} not set[/red]")
            self.console.print(f"[yellow]Set it with: export {env_var}=your_key_here[/yellow]")
            return False

        return True

    async def chat(self, user_message: str):
        """Send message to agent."""
        # Check API key first
        if not self._check_api_key():
            return

        try:
            # Add user message
            self.session.add_message("user", user_message)

            # Get context
            context = self.session.get_context()

            # Build full prompt
            if context:
                full_prompt = f"{context}\n\nUser: {user_message}"
            else:
                full_prompt = user_message

            # Show thinking indicator
            with self.console.status("[bold green]Agent thinking..."):
                # Get response based on provider
                if self.session.provider == "anthropic":
                    client = anthropic.Anthropic()
                    response = client.messages.create(
                        model=self.session.model,
                        max_tokens=8000,
                        messages=[{"role": "user", "content": full_prompt}]
                    )
                    response_text = ""
                    for block in response.content:
                        if hasattr(block, 'text'):
                            response_text += block.text

                elif self.session.provider == "openai":
                    client = openai.OpenAI()
                    response = client.chat.completions.create(
                        model=self.session.model,
                        messages=[{"role": "user", "content": full_prompt}]
                    )
                    response_text = response.choices[0].message.content

                elif self.session.provider == "gemini":
                    client = genai.Client()
                    response = client.models.generate_content(
                        model=self.session.model,
                        contents=full_prompt
                    )
                    response_text = response.text

                elif self.session.provider == "nvidia":
                    client = openai.OpenAI(
                        base_url=self.session.nvidia_base_url,
                        api_key=os.getenv("NVIDIA_API_KEY")
                    )
                    response = client.chat.completions.create(
                        model=self.session.model,
                        messages=[{"role": "user", "content": full_prompt}],
                        temperature=0.7,
                        top_p=0.8,
                        max_tokens=4096
                    )
                    response_text = response.choices[0].message.content

                else:
                    response_text = f"Unsupported provider: {self.session.provider}"

            # Add assistant message
            self.session.add_message("assistant", response_text)

            # Display response
            self.console.print(Panel(
                Markdown(response_text),
                title="[bold cyan]Agent[/bold cyan]",
                border_style="cyan"
            ))

        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            if "api" in str(e).lower() or "key" in str(e).lower() or "auth" in str(e).lower():
                self._check_api_key()  # Show helpful message

    async def run(self):
        """Run the REPL."""
        # Welcome message
        self.console.print(Panel(
            f"[bold cyan]ii-agent Interactive REPL[/bold cyan]\n\n"
            f"Workspace: {self.workspace}\n"
            f"Model: {self.session.provider}/{self.session.model}\n\n"
            f"Type [green]/help[/green] for commands, [green]/exit[/green] to quit",
            border_style="cyan"
        ))

        while self.running:
            try:
                # Get input
                text = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.prompt_session.prompt(
                        [('class:prompt', '> ')],
                        multiline=False
                    )
                )

                if not text.strip():
                    continue

                # Process command or chat
                is_command = await self.process_command(text)
                if not is_command:
                    await self.chat(text)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /exit to quit[/yellow]")
            except EOFError:
                break


async def main_repl(workspace: Optional[str] = None):
    """Main REPL entry point."""
    repl = AgentREPL(workspace)
    await repl.run()


if __name__ == "__main__":
    asyncio.run(main_repl())
