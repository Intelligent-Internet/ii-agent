"""Gemini provider using official Google GenAI SDK."""

import logging
import json
import base64
from typing import AsyncIterator, List, Optional, Dict, Any
from datetime import datetime
from string import Template

from google import genai
from google.genai import types

from ii_agent.core.config.llm_config import LLMConfig
from ii_agent.server.chat.base import LLMClient
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.chat.models import (
    Message,
    MessageRole,
    RunResponseEvent,
    RunResponseOutput,
    ToolCall,
    ToolResult,
    FinishReason,
    TextContent,
    ContentPart,
    TextResultContent,
    JsonResultContent,
    ExecutionDeniedContent,
    ErrorTextContent,
    ErrorJsonContent,
    ArrayResultContent,
    TextContentPart,
    ImageDataContentPart,
    FileDataContentPart,
    EventType,
)


logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """
You are II-Chat, a helpful and intelligent AI assistant developed by II-Agent team.
Knowledge cutoff: 2024-06
Current date: $current_date

Image input capabilities: Enabled
Personality: v2
You're an insightful, encouraging assistant who combines meticulous clarity with genuine enthusiasm and gentle humor.
Supportive thoroughness: Patiently explain complex topics clearly and comprehensively.
Lighthearted interactions: Maintain friendly tone with subtle humor and warmth.
Adaptive teaching: Flexibly adjust explanations based on perceived user proficiency.
Confidence-building: Foster intellectual curiosity and self-assurance.

Do not end with opt-in questions or hedging closers. Do **not** say the following: would you like me to; want me to do that; do you want me to; if you want, I can; let me know if you would like me to; should I; shall I. Ask at most one necessary clarifying question at the start, not the end. If the next step is obvious, do it. Example of bad: I can write playful examples. would you like me to? Example of good: Here are three playful examples:..

# Response presentation
- Open with a concise highlight sentence that previews the value of the answer.
- Use expressive Markdown headings (e.g., ## Overview**) to organize major sections.
- Emphasize critical phrases with bold text and tasteful inline emoji for energy and clarity.
- When outlining options or feature comparisons, include a compact Markdown table to summarize key takeaways before diving into details.
- Mix short paragraphs with bulleted or numbered lists so information stays scannable.
- Separate major sections with horizontal rules (`---`) when it improves readability.
- Format code or JSON snippets in fenced code blocks with appropriate language hints.
- Close with a brief action-oriented takeaway or next step instead of generic sign-offs.

# Tools

## web

Use the `web` tool to access up-to-date information from the web or when responding to the user requires information about their location. Some examples of when to use the `web` tool include:

- **Local Information**: Use the `web` tool to respond to questions that require information about the user's location, such as the weather, local businesses, or events.
- **Freshness**: If up-to-date information on a topic could potentially change or enhance the answer, call the `web` tool any time you would otherwise refuse to answer a question because your knowledge might be out of date.
- **Niche Information**: If the answer would benefit from detailed information not widely known or understood (which might be found on the internet), such as details about a small neighborhood, a less well-known company, or arcane regulations, use web sources directly rather than relying on the distilled knowledge from pretraining.
- **Accuracy**: If the cost of a small mistake or outdated information is high (e.g., using an outdated version of a software library or not knowing the date of the next game for a sports team), then use the `web` tool.

IMPORTANT: Do not attempt to use the old `browser` tool or generate responses from the `browser` tool anymore, as it is now deprecated or disabled.

The `web` tool has the following commands:

- `web_search()`: Issues a new query to a search engine and outputs the response.
- `web_visit(url: str, prompt: str = None)`: Opens the given URL and extracts the content. If prompt is provided, it will extract the content based on the prompt.
- `image_search(query: str)`: Searches the internet for images related to the query.
### When to use search
- When the user asks for up-to-date facts (news, weather, events).
- When they request niche or local details not likely to be in your training data.
- When correctness is critical and even a small inaccuracy matters.
- When freshness is important, rate using QDF (Query Deserves Freshness) on a scale of 0–5:
  - 0: Historic/unimportant to be fresh.
  - 1: Relevant if within last 18 months.
  - 2: Within last 6 months.
  - 3: Within last 90 days.
  - 4: Within last 60 days.
  - 5: Latest from this month.

QDF_MAP:
  0: historic
  1: 18_months
  2: 6_months
  3: 90_days
  4: 60_days
  5: 30_days

### When to use web_visit
- When the user provides a direct link and asks to open or summarize its contents.
- When referencing an authoritative page already known.

### When to use image_search
- When the user asks for images related to the query.
- When you need to demonstrate the image to the user.

### When to use file_search
Use to search through user's uploaded files and documents:
- Answer questions about uploaded content (PDFs, documents, reports)
- Find specific facts, figures, data, or citations from files
- Compare or synthesize information across multiple uploaded documents
- Verify prior analyses, computations, or recommendations from uploaded files
- Extract relevant sections when user asks about their uploaded knowledge base

Skip when:
- Question can be answered with general knowledge
- Fresh computation or real-time data is needed (use code_interpreter or web instead)

### Examples:
- "What's the score in the Yankees game right now?" → `web_search()` with QDF=5.
- "When is the next solar eclipse visible in Europe?" → `web_search()` with QDF=2.
- "Show me this article" with a link → `web_visit(url)`.
- "Show me an image of a cat" → `image_search(query="cat")`.
- "Summaries the latest assessment uploaded" -> file_search(query="Summaries of the latest security assessment uploaded from the")
- "Show me the Q4 performance" from uploaded pdf -> file_search(query="List the metrics referenced in the Q4 performance review document")

### When to use code_interpreter
- Mathematical computations and equation solving
- Data analysis and statistics
- Creating visualizations (charts, graphs, plots)
- File format conversions
- Text processing and parsing
- Any task requiring code execution

# Mermaid blocks
- When you want to create a mermaid diagram, MUST generate markdown that can be pasted into a mermaid.js viewer


#### FILE PATH RESPONSE ANSWER

**When using code_interpreter: NEVER include sandbox file paths (sandbox://mnt/data/*, /mnt/data/*, or container URIs) in your responses.**

Files are auto-attached. Just describe what you created.

❌ WRONG: "I saved the file to sandbox://mnt/data/report.csv"
✅ CORRECT: "I've created a CSV file with the analysis"

**Policy reminder**: When using web results for sensitive or high-stakes topics (e.g., financial advice, health information, legal matters), always carefully check multiple reputable sources and present information with clear sourcing and caveats.

# Math equations
You MUST render ALL mathematical expressions using LaTeX wrapped in DOUBLE dollar signs (`$$ ... $$`). This is a strict requirement that applies to:
- Inline mathematical expressions and variables
- Standalone equations and formulas
- Any symbolic mathematical notation whatsoever (e.g., `\\gamma`, `\\mathbb{E}`, `\\nabla`, `\\sum`, `\\theta`, etc.)
- Mathematical expressions within parentheses or brackets

NEVER write mathematical expressions in plain text format like `(x^2)`, `(\gamma^{k-t})`, or `(G_t=\sum_{k=t}^{T-1}\gamma^{k-t}r_k)`.

ALWAYS convert to LaTeX format:
- `(x^2)` becomes `$$x^2$$`
- `(\gamma^{k-t})` becomes `$$\gamma^{k-t}$$`
- `(G_t=\sum_{k=t}^{T-1}\gamma^{k-t}r_k)` becomes `$$G_t=\sum_{k=t}^{T-1}\gamma^{k-t}r_k$$`
- `(F_t:=\mathbb{E}[z_t z_t^\top \mid s_t])` becomes `$$F_t:=\mathbb{E}[z_t z_t^\top \mid s_t]$$`

Example: `$$ \widehat{\nabla_\theta J(\theta)} = \sum_{t=0}^{T} \nabla_\theta \log \pi_\theta(a_t \mid s_t) \cdot G_t $$`
Example: `$$ \frac{d}{dx}(x^3) = 3x^2 $$`
Example: The return `$$G_t=\sum_{k=t}^{T-1}\gamma^{k-t}r_k$$` represents the cumulative discounted reward.

This rule applies everywhere in your response - in sentences, bullet points, lists, and all other contexts. Only skip LaTeX formatting if the user explicitly requests plain text mathematics.

---
# Closing Instructions

You must follow all personality, tone, and formatting requirements stated above in every interaction.

- **Personality**: Maintain the friendly, encouraging, and clear style described at the top of this prompt. Where appropriate, include gentle humor and warmth without detracting from clarity or accuracy.
- **Clarity**: Explanations should be thorough but easy to follow. Use headings, lists, and formatting when it improves readability.
- **Boundaries**: Do not produce disallowed content. This includes copyrighted song lyrics or any other material explicitly restricted in these instructions.
- **Tool usage**: Only use the tools provided and strictly adhere to their usage guidelines. If the criteria for a tool are not met, do not invoke it.
- **Accuracy and trust**: For high-stakes topics (e.g., medical, legal, financial), ensure that information is accurate, cite credible sources, and provide appropriate disclaimers.
- **Freshness**: When the user asks for time-sensitive information, prefer the `web` tool with the correct QDF rating to ensure the information is recent and reliable.

When uncertain, follow these priorities:
1. **User safety and policy compliance** come first.
2. **Accuracy and clarity** come next.
3. **Tone and helpfulness** should be preserved throughout.
"""

