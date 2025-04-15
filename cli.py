#!/usr/bin/env python3
"""
CLI interface for the Agent.

This script provides a command-line interface for interacting with the Agent.
It instantiates an Agent and prompts the user for input, which is then passed to the Agent.
"""

import os
import argparse
from pathlib import Path
import sys
import logging

from rich.console import Console
from rich.panel import Panel
from prompt_toolkit import prompt
from prompt_toolkit.history import InMemoryHistory

from tools.agent import Agent
from utils.workspace_manager import WorkspaceManager
from utils.llm_client import get_client
from prompts.instruction import INSTRUCTION_PROMPT
from dotenv import load_dotenv

load_dotenv()
MAX_OUTPUT_TOKENS_PER_TURN = 32768
MAX_TURNS = 200


def main():
    """Main entry point for the CLI."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="CLI for interacting with the Agent")
    parser.add_argument(
        "--workspace",
        type=str,
        default="./workspace",
        help="Path to the workspace",
    )
    parser.add_argument(
        "--problem-statement",
        type=str,
        default=None,
        help="Problem statement to pass to the agent. Makes the agent non-interactive.",
    )
    parser.add_argument(
        "--logs-path",
        type=str,
        default="agent_logs.txt",
        help="Path to save logs",
    )
    parser.add_argument(
        "--needs-permission",
        "-p",
        help="Ask for permission before executing commands",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--use-container-workspace",
        type=str,
        default=None,
        help="(Optional) Path to the container workspace to run commands in.",
    )
    parser.add_argument(
        "--docker-container-id",
        type=str,
        default=None,
        help="(Optional) Docker container ID to run commands in.",
    )
    parser.add_argument(
        "--minimize-stdout-logs",
        help="Minimize the amount of logs printed to stdout.",
        action="store_true",
        default=False,
    )

    args = parser.parse_args()

    if os.path.exists(args.logs_path):
        os.remove(args.logs_path)
    logger_for_agent_logs = logging.getLogger("agent_logs")
    logger_for_agent_logs.setLevel(logging.DEBUG)
    logger_for_agent_logs.addHandler(logging.FileHandler(args.logs_path))
    if not args.minimize_stdout_logs:
        logger_for_agent_logs.addHandler(logging.StreamHandler())
    else:
        logger_for_agent_logs.propagate = False



    # Initialize console
    console = Console()

    # Print welcome message
    if not args.minimize_stdout_logs:
        console.print(
            Panel(
                "[bold]Agent CLI[/bold]\n\n"
                + "Type your instructions to the agent. Press Ctrl+C to exit.\n"
                + "Type 'exit' or 'quit' to end the session.",
                title="[bold blue]Agent CLI[/bold blue]",
                border_style="blue",
                padding=(1, 2),
            )
        )
    else:
        logger_for_agent_logs.info(
            "Agent CLI started. Waiting for user input. Press Ctrl+C to exit. Type 'exit' or 'quit' to end the session."
        )

    # Initialize LLM client
    client = get_client(
        "anthropic-direct",
        model_name="claude-3-7-sonnet@20250219",
        use_caching=False,
    )

    # Initialize workspace manager
    workspace_path = Path(args.workspace).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path, container_workspace=args.use_container_workspace
    )

    # Initialize agent
    agent = Agent(
        client=client,
        workspace_manager=workspace_manager,
        console=console,
        logger_for_agent_logs=logger_for_agent_logs,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        ask_user_permission=args.needs_permission,
        docker_container_id=args.docker_container_id,
    )

    if args.problem_statement is not None:
        instruction = INSTRUCTION_PROMPT.format(
            location=(
                workspace_path
                if args.use_container_workspace is None
                else args.use_container_workspace
            ),
            pr_description=args.problem_statement,
        )
    else:
        instruction = None

    history = InMemoryHistory()
    # Main interaction loop
    try:
        while True:
            # Get user input
            if instruction is None:
                user_input = prompt("User input: ", history=history)
                history.append_string(user_input)

                # Check for exit commands
                if user_input.lower() in ["exit", "quit"]:
                    console.print("[bold]Exiting...[/bold]")
                    logger_for_agent_logs.info("Exiting...")
                    break
            else:
                user_input = instruction
                logger_for_agent_logs.info(
                    f"User instruction:\n{user_input}\n-------------"
                )

            # Run the agent with the user input
            logger_for_agent_logs.info("\nAgent is thinking...")
            try:
                result = agent.run_agent(user_input, resume=True)
                logger_for_agent_logs.info(f"Agent: {result}")
            except Exception as e:
                logger_for_agent_logs.info(f"Error: {str(e)}")

            logger_for_agent_logs.info("\n" + "-" * 40 + "\n")

            if instruction is not None:
                break

    except KeyboardInterrupt:
        console.print("\n[bold]Session interrupted. Exiting...[/bold]")

    console.print("[bold]Goodbye![/bold]")
    #import ipdb; ipdb.set_trace()


if __name__ == "__main__":
    main()
