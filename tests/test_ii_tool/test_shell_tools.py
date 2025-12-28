"""Unit tests for ii_tool.tools.shell tool modules.

Tests for ShellInit, ShellList, ShellView, ShellRunCommand, 
ShellStopCommand, and ShellWriteToProcessTool.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

from ii_tool.tools.shell.terminal_manager import (
    BaseShellManager,
    ShellResult,
    SessionState,
    ShellBusyError,
    ShellInvalidSessionNameError,
    ShellSessionNotFoundError,
    ShellSessionExistsError,
    ShellCommandTimeoutError,
)
from ii_tool.tools.base import ToolResult, ToolConfirmationDetails
from ii_tool.core.workspace import WorkspaceManager, FileSystemValidationError

# Import the shell tools
from ii_tool.tools.shell.shell_init import (
    ShellInit,
    NAME as INIT_NAME,
    DISPLAY_NAME as INIT_DISPLAY_NAME,
    DESCRIPTION as INIT_DESCRIPTION,
    INPUT_SCHEMA as INIT_INPUT_SCHEMA,
    MAX_SHELL_SESSIONS,
)
from ii_tool.tools.shell.shell_list import (
    ShellList,
    NAME as LIST_NAME,
    DISPLAY_NAME as LIST_DISPLAY_NAME,
    DESCRIPTION as LIST_DESCRIPTION,
    INPUT_SCHEMA as LIST_INPUT_SCHEMA,
)
from ii_tool.tools.shell.shell_view import (
    ShellView,
    NAME as VIEW_NAME,
    DISPLAY_NAME as VIEW_DISPLAY_NAME,
    DESCRIPTION as VIEW_DESCRIPTION,
    INPUT_SCHEMA as VIEW_INPUT_SCHEMA,
)
from ii_tool.tools.shell.shell_run_command import (
    ShellRunCommand,
    NAME as RUN_NAME,
    DISPLAY_NAME as RUN_DISPLAY_NAME,
    DESCRIPTION as RUN_DESCRIPTION,
    INPUT_SCHEMA as RUN_INPUT_SCHEMA,
    DEFAULT_TIMEOUT,
    MAX_TIMEOUT,
)
from ii_tool.tools.shell.shell_stop_command import (
    ShellStopCommand,
    NAME as STOP_NAME,
    DISPLAY_NAME as STOP_DISPLAY_NAME,
    DESCRIPTION as STOP_DESCRIPTION,
    INPUT_SCHEMA as STOP_INPUT_SCHEMA,
)
from ii_tool.tools.shell.shell_write_to_process import (
    ShellWriteToProcessTool,
    NAME as WRITE_NAME,
    DISPLAY_NAME as WRITE_DISPLAY_NAME,
    DESCRIPTION as WRITE_DESCRIPTION,
    INPUT_SCHEMA as WRITE_INPUT_SCHEMA,
)


# =============================================================================
# Mock Shell Manager Fixture
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
        if not session_name or not session_name.replace('_', '').replace('-', '').isalnum():
            raise ShellInvalidSessionNameError("Invalid session name")
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
        return ShellResult(clean_output=f"$ {command}\noutput", ansi_output=f"$ {command}\n\x1b[32moutput\x1b[0m")
    
    def kill_current_command(self, session_name, timeout=60):
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
        return ShellResult(clean_output=f"wrote: {input}", ansi_output=f"wrote: {input}")


@pytest.fixture
def mock_shell_manager():
    """Create a fresh mock shell manager."""
    return MockShellManager()


@pytest.fixture
def mock_workspace_manager():
    """Create a mock workspace manager."""
    wm = MagicMock(spec=WorkspaceManager)
    wm.get_workspace_path.return_value = Path("/workspace")
    return wm


# =============================================================================
# Test ShellInit
# =============================================================================

class TestShellInitConstants:
    """Tests for ShellInit module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert INIT_NAME == "BashInit"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert INIT_DISPLAY_NAME == "Initialize bash session"

    def test_description_not_empty(self):
        """Test DESCRIPTION is not empty."""
        assert INIT_DESCRIPTION
        assert len(INIT_DESCRIPTION) > 10

    def test_input_schema_structure(self):
        """Test INPUT_SCHEMA structure."""
        assert INIT_INPUT_SCHEMA["type"] == "object"
        assert "properties" in INIT_INPUT_SCHEMA
        assert "session_name" in INIT_INPUT_SCHEMA["properties"]

    def test_max_shell_sessions(self):
        """Test MAX_SHELL_SESSIONS constant."""
        assert MAX_SHELL_SESSIONS == 10


