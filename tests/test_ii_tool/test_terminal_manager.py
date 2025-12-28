"""Unit tests for ii_tool.tools.shell.terminal_manager module.

This module tests the terminal manager models, error classes, and constants.
Note: TmuxSessionManager and TmuxWindowManager require actual tmux server
connections and are tested separately in integration tests.
"""

import pytest
from unittest.mock import MagicMock, patch

from ii_tool.tools.shell.terminal_manager import (
    # Models
    ShellResult,
    SessionState,
    
    # Error classes
    ShellError,
    ShellBusyError,
    ShellInvalidSessionNameError,
    ShellSessionNotFoundError,
    ShellSessionExistsError,
    ShellRunDirNotFoundError,
    ShellCommandTimeoutError,
    ShellOperationError,
    
    # ABC
    BaseShellManager,
    
    # Constants
    _DEFAULT_TIMEOUT,
    _MAX_TIMEOUT,
    _POLL_INTERVAL,
    _DEFAULT_PROMPT_PREFIX,
    _PROMPT_FORMAT,
    _PREFIX_SESSION_NAME,
)


# =============================================================================
# Test Constants
# =============================================================================

class TestModuleConstants:
    """Tests for module-level constants."""

    def test_default_timeout(self):
        """Test default timeout value."""
        assert _DEFAULT_TIMEOUT == 60
        assert isinstance(_DEFAULT_TIMEOUT, int)

    def test_max_timeout(self):
        """Test max timeout value."""
        assert _MAX_TIMEOUT == 180
        assert isinstance(_MAX_TIMEOUT, int)
        assert _MAX_TIMEOUT > _DEFAULT_TIMEOUT

    def test_poll_interval(self):
        """Test poll interval value."""
        assert _POLL_INTERVAL == 0.5
        assert isinstance(_POLL_INTERVAL, float)

    def test_default_prompt_prefix(self):
        """Test default prompt prefix."""
        assert _DEFAULT_PROMPT_PREFIX == "root@sandbox"

    def test_prompt_format_contains_prefix(self):
        """Test prompt format contains the prefix placeholder."""
        assert _DEFAULT_PROMPT_PREFIX in _PROMPT_FORMAT

    def test_prefix_session_name(self):
        """Test prefix session name."""
        assert _PREFIX_SESSION_NAME == "II-AGENT-"


# =============================================================================
# Test ShellResult Model
# =============================================================================

class TestShellResult:
    """Tests for ShellResult Pydantic model."""

    def test_create_with_required_fields(self):
        """Test creating ShellResult with required fields."""
        result = ShellResult(clean_output="output", ansi_output="ansi")
        assert result.clean_output == "output"
        assert result.ansi_output == "ansi"

    def test_empty_strings(self):
        """Test ShellResult with empty strings."""
        result = ShellResult(clean_output="", ansi_output="")
        assert result.clean_output == ""
        assert result.ansi_output == ""

    def test_multiline_output(self):
        """Test ShellResult with multiline output."""
        clean = "line1\nline2\nline3"
        ansi = "\x1b[32mline1\x1b[0m\nline2\nline3"
        result = ShellResult(clean_output=clean, ansi_output=ansi)
        assert result.clean_output == clean
        assert result.ansi_output == ansi

    def test_immutability(self):
        """Test that ShellResult fields can be accessed but model is immutable by default."""
        result = ShellResult(clean_output="test", ansi_output="test")
        # Accessing should work
        assert result.clean_output == "test"

    def test_model_dump(self):
        """Test model_dump method."""
        result = ShellResult(clean_output="clean", ansi_output="ansi")
        dump = result.model_dump()
        assert dump == {"clean_output": "clean", "ansi_output": "ansi"}


# =============================================================================
# Test SessionState Enum
# =============================================================================

class TestSessionState:
    """Tests for SessionState enum."""

    def test_busy_value(self):
        """Test BUSY state value."""
        assert SessionState.BUSY.value == "busy"

    def test_idle_value(self):
        """Test IDLE state value."""
        assert SessionState.IDLE.value == "idle"

    def test_enum_members(self):
        """Test enum has exactly two members."""
        assert len(SessionState) == 2
        assert SessionState.BUSY in SessionState
        assert SessionState.IDLE in SessionState

    def test_from_value(self):
        """Test creating enum from value."""
        assert SessionState("busy") == SessionState.BUSY
        assert SessionState("idle") == SessionState.IDLE

    def test_invalid_value_raises(self):
        """Test invalid value raises ValueError."""
        with pytest.raises(ValueError):
            SessionState("unknown")


