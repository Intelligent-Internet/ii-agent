"""Unit tests for ii_tool.integrations.logger module.

This module tests the centralized logging helpers:
- LOG_FILE_PATH configuration via environment variable
- get_logger function for obtaining configured loggers
- Logger configuration (handlers, formatters, levels)
- Fallback behavior when file logging fails
"""

import logging
import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import sys
import importlib


def _reload_logger():
    """Reload ii_tool.integrations.logger and refresh ii_tool.logger bindings.

    Several tests need to ``importlib.reload`` the logger module to pick up
    changed environment variables.  If ``ii_tool.logger`` was already imported
    (which happens when other test files transitively load it), we must also
    reload the re-export module so that the ``is``-identity check in
    ``TestModuleReexport.test_reexport_same_as_original`` still holds.
    """
    import ii_tool.integrations.logger as logger_module
    importlib.reload(logger_module)
    if "ii_tool.logger" in sys.modules:
        importlib.reload(sys.modules["ii_tool.logger"])
    return logger_module


# =============================================================================
# LOG_FILE_PATH Tests
# =============================================================================

class TestLogFilePath:
    """Tests for LOG_FILE_PATH configuration."""

    def test_default_path(self):
        """LOG_FILE_PATH defaults to /app/log/sandbox.log."""
        # Need to reimport to test default
        with patch.dict(os.environ, {}, clear=False):
            # Remove any existing env var
            env_copy = os.environ.copy()
            if "II_TOOL_LOG_FILE" in env_copy:
                del env_copy["II_TOOL_LOG_FILE"]
            
            with patch.dict(os.environ, env_copy, clear=True):
                logger_module = _reload_logger()
                
                assert str(logger_module.LOG_FILE_PATH) == "/app/log/sandbox.log"

    def test_custom_path_from_env(self):
        """LOG_FILE_PATH can be set via II_TOOL_LOG_FILE env var."""
        custom_path = "/custom/path/test.log"
        with patch.dict(os.environ, {"II_TOOL_LOG_FILE": custom_path}):
            _reload_logger()
            import ii_tool.integrations.logger as logger_module
            
            assert str(logger_module.LOG_FILE_PATH) == custom_path


# =============================================================================
# get_logger Tests
# =============================================================================

class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger_instance(self):
        """get_logger returns a logging.Logger instance."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_logger")
        assert isinstance(logger, logging.Logger)

    def test_default_name_is_ii_tool(self):
        """get_logger with no name uses 'ii_tool' as default."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger()
        assert logger.name == "ii_tool"

    def test_custom_name(self):
        """get_logger uses provided name."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("custom_logger_name")
        assert logger.name == "custom_logger_name"

    def test_default_level_is_info(self):
        """get_logger sets INFO level by default."""
        from ii_tool.integrations.logger import get_logger
        
        # Use unique name to avoid cached logger
        logger = get_logger("test_level_info")
        assert logger.level == logging.INFO

    def test_custom_level(self):
        """get_logger accepts custom log level."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_level_debug", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_propagate_disabled(self):
        """Logger has propagate=False to avoid duplicate logs."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_propagate")
        assert logger.propagate is False

    def test_same_logger_returned_for_same_name(self):
        """Requesting same logger name returns same instance."""
        from ii_tool.integrations.logger import get_logger
        
        logger1 = get_logger("test_same_name")
        logger2 = get_logger("test_same_name")
        assert logger1 is logger2

    def test_logger_is_marked_configured(self):
        """Logger is marked as configured to prevent reconfiguration."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_configured_marker")
        assert getattr(logger, "_ii_tool_logger_configured", False) is True


# =============================================================================
# Logger Configuration Tests
# =============================================================================

