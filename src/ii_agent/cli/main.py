"""
Main CLI entry point for ii-agent.

This module provides the command-line interface for interacting with the AgentController.
"""

import argparse
import asyncio
import json
import sys
import os
from pathlib import Path
from typing import Optional, List

from ii_agent.cli.app import CLIApp
from ii_agent.cli.config import setup_cli_config


def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="ii-agent",
        description="Intelligent Internet Agent - CLI interface for AI-powered automation",
        epilog="Use 'ii-agent <command> --help' for command-specific help.",
    )
    
    # Global options
    parser.add_argument(
        "--workspace", 
        "-w", 
        type=str, 
        default=".", 
        help="Working directory for the agent (default: current directory)"
    )
    parser.add_argument(
        "--config", 
        "-c", 
        type=str, 
        help="Configuration file path"
    )
    parser.add_argument(
        "--mcp-config",
        type=str,
        help="MCP configuration file path"
    )
    parser.add_argument(
        "--minimal", 
        "-m", 
        action="store_true", 
        help="Minimize output"
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Chat command (interactive mode)
    chat_parser = subparsers.add_parser(
        "chat", 
        help="Start interactive chat session"
    )
    chat_parser.add_argument(
        "--session", 
        "-s", 
        type=str, 
        help="Session name to save/restore conversation"
    )
    chat_parser.add_argument(
        "--resume", 
        "-r", 
        action="store_true", 
        help="Resume from previous session"
    ) 
    
    # Config command
    config_parser = subparsers.add_parser(
        "config", 
        help="Manage configuration"
    )
    config_group = config_parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument(
        "--show", 
        action="store_true", 
        help="Show current configuration"
    )
    config_group.add_argument(
        "--set", 
        nargs=2, 
        metavar=("KEY", "VALUE"), 
        help="Set configuration value"
    )
    config_group.add_argument(
        "--reset", 
        action="store_true", 
        help="Reset configuration to defaults"
    )
    
    # LLM configuration options
    parser.add_argument(
        "--llm-provider", 
        choices=["anthropic", "openai", "gemini"], 
        help="LLM provider to use"
    )
    parser.add_argument(
        "--llm-model", 
        type=str, 
        help="Specific model to use"
    )
    parser.add_argument(
        "--max-tokens", 
        type=int, 
        help="Maximum tokens per turn"
    )
    parser.add_argument(
        "--temperature", 
        type=float, 
        help="Temperature for LLM responses"
    )
    parser.add_argument(
        "--tools", 
        nargs="*", 
        help="Specific tools to enable"
    )
    
    return parser


def validate_args(args: argparse.Namespace) -> None:
    """Validate command-line arguments."""
    
    if args.workspace:
        workspace_path = Path(args.workspace)
        if not workspace_path.exists():
            print(f"Error: Workspace directory '{args.workspace}' does not exist")
            sys.exit(1)
        if not workspace_path.is_dir():
            print(f"Error: Workspace path '{args.workspace}' is not a directory")
            sys.exit(1)
    
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Configuration file '{args.config}' does not exist")
            sys.exit(1)


async def main_async() -> int:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    
    # Show help if no command is provided
    if not args.command:
        parser.print_help()
        return 0
    
    # Validate arguments
    validate_args(args)
    
    try:
        # Setup CLI configuration using the new pattern
        config, llm_config, workspace_path = await setup_cli_config(
            workspace=args.workspace,
            model=args.llm_model,
            temperature=args.temperature,
        )
        
        # Handle config command
        if args.command == "config":
            return await handle_config_command(args, config, llm_config)

        if args.mcp_config:
            mcp_config = json.load(open(args.mcp_config))
            assert "mcpServers" in mcp_config, "mcpServers not found in MCP config"
            print(mcp_config)
        
        # Create and run CLI app
        app = CLIApp(config, llm_config, workspace_path, minimal=args.minimal, mcp_config=mcp_config)
        
        if args.command == "chat":
            return await app.run_interactive_mode(
                session_name=args.session,
                resume=args.resume
            )
        else:
            print(f"Unknown command: {args.command}")
            return 1
            
    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
        return 130
    except Exception as e:
        if args.debug:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}")
        return 1


async def handle_config_command(args: argparse.Namespace, config, llm_config) -> int:
    """Handle configuration commands."""
    if args.show:
        print("Current Configuration:")
        print("-" * 30)
        print(f"LLM Model: {llm_config.model}")
        print(f"Temperature: {llm_config.temperature}")
        print(f"Max Output Tokens: {config.max_output_tokens_per_turn}")
        print(f"Max Turns: {config.max_turns}")
        return 0
    elif args.set:
        key, value = args.set
        print(f"Setting {key} = {value} (feature not yet implemented)")
        return 0
    elif args.reset:
        print("Reset configuration (feature not yet implemented)")
        return 0
    
    return 1


def main():
    """Entry point for the CLI script."""
    try:
        exit_code = asyncio.run(main_async())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()