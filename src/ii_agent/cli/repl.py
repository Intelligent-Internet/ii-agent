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
from ii_agent.cli.repl_styles import (
    Color, Symbol, Section,
    format_prompt, format_success, format_error, format_warning, format_info,
    format_provider, format_section_header, format_model_status, format_env_var,
    format_command, format_file, format_workspace,
    create_status_line, create_header_line, ANSIConsole
)

import anthropic
import openai

from ii_agent.core.config.ii_agent_config import config
from ii_agent.llm.model_constants import CONTEXT_WINDOWS, PERFORMANCE_CLIFFS
from ii_agent.llm.token_counter import TokenCounter
import importlib


def _get_context_manager_module():
    try:
        return importlib.import_module("ii_agent.server.chat.context_manager")
    except Exception:
        return None


def _get_ContextWindowManager():
    mod = _get_context_manager_module()
    return getattr(mod, "ContextWindowManager", None) if mod else None


def _get_performance_cliff_threshold(model_id: str):
    mod = _get_context_manager_module()
    if not mod:
        # Fallback to model constants if context_manager is not importable
        from ii_agent.llm.model_constants import PERFORMANCE_CLIFFS
        def _normalize(s: str) -> str:
            return ''.join(ch for ch in s if ch.isalnum()).lower()

        model_norm = _normalize(model_id)
        # Choose the best key match (longest substring match) to avoid firstword collisions
        best_k = None
        best_len = 0
        for k, v in PERFORMANCE_CLIFFS.items():
            key_norm = _normalize(k)
            # Check full key
            if key_norm in model_norm and len(key_norm) > best_len:
                best_len = len(key_norm)
                best_k = k
            # Check first word (shorter match)
            fword_norm = _normalize(k.split()[0])
            if fword_norm in model_norm and len(fword_norm) > best_len:
                best_len = len(fword_norm)
                best_k = k

        if best_k:
            return PERFORMANCE_CLIFFS[best_k]
        # Default fallback - use authoritative model constants
        return PERFORMANCE_CLIFFS.get("Default", {"early_degradation": 30000, "moderate_cliff": 64000, "severe_cliff": 100000})
    try:
        return mod.get_performance_cliff_threshold(model_id)
    except Exception:
        return {}


def _get_checkpoint_threshold_for_model(model_id: str):
    mod = _get_context_manager_module()
    if not mod:
        return 0.9
    try:
        return mod.ContextWindowManager.get_checkpoint_threshold_for_model(model_id)
    except Exception:
        return 0.9


def _track_harmonic_miss(model_id: str, error_type: str, context_tokens: int):
    mod = _get_context_manager_module()
    if not mod:
        return None
    try:
        return mod.ContextWindowManager.track_harmonic_miss(model_id, error_type, context_tokens)
    except Exception:
        return None


def _calculate_model_specific_threshold(model_id: str):
    mod = _get_context_manager_module()
    if not mod:
        from ii_agent.llm.model_constants import CONTEXT_WINDOWS
        return 0.9
    try:
        return mod.calculate_model_specific_threshold(model_id)
    except Exception:
        from ii_agent.llm.model_constants import CONTEXT_WINDOWS
        return 0.9


class FileCompleter(Completer):
    """File path completer for /add and /drop commands."""

    def __init__(self, workspace: str):
        self.workspace = Path(workspace).resolve()

    def get_completions(self, document: Document, complete_event):
        """Generate file path completions."""
        text = document.text_before_cursor

        if not text.startswith(("/add", "/drop")):
            return

        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            # Just the command, suggest files from workspace
            partial = ""
        else:
            partial = parts[1]

        # Expand ~ and resolve path
        if partial.startswith("~"):
            partial = str(Path(partial).expanduser())

        # Determine the directory to search
        if "/" in partial:
            base_dir = Path(partial).parent
            prefix = Path(partial).name
        else:
            base_dir = self.workspace
            prefix = partial

        # Make base_dir absolute
        if not base_dir.is_absolute():
            base_dir = self.workspace / base_dir

        # List matching files and directories
        try:
            if base_dir.exists() and base_dir.is_dir():
                for item in sorted(base_dir.iterdir()):
                    # Skip hidden files unless explicitly requested
                    if item.name.startswith(".") and not prefix.startswith("."):
                        continue

                    # Get relative path from workspace
                    try:
                        rel_path = item.relative_to(self.workspace)
                        display_path = str(rel_path)
                    except ValueError:
                        # Outside workspace
                        display_path = str(item)

                    # Check if it matches the prefix
                    if item.name.startswith(prefix):
                        # Add trailing slash for directories
                        completion_text = display_path + ("/" if item.is_dir() else "")

                        yield Completion(
                            completion_text,
                            start_position=-len(partial),
                            display=display_path + ("/" if item.is_dir() else ""),
                        )
        except (PermissionError, OSError):
            pass


