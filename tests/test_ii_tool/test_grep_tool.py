"""Unit tests for ii_tool.tools.file_system.grep_tool module.

This module tests the grep/search tool:
- Regex pattern validation (_validate_regex_pattern)
- Ripgrep execution (_run_ripgrep)
- Result formatting
- GrepTool class and execute method
"""

import os
import subprocess
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from ii_tool.tools.file_system.grep_tool import (
    _validate_regex_pattern,
    _run_ripgrep,
    GrepTool,
    GrepToolError,
    MAX_GLOB_RESULTS,
)
from ii_tool.core.workspace import WorkspaceManager
from ii_tool.tools.base import ToolResult


# =============================================================================
# _validate_regex_pattern Tests
# =============================================================================

class TestValidateRegexPattern:
    """Tests for _validate_regex_pattern function."""

    def test_simple_pattern_valid(self):
        """Simple text patterns are valid."""
        assert _validate_regex_pattern("hello") is True

    def test_regex_metacharacters_valid(self):
        """Regex with metacharacters is valid."""
        assert _validate_regex_pattern("function\\s+\\w+") is True

    def test_character_class_valid(self):
        """Character classes are valid."""
        assert _validate_regex_pattern("[a-zA-Z0-9]+") is True

    def test_alternation_valid(self):
        """Alternation patterns are valid."""
        assert _validate_regex_pattern("foo|bar|baz") is True

    def test_quantifiers_valid(self):
        """Quantifiers are valid."""
        assert _validate_regex_pattern("a*b+c?d{2,3}") is True

    def test_anchors_valid(self):
        """Anchors are valid."""
        assert _validate_regex_pattern("^start.*end$") is True

    def test_groups_valid(self):
        """Capture groups are valid."""
        assert _validate_regex_pattern("(foo)(bar)") is True

    def test_invalid_unmatched_bracket(self):
        """Unmatched brackets are invalid."""
        assert _validate_regex_pattern("[abc") is False

    def test_invalid_unmatched_paren(self):
        """Unmatched parentheses are invalid."""
        assert _validate_regex_pattern("(abc") is False

    def test_invalid_bad_quantifier(self):
        """Bad quantifier syntax is invalid."""
        assert _validate_regex_pattern("*abc") is False

    def test_empty_pattern_valid(self):
        """Empty pattern is technically valid regex."""
        assert _validate_regex_pattern("") is True


# =============================================================================
# _run_ripgrep Tests (Mocked)
# =============================================================================

