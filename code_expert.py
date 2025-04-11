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


def run_code_expert_agent(
    task: str,
):
    """Main entry point for the CLI."""

    # Initialize LLM client
    client = get_client(
        "anthropic-direct",
        model_name="claude-3-7-sonnet@20250219",
        use_caching=False,
    )

    # Initialize workspace manager
    workspace_path = Path("temp").resolve()
    if not workspace_path.exists():
        workspace_path.mkdir(parents=True)
    workspace_manager = WorkspaceManager(
        root=workspace_path,
    )
    console = Console()
    logger_for_agent_logs = logging.getLogger("agent_logs")
    logger_for_agent_logs.setLevel(logging.DEBUG)
    logger_for_agent_logs.addHandler(logging.FileHandler("temp/agent_logs.txt"))


    # Initialize agent
    agent = Agent(
        client=client,
        workspace_manager=workspace_manager,
        console=console,
        logger_for_agent_logs=logger_for_agent_logs,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        ask_user_permission=False,
        docker_container_id=None,
    )

    instruction = None

    history = InMemoryHistory()
    try:
        if instruction is None:
            user_input = task
            history.append_string(task)
        else:
            user_input = instruction
            logger_for_agent_logs.info(f"User instruction:\n{user_input}\n-------------\n")
            console.print(f"User instruction:\n{user_input}\n-------------\n")
        logger_for_agent_logs.info("Agent is thinking...")
        console.print("Agent is thinking...")
        try:
            result = agent.run_agent(user_input, resume=True)
            logger_for_agent_logs.info(f"Agent: {result}")
            console.print(f"Agent: {result}")
        except Exception as e:
            logger_for_agent_logs.info(f"Error: {str(e)}")
            console.print(f"Error: {str(e)}")
        logger_for_agent_logs.info("\n" + "-" * 40 + "\n")
        console.print("\n" + "-" * 40 + "\n")
    except:
        console.print("Error!!!!")        

if __name__ == "__main__":
    run_code_expert_agent("Write a simple python script that prints 'Hello, World!'")