class CompositeCompleter(Completer):
    """Composite completer that combines multiple completers."""

    def __init__(self, completers: List[Completer]):
        self.completers = completers

    def get_completions(self, document: Document, complete_event):
        """Get completions from all child completers."""
        for completer in self.completers:
            yield from completer.get_completions(document, complete_event)


class ModelCompleter(Completer):
    """Custom completer for /model command with provider and model suggestions."""

    def __init__(self, available_providers: Dict[str, bool]):
        self.available_providers = available_providers
        # Import model fetcher lazily
        from ii_agent.cli.model_fetcher import get_model_fetcher
        self.model_fetcher = get_model_fetcher()

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

            # Just "/model" or "/model " -> suggest providers or provider/model formats
            if len(parts) == 1 or (len(parts) == 2 and not "/" in parts[1] if len(parts) == 2 else True):
                word = parts[1] if len(parts) == 2 else ""

                # If no slash yet, suggest providers first
                if "/" not in word:
                    available = [p for p, avail in self.available_providers.items() if avail]
                    for provider in available:
                        if provider.startswith(word.lower()):
                            yield Completion(
                                provider + "/",
                                start_position=-len(word),
                                display=f"{provider}/ (→ models)",
                            )
                # If slash present, fetch and suggest models for that provider
                else:
                    provider_part, model_part = word.split("/", 1) if "/" in word else (word, "")
                    provider = provider_part.strip()

                    if provider in self.available_providers and self.available_providers[provider]:
                        # Fetch models dynamically
                        models = self.model_fetcher.get_models(provider)

                        for model in models:
                            # For NVIDIA models that already have provider/ prefix
                            if "/" in model:
                                model_slug = model.split("/", 1)[1]
                                full_model = f"{provider}/{model_slug}"
                            else:
                                full_model = f"{provider}/{model}"

                            if full_model.lower().startswith(word.lower()):
                                yield Completion(
                                    full_model,
                                    start_position=-len(word),
                                    display=full_model,
                                )

            # "/model <provider> " or "/model <provider> <model>" (old format support)
            elif len(parts) >= 2 and "/" not in parts[1]:
                provider = parts[1]
                word = parts[2] if len(parts) >= 3 else ""

                if provider in self.available_providers and self.available_providers[provider]:
                    models = self.model_fetcher.get_models(provider)
                    for model in models:
                        # Strip provider prefix if present for old format
                        if "/" in model:
                            model = model.split("/", 1)[1]

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
        # Token accounting
        self.total_tokens = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._token_counter = TokenCounter()
        # Monitoring flags
        self._approaching_cliff = False
        # Context management integration (async background tasks)
        self._context_manager = _get_ContextWindowManager()

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens for text using the configured TokenCounter.

        Falls back to the old heuristic if counting fails.
        """
        try:
            return self._token_counter.count_tokens(text)
        except Exception:
            return len(text) // 4

    def add_message(self, role: str, content: str, tokens: Optional[int] = None):
        """Add message to history with token tracking."""
        if tokens is None:
            tokens = self.estimate_tokens(content)

        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "tokens": tokens
        })

        # Update token counters
        self.total_tokens += tokens
        if role == "user":
            self.prompt_tokens += tokens
        else:
            self.completion_tokens += tokens

        # If the session is approaching model limits, warn on stdout
        try:
            ctx_window = CONTEXT_WINDOWS.get(self.model, CONTEXT_WINDOWS["default"])
            cm = _get_ContextWindowManager()
            summ_threshold = cm.SUMMARIZATION_THRESHOLD if cm else ContextWindowManager.SUMMARIZATION_THRESHOLD if 'ContextWindowManager' in globals() else 0.95
            if self.total_tokens >= int(ctx_window * summ_threshold):
                print(f"{format_warning('Warning')}: approaching context limit ({self.total_tokens}/{ctx_window})")
        except Exception:
            pass
        # Apply local history reduction if needed (best-effort)
        try:
            context_window = CONTEXT_WINDOWS.get(self.model, CONTEXT_WINDOWS["default"])
            # If we are over 90% of context window, reduce history using ContextWindowManager helper
            if self.total_tokens >= int(context_window * 0.9):
                cm = self._context_manager
                if cm and hasattr(cm, 'reduce_history_tokens'):
                    reduced = cm.reduce_history_tokens(self.history, self.model)
                    if len(reduced) != len(self.history):
                        self.history = reduced
                        # Recompute token counts safely
                        self.total_tokens = sum(h.get('tokens', 0) for h in self.history)
                        self.prompt_tokens = sum(h.get('tokens', 0) for h in self.history if h.get('role') == 'user')
                        self.completion_tokens = sum(h.get('tokens', 0) for h in self.history if h.get('role') == 'assistant')
                        print(format_warning("Context reduced locally to avoid exceeding model limits"))
                else:
                    # Fallback to original trimming logic
                    while self.total_tokens >= int(context_window * 0.9) and len(self.history) > 1:
                        removed = self.history.pop(0)
                        self.total_tokens -= removed.get("tokens", 0)
                        if removed.get("role") == "user":
                            self.prompt_tokens -= removed.get("tokens", 0)
                        else:
                            self.completion_tokens -= removed.get("tokens", 0)
                    print(format_warning("Context reduced locally to avoid exceeding model limits"))
        except Exception:
            pass

        # Performance cliff detection for local REPL flows
        try:
            cliffs = _get_performance_cliff_threshold(self.model)
            early = int(cliffs.get("early_degradation", 0) * 0.8)
            # If currently at or above early degradation safety margin, flag
            self._approaching_cliff = self.total_tokens >= early and early > 0
            if self._approaching_cliff:
                print(format_warning(f"Approaching model early degradation ({self.total_tokens}/{early} tokens)"))
        except Exception:
            self._approaching_cliff = False

        # Schedule background context management (checkpointing, tile generation, benchmarks)
        try:
            # It's ok to fire-and-forget these background tasks;
            # they will use asyncio loop if present in REPL
            import asyncio
            if self._context_manager:
                # Create a task to run non-blocking context management
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(self._maybe_manage_context())
                else:
                    # If no loop running, run it in a new one (safe fallback)
                    loop.run_until_complete(self._maybe_manage_context())
        except Exception:
            # Best-effort; don't break REPL flow
            pass

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

    def get_context_status(self) -> dict:
        """Return current token usage and model-specific thresholds/status.

        Returns:
            Dict with keys: total_tokens, prompt_tokens, completion_tokens, context_window, checkpoint_threshold, model_cliffs
        """
        model_id = self.model
        context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])
        checkpoint_threshold_pct = _get_checkpoint_threshold_for_model(model_id)
        checkpoint_threshold = int(context_window * checkpoint_threshold_pct)

        # Performance cliff info
        cliffs = _get_performance_cliff_threshold(model_id)
        # Compute model-specific cliff pressure (0-1)
        try:
            cliff_pressure = 0.0
            early = cliffs.get("early_degradation", 0) or 0
            if early > 0:
                cliff_pressure = min(1.0, self.total_tokens / early)
        except Exception:
            cliff_pressure = 0.0

        # Build a visual usage bar
        def _usage_bar(percent: float, width: int = 20) -> str:
            filled = int(round((percent / 100.0) * width))
            return "[" + ("#" * filled) + ("-" * (width - filled)) + "]"

        usage_pct = (self.total_tokens / context_window) * 100 if context_window and context_window > 0 else 0
        usage_bar = _usage_bar(usage_pct)

        return {
            "model": model_id,
            "provider": self.provider,
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "context_window": context_window,
            "checkpoint_threshold_pct": checkpoint_threshold_pct,
            "checkpoint_threshold": checkpoint_threshold,
            "performance_cliffs": cliffs,
            "cliff_pressure": cliff_pressure,
            "approaching_cliff": self._approaching_cliff,
            "context_usage_bar": usage_bar,
        }

    def to_message_lists(self) -> list:
        """Convert self.history into a list of GeneralContentBlock lists suitable for checkpointing and tile generation."""
        try:
            from ii_agent.llm.base import TextPrompt, TextResult
        except Exception:
            return []

        message_lists = []
        for entry in self.history:
            role = entry.get("role")
            content = entry.get("content", "")
            if role == "user":
                message_lists.append([TextPrompt(text=content)])
            else:
                message_lists.append([TextResult(text=content)])
        return message_lists

    async def _maybe_manage_context(self):
        """Background task to handle checkpointing, tile generation and benchmarking.

        This is a best-effort function that integrates LocalSession with server-side
        ContextWindowManager logic when available.
        """
        if not self._context_manager:
            return

        try:
            cm = self._context_manager
            model_id = self.model
            context_window = CONTEXT_WINDOWS.get(model_id, CONTEXT_WINDOWS["default"])

            # Convert to GeneralContentBlock lists
            message_lists = self.to_message_lists()
            if not message_lists:
                return

            # Checkpoint creation
            try:
                threshold_pct = cm.get_checkpoint_threshold_for_model(model_id)
                checkpoint_threshold = int(context_window * threshold_pct)
                if self.total_tokens >= checkpoint_threshold:
                    checkpoint_system = cm.get_checkpoint_system()
                    # Use the existing microkernel generation used by SlabCheckpoint
                    slab_id = await checkpoint_system.create_checkpoint(message_lists)
                    print(format_info(f"Checkpoint created: {slab_id}"))
            except Exception:
                pass

            # Summarization when exceeding summarization threshold (REPL placeholder)
            try:
                summ_threshold = cm.SUMMARIZATION_THRESHOLD
                if self.total_tokens >= int(context_window * summ_threshold):
                    # Create a simple placeholder summary message (non-LLM)
                    if not getattr(self, '_last_summary_created', False):
                        summary_text = f"[Local summary of {len(self.history)} messages, {self.total_tokens} tokens]"
                        self.history.insert(0, {
                            'role': 'assistant',
                            'content': summary_text,
                            'timestamp': datetime.now().isoformat(),
                            'tokens': self.estimate_tokens(summary_text)
                        })
                        self._last_summary_created = True
                        print(format_info("Local summary created to reduce context pressure"))
            except Exception:
                pass

            # Tile generation at 33%
            try:
                tile_threshold = cm.TILE_GENERATION_THRESHOLD
                if self.total_tokens >= int(context_window * tile_threshold):
                    # Need to call dump_and_generate_tiles; this expects Message objects in server
                    tile_generator = cm.get_tile_generator()
                    result = await tile_generator.dump_and_generate_tiles(message_lists, context_window)
                    if result:
                        print(format_info(f"Tiles generated: {len(result.get('tiles_generated', []))}"))
            except Exception:
                pass

            # Benchmarks: record usage and optionally run background tests
            try:
                bench = cm.get_cliff_benchmark()
                bench.record_usage(model_id)
                # Enable mock mode for REPL to avoid unauthorised API calls
                bench.enable_mock_mode()
                if bench.should_run_tests(model_id):
                    # Provide a minimal llm_call_func that returns a canned response
                    async def _llm_call(prompt: str):
                        return "Mocked response"

                    await bench.run_background_tests(model_id, _llm_call)
            except Exception:
                pass
        except Exception:
            pass

    def is_approaching_cliff(self) -> bool:
        """Return whether this session is approaching a model performance cliff based on token usage."""
        return bool(self._approaching_cliff)


class AgentREPL:
    """Interactive REPL for ii-agent."""

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or os.getcwd()
        self.session = LocalSession(self.workspace)
        self.console = ANSIConsole()
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
            "/context": self.cmd_context,
            "/harmonic": self.cmd_harmonic,
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
        """Get custom completer with model and file completion support."""
        return CompositeCompleter([
            FileCompleter(self.workspace),
            ModelCompleter(self.available_providers),
        ])

    def _get_style(self) -> Style:
        """Get prompt style with ANSI colors."""
        return Style.from_dict({
            'prompt': 'ansigreen bold',
        })

    async def cmd_help(self, args: str):
        """Show help with ANSI colors and symbolic prefixes."""
        # Build provider list with symbolic indicators
        provider_lines = []
        provider_info = {
            "anthropic": ("Claude models", "claude-sonnet-4, claude-opus-4"),
            "openai": ("GPT models", "gpt-4, gpt-4-turbo"),
            "gemini": ("Google models", "gemini-2.0-flash-exp"),
            "nvidia": ("NVIDIA models", "qwen/qwen3-coder-480b-a35b-instruct, kimi/kimi2-0905"),
        }

        for provider, (desc, examples) in provider_info.items():
            if self.available_providers.get(provider, False):
                provider_lines.append(f"  {format_provider(provider, True)} - {desc} ({examples})")
            else:
                env_var = {
                    "anthropic": "ANTHROPIC_API_KEY",
                    "openai": "OPENAI_API_KEY",
                    "gemini": "GOOGLE_API_KEY",
                    "nvidia": "NVIDIA_API_KEY",
                }[provider]
                provider_lines.append(f"  {format_provider(provider, False)} - {desc} (set {format_env_var(env_var)})")

        # Print sections with color hints
        self.console.print(create_header_line("ii-agent REPL", "Interactive Agent", Color.CYAN))
        self.console.print("")

        self.console.print(f"{Section.CHAT}")
        self.console.print("  Just type your message to chat with the agent")
        self.console.print("  Multi-line: End with empty line or Ctrl+D")
        self.console.print("")

        self.console.print(f"{Section.FILES}")
        self.console.print(f"  {format_command('/add')} <path> - Add file to context")
        self.console.print(f"  {format_command('/drop')} <path> - Remove file from context")
        self.console.print(f"  {format_command('/files')} - List files in context")
        self.console.print(f"  {format_command('/ls')} - List files in workspace")
        self.console.print("")

        self.console.print(f"{Section.SESSION}")
        self.console.print(f"  {format_command('/clear')} - Clear chat history")
        self.console.print(f"  {format_command('/reset')} - Reset session (clear history and files)")
        self.console.print(f"  {format_command('/model')} [provider] [model] - Change model")
        self.console.print("")

        self.console.print(f"{Section.PROVIDERS}")
        for line in provider_lines:
            self.console.print(line)
        self.console.print("")

        self.console.print(f"{Section.EXAMPLES}")
        self.console.print(f"  {format_command('/model')} anthropic claude-sonnet-4")
        self.console.print(f"  {format_command('/model')} nvidia qwen/qwen3-coder-480b-a35b-instruct")
        self.console.print(f"  {format_command('/model')} openai gpt-4")
        self.console.print("")

        self.console.print(f"{Section.OTHER}")
        self.console.print(f"  {format_command('/help')} - Show this help")
        self.console.print(f"  {format_command('/exit')} or {format_command('/quit')} - Exit REPL")

    async def cmd_exit(self, args: str):
        """Exit REPL."""
        self.running = False
        self.console.print(format_info("Goodbye!"))

    async def cmd_clear(self, args: str):
        """Clear history."""
        self.session.history.clear()
        self.console.print(format_success("Chat history cleared"))

    async def cmd_model(self, args: str):
        """Change model."""
        parts = args.strip().split()
        if not parts:
            # Show current model and available providers
            current_model = format_model_status(self.session.provider, self.session.model, True)
            self.console.print(f"Current: {current_model}")

            available = [p for p, avail in self.available_providers.items() if avail]
            if available:
                self.console.print(format_success(f"Available providers: {', '.join(available)}"))

            unavailable = [p for p, avail in self.available_providers.items() if not avail]
            if unavailable:
                self.console.print(f"{Color.DIM}Unavailable (no API key): {', '.join(unavailable)}{Color.RESET}")
            return

        # Parse provider and model - support both formats:
        # 1. /model provider/model-slug/sub-slug
        # 2. /model provider model (legacy)
        if len(parts) == 1:
            # Check if it contains a slash (provider/model format)
            if "/" in parts[0]:
                provider_model = parts[0]
                # Split only on first slash to preserve model slugs with slashes
                slash_idx = provider_model.index("/")
                new_provider = provider_model[:slash_idx]
                new_model = provider_model[slash_idx+1:]
            else:
                # Just model name, use current provider
                new_model = parts[0]
                new_provider = self.session.provider
        elif len(parts) == 2:
            new_provider = parts[0]
            new_model = parts[1]
        else:
            self.console.print("[red]Usage: /model provider/model-slug or /model [provider] <model>[/red]")
            return

        # Check if provider has API key
        if not self.available_providers.get(new_provider, False):
            env_var = {
                "anthropic": "ANTHROPIC_API_KEY",
                "openai": "OPENAI_API_KEY",
                "gemini": "GOOGLE_API_KEY",
                "nvidia": "NVIDIA_API_KEY",
            }.get(new_provider, f"{new_provider.upper()}_API_KEY")

            self.console.print(format_error(f"Error: Provider '{new_provider}' not available"))
            self.console.print(format_warning(f"Set API key: export {format_env_var(env_var)}=your_key_here"))
            return

        # Set the model
        self.session.provider = new_provider
        self.session.model = new_model
        self.console.print(format_success(f"Model set to: {self.session.provider}/{self.session.model}"))
        # Show model-specific context info and cliffs
        try:
            cliffs = _get_performance_cliff_threshold(self.session.model)
            context_window = CONTEXT_WINDOWS.get(self.session.model, CONTEXT_WINDOWS["default"])
            threshold_pct = _get_checkpoint_threshold_for_model(self.session.model)
            self.console.print(format_info(f"Context window: {context_window} tokens"))
            self.console.print(format_info(f"Checkpoint threshold: {int(context_window * threshold_pct)} tokens ({threshold_pct:.1%})"))
            self.console.print(format_info("Performance cliffs:"))
            for k, v in cliffs.items():
                self.console.print(f"  {k}: {v}")
        except Exception:
            pass

    async def cmd_add(self, args: str):
        """Add file to context."""
        filepath = args.strip()
        if not filepath:
            self.console.print(format_error("Usage: /add <file>"))
            return

        try:
            self.session.add_file(filepath)
            self.console.print(format_success(f"Added: {format_file(filepath)}"))
        except FileNotFoundError as e:
            self.console.print(format_error(str(e)))

    async def cmd_drop(self, args: str):
        """Remove file from context."""
        filepath = args.strip()
        if not filepath:
            self.console.print(format_error("Usage: /drop <file>"))
            return

        self.session.remove_file(filepath)
        self.console.print(format_success(f"Removed: {format_file(filepath)}"))

    async def cmd_files(self, args: str):
        """List context files."""
        if not self.session.context_files:
            self.console.print(format_warning("No files in context"))
            return

        self.console.print(format_info("Files in context:"))
        for path in self.session.context_files:
            self.console.print(f"  {format_file(str(path))}")

    async def cmd_ls(self, args: str):
        """List workspace files."""
        try:
            files = sorted(Path(self.workspace).iterdir())
            self.console.print(create_status_line("Workspace", format_workspace(self.workspace), Color.CYAN))
            for f in files:
                if f.is_dir():
                    self.console.print(f"  {Color.BLUE}{f.name}/{Color.RESET}")
                else:
                    self.console.print(f"  {f.name}")
        except Exception as e:
            self.console.print(format_error(f"Error: {e}"))

    async def cmd_reset(self, args: str):
        """Reset session."""
        self.session.history.clear()
        self.session.clear_files()
        self.console.print(format_success("Session reset"))

    async def cmd_context(self, args: str):
        """Show context window status for current session"""
        status = self.session.get_context_status()
        # Build a status line
        model = status["model"]
        cw = status["context_window"]
        total = status["total_tokens"]
        pct = (total / cw) * 100 if cw and cw > 0 else 0
        checkpoint_threshold = status["checkpoint_threshold"]

        self.console.print(format_section_header(f"Context status - {model}"))
        # Colorize the usage bar when approaching cliffs
        usage_bar = status.get('context_usage_bar', '')
        if status.get('approaching_cliff'):
            usage_line = f"  {format_warning('Tokens')}: {total} / {cw} ({pct:.1f}%) {format_warning(usage_bar)}"
        else:
            usage_line = f"  {format_info('Tokens')}: {total} / {cw} ({pct:.1f}%) {usage_bar}"
        self.console.print(usage_line)
        self.console.print(f"  {format_info('Checkpoint threshold')}: {checkpoint_threshold} tokens ({status['checkpoint_threshold_pct']:.1%})")
        self.console.print(f"  {format_info('Prompt tokens')}: {status['prompt_tokens']}")
        self.console.print(f"  {format_info('Completion tokens')}: {status['completion_tokens']}")
        self.console.print(f"  {format_info('Performance cliffs')}:")
        for k, v in (status["performance_cliffs"] or {}).items():
            self.console.print(f"    {k}: {v}")

    async def cmd_harmonic(self, args: str):
        """Show harmonic miss stats for current model (if available)."""
        cm = _get_ContextWindowManager()
        if not cm:
            self.console.print(format_warning("Harmonic tracker not available in REPL"))
            return

        stats = cm.get_harmonic_miss_stats(self.session.model)
        if not stats or stats.get('total_errors', 0) == 0:
            self.console.print(format_info("No harmonic misses recorded"))
            return

        self.console.print(format_section_header(f"Harmonic Miss Stats - {self.session.model}"))
        self.console.print(format_info(f"Total errors: {stats.get('total_errors')}"))
        self.console.print(format_info(f"Avg context pressure: {stats.get('avg_context_pressure'):.1%}"))
        for k, v in stats.get('error_types', {}).items():
            self.console.print(f"  {k}: {v}")

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

        self.console.print(format_error(f"Unknown command: {cmd}"))
        self.console.print(format_warning("Type /help for available commands"))
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
            self.console.print(format_error(f"Error: {format_env_var(env_var)} not set"))
            self.console.print(format_warning(f"Set it with: export {format_env_var(env_var)}=your_key_here"))
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

            # Show thinking indicator - using simple text instead of spinner
            self.console.print(f"{Color.MAGENTA}{Symbol.RUNNING} Agent thinking...{Color.RESET}", end="\r")

            try:
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
                    try:
                        from google import genai
                    except ImportError:
                        raise ImportError(
                            "google-genai is required for Gemini provider. "
                            "Install with: pip install google-genai"
                        )
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

                # Clear thinking indicator
                print("\r" + " " * 50 + "\r", end="")

                # Add assistant message
                self.session.add_message("assistant", response_text)

                # Display response with simple formatting
                self.console.print("")
                self.console.print(f"{Color.CYAN}{Color.BOLD}AGENT:{Color.RESET}")
                self.console.print(response_text)
                self.console.print("")

            except Exception as e:
                # Clear thinking indicator on error
                print("\r" + " " * 50 + "\r", end="")
                self.console.print(format_error(f"Error: {e}"))
                if "api" in str(e).lower() or "key" in str(e).lower() or "auth" in str(e).lower():
                    self._check_api_key()  # Show helpful message
                # Track harmonic miss for local REPL sessions
                try:
                    _track_harmonic_miss(self.session.model, error_type="unexpected_error", context_tokens=self.session.total_tokens)
                except Exception:
                    pass
                return  # Exit chat function on error

        except Exception as e:
            # Handle any errors in the outer try block
            self.console.print(format_error(f"Error in chat: {e}"))
            return

    async def run(self):
        """Run the REPL with ANSI styling."""
        # Welcome header with symbolic elements
        self.console.print(create_header_line("ii-agent REPL", "Interactive Agent", Color.CYAN))
        self.console.print("")
        self.console.print(create_status_line("Workspace", format_workspace(self.workspace), Color.BLUE))
        # Show model + context usage
        ctx_status = self.session.get_context_status()
        usage_bar = ctx_status.get('context_usage_bar', '')
        model_status_line = create_status_line("Model", format_model_status(self.session.provider, self.session.model, True), Color.GREEN)
        self.console.print(model_status_line)
        if self.session.is_approaching_cliff():
            self.console.print(format_warning(f"Context: {ctx_status.get('total_tokens')}/{ctx_status.get('context_window')} {usage_bar}"))
        else:
            self.console.print(format_info(f"Context: {ctx_status.get('total_tokens')}/{ctx_status.get('context_window')} {usage_bar}"))
        self.console.print("")
        self.console.print(format_info("Type /help for commands, /exit to quit"))
        self.console.print("")

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