class TestShellInitAttributes:
    """Tests for ShellInit class attributes."""

    def test_class_name(self):
        """Test class name attribute."""
        assert ShellInit.name == INIT_NAME

    def test_class_read_only(self):
        """Test read_only is False (creates sessions)."""
        assert ShellInit.read_only is False


class TestShellInitInit:
    """Tests for ShellInit initialization."""

    def test_init_stores_managers(self, mock_shell_manager, mock_workspace_manager):
        """Test initialization stores both managers."""
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        assert tool.shell_manager is mock_shell_manager
        assert tool.workspace_manager is mock_workspace_manager


class TestShellInitExecute:
    """Tests for ShellInit execute method."""

    @pytest.mark.asyncio
    async def test_create_new_session(self, mock_shell_manager, mock_workspace_manager):
        """Test creating a new session."""
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test_session",
            "start_directory": "/workspace/project"
        })
        
        assert result.is_error is False
        assert "test_session" in result.llm_content
        assert "initialized successfully" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_create_session_default_directory(self, mock_shell_manager, mock_workspace_manager):
        """Test creating session with default directory."""
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "default_dir_session"
        })
        
        assert result.is_error is False
        mock_workspace_manager.get_workspace_path.assert_called()

    @pytest.mark.asyncio
    async def test_session_already_exists(self, mock_shell_manager, mock_workspace_manager):
        """Test error when session already exists."""
        mock_shell_manager.create_session("existing", "/workspace")
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "existing",
            "start_directory": "/workspace"
        })
        
        assert result.is_error is True
        assert "already exists" in result.llm_content

    @pytest.mark.asyncio
    async def test_max_sessions_limit(self, mock_shell_manager, mock_workspace_manager):
        """Test error when max sessions reached."""
        # Create max sessions
        for i in range(MAX_SHELL_SESSIONS):
            mock_shell_manager.create_session(f"session_{i}", "/workspace")
        
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "one_more",
            "start_directory": "/workspace"
        })
        
        assert result.is_error is True
        assert "Maximum" in result.llm_content or "maximum" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_invalid_directory(self, mock_shell_manager, mock_workspace_manager):
        """Test error with invalid directory."""
        mock_workspace_manager.validate_existing_directory_path.side_effect = FileSystemValidationError("Invalid dir")
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "start_directory": "/invalid/path"
        })
        
        assert result.is_error is True
        assert "error" in result.llm_content.lower()


class TestShellInitMCPWrapper:
    """Tests for ShellInit MCP wrapper."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper_calls_correctly(self, mock_shell_manager, mock_workspace_manager):
        """Test MCP wrapper passes correct args."""
        tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="ok"))
        
        await tool.execute_mcp_wrapper(
            session_name="test",
            start_directory="/workspace"
        )
        
        tool._mcp_wrapper.assert_called_once()
        call_args = tool._mcp_wrapper.call_args[1]["tool_input"]
        assert call_args["session_name"] == "test"
        assert call_args["start_directory"] == "/workspace"


# =============================================================================
# Test ShellList
# =============================================================================

class TestShellListConstants:
    """Tests for ShellList module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert LIST_NAME == "BashList"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert LIST_DISPLAY_NAME == "List bash sessions"

    def test_input_schema_no_required(self):
        """Test INPUT_SCHEMA has no required fields."""
        assert LIST_INPUT_SCHEMA["required"] == []


class TestShellListAttributes:
    """Tests for ShellList class attributes."""

    def test_class_read_only(self):
        """Test read_only is True (only lists)."""
        assert ShellList.read_only is True