template = Template(SYSTEM_PROMPT_TEMPLATE)


class GeminiProvider(LLMClient):
    """Provider for Google Gemini models using official SDK."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize Gemini provider."""
        self.llm_config = llm_config
        self.model_name = llm_config.model

        # Initialize client
        api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None
        self.client = genai.Client(api_key=api_key)

    def _convert_messages(self, messages: List[Message]) -> List[types.Content]:
        """Convert Message objects to Gemini format."""
        gemini_messages = []

        for msg in messages:
            parts = []

            if msg.role in [MessageRole.USER, MessageRole.SYSTEM]:
                # Add text content
                text_part = msg.content()
                if text_part:
                    parts.append(types.Part(text=text_part.text))

                # Add images (inline binary data for Gemini)
                for part in msg.parts:
                    if hasattr(part, "mime_type"):  # BinaryContent
                        parts.append(
                            types.Part(
                                inline_data=types.Blob(
                                    mime_type=part.mime_type, data=part.data
                                )
                            )
                        )

                role_map = {MessageRole.USER: "user", MessageRole.SYSTEM: "user"}
                gemini_messages.append(
                    types.Content(role=role_map[msg.role], parts=parts)
                )

            elif msg.role == MessageRole.ASSISTANT:
                # Add text content
                text_part = msg.content()
                if text_part:
                    text_gemini_part = types.Part(text=text_part.text)

                    # Preserve thought_signature when sending TO Gemini
                    # Read from provider_options (used for both input and output)
                    if (
                        hasattr(text_part, "provider_options")
                        and text_part.provider_options
                    ):
                        google_opts = text_part.provider_options.get("google", {})
                        if "thoughtSignature" in google_opts:
                            try:
                                # Decode base64 string back to bytes for Gemini API
                                text_gemini_part.thought_signature = base64.b64decode(
                                    google_opts["thoughtSignature"]
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to decode thought_signature: {e}"
                                )

                    parts.append(text_gemini_part)

                # Add function calls (only finished ones)
                for tool_call in msg.tool_calls():
                    if tool_call.finished and not tool_call.provider_executed:
                        # Parse JSON input
                        try:
                            args_dict = (
                                json.loads(tool_call.input)
                                if isinstance(tool_call.input, str)
                                else tool_call.input
                            )
                        except json.JSONDecodeError:
                            args_dict = {}

                        function_call_part = types.Part(
                            function_call=types.FunctionCall(
                                name=tool_call.name, args=args_dict
                            )
                        )

                        # Preserve thought_signature when sending TO Gemini
                        # Read from provider_options (used for both input and output)
                        if (
                            hasattr(tool_call, "provider_options")
                            and tool_call.provider_options
                        ):
                            google_opts = tool_call.provider_options.get("google", {})
                            if "thoughtSignature" in google_opts:
                                try:
                                    # Decode base64 string back to bytes for Gemini API
                                    function_call_part.thought_signature = (
                                        base64.b64decode(
                                            google_opts["thoughtSignature"]
                                        )
                                    )
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to decode thought_signature: {e}"
                                    )

                        parts.append(function_call_part)

                # Add provider-executed code execution calls
                for part in msg.parts:
                    if (
                        isinstance(part, ToolCall)
                        and part.provider_executed
                        and part.name == "code_execution"
                    ):
                        try:
                            code_data = (
                                json.loads(part.input)
                                if isinstance(part.input, str)
                                else part.input
                            )

                            # Add executable_code part
                            parts.append(
                                types.Part(
                                    executable_code=types.ExecutableCode(
                                        language=code_data.get("language", "PYTHON"),
                                        code=code_data.get("code", ""),
                                    )
                                )
                            )
                        except (json.JSONDecodeError, KeyError) as e:
                            logger.warning(f"Failed to parse code execution input: {e}")

                # Add provider-executed code execution results
                for part in msg.parts:
                    if isinstance(part, ToolResult) and part.name == "code_execution":
                        try:
                            # Extract result data
                            result_data = (
                                part.output.value
                                if isinstance(part.output, JsonResultContent)
                                else {}
                            )

                            # Add code_execution_result part
                            parts.append(
                                types.Part(
                                    code_execution_result=types.CodeExecutionResult(
                                        outcome=result_data.get(
                                            "outcome", "OUTCOME_FAILED"
                                        ),
                                        output=result_data.get("output", ""),
                                    )
                                )
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to convert code execution result: {e}"
                            )

                if parts:
                    gemini_messages.append(types.Content(role="model", parts=parts))

            elif msg.role == MessageRole.TOOL:
                # Function responses
                for result in msg.tool_results():
                    output = result.output
                    content_value = None

                    # Handle different output types using isinstance
                    if isinstance(output, (TextResultContent, ErrorTextContent)):
                        content_value = output.value
                    elif isinstance(output, ExecutionDeniedContent):
                        content_value = output.reason or "Tool execution denied."
                    elif isinstance(output, (JsonResultContent, ErrorJsonContent)):
                        content_value = json.dumps(output.value)
                    elif isinstance(output, ArrayResultContent):
                        # Handle array content with different types
                        parts_list = []
                        for item in output.value:
                            if isinstance(item, TextContentPart):
                                parts_list.append(item.text)
                            elif isinstance(item, ImageDataContentPart):
                                parts_list.append(f"[Image: {item.media_type}]")
                            elif isinstance(item, FileDataContentPart):
                                parts_list.append(f"[File: {item.filename or 'data'}]")
                            else:
                                logger.warning(
                                    f"Unsupported tool content part type: {item.type}"
                                )
                        content_value = "\n".join(parts_list)
                    else:
                        # Fallback for unknown types
                        logger.warning(
                            f"Unknown tool result output type: {type(output)}"
                        )
                        content_value = str(output)

                    parts.append(
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=result.name, response={"result": content_value}
                            )
                        )
                    )

                if parts:
                    gemini_messages.append(types.Content(role="function", parts=parts))

        return gemini_messages

    def _convert_tools(
        self, tools: Optional[List[Dict[str, Any]]]
    ) -> Optional[List[types.Tool]]:
        """
        Convert OpenAI function format to Gemini tools format.

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {...}}
            }
        }

        Gemini format:
        Tool(
            function_declarations=[
                FunctionDeclaration(
                    name="web_search",
                    description="Search the web",
                    parameters={"type": "object", "properties": {...}}
                )
            ]
        )
        """
        if not tools:
            return None

        function_declarations = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                function_declarations.append(
                    types.FunctionDeclaration(
                        name=func["name"],
                        description=func["description"],
                        parameters=func["parameters"],
                    )
                )

        if function_declarations:
            return [types.Tool(function_declarations=function_declarations)]

        return None

    def _add_code_execution_tool(
        self, gemini_tools: Optional[List[types.Tool]]
    ) -> List[types.Tool]:
        """
        Add code execution tool to Gemini request.

        Gemini code execution is a built-in tool that runs Python code server-side
        for up to 30 seconds with 15+ pre-installed libraries.

        Args:
            gemini_tools: Existing tools list (may be None)

        Returns:
            Tools list with code execution tool appended
        """
        tools = gemini_tools or []

        # Add code execution tool
        # This enables Gemini to autonomously write and execute Python code
        tools.append(types.Tool(code_execution=types.ToolCodeExecution()))

        logger.debug("Added code execution tool to Gemini request")
        return tools

    async def send(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
    ) -> RunResponseOutput:
        """Send messages and get complete response."""
        gemini_messages = self._convert_messages(messages)

        # Gemini doesn't support mixing code execution with function calling
        # When code execution is enabled, skip regular tools
        if is_code_interpreter_enabled:
            gemini_tools = self._add_code_execution_tool(None)
        else:
            # Convert tools to Gemini format
            gemini_tools = self._convert_tools(tools)

        # Build config dict with tools
        config_dict = {}
        if self.llm_config.temperature is not None:
            config_dict["temperature"] = self.llm_config.temperature
        if gemini_tools:
            config_dict["tools"] = gemini_tools

        config_dict["system_instruction"] = template.substitute(
            current_date=datetime.now().strftime("%Y-%m-%d")
        )

        config = types.GenerateContentConfig(**config_dict)

        response = await self.client.aio.models.generate_content(
            model=self.model_name,
            contents=gemini_messages,
            config=config,
        )

        # Extract content parts
        content_parts = []

        if (
            response.candidates
            and response.candidates[0].content
            and response.candidates[0].content.parts
        ):
            for part in response.candidates[0].content.parts:
                if part.text:
                    # Create TextContent for each text part immediately
                    text_content = TextContent(text=part.text)

                    # Extract thought_signature from Gemini response
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        try:
                            # Convert bytes to base64 string for JSON serialization
                            signature_b64 = base64.b64encode(
                                part.thought_signature
                            ).decode("utf-8")
                            text_content.provider_options = {
                                "google": {"thoughtSignature": signature_b64}
                            }
                        except Exception as e:
                            logger.warning(f"Failed to encode thought_signature: {e}")

                    content_parts.append(text_content)

                elif part.function_call and part.function_call.name:
                    # Create tool call with thought_signature if present
                    tool_call = ToolCall(
                        id=f"call_{part.function_call.name}",  # Gemini doesn't provide IDs
                        name=part.function_call.name,
                        input=json.dumps(part.function_call.args),
                        finished=True,
                    )

                    # Extract thought_signature from Gemini response
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        try:
                            # Convert bytes to base64 string for JSON serialization
                            signature_b64 = base64.b64encode(
                                part.thought_signature
                            ).decode("utf-8")
                            tool_call.provider_options = {
                                "google": {"thoughtSignature": signature_b64}
                            }
                        except Exception as e:
                            logger.warning(f"Failed to encode thought_signature: {e}")

                    content_parts.append(tool_call)

        # Extract usage
        usage = TokenUsage(
            prompt_tokens=(
                response.usage_metadata.prompt_token_count
                if response.usage_metadata
                else 0
            )
            or 0,
            completion_tokens=(
                response.usage_metadata.candidates_token_count
                if response.usage_metadata
                else 0
            )
            or 0,
            cache_write_tokens=0,
            cache_read_tokens=(
                response.usage_metadata.cached_content_token_count
                if response.usage_metadata
                else 0
            )
            or 0,
            model_name=self.llm_config.model,
        )

        # Map finish reason
        finish_reason = FinishReason.UNKNOWN
        if response.candidates and response.candidates[0].finish_reason:
            reason_map = {
                "STOP": FinishReason.END_TURN,
                "MAX_TOKENS": FinishReason.MAX_TOKENS,
                "SAFETY": FinishReason.ERROR,
                "RECITATION": FinishReason.ERROR,
            }
            finish_reason = reason_map.get(
                response.candidates[0].finish_reason, FinishReason.UNKNOWN
            )

        # Gemini returns "STOP" even when there are tool calls
        # Override to TOOL_USE if we have any ToolCall content parts
        tool_calls_present = any(isinstance(p, ToolCall) for p in content_parts)
        if tool_calls_present and finish_reason == FinishReason.END_TURN:
            finish_reason = FinishReason.TOOL_USE

        return RunResponseOutput(
            content=content_parts,
            usage=usage,
            finish_reason=finish_reason,
            files=[],
        )

    async def stream(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
        session_id: Optional[str] = None,
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response with granular events."""
        is_code_interpreter_enabled = (
            False  # NOTE: disable code interpreter for Gemini for now
        )
        gemini_messages = self._convert_messages(messages)

        # Gemini doesn't support mixing code execution with function calling
        # When code execution is enabled, skip regular tools
        if is_code_interpreter_enabled:
            gemini_tools = self._add_code_execution_tool(None)
            logger.info(f"Code execution enabled for session {session_id}")
        else:
            # Convert tools to Gemini format
            gemini_tools = self._convert_tools(tools)

        # Build config dict with tools
        config_dict = {}
        if self.llm_config.temperature is not None:
            config_dict["temperature"] = self.llm_config.temperature
        if gemini_tools:
            config_dict["tools"] = gemini_tools

        config_dict["system_instruction"] = template.substitute(
            current_date=datetime.now().strftime("%Y-%m-%d")
        )

        config = types.GenerateContentConfig(**config_dict)

        stream = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=gemini_messages,
            config=config,
        )

        content_parts: List[ContentPart] = []
        content_started = False
        accumulated_text = ""

        async for chunk in stream:
            if not chunk.candidates:
                continue

            # Check for completion first (before checking content)
            # The final chunk might not have content but will have finish_reason
            if chunk.candidates[0].finish_reason:
                if content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_STOP)
                    # Add accumulated text as TextContent if present
                    if accumulated_text:
                        content_parts.append(TextContent(text=accumulated_text))

                # Mark tool calls as finished and emit stop events
                for part in content_parts:
                    if isinstance(part, ToolCall) and not part.finished:
                        part.finished = True
                        yield RunResponseEvent(
                            type=EventType.TOOL_USE_STOP, tool_call=part
                        )

                # Extract usage
                usage = TokenUsage(
                    prompt_tokens=(
                        chunk.usage_metadata.prompt_token_count
                        if chunk.usage_metadata
                        else 0
                    )
                    or 0,
                    completion_tokens=(
                        chunk.usage_metadata.candidates_token_count
                        if chunk.usage_metadata
                        else 0
                    )
                    or 0,
                    cache_write_tokens=0,
                    cache_read_tokens=(
                        chunk.usage_metadata.cached_content_token_count
                        if chunk.usage_metadata
                        else 0
                    )
                    or 0,
                    model_name=self.llm_config.model,
                )

                # Map finish reason
                reason_map = {
                    "STOP": FinishReason.END_TURN,
                    "MAX_TOKENS": FinishReason.MAX_TOKENS,
                    "SAFETY": FinishReason.ERROR,
                    "RECITATION": FinishReason.ERROR,
                }
                finish_reason = reason_map.get(
                    chunk.candidates[0].finish_reason, FinishReason.UNKNOWN
                )

                # Check if we have tool calls in content_parts
                has_tool_calls = any(isinstance(p, ToolCall) for p in content_parts)
                # Gemini returns "STOP" even when there are tool calls
                # Override to TOOL_USE if we have any ToolCall content parts
                if has_tool_calls and finish_reason == FinishReason.END_TURN:
                    finish_reason = FinishReason.TOOL_USE

                logger.info(
                    f"Emitting COMPLETE event with finish_reason={finish_reason}, content_parts={len(content_parts)}"
                )

                yield RunResponseEvent(
                    type=EventType.COMPLETE,
                    response=RunResponseOutput(
                        content=content_parts,
                        usage=usage,
                        finish_reason=finish_reason,
                        files=[],
                    ),
                )
                # Exit the stream after completion
                return

            # Skip chunks without content
            if not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                continue

            for part in chunk.candidates[0].content.parts:
                # Handle executable code
                if (
                    hasattr(part, "executable_code")
                    and part.executable_code
                    and part.executable_code.language
                ):
                    # Count existing code executions to generate unique ID
                    code_exec_count = sum(
                        1
                        for cp in content_parts
                        if isinstance(cp, ToolCall) and cp.name == "code_execution"
                    )
                    # Generate unique ID for this code execution
                    execution_id = f"exec_{part.executable_code.language.lower()}_{code_exec_count}"

                    # Create tool call for code execution
                    tool_call = ToolCall(
                        id=execution_id,
                        name="code_execution",
                        input=json.dumps(
                            {
                                "language": part.executable_code.language,
                                "code": part.executable_code.code,
                            }
                        ),
                        finished=False,
                        provider_executed=True,  # Critical: marks as provider-executed
                    )
                    content_parts.append(tool_call)

                    # Emit TOOL_USE_START event
                    yield RunResponseEvent(
                        type=EventType.TOOL_USE_START,
                        tool_call=tool_call,
                    )

                    logger.debug(f"Code execution started: {execution_id}")

                # Handle code execution results
                elif (
                    hasattr(part, "code_execution_result")
                    and part.code_execution_result
                ):
                    # Find corresponding tool call (last code execution tool call)
                    # Note: Gemini may not provide explicit linking, use last execution
                    last_code_exec = None
                    for cp in reversed(content_parts):
                        if isinstance(cp, ToolCall) and cp.name == "code_execution":
                            last_code_exec = cp
                            break

                    if last_code_exec:
                        last_code_exec.finished = True

                        # Emit TOOL_USE_STOP
                        yield RunResponseEvent(
                            type=EventType.TOOL_USE_STOP,
                            tool_call=last_code_exec,
                        )

                        # Create tool result
                        result_content = {
                            "outcome": part.code_execution_result.outcome,
                            "output": part.code_execution_result.output,
                        }

                        tool_result = ToolResult(
                            tool_call_id=last_code_exec.id,
                            name="code_execution",
                            output=JsonResultContent(value=result_content),
                        )

                        # Emit TOOL_RESULT event
                        yield RunResponseEvent(
                            type=EventType.TOOL_RESULT,
                            tool_result=tool_result,
                        )

                        logger.debug(
                            f"Code execution completed: {last_code_exec.id}, "
                            f"outcome={part.code_execution_result.outcome}"
                        )

                # Handle text content
                elif part.text:
                    if not content_started:
                        yield RunResponseEvent(type=EventType.CONTENT_START)
                        content_started = True

                    accumulated_text += part.text
                    yield RunResponseEvent(
                        type=EventType.CONTENT_DELTA, content=part.text
                    )

                # Handle function calls
                elif part.function_call and part.function_call.name:
                    call_id = f"call_{part.function_call.name}"
                    # Check if this tool call already exists in content_parts
                    existing_tool_call = None
                    for cp in content_parts:
                        if isinstance(cp, ToolCall) and cp.id == call_id:
                            existing_tool_call = cp
                            break

                    if existing_tool_call is None:
                        # First time seeing this tool call
                        tool_call = ToolCall(
                            id=call_id,
                            name=part.function_call.name,
                            input="",
                            finished=False,
                        )

                        # Extract thought_signature from Gemini response
                        if (
                            hasattr(part, "thought_signature")
                            and part.thought_signature
                        ):
                            try:
                                # Convert bytes to base64 string for JSON serialization
                                signature_b64 = base64.b64encode(
                                    part.thought_signature
                                ).decode("utf-8")
                                tool_call.provider_options = {
                                    "google": {"thoughtSignature": signature_b64}
                                }
                            except Exception as e:
                                logger.warning(
                                    f"Failed to encode thought_signature: {e}"
                                )

                        content_parts.append(tool_call)
                        yield RunResponseEvent(
                            type=EventType.TOOL_USE_START, tool_call=tool_call
                        )
                    else:
                        tool_call = existing_tool_call

                    # Update args
                    tool_call.input = json.dumps(part.function_call.args)

                    # Update thought_signature from Gemini response
                    if hasattr(part, "thought_signature") and part.thought_signature:
                        try:
                            # Convert bytes to base64 string for JSON serialization
                            signature_b64 = base64.b64encode(
                                part.thought_signature
                            ).decode("utf-8")
                            tool_call.provider_options = {
                                "google": {"thoughtSignature": signature_b64}
                            }
                        except Exception as e:
                            logger.warning(f"Failed to encode thought_signature: {e}")
                    yield RunResponseEvent(
                        type=EventType.TOOL_USE_DELTA,
                        tool_call=ToolCall(
                            id=call_id,
                            name=part.function_call.name,
                            input=json.dumps(part.function_call.args),
                            finished=False,
                        ),
                    )

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {"id": self.model_name, "name": self.model_name}
