"""Unit tests for the BashTool class.

This module contains tests for the core functionality of BashTool,
including command execution, error handling, and integration with command filters.
"""

import pytest
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

from utils.common import ToolImplOutput
from tools.bash_tool import (
    BashTool,
    CommandFilter,
    DockerCommandFilter,
    start_persistent_shell,
    run_command,
    create_bash_tool,
)


def bash_tool():
    return BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
    )


def test_successful_command():
    """Test that a successful command returns the expected output."""
    bash_tool = BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
    )
    with patch("tools.bash_tool.run_command") as mock_run_command:
        # Mock a successful command execution
        mock_run_command.return_value = "Command output"

        result = bash_tool.run_impl({"command": "echo hello"})

        assert result.tool_output == "Command output"
        assert result.tool_result_message == "Command 'echo hello' executed."
        assert result.auxiliary_data == {
            "success": True,
            "original_command": "echo hello",
            "executed_command": "echo hello",
        }


def test_failed_command():
    """Test that a failed command returns the appropriate error."""
    bash_tool = BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
    )
    with patch("tools.bash_tool.run_command") as mock_run_command:
        # Mock a failed command execution that raises an exception
        mock_run_command.side_effect = Exception("Command failed")

        result = bash_tool.run_impl({"command": "invalid_command"})

        # Check the result
        assert "Error executing command: Command failed" == result.tool_output
        assert (
            "Failed to execute command 'invalid_command'" == result.tool_result_message
        )
        assert result.auxiliary_data == {
            "success": False,
            "error": "Command failed",
            "original_command": "invalid_command",
            "executed_command": "invalid_command",
        }


def test_command_with_exception():
    """Test that an exception during command execution is handled properly."""
    bash_tool = BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
    )
    with patch("tools.bash_tool.run_command") as mock_run_command:
        # Mock an exception during command execution
        mock_run_command.side_effect = Exception("Test exception")

        result = bash_tool.run_impl({"command": "echo hello"})

        # Check the result
        assert "Error executing command: Test exception" == result.tool_output
        assert "Failed to execute command 'echo hello'" == result.tool_result_message
        assert result.auxiliary_data == {
            "success": False,
            "error": "Test exception",
            "original_command": "echo hello",
            "executed_command": "echo hello",
        }


def test_get_tool_start_message():
    """Test that the tool start message is formatted correctly."""
    bash_tool = BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
    )
    message = bash_tool.get_tool_start_message({"command": "echo hello"})
    assert message == "Executing bash command: echo hello"


class MockCommandFilter(CommandFilter):
    """Mock command filter for testing."""

    def __init__(self, prefix="PREFIX:"):
        self.prefix = prefix
        self.called = False

    def filter_command(self, command: str) -> str:
        """Add a prefix to the command."""
        self.called = True
        return f"{self.prefix} {command}"


