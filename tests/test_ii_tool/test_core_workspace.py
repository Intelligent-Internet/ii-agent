"""Unit tests for ii_tool.core.workspace module.

This module tests the WorkspaceManager class:
- Workspace path validation and initialization
- Boundary checks for path containment
- File and directory validation methods
- Error handling for invalid paths
"""

import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from ii_tool.core.workspace import (
    FileSystemValidationError,
    WorkspaceError,
    WorkspaceManager,
)


# =============================================================================
# WorkspaceError Tests
# =============================================================================

class TestWorkspaceError:
    """Tests for WorkspaceError exception."""

    def test_is_exception(self):
        """WorkspaceError is an Exception subclass."""
        assert issubclass(WorkspaceError, Exception)

    def test_message(self):
        """WorkspaceError stores message correctly."""
        error = WorkspaceError("test message")
        assert str(error) == "test message"


class TestFileSystemValidationError:
    """Tests for FileSystemValidationError exception."""

    def test_is_exception(self):
        """FileSystemValidationError is an Exception subclass."""
        assert issubclass(FileSystemValidationError, Exception)

    def test_message(self):
        """FileSystemValidationError stores message correctly."""
        error = FileSystemValidationError("path not valid")
        assert str(error) == "path not valid"


# =============================================================================
# WorkspaceManager Initialization Tests
# =============================================================================