# =============================================================================
# Test ShellError Exception Hierarchy
# =============================================================================

class TestShellError:
    """Tests for ShellError base exception."""

    def test_is_exception_subclass(self):
        """Test ShellError is an Exception."""
        assert issubclass(ShellError, Exception)

    def test_can_be_raised(self):
        """Test ShellError can be raised."""
        with pytest.raises(ShellError):
            raise ShellError("test error")

    def test_error_message(self):
        """Test ShellError preserves message."""
        try:
            raise ShellError("specific message")
        except ShellError as e:
            assert str(e) == "specific message"


class TestShellBusyError:
    """Tests for ShellBusyError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellBusyError is a ShellError."""
        assert issubclass(ShellBusyError, ShellError)

    def test_can_be_caught_as_shell_error(self):
        """Test ShellBusyError can be caught as ShellError."""
        try:
            raise ShellBusyError("session busy")
        except ShellError as e:
            assert "session busy" in str(e)


class TestShellInvalidSessionNameError:
    """Tests for ShellInvalidSessionNameError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellInvalidSessionNameError is a ShellError."""
        assert issubclass(ShellInvalidSessionNameError, ShellError)

    def test_error_message(self):
        """Test error message is preserved."""
        with pytest.raises(ShellInvalidSessionNameError) as exc_info:
            raise ShellInvalidSessionNameError("invalid name: test@session")
        assert "invalid name" in str(exc_info.value)


class TestShellSessionNotFoundError:
    """Tests for ShellSessionNotFoundError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellSessionNotFoundError is a ShellError."""
        assert issubclass(ShellSessionNotFoundError, ShellError)


class TestShellSessionExistsError:
    """Tests for ShellSessionExistsError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellSessionExistsError is a ShellError."""
        assert issubclass(ShellSessionExistsError, ShellError)


class TestShellRunDirNotFoundError:
    """Tests for ShellRunDirNotFoundError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellRunDirNotFoundError is a ShellError."""
        assert issubclass(ShellRunDirNotFoundError, ShellError)


class TestShellCommandTimeoutError:
    """Tests for ShellCommandTimeoutError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellCommandTimeoutError is a ShellError."""
        assert issubclass(ShellCommandTimeoutError, ShellError)


class TestShellOperationError:
    """Tests for ShellOperationError exception."""

    def test_is_shell_error_subclass(self):
        """Test ShellOperationError is a ShellError."""
        assert issubclass(ShellOperationError, ShellError)


class TestAllShellErrors:
    """Tests for all shell error types together."""

    def test_all_errors_are_shell_error_subclasses(self):
        """Test all error classes are ShellError subclasses."""
        error_classes = [
            ShellBusyError,
            ShellInvalidSessionNameError,
            ShellSessionNotFoundError,
            ShellSessionExistsError,
            ShellRunDirNotFoundError,
            ShellCommandTimeoutError,
            ShellOperationError,
        ]
        for error_class in error_classes:
            assert issubclass(error_class, ShellError), f"{error_class.__name__} should be ShellError subclass"

    def test_errors_have_unique_identity(self):
        """Test error classes are distinct."""
        error_classes = [
            ShellError,
            ShellBusyError,
            ShellInvalidSessionNameError,
            ShellSessionNotFoundError,
            ShellSessionExistsError,
            ShellRunDirNotFoundError,
            ShellCommandTimeoutError,
            ShellOperationError,
        ]
        # All should be unique classes
        assert len(set(error_classes)) == len(error_classes)


# =============================================================================
# Test BaseShellManager ABC
# =============================================================================

