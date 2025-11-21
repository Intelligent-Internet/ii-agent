"""Smoke tests for REPL functionality - verify basic operations work."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

from ii_agent.cli.repl import AgentREPL, LocalSession, ModelCompleter
from unittest.mock import AsyncMock


class TestLocalSession:
    """Test LocalSession functionality."""

    def test_session_initialization(self, tmp_path):
        """Test session initializes with correct defaults."""
        session = LocalSession(str(tmp_path))

        assert session.workspace == tmp_path.resolve()
        assert session.history == []
        assert session.context_files == []
        assert session.model == "qwen/qwen3-coder-480b-a35b-instruct"
        assert session.provider == "nvidia"

    def test_add_message(self):
        """Test adding messages to history."""
        session = LocalSession(".")

        session.add_message("user", "test message")

        assert len(session.history) == 1
        assert session.history[0]["role"] == "user"
        assert session.history[0]["content"] == "test message"
        assert "timestamp" in session.history[0]

    def test_add_file_existing(self, tmp_path):
        """Test adding existing file to context."""
        session = LocalSession(str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        session.add_file(str(test_file))

        assert len(session.context_files) == 1
        assert session.context_files[0] == test_file.resolve()

    def test_add_file_nonexistent(self):
        """Test adding nonexistent file raises error."""
        session = LocalSession(".")

        with pytest.raises(FileNotFoundError):
            session.add_file("/nonexistent/file.txt")

    def test_add_duplicate_file(self, tmp_path):
        """Test adding same file twice doesn't duplicate."""
        session = LocalSession(str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        session.add_file(str(test_file))
        session.add_file(str(test_file))

        assert len(session.context_files) == 1

    def test_remove_file(self, tmp_path):
        """Test removing file from context."""
        session = LocalSession(str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        session.add_file(str(test_file))
        session.remove_file(str(test_file))

        assert len(session.context_files) == 0

    def test_clear_files(self, tmp_path):
        """Test clearing all context files."""
        session = LocalSession(str(tmp_path))
        for i in range(3):
            f = tmp_path / f"test{i}.txt"
            f.write_text(f"test{i}")
            session.add_file(str(f))

        session.clear_files()

        assert len(session.context_files) == 0

    def test_get_context(self, tmp_path):
        """Test getting context from files."""
        session = LocalSession(str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        session.add_file(str(test_file))
        context = session.get_context()

        assert "test content" in context
        assert str(test_file) in context

    def test_get_context_status(self):
        """Test get_context_status returns expected structure and values."""
        session = LocalSession(".")
        session.add_message("user", "hello world")
        status = session.get_context_status()

        assert "total_tokens" in status
        assert "context_window" in status
        assert "checkpoint_threshold" in status
        assert "performance_cliffs" in status

    @pytest.mark.asyncio
    async def test_checkpoint_and_tile_generation_integration(self, tmp_path, monkeypatch):
        """Test that LocalSession schedules checkpoint and tile generation when threshold hit."""
        # Arrange: small context window to trigger quickly
        from ii_agent.llm.model_constants import CONTEXT_WINDOWS

        # Create a fake ContextWindowManager with async stubs
        class FakeCM:
            SUMMARIZATION_THRESHOLD = 0.95
            TILE_GENERATION_THRESHOLD = 0.33

            @classmethod
            def get_checkpoint_threshold_for_model(cls, model_id: str):
                return 0.2  # 20% threshold

            @classmethod
            def get_checkpoint_system(cls):
                class FakeCheckpoint:
                    async def create_checkpoint(self, message_lists, microkernel=None):
                        return "fake_slab"
                return FakeCheckpoint()

            @classmethod
            def get_tile_generator(cls):
                class FakeTileGen:
                    async def dump_and_generate_tiles(self, message_lists, context_window):
                        return {"tiles_generated": [1, 2], "retained_breadcrumbs": []}
                return FakeTileGen()

            @classmethod
            def get_cliff_benchmark(cls):
                class FakeBench:
                    def record_usage(self, model_id):
                        pass

                    def should_run_tests(self, model_id):
                        return False

                    async def run_background_tests(self, model_id, llm_call_func):
                        return None
                return FakeBench()

        # Patch _get_ContextWindowManager used by LocalSession __init__
        monkeypatch.setattr('ii_agent.cli.repl._get_ContextWindowManager', lambda: FakeCM)

        session = LocalSession(str(tmp_path))

        # Make context window tiny to trigger tile generation too
        CONTEXT_WINDOWS[session.model] = 100

        # Spy on checkpoint & tile by patching their methods to AsyncMock
        fake_cp = FakeCM.get_checkpoint_system()
        fake_cp.create_checkpoint = AsyncMock(return_value="fake_slab")
        monkeypatch.setattr(FakeCM, 'get_checkpoint_system', classmethod(lambda cls: fake_cp))

        fake_tg = FakeCM.get_tile_generator()
        fake_tg.dump_and_generate_tiles = AsyncMock(return_value={"tiles_generated": [1], "retained_breadcrumbs": []})
        monkeypatch.setattr(FakeCM, 'get_tile_generator', classmethod(lambda cls: fake_tg))

        # Now add a message with tokens exceeding 20 tokens threshold
        session.add_message("user", "X" * 300)  # estimate tokens ~100

        # give background tasks a moment to run
        await asyncio.sleep(0.1)

        assert fake_cp.create_checkpoint.called
        assert fake_tg.dump_and_generate_tiles.called

    def test_local_session_uses_context_manager_reduction(self, tmp_path, monkeypatch):
        """Verify LocalSession uses ContextWindowManager.reduce_history_tokens when available."""
        from ii_agent.cli.repl import LocalSession
        from ii_agent.server.chat.context_manager import ContextWindowManager

        class FakeCM:
            @classmethod
            def reduce_history_tokens(cls, history, model_id=None):
                # Return only last entry
                return history[-1:]

        monkeypatch.setattr('ii_agent.cli.repl._get_ContextWindowManager', lambda: FakeCM)

        session = LocalSession(str(tmp_path))
        session.model = 'gpt-4o'
        # Add several messages to exceed local threshold
        for _ in range(5):
            session.add_message('user', 'x' * 500, tokens=1000)

        # Since we replaced the reduction function to return only last message, after add_message the history should be trimmed
        assert len(session.history) <= 1

    @pytest.mark.asyncio
    async def test_local_summarization_placeholder(self, tmp_path, monkeypatch):
        """Test local summarization placeholder triggers when threshold reached."""
        from ii_agent.llm.model_constants import CONTEXT_WINDOWS

        class FakeCM:
            SUMMARIZATION_THRESHOLD = 0.2
            TILE_GENERATION_THRESHOLD = 0.9

            @classmethod
            def get_checkpoint_threshold_for_model(cls, model_id: str):
                return 0.5

            @classmethod
            def get_checkpoint_system(cls):
                class FakeCheckpoint:
                    async def create_checkpoint(self, message_lists, microkernel=None):
                        return "fake_slab"
                return FakeCheckpoint()

            @classmethod
            def get_tile_generator(cls):
                class FakeTileGen:
                    async def dump_and_generate_tiles(self, message_lists, context_window):
                        return None
                return FakeTileGen()

            @classmethod
            def get_cliff_benchmark(cls):
                class FakeBench:
                    def record_usage(self, model_id):
                        pass

                    def should_run_tests(self, model_id):
                        return False

                    async def run_background_tests(self, model_id, llm_call_func):
                        return None
                return FakeBench()

        monkeypatch.setattr('ii_agent.cli.repl._get_ContextWindowManager', lambda: FakeCM)
        session = LocalSession(str(tmp_path))
        # Make context window tiny
        CONTEXT_WINDOWS[session.model] = 200

        # Add a big message to exceed SUMMARIZATION_THRESHOLD
        session.add_message("user", "X" * 400)
        await asyncio.sleep(0.1)

        # A summary message should be at the beginning of history
        assert session.history
        assert session.history[0]["role"] == "assistant"
        assert "Local summary" in session.history[0]["content"]


class TestModelCompleter:
    """Test model completion functionality."""

    def test_completer_initialization(self):
        """Test completer initializes with providers."""
        providers = {"anthropic": True, "openai": False}
        completer = ModelCompleter(providers)

        assert completer.available_providers == providers
        assert "anthropic" in completer.model_suggestions
        assert "nvidia" in completer.model_suggestions

    def test_provider_completion(self):
        """Test provider name completion."""
        from prompt_toolkit.document import Document

        providers = {"anthropic": True, "openai": True}
        completer = ModelCompleter(providers)

        # Test partial provider match
        doc = Document("/model ant", cursor_position=10)
        completions = list(completer.get_completions(doc, None))

        # Should suggest anthropic
        completion_texts = [c.text for c in completions]
        assert "anthropic" in completion_texts

    def test_model_completion_for_provider(self):
        """Test model name completion for a provider."""
        from prompt_toolkit.document import Document

        providers = {"anthropic": True}
        completer = ModelCompleter(providers)

        # Test model completion after provider
        doc = Document("/model anthropic claude", cursor_position=23)
        completions = list(completer.get_completions(doc, None))

        # Should suggest claude models
        completion_texts = [c.text for c in completions]
        assert any("claude" in c for c in completion_texts)


class TestAgentREPL:
    """Test AgentREPL initialization and basic operations."""

    def test_repl_initialization(self, tmp_path):
        """Test REPL initializes without errors."""
        repl = AgentREPL(workspace=str(tmp_path))

        assert repl.workspace == str(tmp_path)
        assert repl.session is not None
        assert repl.console is not None
        assert repl.running is True

    def test_provider_detection(self):
        """Test REPL detects available providers."""
        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "test-key",
            "NVIDIA_API_KEY": "test-key"
        }):
            repl = AgentREPL()

            assert repl.available_providers["anthropic"] is True
            assert repl.available_providers["nvidia"] is True
            assert repl.available_providers["openai"] is False

    @pytest.mark.asyncio
    async def test_command_help(self, tmp_path):
        """Test /help command doesn't crash."""
        repl = AgentREPL(workspace=str(tmp_path))

        # Should not raise
        await repl.cmd_help("")

    @pytest.mark.asyncio
    async def test_command_model_show_current(self, tmp_path):
        """Test /model shows current model."""
        repl = AgentREPL(workspace=str(tmp_path))

        # Should not raise
        await repl.cmd_model("")

        assert repl.session.model == "qwen/qwen3-coder-480b-a35b-instruct"
        assert repl.session.provider == "nvidia"

    @pytest.mark.asyncio
    async def test_command_model_change(self, tmp_path):
        """Test /model changes model."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test"}):
            repl = AgentREPL(workspace=str(tmp_path))

            await repl.cmd_model("anthropic claude-sonnet-4")

            assert repl.session.provider == "anthropic"
            assert repl.session.model == "claude-sonnet-4"

    @pytest.mark.asyncio
    async def test_command_model_unavailable_provider(self, tmp_path):
        """Test /model with unavailable provider shows error."""
        repl = AgentREPL(workspace=str(tmp_path))

        # Should not raise, but should not change model
        await repl.cmd_model("openai gpt-4")

        # Model should not change if provider unavailable
        assert repl.session.provider == "nvidia"

    @pytest.mark.asyncio
    async def test_command_add_file(self, tmp_path):
        """Test /add command adds file to context."""
        repl = AgentREPL(workspace=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        await repl.cmd_add(str(test_file))

        assert len(repl.session.context_files) == 1

    @pytest.mark.asyncio
    async def test_command_drop_file(self, tmp_path):
        """Test /drop command removes file from context."""
        repl = AgentREPL(workspace=str(tmp_path))
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        await repl.cmd_add(str(test_file))
        await repl.cmd_drop(str(test_file))

        assert len(repl.session.context_files) == 0

    @pytest.mark.asyncio
    async def test_command_files_empty(self, tmp_path):
        """Test /files shows message when no files."""
        repl = AgentREPL(workspace=str(tmp_path))

        # Should not raise
        await repl.cmd_files("")

    @pytest.mark.asyncio
    async def test_command_ls(self, tmp_path):
        """Test /ls lists workspace files."""
        repl = AgentREPL(workspace=str(tmp_path))
        (tmp_path / "test.txt").write_text("test")

        # Should not raise
        await repl.cmd_ls("")

    @pytest.mark.asyncio
    async def test_command_clear(self, tmp_path):
        """Test /clear clears history."""
        repl = AgentREPL(workspace=str(tmp_path))
        repl.session.add_message("user", "test")

        await repl.cmd_clear("")

        assert len(repl.session.history) == 0

    @pytest.mark.asyncio
    async def test_command_reset(self, tmp_path):
        """Test /reset clears history and files."""
        repl = AgentREPL(workspace=str(tmp_path))
        repl.session.add_message("user", "test")
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")
        repl.session.add_file(str(test_file))

        await repl.cmd_reset("")

        assert len(repl.session.history) == 0
        assert len(repl.session.context_files) == 0

    @pytest.mark.asyncio
    async def test_command_context(self, tmp_path):
        """Test /context command prints context info without error."""
        repl = AgentREPL(workspace=str(tmp_path))
        repl.session.add_message("user", "test for context")

        # Should not raise
        await repl.cmd_context("")

    @pytest.mark.asyncio
    async def test_command_harmonic_no_data(self, tmp_path):
        """Test /harmonic command when no context manager is present."""
        repl = AgentREPL(workspace=str(tmp_path))

        # No error - no ContextWindowManager
        await repl.cmd_harmonic("")

    @pytest.mark.asyncio
    async def test_command_harmonic_with_data(self, tmp_path, monkeypatch):
        """Test /harmonic shows stats from a fake context manager."""
        class FakeCM:
            @classmethod
            def get_harmonic_miss_stats(cls, model_id: str):
                return {"model_id": model_id, "total_errors": 3, "avg_context_pressure": 0.5, "error_types": {"hallucination": 1, "edit_slip": 2}}

        monkeypatch.setattr('ii_agent.cli.repl._get_ContextWindowManager', lambda: FakeCM)
        repl = AgentREPL(workspace=str(tmp_path))

        await repl.cmd_harmonic("")

    @pytest.mark.asyncio
    async def test_command_exit(self, tmp_path):
        """Test /exit sets running to False."""
        repl = AgentREPL(workspace=str(tmp_path))

        await repl.cmd_exit("")

        assert repl.running is False

    @pytest.mark.asyncio
    async def test_process_command_valid(self, tmp_path):
        """Test processing valid command."""
        repl = AgentREPL(workspace=str(tmp_path))

        result = await repl.process_command("/help")

        assert result is True

    @pytest.mark.asyncio
    async def test_process_command_invalid(self, tmp_path):
        """Test processing invalid command."""
        repl = AgentREPL(workspace=str(tmp_path))

        result = await repl.process_command("/invalid")

        assert result is True  # Returns True even for invalid commands

    @pytest.mark.asyncio
    async def test_process_command_not_command(self, tmp_path):
        """Test processing non-command text."""
        repl = AgentREPL(workspace=str(tmp_path))

        result = await repl.process_command("regular text")

        assert result is False

    def test_api_key_check_missing(self, tmp_path):
        """Test API key check fails when key missing."""
        with patch.dict(os.environ, {}, clear=True):
            repl = AgentREPL(workspace=str(tmp_path))
            repl.session.provider = "anthropic"

            result = repl._check_api_key()

            assert result is False

    def test_api_key_check_present(self, tmp_path):
        """Test API key check succeeds when key present."""
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "test"}):
            repl = AgentREPL(workspace=str(tmp_path))

            result = repl._check_api_key()

            assert result is True

        def test_context_manager_model_thresholds(self):
            """Test ContextWindowManager model-specific thresholds and cliffs."""
            from ii_agent.server.chat.context_manager import calculate_model_specific_threshold, get_performance_cliff_threshold

            # Known models should return cliffs and thresholds within 0.10-0.90
            for model_id in ["gpt-4", "claude-3-5-sonnet", "gemini-1.5-pro", "meta/llama-3.1-405b-instruct"]:
                thr = calculate_model_specific_threshold(model_id)
                assert 0.1 <= thr <= 0.9
                cliffs = get_performance_cliff_threshold(model_id)
                assert "early_degradation" in cliffs


class TestCLIAutoSwitch:
    """Test CLI auto-switch behavior."""

    @patch("ii_agent.cli.main.SERVER_AVAILABLE", False)
    @patch("ii_agent.cli.main.asyncio.run")
    def test_auto_switch_to_repl_when_server_unavailable(self, mock_run):
        """Test CLI auto-switches to REPL when server deps missing."""
        from ii_agent.cli.main import main

        with patch("sys.argv", ["ii-agent"]):
            main()

        # Should have called REPL
        mock_run.assert_called_once()

    @patch("ii_agent.cli.main.SERVER_AVAILABLE", True)
    @patch("ii_agent.cli.main.uvicorn.run")
    def test_server_mode_when_available(self, mock_uvicorn):
        """Test CLI runs server when deps available."""
        from ii_agent.cli.main import main

        with patch("sys.argv", ["ii-agent"]):
            main()

        # Should have called uvicorn
        mock_uvicorn.assert_called_once()

    @patch("ii_agent.cli.main.SERVER_AVAILABLE", True)
    @patch("ii_agent.cli.main.asyncio.run")
    def test_explicit_repl_flag_overrides(self, mock_run):
        """Test --repl flag works even when server available."""
        from ii_agent.cli.main import main

        with patch("sys.argv", ["ii-agent", "--repl"]):
            main()

        # Should have called REPL, not server
        mock_run.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