class TestWorkspaceManagerInit:
    """Tests for WorkspaceManager initialization."""

    def test_init_with_string_path(self, tmp_path):
        """WorkspaceManager accepts string path."""
        manager = WorkspaceManager(str(tmp_path))
        assert manager.workspace_path == tmp_path.resolve()

    def test_init_with_path_object(self, tmp_path):
        """WorkspaceManager accepts Path object."""
        manager = WorkspaceManager(tmp_path)
        assert manager.workspace_path == tmp_path.resolve()

    def test_init_resolves_path(self, tmp_path):
        """WorkspaceManager resolves relative paths."""
        # Create a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        
        # Use a path with .. in it
        complex_path = str(subdir / ".." / "subdir")
        manager = WorkspaceManager(complex_path)
        assert manager.workspace_path == subdir.resolve()

    def test_init_nonexistent_path_raises(self):
        """WorkspaceManager raises WorkspaceError for nonexistent path."""
        with pytest.raises(WorkspaceError, match="does not exist"):
            WorkspaceManager("/nonexistent/path/12345")

    def test_init_file_path_raises(self, tmp_path):
        """WorkspaceManager raises WorkspaceError when path is a file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        with pytest.raises(WorkspaceError, match="is not a directory"):
            WorkspaceManager(str(test_file))


# =============================================================================
# get_workspace_path Tests
# =============================================================================

class TestGetWorkspacePath:
    """Tests for WorkspaceManager.get_workspace_path method."""

    def test_returns_path_object(self, tmp_path):
        """get_workspace_path returns Path object."""
        manager = WorkspaceManager(tmp_path)
        result = manager.get_workspace_path()
        assert isinstance(result, Path)

    def test_returns_resolved_path(self, tmp_path):
        """get_workspace_path returns absolute resolved path."""
        manager = WorkspaceManager(tmp_path)
        result = manager.get_workspace_path()
        assert result.is_absolute()
        assert result == tmp_path.resolve()


# =============================================================================
# validate_boundary Tests
# =============================================================================

class TestValidateBoundary:
    """Tests for WorkspaceManager.validate_boundary method."""

    def test_workspace_path_is_valid(self, tmp_path):
        """Workspace path itself is within boundary."""
        manager = WorkspaceManager(tmp_path)
        assert manager.validate_boundary(tmp_path) is True

    def test_subdirectory_is_valid(self, tmp_path):
        """Subdirectory of workspace is within boundary."""
        manager = WorkspaceManager(tmp_path)
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        assert manager.validate_boundary(subdir) is True

    def test_nested_path_is_valid(self, tmp_path):
        """Deeply nested path is within boundary."""
        manager = WorkspaceManager(tmp_path)
        nested = tmp_path / "a" / "b" / "c" / "file.txt"
        # Path doesn't need to exist for boundary check
        assert manager.validate_boundary(nested) is True

    def test_parent_directory_is_invalid(self, tmp_path):
        """Parent directory is outside boundary."""
        subdir = tmp_path / "workspace"
        subdir.mkdir()
        manager = WorkspaceManager(subdir)
        assert manager.validate_boundary(tmp_path) is False

    def test_sibling_directory_is_invalid(self, tmp_path):
        """Sibling directory is outside boundary."""
        workspace = tmp_path / "workspace"
        sibling = tmp_path / "sibling"
        workspace.mkdir()
        sibling.mkdir()
        
        manager = WorkspaceManager(workspace)
        assert manager.validate_boundary(sibling) is False

    def test_root_path_is_invalid(self, tmp_path):
        """Root path is outside workspace boundary."""
        manager = WorkspaceManager(tmp_path)
        assert manager.validate_boundary("/") is False

    def test_accepts_string_path(self, tmp_path):
        """validate_boundary accepts string path."""
        manager = WorkspaceManager(tmp_path)
        assert manager.validate_boundary(str(tmp_path / "file.txt")) is True

    def test_handles_symlink_traversal(self, tmp_path):
        """validate_boundary handles symlinks correctly."""
        # Create workspace and external directory
        workspace = tmp_path / "workspace"
        external = tmp_path / "external"
        workspace.mkdir()
        external.mkdir()
        
        # Create symlink inside workspace pointing outside
        symlink = workspace / "link"
        try:
            symlink.symlink_to(external)
        except OSError:
            pytest.skip("Symlink creation not supported")
        
        manager = WorkspaceManager(workspace)
        # The resolved symlink path should be outside workspace
        # Note: validate_boundary resolves paths, so symlink target is checked
        assert manager.validate_boundary(symlink) is False

    def test_invalid_path_returns_false(self, tmp_path):
        """validate_boundary returns False for malformed paths."""
        manager = WorkspaceManager(tmp_path)
        # Various edge cases that might cause exceptions
        assert manager.validate_boundary("") is False


# =============================================================================
# validate_path Tests
# =============================================================================

class TestValidatePath:
    """Tests for WorkspaceManager.validate_path method."""

    def test_valid_absolute_path_in_workspace(self, tmp_path):
        """Valid absolute path within workspace passes."""
        manager = WorkspaceManager(tmp_path)
        # Should not raise
        manager.validate_path(str(tmp_path / "file.txt"))

    def test_empty_path_raises(self, tmp_path):
        """Empty path raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="cannot be empty"):
            manager.validate_path("")

    def test_whitespace_only_path_raises(self, tmp_path):
        """Whitespace-only path raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="cannot be empty"):
            manager.validate_path("   ")

    def test_relative_path_raises(self, tmp_path):
        """Relative path raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="is not absolute"):
            manager.validate_path("relative/path.txt")

    def test_path_outside_workspace_raises(self, tmp_path):
        """Path outside workspace raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="not within workspace boundary"):
            manager.validate_path("/etc/passwd")

    def test_path_with_traversal_outside_workspace(self, tmp_path):
        """Path with .. traversal outside workspace raises."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        manager = WorkspaceManager(workspace)
        
        # This path resolves to outside workspace
        with pytest.raises(FileSystemValidationError, match="not within workspace boundary"):
            manager.validate_path(str(workspace / ".." / "other"))


# =============================================================================
# validate_existing_file_path Tests
# =============================================================================