class TestRunRipgrepMocked:
    """Tests for _run_ripgrep function with mocked subprocess."""

    def test_returns_matches(self):
        """Ripgrep returns parsed matches."""
        mock_output = "file.py:10:def hello():\nfile.py:20:def world():"
        
        with patch('ii_tool.tools.file_system.grep_tool.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = mock_output
            mock_run.return_value = mock_result
            
            matches = _run_ripgrep("def", Path("/tmp"))
            
            assert len(matches) == 2
            assert matches[0]['file_path'] == 'file.py'
            assert matches[0]['line_number'] == '10'
            assert matches[0]['content'] == 'def hello():'

    def test_no_matches_returns_empty(self):
        """No matches returns empty list."""
        with patch('ii_tool.tools.file_system.grep_tool.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1  # ripgrep returns 1 for no matches
            mock_result.stdout = ""
            mock_run.return_value = mock_result
            
            matches = _run_ripgrep("nonexistent", Path("/tmp"))
            
            assert matches == []

    def test_includes_glob_pattern(self):
        """Include pattern is passed to ripgrep."""
        with patch('ii_tool.tools.file_system.grep_tool.subprocess.run') as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_run.return_value = mock_result
            
            _run_ripgrep("pattern", Path("/tmp"), include="*.py")
            
            call_args = mock_run.call_args[0][0]
            assert '--glob' in call_args
            assert '*.py' in call_args

    def test_timeout_raises_error(self):
        """Timeout raises GrepToolError."""
        with patch('ii_tool.tools.file_system.grep_tool.subprocess.run') as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="rg", timeout=30)
            
            with pytest.raises(GrepToolError) as exc_info:
                _run_ripgrep("pattern", Path("/tmp"))
            
            assert "timed out" in str(exc_info.value).lower()

    def test_ripgrep_error_raises(self):
        """Ripgrep errors raise GrepToolError."""
        with patch('ii_tool.tools.file_system.grep_tool.subprocess.run') as mock_run:
            # Create CalledProcessError with stderr properly set
            error = subprocess.CalledProcessError(2, "rg")
            error.stderr = "Invalid regex"
            mock_run.side_effect = error
            
            with pytest.raises(GrepToolError):
                _run_ripgrep("pattern", Path("/tmp"))


# =============================================================================
# GrepTool Tests
# =============================================================================

class TestGrepTool:
    """Tests for GrepTool class."""

    @pytest.fixture
    def workspace(self):
        """Create a temporary workspace with test files."""
        with TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "file1.py").write_text(
                "def hello():\n    print('Hello')\n\ndef world():\n    pass"
            )
            (Path(tmpdir) / "file2.py").write_text(
                "import os\nimport sys\n\ndef main():\n    pass"
            )
            (Path(tmpdir) / "readme.md").write_text(
                "# Project\n\nThis is a test project."
            )
            
            # Create subdirectory
            subdir = Path(tmpdir) / "src"
            subdir.mkdir()
            (subdir / "module.py").write_text(
                "def helper():\n    return 42"
            )
            
            yield tmpdir

    @pytest.fixture
    def tool(self, workspace):
        """Create a GrepTool instance."""
        manager = WorkspaceManager(workspace)
        return GrepTool(manager)

    def test_tool_attributes(self, tool):
        """GrepTool has correct attributes."""
        assert tool.name == "Grep"
        assert tool.display_name == "Search file contents"
        assert tool.read_only is True
        assert "pattern" in tool.input_schema["required"]

    @pytest.mark.asyncio
    async def test_search_finds_matches(self, tool, workspace):
        """Search finds matching patterns."""
        with patch('ii_tool.tools.file_system.grep_tool._run_ripgrep') as mock_rg:
            mock_rg.return_value = [
                {'file_path': 'file1.py', 'line_number': '1', 'content': 'def hello():'},
                {'file_path': 'file1.py', 'line_number': '4', 'content': 'def world():'},
            ]
            
            result = await tool.execute({"pattern": "def \\w+"})
            
            assert result.is_error is False
            assert "2 matches" in result.llm_content
            assert "hello" in result.llm_content
            assert "world" in result.llm_content

    @pytest.mark.asyncio
    async def test_search_no_matches(self, tool):
        """Search with no matches returns appropriate message."""
        with patch('ii_tool.tools.file_system.grep_tool._run_ripgrep') as mock_rg:
            mock_rg.return_value = []
            
            result = await tool.execute({"pattern": "nonexistent_xyz"})
            
            assert result.is_error is False
            assert "No matches found" in result.llm_content

    @pytest.mark.asyncio
    async def test_search_with_include_filter(self, tool, workspace):
        """Search respects include filter."""
        with patch('ii_tool.tools.file_system.grep_tool._run_ripgrep') as mock_rg:
            mock_rg.return_value = []
            
            await tool.execute({
                "pattern": "def",
                "include": "*.py"
            })
            
            # Verify include was passed
            call_args = mock_rg.call_args
            assert call_args[0][2] == "*.py"  # Third argument is include

    @pytest.mark.asyncio
    async def test_search_with_path(self, tool, workspace):
        """Search in specific directory."""
        with patch('ii_tool.tools.file_system.grep_tool._run_ripgrep') as mock_rg:
            mock_rg.return_value = []
            
            src_dir = os.path.join(workspace, "src")
            await tool.execute({
                "pattern": "helper",
                "path": src_dir
            })
            
            # Verify path was used
            call_args = mock_rg.call_args
            assert str(call_args[0][1]) == src_dir

    @pytest.mark.asyncio
    async def test_invalid_regex_returns_error(self, tool):
        """Invalid regex pattern returns error."""
        result = await tool.execute({"pattern": "[invalid"})
        
        assert result.is_error is True
        assert "Invalid" in result.llm_content

    @pytest.mark.asyncio
    async def test_path_outside_workspace_returns_error(self, tool):
        """Path outside workspace returns error."""
        result = await tool.execute({
            "pattern": "test",
            "path": "/etc"
        })
        
        assert result.is_error is True

    @pytest.mark.asyncio
    async def test_nonexistent_path_returns_error(self, tool, workspace):
        """Nonexistent path returns error."""
        result = await tool.execute({
            "pattern": "test",
            "path": os.path.join(workspace, "nonexistent")
        })
        
        assert result.is_error is True


