#!/usr/bin/env python3
"""
CLI interface for the Agent.

This script provides a command-line interface for interacting with the Agent.
It instantiates an Agent and prompts the user for input, which is then passed to the Agent.
"""

import os
import argparse
import logging
import asyncio
from dotenv import load_dotenv

from ii_agent.llm.message_history import MessageHistory

load_dotenv()

from ii_agent.core.event import RealtimeEvent, EventType
from ii_agent.utils.constants import TOKEN_BUDGET
from utils import parse_common_args, create_workspace_manager_for_connection
from rich.console import Console
from rich.panel import Panel

from ii_agent.tools import get_system_tools
from ii_agent.prompts.system_prompt import SYSTEM_PROMPT
from ii_agent.prompts.reviewer_system_prompt import REVIEWER_SYSTEM_PROMPT
from ii_agent.agents.function_call import FunctionCallAgent
from ii_agent.agents.reviewer import ReviewerAgent
from ii_agent.utils import WorkspaceManager
from ii_agent.llm import get_client
from ii_agent.llm.context_manager.llm_summarizing import LLMSummarizingContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.db.manager import Sessions

MAX_OUTPUT_TOKENS_PER_TURN = 32768
MAX_TURNS = 200


async def async_main():
    """Async main entry point"""
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description="CLI for interacting with the Agent")
    parser = parse_common_args(parser)

    args = parser.parse_args()

    if os.path.exists(args.logs_path):
        os.remove(args.logs_path)
    logger_for_agent_logs = logging.getLogger("agent_logs")
    logger_for_agent_logs.setLevel(logging.DEBUG)
    # Prevent propagation to root logger to avoid duplicate logs
    logger_for_agent_logs.propagate = False
    logger_for_agent_logs.addHandler(logging.FileHandler(args.logs_path))
    if not args.minimize_stdout_logs:
        logger_for_agent_logs.addHandler(logging.StreamHandler())

    # Initialize console
    console = Console()

    # Create a new workspace manager for the CLI session
    workspace_manager, session_id = create_workspace_manager_for_connection(
        args.workspace, args.use_container_workspace
    )
    workspace_path = workspace_manager.root

    # Create a new session and get its workspace directory
    Sessions.create_session(
        session_uuid=session_id, workspace_path=workspace_manager.root
    )
    logger_for_agent_logs.info(
        f"Created new session {session_id} with workspace at {workspace_manager.root}"
    )

    # Print welcome message
    if not args.minimize_stdout_logs:
        console.print(
            Panel(
                "[bold]Agent CLI[/bold]\n\n"
                + f"Session ID: {session_id}\n"
                + f"Workspace: {workspace_path}\n\n"
                + "Type your instructions to the agent. Press Ctrl+C to exit.\n"
                + "Type 'exit' or 'quit' to end the session.",
                title="[bold blue]Agent CLI[/bold blue]",
                border_style="blue",
                padding=(1, 2),
            )
        )
    else:
        logger_for_agent_logs.info(
            f"Agent CLI started with session {session_id}. Waiting for user input. Press Ctrl+C to exit. Type 'exit' or 'quit' to end the session."
        )

    # Initialize LLM client
    client_kwargs = {
        "model_name": args.model_name,
    }
    if args.llm_client == "anthropic-direct":
        client_kwargs["use_caching"] = False  # Or a configurable value if needed later
        client_kwargs["project_id"] = args.project_id
        client_kwargs["region"] = args.region
    elif args.llm_client == "openai-direct":
        client_kwargs["azure_model"] = args.azure_model
        client_kwargs["cot_model"] = args.cot_model

    client = get_client(args.llm_client, **client_kwargs)

    # Initialize workspace manager with the session-specific workspace
    workspace_manager = WorkspaceManager(
        root=workspace_path, container_workspace=args.use_container_workspace
    )

    # Initialize token counter
    token_counter = TokenCounter()

    # Create context manager based on argument
    context_manager = LLMSummarizingContextManager(
        client=client,
        token_counter=token_counter,
        logger=logger_for_agent_logs,
        token_budget=TOKEN_BUDGET,
    )
    init_history = MessageHistory(context_manager)

    queue = asyncio.Queue()
    tools = get_system_tools(
        client=client,
        workspace_manager=workspace_manager,
        message_queue=queue,
        container_id=args.docker_container_id,
        ask_user_permission=args.needs_permission,
        tool_args={
            "deep_research": False,
            "pdf": True,
            "media_generation": False,
            "audio_generation": False,
            "browser": True,
            "memory_tool": args.memory_tool,
        },
    )
    agent = FunctionCallAgent(
        system_prompt=SYSTEM_PROMPT,
        client=client,
        workspace_manager=workspace_manager,
        tools=tools,
        message_queue=queue,
        logger_for_agent_logs=logger_for_agent_logs,
        init_history=init_history,
        max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
        max_turns=MAX_TURNS,
        session_id=session_id,  # Pass the session_id from database manager
    )


    # Create reviewer agent only if enabled
    enable_reviewer = args.enable_reviewer if hasattr(args, 'enable_reviewer') else False
    reviewer_agent = None
    
    if enable_reviewer:
        reviewer_agent = ReviewerAgent(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            client=client,
            tools=tools,
            workspace_manager=workspace_manager,
            message_queue=queue,
            logger_for_agent_logs=logger_for_agent_logs,
            context_manager=context_manager,
            max_output_tokens_per_turn=MAX_OUTPUT_TOKENS_PER_TURN,
            max_turns=MAX_TURNS,
            session_id=session_id,
        )

    # Create background task for message processing
    message_task = agent.start_message_processing()
    reviewer_message_task = None
    if reviewer_agent:
        reviewer_message_task = reviewer_agent.start_message_processing()

    loop = asyncio.get_running_loop()
    # Main interaction loop
    try:
        while True:
            # Use async input
            if args.prompt is None:
                user_input = await loop.run_in_executor(
                    None, lambda: input("User input: ")
                )
            else:
                user_input = args.prompt

            agent.message_queue.put_nowait(
                RealtimeEvent(type=EventType.USER_MESSAGE, content={"text": user_input})
            )

            if user_input.lower() in ["exit", "quit"]:
                console.print("[bold]Exiting...[/bold]")
                logger_for_agent_logs.info("Exiting...")
                break

            logger_for_agent_logs.info("\nAgent is thinking...")
            try:
                # Run the agent using the new async method
                result = await agent.run_agent_async(user_input, resume=True)
                
                # Extract final result for reviewer
                final_result = ""
                for message in agent.history._message_lists[::-1]:
                    message = message[0]
                    if str(type(message)) == "ToolFormattedResult" and message.tool_name == "message_user":
                        final_result = message.tool_output
                        break
                        
                logger_for_agent_logs.info(f"Agent: {result}")
                
                # Run reviewer if enabled
                if reviewer_agent and final_result:
                    logger_for_agent_logs.info("\nReviewer agent is analyzing the output...")
                    status = await loop.run_in_executor(
                        None,  # Uses default ThreadPoolExecutor
                        lambda: reviewer_agent.run_agent(
                            task=user_input,
                            result=final_result,
                            workspace_dir=str(workspace_path),
                        ),
                    )
                    
                    # Extract reviewer feedback
                    try:
                        review_result = reviewer_agent.history._message_lists[-1][0].text
                    except:
                        try:
                            review_result = reviewer_agent.history._message_lists[-2][0].text
                        except:
                            review_result = ""
                    
                    if review_result:
                        logger_for_agent_logs.info(f"Reviewer: {review_result}")
                    
                    # Continue agent with reviewer feedback
                    if review_result and review_result.strip():
                        logger_for_agent_logs.info("\nFeeding reviewer feedback to agent for improvement...")
                        feedback_prompt = f"""Based on the reviewer's analysis, here is the feedback for improvement:

{review_result}

Please review this feedback and implement the suggested improvements to better complete the original task: "{user_input}"
"""
                        
                        # Run agent with reviewer feedback
                        improved_result = await agent.run_agent_async(feedback_prompt, resume=True)
                        logger_for_agent_logs.info(f"Agent improvement response: {improved_result}")
            except (KeyboardInterrupt, asyncio.CancelledError):
                agent.cancel()
                logger_for_agent_logs.info("Agent cancelled")
            except Exception as e:
                logger_for_agent_logs.info(f"Error: {str(e)}")
                logger_for_agent_logs.debug("Full error:", exc_info=True)

            logger_for_agent_logs.info("\n" + "-" * 40 + "\n")

    except KeyboardInterrupt:
        console.print("\n[bold]Session interrupted. Exiting...[/bold]")
        loop.stop()
    finally:
        # Cleanup tasks
        message_task.cancel()
        if reviewer_message_task:
            reviewer_message_task.cancel()

    console.print("[bold]Goodbye![/bold]")


if __name__ == "__main__":
    asyncio.run(async_main())