class TestShellListExecute:
    """Tests for ShellList execute method."""

    @pytest.mark.asyncio
    async def test_list_empty_sessions(self, mock_shell_manager):
        """Test listing when no sessions exist."""
        tool = ShellList(mock_shell_manager)
        
        result = await tool.execute({})
        
        assert result.is_error is False
        assert "[]" in result.llm_content or "Available sessions" in result.llm_content

    @pytest.mark.asyncio
    async def test_list_multiple_sessions(self, mock_shell_manager):
        """Test listing multiple sessions."""
        mock_shell_manager.create_session("session1", "/workspace")
        mock_shell_manager.create_session("session2", "/workspace")
        tool = ShellList(mock_shell_manager)
        
        result = await tool.execute({})
        
        assert result.is_error is False
        assert "session1" in result.llm_content
        assert "session2" in result.llm_content


class TestShellListMCPWrapper:
    """Tests for ShellList MCP wrapper."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper_no_args(self, mock_shell_manager):
        """Test MCP wrapper with no args."""
        tool = ShellList(mock_shell_manager)
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="ok"))
        
        await tool.execute_mcp_wrapper()
        
        tool._mcp_wrapper.assert_called_once_with(tool_input={})


# =============================================================================
# Test ShellView
# =============================================================================

class TestShellViewConstants:
    """Tests for ShellView module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert VIEW_NAME == "BashView"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert VIEW_DISPLAY_NAME == "View bash session output"


class TestShellViewAttributes:
    """Tests for ShellView class attributes."""

    def test_class_read_only(self):
        """Test read_only is True (only views)."""
        assert ShellView.read_only is True


class TestShellViewExecute:
    """Tests for ShellView execute method."""

    @pytest.mark.asyncio
    async def test_view_single_session(self, mock_shell_manager):
        """Test viewing a single session."""
        mock_shell_manager.create_session("test", "/workspace")
        mock_shell_manager._outputs["test"] = ShellResult(
            clean_output="$ echo hello\nhello",
            ansi_output="$ echo hello\n\x1b[32mhello\x1b[0m"
        )
        tool = ShellView(mock_shell_manager)
        
        result = await tool.execute({"session_names": ["test"]})
        
        assert result.is_error is False
        assert "test" in result.llm_content
        assert "hello" in result.llm_content

    @pytest.mark.asyncio
    async def test_view_multiple_sessions(self, mock_shell_manager):
        """Test viewing multiple sessions."""
        mock_shell_manager.create_session("session1", "/workspace")
        mock_shell_manager.create_session("session2", "/workspace")
        tool = ShellView(mock_shell_manager)
        
        result = await tool.execute({"session_names": ["session1", "session2"]})
        
        assert result.is_error is False
        assert "session1" in result.llm_content
        assert "session2" in result.llm_content

    @pytest.mark.asyncio
    async def test_view_nonexistent_session(self, mock_shell_manager):
        """Test viewing nonexistent session."""
        tool = ShellView(mock_shell_manager)
        
        result = await tool.execute({"session_names": ["nonexistent"]})
        
        assert result.is_error is True
        assert "not initialized" in result.llm_content.lower() or "nonexistent" in result.llm_content


# =============================================================================
# Test ShellRunCommand
# =============================================================================