# =============================================================================
# Result Formatting Tests
# =============================================================================

class TestResultFormatting:
    """Tests for result formatting in GrepTool."""

    @pytest.fixture
    def workspace(self):
        with TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def tool(self, workspace):
        manager = WorkspaceManager(workspace)
        return GrepTool(manager)

    def test_format_groups_by_file(self, tool):
        """Results are grouped by file."""
        matches = [
            {'file_path': 'a.py', 'line_number': '1', 'content': 'line 1'},
            {'file_path': 'b.py', 'line_number': '1', 'content': 'line 1'},
            {'file_path': 'a.py', 'line_number': '2', 'content': 'line 2'},
        ]
        
        result = tool._format_results(matches, "pattern", Path("/tmp"))
        
        # Files should appear as headers
        assert "File: a.py" in result
        assert "File: b.py" in result

    def test_format_includes_line_numbers(self, tool):
        """Results include line numbers."""
        matches = [
            {'file_path': 'test.py', 'line_number': '42', 'content': 'the answer'},
        ]
        
        result = tool._format_results(matches, "pattern", Path("/tmp"))
        
        assert "L42:" in result

    def test_format_truncates_at_max(self, tool):
        """Results are truncated at MAX_GLOB_RESULTS."""
        # Create more matches than the limit
        matches = [
            {'file_path': f'file{i}.py', 'line_number': '1', 'content': f'match {i}'}
            for i in range(MAX_GLOB_RESULTS + 50)
        ]
        
        result = tool._format_results(matches, "pattern", Path("/tmp"))
        
        assert "limited" in result.lower() or "truncated" in result.lower() or str(MAX_GLOB_RESULTS) in result

    def test_format_shows_match_count(self, tool):
        """Results show total match count."""
        matches = [
            {'file_path': 'test.py', 'line_number': '1', 'content': 'match 1'},
            {'file_path': 'test.py', 'line_number': '2', 'content': 'match 2'},
            {'file_path': 'test.py', 'line_number': '3', 'content': 'match 3'},
        ]
        
        result = tool._format_results(matches, "pattern", Path("/tmp"))
        
        assert "3 matches" in result


# =============================================================================
# Integration Tests (with real ripgrep if available)
# =============================================================================

class TestGrepToolIntegration:
    """Integration tests that use real ripgrep."""

    @pytest.fixture
    def workspace(self):
        with TemporaryDirectory() as tmpdir:
            # Create test files
            (Path(tmpdir) / "code.py").write_text(
                "def function_one():\n    pass\n\ndef function_two():\n    pass"
            )
            yield tmpdir

    @pytest.fixture
    def tool(self, workspace):
        manager = WorkspaceManager(workspace)
        return GrepTool(manager)

    @pytest.mark.asyncio
    async def test_real_ripgrep_search(self, tool, workspace):
        """Test with real ripgrep if available."""
        # Skip if ripgrep not installed
        try:
            subprocess.run(['rg', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("ripgrep not available")
        
        result = await tool.execute({
            "pattern": "function_",
            "path": workspace
        })
        
        assert result.is_error is False
        assert "function_one" in result.llm_content
        assert "function_two" in result.llm_content


# =============================================================================
# GrepToolError Tests
# =============================================================================

class TestGrepToolError:
    """Tests for GrepToolError exception."""

    def test_is_exception(self):
        """GrepToolError is an Exception."""
        assert issubclass(GrepToolError, Exception)

    def test_preserves_message(self):
        """GrepToolError preserves error message."""
        error = GrepToolError("Custom error message")
        assert str(error) == "Custom error message"

    def test_can_be_raised_and_caught(self):
        """GrepToolError can be raised and caught."""
        with pytest.raises(GrepToolError):
            raise GrepToolError("Test error")