class BashToolTest(unittest.TestCase):
    """Tests for the BashTool class."""

    def setUp(self):
        """Set up test fixtures."""
        self.workspace_root = Path("/workspace")

        # Mock the shell interaction
        self.mock_child = MagicMock()
        self.mock_child.before = "command output"
        self.mock_prompt = "PROMPT>>"

        # Create patches
        self.start_shell_patch = patch(
            "tools.bash_tool.start_persistent_shell",
            return_value=(self.mock_child, self.mock_prompt),
        )
        self.run_command_patch = patch(
            "tools.bash_tool.run_command",
            return_value="command output",
        )

        # Start patches
        self.mock_start_shell = self.start_shell_patch.start()
        self.mock_run_command = self.run_command_patch.start()

        # Reset mocks for each test to avoid interference between tests
        self.mock_run_command.reset_mock()

    def tearDown(self):
        """Tear down test fixtures."""
        self.start_shell_patch.stop()
        self.run_command_patch.stop()

    def test_init(self):
        """Test BashTool initialization."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
        )

        # Check that shell was started
        self.mock_start_shell.assert_called_once()

        # Check that we changed to the workspace directory
        self.mock_run_command.assert_called_once_with(
            self.mock_child, self.mock_prompt, f"cd {self.workspace_root}"
        )

        # Check that command_filters is initialized as empty list
        self.assertEqual(tool.command_filters, [])

    def test_init_with_filters(self):
        """Test BashTool initialization with command filters."""
        filter1 = MockCommandFilter("PREFIX1:")
        filter2 = MockCommandFilter("PREFIX2:")

        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
            command_filters=[filter1, filter2],
        )

        # Check that command_filters contains our filters
        self.assertEqual(tool.command_filters, [filter1, filter2])

    def test_add_command_filter(self):
        """Test adding a command filter."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
        )

        filter1 = MockCommandFilter("PREFIX1:")
        filter2 = MockCommandFilter("PREFIX2:")

        tool.add_command_filter(filter1)
        tool.add_command_filter(filter2)

        # Check that filters were added in the correct order
        self.assertEqual(tool.command_filters, [filter1, filter2])

    def test_apply_filters(self):
        """Test applying command filters."""
        filter1 = MockCommandFilter("PREFIX1:")
        filter2 = MockCommandFilter("PREFIX2:")

        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
            command_filters=[filter1, filter2],
        )

        # Apply filters to a command
        result = tool.apply_filters("ls -l")

        # Check that both filters were called
        self.assertTrue(filter1.called)
        self.assertTrue(filter2.called)

        # Check that filters were applied in the correct order
        # filter2 should be applied to the output of filter1
        self.assertEqual(result, "PREFIX2: PREFIX1: ls -l")

    @patch("builtins.input", return_value="y")
    def test_run_impl_with_confirmation(self, mock_input):
        """Test running a command with user confirmation."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=True,
        )
        # Creating the tool with a workspace calls run_impl once, we reset it here.
        self.mock_run_command.reset_mock()

        result = tool.run_impl({"command": "ls -l"})

        # Check that input was called for confirmation
        mock_input.assert_called_once()

        # Check that command was executed
        self.mock_run_command.assert_called_with(
            self.mock_child, self.mock_prompt, "ls -l"
        )

        # Check result
        self.assertIsInstance(result, ToolImplOutput)
        self.assertEqual(result.tool_output, "command output")
        self.assertEqual(result.auxiliary_data["success"], True)

    @patch("builtins.input", return_value="n")
    def test_run_impl_confirmation_denied(self, mock_input):
        """Test running a command with user confirmation denied."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=True,
        )
        # Creating the tool with a workspace calls run_impl once, we reset it here.
        self.mock_run_command.reset_mock()

        result = tool.run_impl({"command": "ls -l"})

        # Check that input was called for confirmation
        mock_input.assert_called_once()

        # Check that command was NOT executed
        self.mock_run_command.assert_not_called()

        # Check result
        self.assertIsInstance(result, ToolImplOutput)
        self.assertEqual(result.auxiliary_data["success"], False)
        self.assertEqual(result.auxiliary_data["reason"], "User did not confirm")

    def test_run_impl_no_confirmation(self):
        """Test running a command without requiring confirmation."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
        )

        result = tool.run_impl({"command": "ls -l"})

        # Check that command was executed
        self.mock_run_command.assert_called_with(
            self.mock_child, self.mock_prompt, "ls -l"
        )

        # Check result
        self.assertIsInstance(result, ToolImplOutput)
        self.assertEqual(result.tool_output, "command output")
        self.assertEqual(result.auxiliary_data["success"], True)

    def test_run_impl_with_filters(self):
        """Test running a command with command filters."""
        filter1 = MockCommandFilter("PREFIX:")

        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
            command_filters=[filter1],
        )

        result = tool.run_impl({"command": "ls -l"})

        # Check that filter was called
        self.assertTrue(filter1.called)

        # Check that transformed command was executed
        self.mock_run_command.assert_called_with(
            self.mock_child, self.mock_prompt, "PREFIX: ls -l"
        )

        # Check result includes both original and executed commands
        self.assertEqual(result.auxiliary_data["original_command"], "ls -l")
        self.assertEqual(result.auxiliary_data["executed_command"], "PREFIX: ls -l")

    def test_run_impl_error(self):
        """Test handling of command execution errors."""
        # Make run_command raise an exception
        self.mock_run_command.side_effect = Exception("Command failed")

        # No workspace root here or we get a real failure on a non-existent directory
        tool = BashTool(
            require_confirmation=False,
        )

        result = tool.run_impl({"command": "ls -l"})

        # Check result
        self.assertIsInstance(result, ToolImplOutput)
        self.assertEqual(result.auxiliary_data["success"], False)
        self.assertEqual(result.auxiliary_data["error"], "Command failed")

    def test_get_tool_start_message(self):
        """Test getting the tool start message."""
        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
        )

        message = tool.get_tool_start_message({"command": "ls -l"})

        # Check message
        self.assertEqual(message, "Executing bash command: ls -l")

    def test_create_bash_tool(self):
        """Test the create_bash_tool factory function."""

        with patch("tools.bash_tool.BashTool") as mock_bash_tool:
            _ = create_bash_tool(
                ask_user_permission=True,
                cwd=self.workspace_root,
            )

            # Check that BashTool was created with correct parameters
            mock_bash_tool.assert_called_once_with(
                workspace_root=self.workspace_root,
                require_confirmation=True,
                command_filters=None,
                additional_banned_command_strs=None,
            )


class RunCommandTest(unittest.TestCase):
    """Tests for the run_command function."""

    def test_run_command(self):
        """Test the run_command function."""
        # Create a mock child process
        mock_child = MagicMock()
        mock_child.before = "\ncommand output\n"
        mock_prompt = "PROMPT>>"

        # Call run_command
        result = run_command(mock_child, mock_prompt, "ls -l")

        # Check that command was sent
        mock_child.sendline.assert_called_once_with("ls -l")

        # Check that we waited for the prompt
        mock_child.expect.assert_called_once_with(mock_prompt)

        # Check result
        self.assertEqual(result, "command output")


class StartPersistentShellTest(unittest.TestCase):
    """Tests for the start_persistent_shell function."""

    @patch("tools.bash_tool.pexpect.spawn")
    def test_start_persistent_shell(self, mock_spawn):
        """Test the start_persistent_shell function."""
        # Create a mock child process
        mock_child = MagicMock()
        mock_spawn.return_value = mock_child

        # Call start_persistent_shell
        child, prompt = start_persistent_shell(timeout=60)

        # Check that spawn was called with bash
        mock_spawn.assert_called_once_with(
            "/bin/bash", encoding="utf-8", echo=False, timeout=60
        )

        # Check that we set up the prompt
        self.assertEqual(child, mock_child)
        self.assertTrue(isinstance(prompt, str))
        self.assertTrue(len(prompt) > 0)

        # Check that we sent the commands to set up the prompt
        mock_child.sendline.assert_any_call("stty -onlcr")
        self.assertEqual(mock_child.sendline.call_count, 3)

        # Check that we waited for the prompt
        mock_child.expect.assert_called_once()


def test_command_with_timeout():
    """Test that timeouts are handled properly and we can run subsequent commands."""
    bash_tool = BashTool(
        workspace_root=Path("/tmp"),
        require_confirmation=False,
        timeout=5,
    )

    output = bash_tool.run_impl({"command": "sleep 10"})
    assert output.tool_output == "Command timed out. Please try again."
    assert output.tool_result_message == "Command timed out. Please try again."
    assert not output.auxiliary_data["success"]

    output = bash_tool.run_impl({"command": "echo hello"})
    assert output.tool_output.strip() == "hello"
    assert output.tool_result_message == "Command 'echo hello' executed."
    assert output.auxiliary_data["success"]


# These will pass, but don't run in CI.
@pytest.mark.xfail
class TestWithRealContainer(unittest.TestCase):
    """Test the BashTool with a real container."""

    def setUp(self):
        """Set up the test."""
        self.workspace_root = Path("/workspace")
        self.start_container()

    def tearDown(self):
        """Tear down the test."""
        pass
        self.stop_container()

    def start_container(self):
        """Start a container for testing."""
        import docker

        client = docker.from_env()
        container = client.containers.run(
            "alpine:3.14",
            "tail -f /dev/null",
            detach=True,
        )
        self.container = container

    def stop_container(self):
        """Stop a container for testing."""
        import docker

        client = docker.from_env()
        assert self.container is not None and self.container.id is not None
        container = client.containers.get(self.container.id)
        container.stop()
        container.remove()

    def test_run_impl(self):
        """Test the run_impl method with a real container."""
        assert self.container is not None and self.container.id is not None
        docker_filter = DockerCommandFilter(
            container=self.container.id,
            user=None,
        )

        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
            command_filters=[docker_filter],
        )

        result = tool.run_impl({"command": "ls -l"})

        self.assertIsInstance(result, ToolImplOutput)
        self.assertEqual(result.auxiliary_data["success"], True)
        self.assertEqual(result.tool_output.strip().splitlines()[0].strip(), "total 56")

    def test_compound_command(self):
        assert self.container is not None and self.container.id is not None
        docker_filter = DockerCommandFilter(
            container=self.container.id,
            user=None,
        )

        tool = BashTool(
            workspace_root=self.workspace_root,
            require_confirmation=False,
            command_filters=[docker_filter],
        )

        result = tool.run_impl({"command": "touch /tmp/test.txt && ls /tmp/test.txt"})
        print(result.auxiliary_data["executed_command"])
        print(result.tool_output)
        self.assertEqual(result.tool_output.strip(), "/tmp/test.txt")


if __name__ == "__main__":
    unittest.main()