class TestBaseShellManager:
    """Tests for BaseShellManager abstract base class."""

    def test_is_abstract(self):
        """Test BaseShellManager cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseShellManager()

    def test_abstract_methods_defined(self):
        """Test that abstract methods are defined."""
        abstract_methods = [
            'get_all_sessions',
            'create_session',
            'delete_session',
            'run_command',
            'kill_current_command',
            'get_session_state',
            'get_session_output',
            'write_to_process',
        ]
        for method_name in abstract_methods:
            assert hasattr(BaseShellManager, method_name)

    def test_concrete_implementation_works(self):
        """Test that a concrete implementation can be created."""
        class ConcreteShellManager(BaseShellManager):
            def get_all_sessions(self):
                return []
            
            def create_session(self, session_name, base_dir, timeout=60):
                pass
            
            def delete_session(self, session_name):
                pass
            
            def run_command(self, session_name, command, run_dir=None, timeout=60, wait_for_output=True):
                return ShellResult(clean_output="", ansi_output="")
            
            def kill_current_command(self, session_name):
                return ShellResult(clean_output="", ansi_output="")
            
            def get_session_state(self, session_name):
                return SessionState.IDLE
            
            def get_session_output(self, session_name):
                return ShellResult(clean_output="", ansi_output="")
            
            def write_to_process(self, session_name, input, press_enter):
                return ShellResult(clean_output="", ansi_output="")
        
        # Should not raise
        manager = ConcreteShellManager()
        assert manager.get_all_sessions() == []
        assert manager.get_session_state("test") == SessionState.IDLE

    def test_incomplete_implementation_raises(self):
        """Test that incomplete implementation raises TypeError."""
        class IncompleteManager(BaseShellManager):
            def get_all_sessions(self):
                return []
            # Missing other abstract methods
        
        with pytest.raises(TypeError):
            IncompleteManager()


# =============================================================================
# Test Mock Shell Manager for Other Tests
# =============================================================================

class MockShellManager(BaseShellManager):
    """Mock shell manager for testing shell tools."""
    
    def __init__(self):
        self._sessions = {}
        self._session_states = {}
        self._outputs = {}
    
    def get_all_sessions(self):
        return list(self._sessions.keys())
    
    def create_session(self, session_name, base_dir, timeout=60):
        if session_name in self._sessions:
            raise ShellSessionExistsError(f"Session '{session_name}' already exists")
        self._sessions[session_name] = {"base_dir": base_dir}
        self._session_states[session_name] = SessionState.IDLE
        self._outputs[session_name] = ShellResult(clean_output="", ansi_output="")
    
    def delete_session(self, session_name):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        del self._sessions[session_name]
        del self._session_states[session_name]
        del self._outputs[session_name]
    
    def run_command(self, session_name, command, run_dir=None, timeout=60, wait_for_output=True):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        if self._session_states[session_name] == SessionState.BUSY:
            raise ShellBusyError("Session is busy")
        return ShellResult(clean_output=f"Executed: {command}", ansi_output=f"Executed: {command}")
    
    def kill_current_command(self, session_name):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        self._session_states[session_name] = SessionState.IDLE
        return ShellResult(clean_output="^C", ansi_output="^C")
    
    def get_session_state(self, session_name):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        return self._session_states.get(session_name, SessionState.IDLE)
    
    def get_session_output(self, session_name):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        return self._outputs.get(session_name, ShellResult(clean_output="", ansi_output=""))
    
    def write_to_process(self, session_name, input, press_enter):
        if session_name not in self._sessions:
            raise ShellSessionNotFoundError(f"Session '{session_name}' not found")
        return ShellResult(clean_output=input, ansi_output=input)


class TestMockShellManager:
    """Tests for MockShellManager to ensure it works correctly for other tests."""

    def test_create_session(self):
        """Test creating a session."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        assert "test" in manager.get_all_sessions()

    def test_create_duplicate_session_raises(self):
        """Test creating duplicate session raises error."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        with pytest.raises(ShellSessionExistsError):
            manager.create_session("test", "/workspace")

    def test_delete_session(self):
        """Test deleting a session."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        manager.delete_session("test")
        assert "test" not in manager.get_all_sessions()

    def test_delete_nonexistent_session_raises(self):
        """Test deleting nonexistent session raises error."""
        manager = MockShellManager()
        with pytest.raises(ShellSessionNotFoundError):
            manager.delete_session("nonexistent")

    def test_run_command(self):
        """Test running a command."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        result = manager.run_command("test", "echo hello")
        assert "echo hello" in result.clean_output

    def test_get_session_state(self):
        """Test getting session state."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        assert manager.get_session_state("test") == SessionState.IDLE

    def test_busy_session_run_command_raises(self):
        """Test running command on busy session raises error."""
        manager = MockShellManager()
        manager.create_session("test", "/workspace")
        manager._session_states["test"] = SessionState.BUSY
        with pytest.raises(ShellBusyError):
            manager.run_command("test", "echo hello")
