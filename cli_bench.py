#!/usr/bin/env python3
"""
CLI interface for the Agent.

This script provides a command-line interface for interacting with the Agent.
It instantiates an Agent and prompts the user for input, which is then passed to the Agent.
"""

import os
import argparse
from pathlib import Path
import logging
import json
from utils import parse_common_args
from rich.console import Console
from rich.panel import Panel

from ii_agent.agents.anthropic_fc import AnthropicFC
from ii_agent.utils import WorkspaceManager
from ii_agent.llm import get_client
from dotenv import load_dotenv
from ii_agent.llm.context_manager.file_based import FileBasedContextManager
from ii_agent.llm.context_manager.standard import StandardContextManager
from ii_agent.llm.token_counter import TokenCounter

load_dotenv()
MAX_OUTPUT_TOKENS_PER_TURN = 32768
MAX_TURNS = 200
BASE_LOG_DIR = "logs"
os.makedirs(BASE_LOG_DIR, exist_ok=True)


def main():
    """Main entry point for the CLI."""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="CLI for interacting with the Agent")
    parser = parse_common_args(parser)

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
        project_id=args.project_id,
        region=args.region,
    )

    # Initialize workspace manager
    workspace_path = Path(args.workspace).resolve()
    workspace_manager = WorkspaceManager(
        root=workspace_path, container_workspace=args.use_container_workspace
    )

    # Initialize token counter
    token_counter = TokenCounter()

    # Create context manager based on argument
    if args.context_manager == "file-based":
        context_manager = FileBasedContextManager(
            workspace_dir=workspace_path,
            token_counter=token_counter,
            logger=logger_for_agent_logs,
            token_budget=120_000,
        )
    else:  # standard
        context_manager = StandardContextManager(
            token_counter=token_counter,
            logger=logger_for_agent_logs,
            token_budget=120_000,
        )

    # Initialize agent
    agent = AnthropicFC(
        client=client,
        workspace_manager=workspace_manager,
        logger_for_agent_logs=logger_for_agent_logs,
        context_manager=context_manager,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        ask_user_permission=args.needs_permission,
        docker_container_id=args.docker_container_id,
    )


    user_input = args.task
    task_id = args.task_id
    task_log_dir = f"{BASE_LOG_DIR}/task_{task_id}"
    os.makedirs(task_log_dir, exist_ok=True)
    with open(f"{task_log_dir}/user_input.json", "w") as f:
        json.dump({"user_input": user_input}, f)

    # Run the agent with the user input
    logger_for_agent_logs.info("\nAgent is thinking...")

    result = agent.run_agent(user_input, resume=True, log_dir=task_log_dir)
    logger_for_agent_logs.info(f"Agent: {result}")

    with open(f"{task_log_dir}/agent_output.json", "w") as f:
        json.dump({"agent_output": result}, f)


if __name__ == "__main__":
    main()