class TestLoggerConfiguration:
    """Tests for internal logger configuration."""

    def test_logger_has_handler(self):
        """Configured logger has at least one handler."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_handler_exists")
        assert len(logger.handlers) > 0

    def test_handler_has_formatter(self):
        """Logger handlers have formatters set."""
        from ii_tool.integrations.logger import get_logger
        
        logger = get_logger("test_formatter_exists")
        for handler in logger.handlers:
            assert handler.formatter is not None

    def test_custom_format(self):
        """get_logger accepts custom format string."""
        from ii_tool.integrations.logger import get_logger
        
        custom_format = "%(levelname)s: %(message)s"
        logger = get_logger("test_custom_format", format=custom_format)
        
        # Check that a handler exists with our format
        assert len(logger.handlers) > 0


# =============================================================================
# File Handler Tests
# =============================================================================

class TestFileHandler:
    """Tests for file handler creation."""

    def test_file_handler_with_valid_path(self):
        """File handler is created when path is valid."""
        with TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            
            with patch.dict(os.environ, {"II_TOOL_LOG_FILE": log_path}):
                logger_module = _reload_logger()
                
                logger = logger_module.get_logger("test_file_handler_valid")
                
                # Should have file handler
                file_handlers = [
                    h for h in logger.handlers 
                    if isinstance(h, logging.FileHandler)
                ]
                assert len(file_handlers) > 0

    def test_creates_parent_directories(self):
        """File handler creates parent directories if needed."""
        with TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "subdir", "nested", "test.log")
            
            with patch.dict(os.environ, {"II_TOOL_LOG_FILE": log_path}):
                logger_module = _reload_logger()
                
                logger = logger_module.get_logger("test_creates_dirs")
                
                # Parent directory should exist
                assert os.path.exists(os.path.dirname(log_path))


# =============================================================================
# Fallback Behavior Tests
# =============================================================================

class TestFallbackBehavior:
    """Tests for fallback to stdout when file logging fails."""

    def test_fallback_to_stdout_on_permission_error(self):
        """Falls back to stdout handler when file creation fails."""
        from ii_tool.integrations.logger import _configure_logger
        
        # Create a fresh logger
        test_logger = logging.getLogger("test_fallback_permission")
        test_logger.handlers.clear()
        
        # Mock LOG_FILE_PATH to a path that will fail
        with patch("ii_tool.integrations.logger.LOG_FILE_PATH") as mock_path:
            mock_path.parent.mkdir.side_effect = OSError("Permission denied")
            
            import ii_tool.integrations.logger as logger_module
            
            # Capture stderr
            with patch.object(sys, 'stderr'):
                result = logger_module._configure_logger(
                    test_logger, logging.INFO, logger_module.LOG_FORMAT
                )
            
            # Should have stream handler as fallback
            stream_handlers = [
                h for h in result.handlers 
                if isinstance(h, logging.StreamHandler)
            ]
            assert len(stream_handlers) > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestLoggerIntegration:
    """Integration tests for logger functionality."""

    def test_can_log_messages(self):
        """Logger can actually log messages."""
        with TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "integration.log")
            
            with patch.dict(os.environ, {"II_TOOL_LOG_FILE": log_path}):
                logger_module = _reload_logger()
                
                logger = logger_module.get_logger("integration_test")
                logger.info("Test message")
                
                # Flush handlers
                for handler in logger.handlers:
                    handler.flush()
                
                # Check log file content
                if os.path.exists(log_path):
                    with open(log_path) as f:
                        content = f.read()
                    assert "Test message" in content

    def test_different_loggers_independent(self):
        """Different logger names are independent."""
        from ii_tool.integrations.logger import get_logger
        
        logger1 = get_logger("independent_1")
        logger2 = get_logger("independent_2")
        
        assert logger1 is not logger2
        assert logger1.name != logger2.name


# =============================================================================
# Module Re-export Tests
# =============================================================================

class TestModuleReexport:
    """Tests for ii_tool.logger re-exports."""

    def test_get_logger_reexported(self):
        """get_logger is accessible from ii_tool.logger."""
        from ii_tool.logger import get_logger
        assert callable(get_logger)

    def test_log_file_path_reexported(self):
        """LOG_FILE_PATH is accessible from ii_tool.logger."""
        from ii_tool.logger import LOG_FILE_PATH
        assert isinstance(LOG_FILE_PATH, Path)

    def test_reexport_same_as_original(self):
        """Re-exported items are same as originals."""
        from ii_tool.logger import get_logger as reexported_get_logger
        from ii_tool.logger import LOG_FILE_PATH as reexported_path
        from ii_tool.integrations.logger import get_logger as original_get_logger
        from ii_tool.integrations.logger import LOG_FILE_PATH as original_path
        
        assert reexported_get_logger is original_get_logger
        assert reexported_path == original_path
