"""Tests for the sequential thinking tool."""

import json
import unittest
from unittest.mock import Mock, patch

from tools.sequential_thinking_tool import (
    SequentialThinkingTool,
)


class TestSequentialThinkingTool(unittest.TestCase):
    """Test cases for the SequentialThinkingTool."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = Mock()
        self.tool = SequentialThinkingTool(self.mock_logger)

    def test_initialization(self):
        """Test that the tool initializes correctly."""
        self.assertEqual(self.tool.name, "sequential_thinking")
        self.assertIn("dynamic and reflective problem-solving", self.tool.description)
        self.assertEqual(len(self.tool.thought_history), 0)
        self.assertEqual(len(self.tool.branches), 0)

    def test_validate_thought_data_valid(self):
        """Test validation with valid input."""
        valid_input = {
            "thought": "This is a test thought",
            "thoughtNumber": 1,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }
        result = self.tool._validate_thought_data(valid_input)
        self.assertEqual(result["thought"], "This is a test thought")  # pyright: ignore[reportTypedDictNotRequiredAccess]
        self.assertEqual(result["thoughtNumber"], 1)  # pyright: ignore[reportTypedDictNotRequiredAccess]
        self.assertEqual(result["totalThoughts"], 5)  # pyright: ignore[reportTypedDictNotRequiredAccess]
        self.assertTrue(result["nextThoughtNeeded"])  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_validate_thought_data_invalid(self):
        """Test validation with invalid input."""
        # Missing thought
        invalid_input = {
            "thoughtNumber": 1,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }
        with self.assertRaises(ValueError):
            self.tool._validate_thought_data(invalid_input)

        # Invalid thoughtNumber
        invalid_input = {
            "thought": "This is a test thought",
            "thoughtNumber": "1",  # Should be an integer
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }
        with self.assertRaises(ValueError):
            self.tool._validate_thought_data(invalid_input)

    def test_format_thought_regular(self):
        """Test formatting a regular thought."""
        thought_data = {
            "thought": "This is a regular thought",
            "thoughtNumber": 1,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }
        formatted = self.tool._format_thought(thought_data)  # pyright: ignore[reportArgumentType]
        self.assertIn("💭 Thought 1/5", formatted)
        self.assertIn("This is a regular thought", formatted)

    def test_format_thought_revision(self):
        """Test formatting a revision thought."""
        thought_data = {
            "thought": "This is a revision",
            "thoughtNumber": 2,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
            "isRevision": True,
            "revisesThought": 1,
        }
        formatted = self.tool._format_thought(thought_data)  # pyright: ignore[reportArgumentType]
        self.assertIn("🔄 Revision 2/5", formatted)
        self.assertIn("(revising thought 1)", formatted)
        self.assertIn("This is a revision", formatted)

    def test_format_thought_branch(self):
        """Test formatting a branch thought."""
        thought_data = {
            "thought": "This is a branch",
            "thoughtNumber": 3,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
            "branchFromThought": 2,
            "branchId": "branch-1",
        }
        formatted = self.tool._format_thought(thought_data)  # pyright: ignore[reportArgumentType]
        self.assertIn("🌿 Branch 3/5", formatted)
        self.assertIn("(from thought 2, ID: branch-1)", formatted)
        self.assertIn("This is a branch", formatted)

    def test_run_impl_success(self):
        """Test successful execution of run_impl."""
        input_data = {
            "thought": "This is a test thought",
            "thoughtNumber": 1,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
        }

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = Mock()
            mock_get_logger.return_value = mock_logger

            result = self.tool.run_impl(input_data)

            # Verify the result
            self.assertIsNotNone(result)
            self.assertIn("thoughtNumber", result.tool_output)

            # Parse the JSON output
            output_data = json.loads(result.tool_output)
            self.assertEqual(output_data["thoughtNumber"], 1)
            self.assertEqual(output_data["totalThoughts"], 5)
            self.assertTrue(output_data["nextThoughtNeeded"])
            self.assertEqual(output_data["thoughtHistoryLength"], 1)

            # Verify thought was added to history
            self.assertEqual(len(self.tool.thought_history), 1)
            self.assertEqual(
                self.tool.thought_history[0]["thought"],  # pyright: ignore[reportTypedDictNotRequiredAccess]
                "This is a test thought",
            )

    def test_run_impl_with_branch(self):
        """Test run_impl with a branch thought."""
        # First add a regular thought
        self.tool.run_impl(
            {
                "thought": "Initial thought",
                "thoughtNumber": 1,
                "totalThoughts": 5,
                "nextThoughtNeeded": True,
            }
        )

        # Then add a branch thought
        branch_input = {
            "thought": "Branch thought",
            "thoughtNumber": 2,
            "totalThoughts": 5,
            "nextThoughtNeeded": True,
            "branchFromThought": 1,
            "branchId": "test-branch",
        }

        result = self.tool.run_impl(branch_input)

        # Verify branch was created
        self.assertIn("test-branch", self.tool.branches)
        self.assertEqual(len(self.tool.branches["test-branch"]), 1)

        # Verify output contains branch info
        output_data = json.loads(result.tool_output)
        self.assertIn("test-branch", output_data["branches"])

    def test_run_impl_error(self):
        """Test run_impl with invalid input that causes an error."""
        invalid_input = {
            # Missing required fields
            "thought": "Test thought"
        }

        result = self.tool.run_impl(invalid_input)

        # Verify error response
        self.assertIn("error", result.tool_output)
        self.assertIn("failed", result.tool_output)

        # Parse the JSON output
        output_data = json.loads(result.tool_output)
        self.assertEqual(output_data["status"], "failed")
        self.assertIn("Invalid", output_data["error"])

    def test_adjust_total_thoughts(self):
        """Test that totalThoughts is adjusted if thoughtNumber is greater."""
        input_data = {
            "thought": "Thought beyond the initial estimate",
            "thoughtNumber": 10,
            "totalThoughts": 5,  # This should be adjusted to 10
            "nextThoughtNeeded": True,
        }

        result = self.tool.run_impl(input_data)
        output_data = json.loads(result.tool_output)

        # Verify totalThoughts was adjusted
        self.assertEqual(output_data["totalThoughts"], 10)
        self.assertEqual(self.tool.thought_history[0]["totalThoughts"], 10)  # pyright: ignore[reportTypedDictNotRequiredAccess]

    def test_get_tool_start_message(self):
        """Test the get_tool_start_message method."""
        input_data = {
            "thought": "Test thought",
            "thoughtNumber": 3,
            "totalThoughts": 7,
            "nextThoughtNeeded": True,
        }

        message = self.tool.get_tool_start_message(input_data)
        self.assertEqual(message, "Processing sequential thought 3/7")


if __name__ == "__main__":
    unittest.main()
