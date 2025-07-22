"""Agent tool for launching sub-agents to handle complex tasks."""

import asyncio
import time
from typing import Annotated, Dict, Any, List, Optional
from pydantic import Field
from ii_tool.tools.base import BaseTool
from ii_tool.core.agent_executor import AgentExecutor

DESCRIPTION = """Launch a new agent that has access to the following tools: Bash, Glob, Grep, LS, exit_plan_mode, Read, Edit, MultiEdit, Write, NotebookRead, NotebookEdit, WebFetch, TodoRead, TodoWrite, WebSearch, mcp__ide__getDiagnostics, mcp__ide__executeCode. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries, use the Agent tool to perform the search for you.

When to use the Agent tool:
- If you are searching for a keyword like "config" or "logger", or for questions like "which file does X?", the Agent tool is strongly recommended

When NOT to use the Agent tool:
- If you want to read a specific file path, use the Read or Glob tool instead of the Agent tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly
- If you are searching for code within a specific file or set of 2-3 files, use the Read tool instead of the Agent tool, to find the match more quickly
- Writing code and running bash commands (use other tools for that)
- Other tasks that are not related to searching for a keyword or file

Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to write code or just to do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent"""

class AgentTool(BaseTool):
    """Tool for launching new agents with specific capabilities."""
    
    name = "Task"
    description = DESCRIPTION

    def _get_agent_prompt(self, task_prompt: str, dangerous_skip_permissions: bool = False) -> str:
        """
        Construct the system prompt for the agent based on the TypeScript implementation.
        
        Args:
            task_prompt: The task description for the agent
            dangerous_skip_permissions: Whether to allow write operations
            
        Returns:
            The formatted system prompt for the agent
        """
        available_tools = [
            'Bash', 'Glob', 'Grep', 'LS', 'exit_plan_mode', 'Read', 'Edit', 
            'MultiEdit', 'Write', 'NotebookRead', 'NotebookEdit', 'WebFetch', 
            'TodoRead', 'TodoWrite', 'WebSearch', 'mcp__ide__getDiagnostics', 
            'mcp__ide__executeCode'
        ]
        
        tool_names = ', '.join(available_tools)
        base_prompt = f"""Launch a new agent that has access to the following tools: {tool_names}. When you are searching for a keyword or file and are not confident that you will find the right match on the first try, use the Agent tool to perform the search for you. For example:

- If you are searching for a keyword like "config" or "logger", the Agent tool is appropriate
- If you want to read a specific file path, use the Read or Glob tool instead of the Agent tool, to find the match more quickly
- If you are searching for a specific class definition like "class Foo", use the Glob tool instead, to find the match more quickly

Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted"""

        if not dangerous_skip_permissions:
            base_prompt += """
5. IMPORTANT: The agent can not use Bash, Write, Edit, MultiEdit, NotebookEdit, so can not modify files. If you want to use these tools, use them directly instead of going through the agent."""

        return base_prompt

    def _format_result_for_assistant(self, result: Dict[str, Any]) -> str:
        """
        Format the agent result for return to the calling assistant.
        
        Args:
            result: The agent execution result
            
        Returns:
            Formatted result string
        """
        if result["status"] == "completed":
            stats = []
            if result.get("tool_use_count", 0) > 0:
                stats.append(f"{result['tool_use_count']} tool use{'s' if result['tool_use_count'] != 1 else ''}")
            if result.get("tokens_used", 0) > 0:
                stats.append(f"{result['tokens_used']} tokens")
            if result.get("duration_ms", 0) > 0:
                stats.append(f"{result['duration_ms']}ms")
            
            base_result = result.get("final_message", result.get("result", "Agent completed successfully"))
            
            if stats:
                return f"{base_result}\n\nExecution summary: {' · '.join(stats)}"
            else:
                return base_result
        else:
            return f"Agent execution failed: {result.get('error', 'Unknown error')}"

    def run_impl(
        self,
        prompt: Annotated[str, Field(description="The task for the agent to perform")],
        dangerous_skip_permissions: Annotated[Optional[bool], Field(description="Allow the agent to use write tools", default=False)],
    ) -> str:
        """
        Execute the agent with the given task.
        
        Args:
            prompt: Detailed task description for the agent
            dangerous_skip_permissions: Whether to allow write operations
            
        Returns:
            The agent's execution result formatted for the assistant
        """
        try:
            # Create agent executor
            executor = AgentExecutor(dangerous_skip_permissions or False)
            
            # Execute the agent task
            result = asyncio.run(executor.execute_agent_task(
                prompt=prompt,
                description="Agent task execution",
                max_thinking_tokens=0,
                model="claude-3-5-sonnet-20241022"
            ))
            
            # Format and return the result
            return self._format_result_for_assistant(result)
            
        except Exception as e:
            return f"Agent execution failed: {str(e)}"