class TestShellRunCommandConstants:
    """Tests for ShellRunCommand module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert RUN_NAME == "Bash"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert RUN_DISPLAY_NAME == "Run bash command"

    def test_default_timeout(self):
        """Test DEFAULT_TIMEOUT constant."""
        assert DEFAULT_TIMEOUT == 60

    def test_max_timeout(self):
        """Test MAX_TIMEOUT constant."""
        assert MAX_TIMEOUT == 180

    def test_input_schema_required_fields(self):
        """Test required fields in INPUT_SCHEMA."""
        assert "session_name" in RUN_INPUT_SCHEMA["required"]
        assert "command" in RUN_INPUT_SCHEMA["required"]
        assert "description" in RUN_INPUT_SCHEMA["required"]


class TestShellRunCommandAttributes:
    """Tests for ShellRunCommand class attributes."""

    def test_class_read_only(self):
        """Test read_only is False (executes commands)."""
        assert ShellRunCommand.read_only is False


class TestShellRunCommandShouldConfirm:
    """Tests for ShellRunCommand should_confirm_execute."""

    def test_returns_confirmation(self, mock_shell_manager, mock_workspace_manager):
        """Test should_confirm_execute returns ToolConfirmationDetails."""
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = tool.should_confirm_execute({
            "command": "rm -rf /",
            "description": "Dangerous command"
        })
        
        assert isinstance(result, ToolConfirmationDetails)
        assert result.type == "bash"

    def test_confirmation_contains_command_and_description(self, mock_shell_manager, mock_workspace_manager):
        """Test confirmation message contains command and description."""
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = tool.should_confirm_execute({
            "command": "echo hello",
            "description": "Print hello"
        })
        
        assert "echo hello" in result.message
        assert "Print hello" in result.message


class TestShellRunCommandExecute:
    """Tests for ShellRunCommand execute method."""

    @pytest.mark.asyncio
    async def test_run_command_existing_session(self, mock_shell_manager, mock_workspace_manager):
        """Test running command in existing session."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "command": "echo hello",
            "description": "Print hello"
        })
        
        assert result.is_error is False
        assert "echo hello" in result.llm_content

    @pytest.mark.asyncio
    async def test_run_command_creates_session_if_missing(self, mock_shell_manager, mock_workspace_manager):
        """Test that missing session is auto-created."""
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "auto_created",
            "command": "pwd",
            "description": "Print working directory"
        })
        
        assert result.is_error is False
        assert "auto_created" in mock_shell_manager.get_all_sessions()

    @pytest.mark.asyncio
    async def test_run_command_empty_command_error(self, mock_shell_manager, mock_workspace_manager):
        """Test error with empty command."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "command": "",
            "description": "Empty"
        })
        
        assert result.is_error is True
        assert "required" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_run_command_timeout_too_large(self, mock_shell_manager, mock_workspace_manager):
        """Test error with timeout exceeding max."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "command": "sleep 1",
            "description": "Sleep",
            "timeout": MAX_TIMEOUT + 100
        })
        
        assert result.is_error is True
        assert str(MAX_TIMEOUT) in result.llm_content

    @pytest.mark.asyncio
    async def test_run_command_busy_session(self, mock_shell_manager, mock_workspace_manager):
        """Test running command on busy session."""
        mock_shell_manager.create_session("test", "/workspace")
        mock_shell_manager._session_states["test"] = SessionState.BUSY
        tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "command": "echo hello",
            "description": "Print"
        })
        
        assert result.is_error is True
        assert "not finished" in result.llm_content.lower() or "busy" in result.llm_content.lower()


# =============================================================================
# Test ShellStopCommand
# =============================================================================

class TestShellStopCommandConstants:
    """Tests for ShellStopCommand module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert STOP_NAME == "BashStop"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert "Stop" in STOP_DISPLAY_NAME


class TestShellStopCommandAttributes:
    """Tests for ShellStopCommand class attributes."""

    def test_class_read_only(self):
        """Test read_only is False (modifies state)."""
        assert ShellStopCommand.read_only is False


class TestShellStopCommandExecute:
    """Tests for ShellStopCommand execute method."""

    @pytest.mark.asyncio
    async def test_stop_command(self, mock_shell_manager):
        """Test stopping a command."""
        mock_shell_manager.create_session("test", "/workspace")
        mock_shell_manager._session_states["test"] = SessionState.BUSY
        tool = ShellStopCommand(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "kill_session": False
        })
        
        assert result.is_error is False
        assert "stopped" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_kill_session(self, mock_shell_manager):
        """Test killing entire session."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellStopCommand(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "kill_session": True
        })
        
        assert result.is_error is False
        assert "killed" in result.llm_content.lower()
        assert "test" not in mock_shell_manager.get_all_sessions()

    @pytest.mark.asyncio
    async def test_stop_nonexistent_session(self, mock_shell_manager):
        """Test stopping nonexistent session."""
        tool = ShellStopCommand(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "nonexistent"
        })
        
        assert result.is_error is True
        assert "not available" in result.llm_content.lower() or "nonexistent" in result.llm_content


# =============================================================================
# Test ShellWriteToProcessTool
# =============================================================================

class TestShellWriteToProcessConstants:
    """Tests for ShellWriteToProcessTool module constants."""

    def test_name_constant(self):
        """Test NAME constant."""
        assert WRITE_NAME == "BashWriteToProcess"

    def test_display_name_constant(self):
        """Test DISPLAY_NAME constant."""
        assert "Write" in WRITE_DISPLAY_NAME


