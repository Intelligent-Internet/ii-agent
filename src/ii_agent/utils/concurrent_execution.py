"""Concurrent execution utilities for parallel tool execution.

This module provides utilities for running async generators concurrently,
inspired by Claude Code's parallel tool execution architecture. It implements
a Promise.race()-based approach for dynamic concurrency control.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, TypeVar, List, Set, Optional
from dataclasses import dataclass

T = TypeVar('T')

# Maximum concurrent tool executions
MAX_TOOL_CONCURRENCY = 10


@dataclass
class QueuedGenerator:
    """Represents a queued async generator result."""
    done: bool
    value: Optional[T]
    generator: AsyncGenerator[T, None]
    task: asyncio.Task


async def run_generator_step(generator: AsyncGenerator[T, None]) -> QueuedGenerator[T]:
    """Run one step of an async generator and return the result."""
    try:
        result = await generator.__anext__()
        return QueuedGenerator(
            done=False,
            value=result,
            generator=generator,
            task=None  # Will be set by caller
        )
    except StopAsyncIteration:
        return QueuedGenerator(
            done=True,
            value=None,
            generator=generator,
            task=None
        )


async def all_concurrent(
    generators: List[AsyncGenerator[T, None]],
    concurrency_limit: int = MAX_TOOL_CONCURRENCY,
    abort_signal: Optional[asyncio.Event] = None
) -> AsyncGenerator[T, None]:
    """
    Run multiple async generators concurrently with a concurrency limit.
    
    This is inspired by Claude Code's Promise.race()-based approach, adapted for Python.
    It dynamically manages a pool of running generators, starting new ones as others complete.
    
    Args:
        generators: List of async generators to run
        concurrency_limit: Maximum number of generators to run simultaneously
        
    Yields:
        Values from the generators as they become available
    """
    if not generators:
        return
    
    waiting = list(generators)
    running_tasks: Set[asyncio.Task] = set()
    
    # Create a task for running one step of a generator
    def create_task(gen: AsyncGenerator[T, None]) -> asyncio.Task:
        task = asyncio.create_task(run_generator_step(gen))
        task.generator = gen  # Store reference to generator
        return task
    
    # Start initial batch up to concurrency limit
    while len(running_tasks) < concurrency_limit and waiting:
        generator = waiting.pop(0)
        task = create_task(generator)
        running_tasks.add(task)
    
    # Process generators as they complete
    while running_tasks:
        # Check for abort signal
        if abort_signal and abort_signal.is_set():
            # Cancel all running tasks
            for task in running_tasks:
                task.cancel()
            break
            
        # Wait for any task to complete
        done_tasks, _ = await asyncio.wait(running_tasks, return_when=asyncio.FIRST_COMPLETED)
        
        for task in done_tasks:
            running_tasks.remove(task)
            
            try:
                result = await task
                
                if not result.done:
                    # Generator has more values, restart it
                    new_task = create_task(result.generator)
                    running_tasks.add(new_task)
                    
                    # Yield the value if it's not None
                    if result.value is not None:
                        yield result.value
                        
                elif waiting:
                    # Generator is done, start a new one if available
                    next_generator = waiting.pop(0)
                    new_task = create_task(next_generator)
                    running_tasks.add(new_task)
                    
            except Exception as e:
                # Log error but continue with other generators
                import logging
                logging.error(f"Error in concurrent generator execution: {e}")
                
                # Start a new generator if available to maintain concurrency
                if waiting:
                    next_generator = waiting.pop(0)
                    new_task = create_task(next_generator)
                    running_tasks.add(new_task)


async def run_tools_concurrently(
    tool_generators: List[AsyncGenerator[T, None]],
    concurrency_limit: int = MAX_TOOL_CONCURRENCY,
    abort_signal: Optional[asyncio.Event] = None
) -> AsyncGenerator[T, None]:
    """
    Execute tool generators concurrently.
    
    Args:
        tool_generators: List of tool execution generators
        concurrency_limit: Maximum concurrent executions
        abort_signal: Optional event to signal abortion
        
    Yields:
        Tool results as they complete
    """
    async for result in all_concurrent(tool_generators, concurrency_limit, abort_signal):
        yield result


async def run_tools_serially(
    tool_generators: List[AsyncGenerator[T, None]]
) -> AsyncGenerator[T, None]:
    """
    Execute tool generators serially (one after another).
    
    Args:
        tool_generators: List of tool execution generators
        
    Yields:
        Tool results in order of completion
    """
    for generator in tool_generators:
        async for result in generator:
            yield result


def should_run_concurrently(tools: List, tool_manager) -> bool:
    """
    Determine if tools should run concurrently based on read-only status.
    
    Tools run concurrently ONLY if ALL tools are read-only.
    
    Args:
        tools: List of tool call parameters
        tool_manager: Tool manager instance to look up tools
        
    Returns:
        True if all tools are read-only, False otherwise
    """
    try:
        for tool_call in tools:
            tool = tool_manager.get_tool(tool_call.tool_name)
            if not tool.is_read_only():
                return False
        return True
    except Exception:
        # If we can't determine read-only status, err on the side of caution
        return False