class TestValidateExistingFilePath:
    """Tests for WorkspaceManager.validate_existing_file_path method."""

    def test_valid_existing_file(self, tmp_path):
        """Existing file passes validation."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        manager = WorkspaceManager(tmp_path)
        # Should not raise
        manager.validate_existing_file_path(str(test_file))

    def test_nonexistent_file_raises(self, tmp_path):
        """Nonexistent file raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="does not exist"):
            manager.validate_existing_file_path(str(tmp_path / "missing.txt"))

    def test_directory_instead_of_file_raises(self, tmp_path):
        """Directory path raises FileSystemValidationError."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="is not a file"):
            manager.validate_existing_file_path(str(subdir))

    def test_validates_boundary_first(self, tmp_path):
        """validate_existing_file_path checks boundary before existence."""
        manager = WorkspaceManager(tmp_path)
        # /etc/passwd exists but is outside workspace
        with pytest.raises(FileSystemValidationError, match="not within workspace"):
            manager.validate_existing_file_path("/etc/passwd")


# =============================================================================
# validate_existing_directory_path Tests
# =============================================================================

class TestValidateExistingDirectoryPath:
    """Tests for WorkspaceManager.validate_existing_directory_path method."""

    def test_valid_existing_directory(self, tmp_path):
        """Existing directory passes validation."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        
        manager = WorkspaceManager(tmp_path)
        # Should not raise
        manager.validate_existing_directory_path(str(subdir))

    def test_workspace_root_is_valid(self, tmp_path):
        """Workspace root directory is valid."""
        manager = WorkspaceManager(tmp_path)
        manager.validate_existing_directory_path(str(tmp_path))

    def test_nonexistent_directory_raises(self, tmp_path):
        """Nonexistent directory raises FileSystemValidationError."""
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="does not exist"):
            manager.validate_existing_directory_path(str(tmp_path / "missing"))

    def test_file_instead_of_directory_raises(self, tmp_path):
        """File path raises FileSystemValidationError."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")
        
        manager = WorkspaceManager(tmp_path)
        with pytest.raises(FileSystemValidationError, match="is not a directory"):
            manager.validate_existing_directory_path(str(test_file))

    def test_validates_boundary_first(self, tmp_path):
        """validate_existing_directory_path checks boundary before existence."""
        manager = WorkspaceManager(tmp_path)
        # /tmp exists but may be outside workspace
        with pytest.raises(FileSystemValidationError):
            manager.validate_existing_directory_path("/tmp")


# =============================================================================
# Integration Tests
# =============================================================================

class TestWorkspaceManagerIntegration:
    """Integration tests for WorkspaceManager."""

    def test_typical_file_workflow(self, tmp_path):
        """Test typical file creation and validation workflow."""
        manager = WorkspaceManager(tmp_path)
        
        # Create a file
        test_file = tmp_path / "new_file.txt"
        test_file.write_text("Hello, World!")
        
        # Validate it exists
        manager.validate_existing_file_path(str(test_file))
        
        # Create a subdirectory
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        manager.validate_existing_directory_path(str(subdir))
        
        # Create file in subdirectory
        nested_file = subdir / "nested.txt"
        nested_file.write_text("Nested content")
        manager.validate_existing_file_path(str(nested_file))

    def test_boundary_enforcement_prevents_escape(self, tmp_path):
        """Test that boundary checks prevent workspace escape."""
        workspace = tmp_path / "workspace"
        secrets = tmp_path / "secrets"
        workspace.mkdir()
        secrets.mkdir()
        (secrets / "password.txt").write_text("secret123")
        
        manager = WorkspaceManager(workspace)
        
        # Cannot access sibling directory
        assert manager.validate_boundary(secrets) is False
        
        # Cannot validate sibling files
        with pytest.raises(FileSystemValidationError):
            manager.validate_path(str(secrets / "password.txt"))

    def test_nested_workspace(self, tmp_path):
        """Test workspace can be nested inside another directory."""
        outer = tmp_path / "outer"
        inner = outer / "inner"
        inner.mkdir(parents=True)
        
        manager = WorkspaceManager(inner)
        
        # Inner paths are valid
        assert manager.validate_boundary(inner / "file.txt") is True
        
        # Outer path is invalid
        assert manager.validate_boundary(outer) is False
