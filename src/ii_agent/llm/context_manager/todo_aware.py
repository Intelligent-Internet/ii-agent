"""Todo-aware context manager that uses TodoWrite calls as natural segmentation points for intelligent summarization."""

import asyncio
from typing import Optional, Any
from dataclasses import dataclass
from ii_agent.llm.base import (
    GeneralContentBlock,
    LLMClient,
    TextPrompt,
    TextResult,
    ToolCall,
    ToolFormattedResult,
    ThinkingBlock,
    RedactedThinkingBlock,
)
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.llm.token_counter import TokenCounter
from ii_agent.utils.constants import TOKEN_BUDGET, SUMMARY_MAX_TOKENS
from ii_agent.core.logger import logger
from ii_agent.llm.context_manager.llm_compact import COMPACT_PROMPT, COMPACT_USER_MESSAGE


@dataclass
class TodoSegment:
    """Represents a segment of conversation between TodoWrite calls."""
    
    start_idx: int
    end_idx: int
    todo_states: list[dict[str, Any]]
    is_completed: bool
    message_count: int
    has_todo_write: bool


class TodoAwareContextManager(ContextManager):
    """Context manager that uses TodoWrite tool calls for intelligent segmentation and summarization.
    
    This manager identifies natural task boundaries through TodoWrite calls and only summarizes
    completed task segments, preserving full context for active work.
    """
    
    def __init__(
        self,
        client: LLMClient,
        token_counter: TokenCounter,
        token_budget: int = TOKEN_BUDGET,
        min_segment_size: int = 3,
        preserve_recent_segments: int = 1,
    ):
        """Initialize the TodoAwareContextManager.
        
        Args:
            client: LLM client for generating summaries
            token_counter: Token counter for managing context size
            token_budget: Maximum tokens allowed in context
            min_segment_size: Minimum messages in a segment before considering summarization
            preserve_recent_segments: Number of recent segments to always keep in full
        """
        super().__init__(token_counter=token_counter, token_budget=token_budget)
        self.client = client
        self.min_segment_size = min_segment_size
        self.preserve_recent_segments = preserve_recent_segments
        self._last_summarized_index = 0
    
    def _find_todo_segments(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[TodoSegment]:
        """Find and analyze segments between TodoWrite calls with success messages.
        
        Args:
            message_lists: List of message lists to analyze
            
        Returns:
            List of TodoSegment objects describing each segment
        """
        segments = []
        current_start = 0
        
        for idx, message_list in enumerate(message_lists):
            has_todo_write = False
            has_success_message = False
            todo_states = []
            
            for message in message_list:
                if isinstance(message, ToolCall) and message.tool_name == "TodoWrite":
                    has_todo_write = True
                    if "todos" in message.tool_input:
                        todos = message.tool_input.get("todos", [])
                        for todo in todos:
                            todo_states.append({
                                "id": todo.get("id"),
                                "content": todo.get("content"),
                                "status": todo.get("status", "pending"),
                                "priority": todo.get("priority", "medium")
                            })
                
                # Check for TodoWrite success message (ToolFormattedResult)
                elif isinstance(message, ToolFormattedResult) and message.tool_name == "TodoWrite":
                    has_success_message = True
            
            # Create segment when we find a TodoWrite success message (not just the call)
            if has_success_message and idx > current_start:
                # Segment is considered "completed" if it has a success message
                # This indicates the TodoWrite operation was successful
                is_completed = True
                
                segments.append(TodoSegment(
                    start_idx=current_start,
                    end_idx=idx,
                    todo_states=todo_states,
                    is_completed=is_completed,
                    message_count=idx - current_start + 1,
                    has_todo_write=has_todo_write
                ))
                current_start = idx + 1
        
        # Handle the final segment
        if current_start < len(message_lists):
            segments.append(TodoSegment(
                start_idx=current_start,
                end_idx=len(message_lists) - 1,
                todo_states=[],
                is_completed=False,  # Current work is never completed
                message_count=len(message_lists) - current_start,
                has_todo_write=False
            ))
        
        return segments
    
    def _should_summarize_segment(
        self, segment: TodoSegment, segment_index: int, total_segments: int
    ) -> bool:
        """Determine if a segment should be summarized.
        
        Args:
            segment: The segment to evaluate
            segment_index: Index of this segment in the list
            total_segments: Total number of segments
            
        Returns:
            True if segment should be summarized
        """
        # Never summarize the current/active segment
        if segment_index >= total_segments - 1:
            return False
        
        # Preserve recent segments based on configuration
        if segment_index >= total_segments - self.preserve_recent_segments - 1:
            return False
        
        # Summarize segments that ended with a TodoWrite success message
        # This indicates the task segment was successfully completed
        if not segment.is_completed:
            return False
        
        return True
    
    def _generate_segment_summary(
        self, 
        message_lists: list[list[GeneralContentBlock]], 
        segment: TodoSegment
    ) -> str:
        """Generate a focused summary for a specific task segment.
        
        Args:
            message_lists: All message lists
            segment: The segment to summarize
            
        Returns:
            Summary text for the segment
        """
        segment_messages = message_lists[segment.start_idx:segment.end_idx + 1]
        
        # Build prompt for segment summarization using LLMCompact style
        prompt = TASK_SEGMENT_SUMMARY_PROMPT
        
        # Add todo context if available
        if segment.todo_states:
            prompt += "\n<todos_context>\n"
            for todo in segment.todo_states:
                status_emoji = "✓" if todo.get("status") == "completed" else "○"
                prompt += f"{status_emoji} [{todo.get('priority')}] {todo.get('content')} - Status: {todo.get('status')}\n"
            prompt += "</todos_context>\n\n"
        
        # Add the segment content
        prompt += "<sub_task>\n"
        for msg_list in segment_messages:
            for message in msg_list:
                if isinstance(message, TextPrompt):
                    prompt += f"USER: {message.text}\n\n"
                elif isinstance(message, TextResult):
                    prompt += f"ASSISTANT: {message.text}\n\n"
                elif isinstance(message, ToolCall):
                    prompt += f"TOOL_CALL [{message.tool_name}]: {message.tool_input}\n\n"
                elif isinstance(message, ToolFormattedResult):
                    # Keep full tool output without truncation
                    prompt += f"TOOL_RESULT [{message.tool_name}]: {message.tool_output}\n\n"
                elif isinstance(message, ThinkingBlock):
                    # Include thinking for context
                    prompt += f"THINKING: {message.thinking}\n\n"
        prompt += "</sub_task>\n"
        
        prompt += "\nNow provide your sub task summary following the structure above."
        
        # Generate summary using LLM
        try:
            summary_messages = [[TextPrompt(text=prompt)]]
            
            # Call the synchronous generate method directly
            model_response, _ = self.client.generate(
                messages=summary_messages,
                max_tokens=SUMMARY_MAX_TOKENS,
                thinking_tokens=0,
                system_prompt="You are a technical assistant that creates focused, accurate summaries of sub tasks, preserving all critical technical details needed for continuity.",
            )
            
            summary = ""
            for message in model_response:
                if isinstance(message, TextResult):
                    summary += message.text
            
            if not summary:
                summary = f"Sub Task {segment.start_idx}-{segment.end_idx}: Work performed on tasks"
            
            logger.info(
                f"Generated summary for segment {segment.start_idx}-{segment.end_idx} "
                f"({segment.message_count} messages)"
            )
            
        except Exception as e:
            logger.error(f"Failed to generate segment summary: {e}")
            summary = f"Failed to summarize segment {segment.start_idx}-{segment.end_idx}: {str(e)}"
        
        return summary
    
    def apply_truncation(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Apply todo-aware truncation to message lists.
        
        This method identifies segments based on TodoWrite calls and summarizes
        completed segments while preserving active work context.
        
        Args:
            message_lists: Original message lists
            
        Returns:
            Truncated message lists with summaries
        """
        if len(message_lists) <= 2:
            return message_lists
        
        # Find todo segments
        segments = self._find_todo_segments(message_lists)
        
        if not segments:
            # Fall back to LLMCompact if no segments found
            logger.info("No todo segments found, falling back to LLMCompact")
            return self._llm_compact_fallback(message_lists)
        
        logger.info(f"Found {len(segments)} todo segments in conversation")
        
        # Count how many segments will be summarized
        summarizable_count = sum(
            1 for idx, segment in enumerate(segments)
            if self._should_summarize_segment(segment, idx, len(segments))
            and segment.start_idx > self._last_summarized_index
        )
        
        if summarizable_count == 0:
            # Fall back to LLMCompact if no segments can be summarized
            logger.info("No segments can be summarized, falling back to LLMCompact")
            return self._llm_compact_fallback(message_lists)
        
        # Build new message list with summaries
        new_messages = []
        
        for idx, segment in enumerate(segments):
            should_summarize = self._should_summarize_segment(
                segment, idx, len(segments)
            )
            
            if should_summarize and segment.start_idx > self._last_summarized_index:
                # Generate and add summary
                summary_text = self._generate_segment_summary(message_lists, segment)
                
                # Add summary as a system message
                summary_message = [TextResult(
                    text=f"[Sub Task {idx+1}]\n{summary_text}"
                )]
                new_messages.append(summary_message)
                
                # If segment has a TodoWrite at the end, preserve it
                if segment.has_todo_write and segment.end_idx < len(message_lists):
                    # Keep the TodoWrite message to maintain task structure
                    for message in message_lists[segment.end_idx]:
                        if isinstance(message, ToolCall) and message.tool_name == "TodoWrite":
                            new_messages.append([message])
                            break
                
                # Update last summarized index
                self._last_summarized_index = max(self._last_summarized_index, segment.end_idx)
                
            else:
                # Keep the segment as-is
                new_messages.extend(
                    message_lists[segment.start_idx:segment.end_idx + 1]
                )
        
        # Log the reduction
        original_count = len(message_lists)
        new_count = len(new_messages)
        logger.info(
            f"Todo-aware truncation: {original_count} -> {new_count} message lists "
            f"({original_count - new_count} consolidated into summaries)"
        )
        
        return new_messages
    
    def _llm_compact_fallback(
        self, message_lists: list[list[GeneralContentBlock]]
    ) -> list[list[GeneralContentBlock]]:
        """Fallback to LLMCompact when no segments can be summarized.
        
        Args:
            message_lists: Original message lists
            
        Returns:
            LLMCompact truncated message lists
        """
        # Create summary request by appending COMPACT_PROMPT as user message
        summary_request_message = [TextPrompt(text=COMPACT_PROMPT)]
        messages_for_summary = message_lists + [summary_request_message]

        # Generate summary using LLM
        try:
            # Use simple system prompt for summarization
            model_response, _ = self.client.generate(
                messages=messages_for_summary,
                max_tokens=SUMMARY_MAX_TOKENS,
                thinking_tokens=0,
                system_prompt="You are a helpful AI assistant tasked with summarizing conversations.",
            )

            # Extract summary text from response
            summary_text = ""
            for message in model_response:
                if isinstance(message, TextResult):
                    summary_text += message.text

            if not summary_text:
                logger.warning("No summary text generated, using fallback")
                summary_text = "Conversation summary could not be generated."

            logger.info(
                f"Generated LLMCompact fallback summary for {len(message_lists)} message lists"
            )

        except Exception as e:
            logger.error(f"Failed to generate LLMCompact fallback summary: {e}")
            summary_text = f"Failed to generate summary due to error: {str(e)}"

        # Return user message about compact command + summary as assistant message
        user_message = [TextPrompt(text=COMPACT_USER_MESSAGE)]
        assistant_message = [TextResult(text=summary_text)]
        return [user_message, assistant_message]

# Task segment summary prompt using LLMCompact style
TASK_SEGMENT_SUMMARY_PROMPT = """
Your task is to create a focused summary of a specific sub task from a larger conversation.
This sub task represents work on specific todos/subtasks that have been completed or progressed significantly.
The summary should preserve all technical details necessary for understanding what was accomplished and maintaining continuity.


MOST IMPORTANT:
- If the sub task is Requirements / Design / Tasks, you should not summarize the sub task, you MUST keep original content for requirements, design, and tasks.
- Requirements / Design / Tasks are not considered to summarize, its very important to keep original content for later reference.

With other tasks, providing your final summary, wrap your analysis in <analysis> tags to organize your thoughts and ensure you've covered all necessary points. In your analysis:

1. Identify the specific todos/tasks being worked on in this sub task
2. Trace the approach taken to address each task
3. Note all concrete actions, code changes, and results
4. Identify any problems encountered and how they were resolved
5. Determine the final state at the end of this sub task



Your summary should include the following sections:

1. Task Context: The specific todos/tasks being worked on in this segment
2. Actions Taken: Key operations, commands run, analysis performed, and approach used
3. Code Changes: Specific files modified, functions added/changed, imports updated, with relevant code snippets
4. Results & Validation: Test outcomes, errors resolved, validation performed, and success criteria met
5. Problems Solved: Any issues encountered and their resolutions
6. Final State: The state of the system/code at the end of this segment
7. Dependencies & Side Effects: Any new dependencies added or external systems affected


Here's an example of how your output should be structured:

<example>
<analysis>
[Your analysis of the sub task and its results, identifying key tasks, actions, and outcomes]
</analysis>

<summary>
1. Task Context:
   - Todo #3: Implement user authentication middleware
   - Todo #4: Add JWT token validation

2. Actions Taken:
   - Created middleware function in src/auth/middleware.ts
   - Integrated JWT library for token validation
   - Added error handling for invalid tokens
   - Set up token refresh mechanism

3. Code Changes:
   - src/auth/middleware.ts: Added authenticateUser() middleware
     ```typescript
     export const authenticateUser = async (req, res, next) => {
       const token = req.headers.authorization?.split(' ')[1];
       // ... validation logic
     }
     ```
   - src/routes/api.ts: Applied middleware to protected routes
   - package.json: Added jsonwebtoken dependency

4. Results & Validation:
   - All authentication tests passing (8/8)
   - Manual testing confirmed token validation working
   - Expired tokens correctly rejected with 401 status

5. Problems Solved:
   - Fixed issue with token expiry not being checked
   - Resolved CORS headers missing for auth endpoints

6. Final State:
   - Authentication middleware fully functional
   - All protected routes now require valid JWT
   - Token refresh endpoint operational

7. Dependencies & Side Effects:
   - Added jsonwebtoken@9.0.0 dependency
   - Updated API documentation for auth headers
</summary>
</example>

Remember to:
- Include specific file paths and function names
- Preserve important code snippets that show the implementation
- Note test results and validation outcomes
- Keep technical details that would be needed to continue or modify the work
"""