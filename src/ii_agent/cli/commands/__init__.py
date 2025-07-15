"""
Command system for the CLI.

This module provides the command infrastructure for handling slash commands
in the CLI interface.
"""

from .command_handler import CommandHandler
from .base_command import BaseCommand

__all__ = ['CommandHandler', 'BaseCommand']