class TestShellWriteToProcessAttributes:
    """Tests for ShellWriteToProcessTool class attributes."""

    def test_class_read_only(self):
        """Test read_only is False (writes to process)."""
        assert ShellWriteToProcessTool.read_only is False


class TestShellWriteToProcessExecute:
    """Tests for ShellWriteToProcessTool execute method."""

    @pytest.mark.asyncio
    async def test_write_to_process(self, mock_shell_manager):
        """Test writing to a process."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellWriteToProcessTool(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "input": "y",
            "press_enter": True
        })
        
        assert result.is_error is False
        assert "y" in result.llm_content

    @pytest.mark.asyncio
    async def test_write_empty_input_error(self, mock_shell_manager):
        """Test error with empty input."""
        mock_shell_manager.create_session("test", "/workspace")
        tool = ShellWriteToProcessTool(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "test",
            "input": "",
            "press_enter": True
        })
        
        assert result.is_error is True
        assert "required" in result.llm_content.lower()

    @pytest.mark.asyncio
    async def test_write_nonexistent_session(self, mock_shell_manager):
        """Test writing to nonexistent session."""
        tool = ShellWriteToProcessTool(mock_shell_manager)
        
        result = await tool.execute({
            "session_name": "nonexistent",
            "input": "test"
        })
        
        assert result.is_error is True
        assert "not initialized" in result.llm_content.lower()


class TestShellWriteToProcessMCPWrapper:
    """Tests for ShellWriteToProcessTool MCP wrapper."""

    @pytest.mark.asyncio
    async def test_mcp_wrapper(self, mock_shell_manager):
        """Test MCP wrapper."""
        tool = ShellWriteToProcessTool(mock_shell_manager)
        tool._mcp_wrapper = AsyncMock(return_value=ToolResult(llm_content="ok"))
        
        await tool.execute_mcp_wrapper(
            session_name="test",
            input="hello",
            press_enter=False
        )
        
        tool._mcp_wrapper.assert_called_once()
        call_args = tool._mcp_wrapper.call_args[1]["tool_input"]
        assert call_args["session_name"] == "test"
        assert call_args["input"] == "hello"
        assert call_args["press_enter"] is False


# =============================================================================
# Test Cross-tool Integration
# =============================================================================

class TestShellToolIntegration:
    """Integration tests for shell tools working together."""

    @pytest.mark.asyncio
    async def test_init_list_run_view_workflow(self, mock_shell_manager, mock_workspace_manager):
        """Test typical workflow: init -> list -> run -> view."""
        init_tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        list_tool = ShellList(mock_shell_manager)
        run_tool = ShellRunCommand(mock_shell_manager, mock_workspace_manager)
        view_tool = ShellView(mock_shell_manager)
        
        # Initialize
        result = await init_tool.execute({
            "session_name": "workflow_test",
            "start_directory": "/workspace"
        })
        assert result.is_error is False
        
        # List
        result = await list_tool.execute({})
        assert "workflow_test" in result.llm_content
        
        # Run command
        result = await run_tool.execute({
            "session_name": "workflow_test",
            "command": "ls -la",
            "description": "List files"
        })
        assert result.is_error is False
        
        # View output
        result = await view_tool.execute({
            "session_names": ["workflow_test"]
        })
        assert result.is_error is False
        assert "workflow_test" in result.llm_content

    @pytest.mark.asyncio
    async def test_stop_and_delete_workflow(self, mock_shell_manager, mock_workspace_manager):
        """Test stop and delete workflow."""
        init_tool = ShellInit(mock_shell_manager, mock_workspace_manager)
        stop_tool = ShellStopCommand(mock_shell_manager)
        list_tool = ShellList(mock_shell_manager)
        
        # Initialize
        await init_tool.execute({
            "session_name": "to_delete",
            "start_directory": "/workspace"
        })
        
        # Verify exists
        result = await list_tool.execute({})
        assert "to_delete" in result.llm_content
        
        # Kill session
        result = await stop_tool.execute({
            "session_name": "to_delete",
            "kill_session": True
        })
        assert result.is_error is False
        
        # Verify deleted
        result = await list_tool.execute({})
        assert "to_delete" not in result.llm_content or "[]" in result.llm_content
