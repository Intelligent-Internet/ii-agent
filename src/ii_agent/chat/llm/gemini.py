"""Gemini provider using official Google GenAI SDK."""

import logging
import json
import base64
import uuid
from typing import AsyncIterator, List, Optional, Dict, Any
from datetime import datetime
from google import genai
from google.genai import types

from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.chat.base import LLMClient
from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.types import (
    Message,
    MessageRole,
    RunResponseEvent,
    RunResponseOutput,
    ToolCall,
    FinishReason,
    TextContent,
    ReasoningContent,
    ContentPart,
    EventType,
    BinaryContent,
)
from ii_agent.chat.prompts.gemini_system_prompt import template


logger = logging.getLogger(__name__)


class GeminiProvider(LLMClient):
    """Provider for Google Gemini models using official SDK."""

    def __init__(self, llm_config: ModelConfig):
        """Initialize Gemini provider."""
        self.llm_config = llm_config
        self.model_name = llm_config.model

        # Initialize client
        if llm_config.vertex_project_id and llm_config.vertex_region:
            self.client = genai.Client(
                vertexai=True,
                project=llm_config.vertex_project_id,
                location=llm_config.vertex_region,
            )
        else:
            api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None
            self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _extract_system_text(messages: List[Message]) -> Optional[str]:
        """Extract concatenated text from SYSTEM role messages.

        Gemini does not support a ``system`` role in contents — system text
        must be passed via ``config.system_instruction`` instead.
        """
        parts: list[str] = []
        for msg in messages:
            if msg.role != MessageRole.SYSTEM:
                continue
            for part in msg.parts:
                if isinstance(part, TextContent) and part.text:
                    parts.append(part.text)
        return "\n".join(parts) if parts else None

    def _convert_messages(
        self,
        messages: List[Message],
    ) -> List[types.Content]:
        """Convert Message objects to Gemini format.

        Files are preprocessed in the service layer and added as BinaryContent parts.
        SYSTEM messages are skipped here — use ``_extract_system_text`` to
        collect them for ``config.system_instruction``.
        """
        contents = []
        for msg in messages:
            match msg.role:
                case MessageRole.SYSTEM:
                    continue
                case MessageRole.USER:
                    parts = []
                    # Convert all parts (BinaryContent from file preprocessing comes first)
                    for part in msg.parts:
                        match part:
                            case TextContent():
                                if part.text:
                                    parts.append(types.Part(text=part.text))
                            case BinaryContent():
                                # Handle inline binary (from file preprocessing or direct)
                                parts.append(
                                    types.Part(
                                        inline_data=types.Blob(
                                            mime_type=part.mime_type,
                                            data=part.data,
                                        )
                                    )
                                )
                            case _:
                                logger.warning(f"Unsupported user message part type: {type(part)}")
                    contents.append(types.Content(role="user", parts=parts))
                case MessageRole.ASSISTANT:
                    parts = []
                    for part in msg.parts:
                        match part:
                            case TextContent():
                                if part.text:
                                    google_part = types.Part(text=part.text)
                                    # Preserve thought_signature when sending TO Gemini
                                    google_part.thought_signature = (
                                        get_thought_signature_from_provider_options(
                                            part.provider_options
                                        )
                                    )
                                    parts.append(google_part)
                            case ReasoningContent():
                                if part.thinking:
                                    thought_part = types.Part(
                                        text=part.thinking,
                                        thought=True,
                                        thought_signature=get_thought_signature_from_provider_options(
                                            part.provider_options
                                        ),
                                    )
                                    parts.append(thought_part)
                            case ToolCall():
                                if part.finished:
                                    try:
                                        args_dict = (
                                            json.loads(part.input)
                                            if isinstance(part.input, str)
                                            else part.input
                                        )
                                    except json.JSONDecodeError:
                                        args_dict = {}

                                    function_call_part = types.Part(
                                        function_call=types.FunctionCall(
                                            name=part.name, args=args_dict
                                        ),
                                        thought_signature=get_thought_signature_from_provider_options(
                                            part.provider_options
                                        ),
                                    )
                                    parts.append(function_call_part)
                            case _:
                                logger.warning(
                                    f"Unsupported assistant message part type: {type(part)}"
                                )
                    # Gemini expects previous model turns as role=\"model\"
                    contents.append(types.Content(role="model", parts=parts))
                case MessageRole.TOOL:
                    # Tool results from previous turn -> functionResponse parts
                    parts = []
                    for result in msg.tool_results():
                        # Pack the full ToolResultContent into the response payload.
                        response_payload = result.output.model_dump()
                        parts.append(
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=result.name,
                                    response=response_payload,
                                )
                            )
                        )

                    if parts:
                        contents.append(types.Content(role="user", parts=parts))

                case _:
                    logger.warning(f"Unsupported message role: {msg.role}")
        return contents

    def _convert_tools(self, tools: Optional[List[Dict[str, Any]]]) -> Optional[List[types.Tool]]:
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
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> RunResponseOutput:
        """Send messages and get complete response.

        Files are preprocessed in the service layer and added as BinaryContent parts.

        Supported ``provider_options["gemini"]`` keys:

        - ``system_instruction`` (str | None): override the default chat system
          prompt.  ``None`` omits the system instruction entirely.
        - ``thinking_config`` (ThinkingConfig | None): override the default
          thinking config.  ``None`` disables thinking.
        """
        gemini_messages = self._convert_messages(messages)
        gemini_opts = (provider_options or {}).get("gemini", {})

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
        if gemini_opts.get("max_output_tokens") is not None:
            config_dict["max_output_tokens"] = gemini_opts["max_output_tokens"]

        # System instruction: provider_options override > inline SYSTEM messages > default
        inline_system = self._extract_system_text(messages)
        if "system_instruction" in gemini_opts:
            if gemini_opts["system_instruction"] is not None:
                config_dict["system_instruction"] = gemini_opts["system_instruction"]
        elif inline_system:
            config_dict["system_instruction"] = inline_system
        else:
            config_dict["system_instruction"] = template.substitute(
                current_date=datetime.now().strftime("%Y-%m-%d")
            )

        # Thinking config: provider_options override > llm_config.thinking_tokens
        if "thinking_config" in gemini_opts:
            if gemini_opts["thinking_config"] is not None:
                config_dict["thinking_config"] = gemini_opts["thinking_config"]
        elif self.llm_config.thinking_tokens and self.llm_config.thinking_tokens > 0:
            config_dict["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
                include_thoughts=True,
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
                    # Check if this is a thought/reasoning part
                    is_thought = hasattr(part, "thought") and part.thought is True

                    if is_thought:
                        # Create ReasoningContent for thinking parts
                        signature = ""
                        if hasattr(part, "thought_signature") and part.thought_signature:
                            try:
                                signature = base64.b64encode(part.thought_signature).decode("utf-8")
                            except Exception as e:
                                logger.warning(f"Failed to encode thought_signature: {e}")

                        reasoning_content = ReasoningContent(
                            thinking=part.text,
                            signature=signature,
                        )
                        if signature:
                            reasoning_content.provider_options = {
                                "google": {"thoughtSignature": signature}
                            }
                        content_parts.append(reasoning_content)
                    else:
                        # Create TextContent for regular text parts
                        text_content = TextContent(text=part.text)

                        # Extract thought_signature from Gemini response
                        if hasattr(part, "thought_signature") and part.thought_signature:
                            try:
                                # Convert bytes to base64 string for JSON serialization
                                signature_b64 = base64.b64encode(part.thought_signature).decode(
                                    "utf-8"
                                )
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
                            signature_b64 = base64.b64encode(part.thought_signature).decode("utf-8")
                            tool_call.provider_options = {
                                "google": {"thoughtSignature": signature_b64}
                            }
                        except Exception as e:
                            logger.warning(f"Failed to encode thought_signature: {e}")

                    content_parts.append(tool_call)

        # Extract usage
        usage = TokenUsage(
            input_tokens=(
                response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            )
            or 0,
            output_tokens=(
                response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            )
            or 0,
            cache_write_tokens=0,
            cache_read_tokens=(
                response.usage_metadata.cached_content_token_count if response.usage_metadata else 0
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
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response with granular events.

        Files are preprocessed in the service layer and added as BinaryContent parts.
        """
        is_code_interpreter_enabled = False  # NOTE: disable code interpreter for Gemini for now

        gemini_messages = self._convert_messages(messages)
        gemini_opts = (provider_options or {}).get("gemini", {})

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
        if gemini_opts.get("max_output_tokens") is not None:
            config_dict["max_output_tokens"] = gemini_opts["max_output_tokens"]

        # System instruction: provider_options override > inline SYSTEM messages > default
        inline_system = self._extract_system_text(messages)
        if "system_instruction" in gemini_opts:
            if gemini_opts["system_instruction"] is not None:
                config_dict["system_instruction"] = gemini_opts["system_instruction"]
        elif inline_system:
            config_dict["system_instruction"] = inline_system
        else:
            config_dict["system_instruction"] = template.substitute(
                current_date=datetime.now().strftime("%Y-%m-%d")
            )

        if "thinking_config" in gemini_opts:
            if gemini_opts["thinking_config"] is not None:
                config_dict["thinking_config"] = gemini_opts["thinking_config"]
        elif self.llm_config.thinking_tokens and self.llm_config.thinking_tokens > 0:
            config_dict["thinking_config"] = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
                include_thoughts=True,
            )

        config = types.GenerateContentConfig(**config_dict)

        stream = await self.client.aio.models.generate_content_stream(
            model=self.model_name,
            contents=gemini_messages,
            config=config,
        )

        # Shared state between streaming events and final aggregated content
        content_parts: List[ContentPart] = []
        state = GeminiStreamState(content_parts=content_parts)

        finish_reason = FinishReason.UNKNOWN
        usage = TokenUsage(model_name=self.llm_config.model)

        async for chunk in stream:
            if not chunk.candidates or len(chunk.candidates) == 0:
                continue

            usage_metadata = chunk.usage_metadata
            if usage_metadata:
                usage.input_tokens = (
                    usage_metadata.prompt_token_count if usage_metadata.prompt_token_count else 0
                )
                usage.output_tokens = (
                    usage_metadata.candidates_token_count
                    if usage_metadata.candidates_token_count
                    else 0
                )
                usage.cache_read_tokens = (
                    usage_metadata.cached_content_token_count
                    if usage_metadata.cached_content_token_count
                    else 0
                )
                usage.cache_write_tokens = 0
                usage.total_tokens = (
                    usage_metadata.total_token_count if usage_metadata.total_token_count else 0
                )

            candidate = chunk.candidates[0]

            content = candidate.content

            if content:
                parts = content.parts or []
                for part in parts:
                    # Text and reasoning parts are handled by the state machine
                    if part.text is not None:
                        for event in state.handle_text_or_reasoning_part(part):
                            yield event

                # Tool calls (function_call parts) are handled after text/reasoning
                for event in state.handle_tool_calls(parts):
                    yield event

            # Track finish reason, but only emit COMPLETE after the stream ends
            if candidate.finish_reason:
                finish_reason = map_googe_finish_reason(
                    candidate.finish_reason, state.has_tool_calls
                )

        # Flush any remaining open text or reasoning blocks into content_parts
        for event in state.flush():
            yield event

        # Emit final COMPLETE event with aggregated content_parts
        yield RunResponseEvent(
            type=EventType.COMPLETE,
            response=RunResponseOutput(
                content=content_parts,
                usage=usage,
                finish_reason=finish_reason,
            ),
        )

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {"id": self.model_name, "name": self.model_name}


def map_googe_finish_reason(finish_reason: str, has_tool_calls: bool) -> FinishReason:
    reason_map = {
        "STOP": FinishReason.END_TURN,
        "MAX_TOKENS": FinishReason.MAX_TOKENS,
        "SAFETY": FinishReason.ERROR,
        "RECITATION": FinishReason.ERROR,
    }
    reason = reason_map.get(finish_reason, FinishReason.UNKNOWN)
    if has_tool_calls and reason == FinishReason.END_TURN:
        reason = FinishReason.TOOL_USE
    return reason


def generate_tool_call_id() -> str:
    """Generate a unique ID for a tool call."""
    return f"call_{uuid.uuid4().hex[:12]}"


def get_tool_call_from_parts(parts: List[types.Part]) -> List[ToolCall]:
    tool_call_parts = [part for part in parts if part.function_call]
    return [
        ToolCall(
            id=generate_tool_call_id(),
            name=part.function_call.name,
            input=json.dumps(part.function_call.args),
            provider_options={
                "google": {
                    "thoughtSignature": get_thought_signature_from_content(part),
                }
            },
            finished=True,
        )
        for part in tool_call_parts
    ]


def get_thought_signature_from_content(
    content: types.Part,
) -> str:
    """Extract thoughtSignature from Gemini content part."""
    signature_b64 = ""
    if hasattr(content, "thought_signature") and content.thought_signature:
        try:
            signature_b64 = base64.b64encode(content.thought_signature).decode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to encode thought_signature: {e}")
    return signature_b64


def get_thought_signature_from_provider_options(
    provider_options: Optional[Dict[str, Any]],
) -> bytes | None:
    """Extract thoughtSignature from provider options dict."""
    signature_b64 = ""
    if provider_options:
        google_opts = provider_options.get("google", {})
        if "thoughtSignature" in google_opts:
            signature_b64 = google_opts["thoughtSignature"]
    return base64.b64decode(signature_b64) if signature_b64 else None


class GeminiStreamState:
    """Small state machine for grouping Gemini text, reasoning, and tool calls.

    This mirrors the Google GenAI JS implementation conceptually but keeps the
    Python code focused and readable.
    """

    def __init__(self, content_parts: List[ContentPart]):
        self.content_parts = content_parts
        self.current_block: Optional[str] = None  # "text", "reasoning", or None
        self.accumulated_text: str = ""
        self.accumulated_thinking: str = ""
        self.last_text_signature: str = ""
        self.last_thinking_signature: str = ""
        self.has_tool_calls: bool = False

    def handle_text_or_reasoning_part(self, part: types.Part) -> List[RunResponseEvent]:
        """Update state for a single text/reasoning part and emit events."""
        events: List[RunResponseEvent] = []
        text = getattr(part, "text", None)

        is_thought = bool(getattr(part, "thought", False))
        signature_b64 = get_thought_signature_from_content(part)

        if is_thought:
            # Transition away from any active text block
            if self.current_block == "text":
                events.extend(self._close_text_block())

            # Start reasoning block if needed
            if self.current_block != "reasoning":
                self.current_block = "reasoning"
                events.append(RunResponseEvent(type=EventType.THINKING_START))

            self.accumulated_thinking += text
            self.last_thinking_signature = signature_b64
            events.append(
                RunResponseEvent(
                    type=EventType.THINKING_DELTA,
                    thinking=text,
                )
            )
        else:
            # Transition away from any active reasoning block
            if self.current_block == "reasoning":
                events.extend(self._close_reasoning_block())

            # Start text block if needed
            if self.current_block != "text":
                self.current_block = "text"
                events.append(RunResponseEvent(type=EventType.CONTENT_START))

            self.accumulated_text += text
            self.last_text_signature = signature_b64
            events.append(
                RunResponseEvent(
                    type=EventType.CONTENT_DELTA,
                    content=text,
                )
            )

        return events

    def handle_tool_calls(self, parts: List[types.Part]) -> List[RunResponseEvent]:
        """Emit tool use events and record ToolCall content parts."""
        events: List[RunResponseEvent] = []
        tool_calls = get_tool_call_from_parts(parts)
        if not tool_calls:
            return events

        self.has_tool_calls = True
        for tool_call in tool_calls:
            # Streamed events for frontend
            events.append(
                RunResponseEvent(
                    type=EventType.TOOL_USE_START,
                    tool_call=tool_call,
                )
            )
            events.append(
                RunResponseEvent(
                    type=EventType.TOOL_USE_DELTA,
                    tool_call=tool_call,
                )
            )
            events.append(
                RunResponseEvent(
                    type=EventType.TOOL_USE_STOP,
                    tool_call=tool_call,
                )
            )

            # Aggregate into final content list
            self.content_parts.append(tool_call)

        return events

    def _close_text_block(self) -> List[RunResponseEvent]:
        """Flush current text block into content parts."""
        events: List[RunResponseEvent] = []
        if self.current_block == "text" and self.accumulated_text:
            content_part = TextContent(text=self.accumulated_text)
            if self.last_text_signature:
                content_part.provider_options = {
                    "google": {"thoughtSignature": self.last_text_signature}
                }
            self.content_parts.append(content_part)
            events.append(RunResponseEvent(type=EventType.CONTENT_STOP))

        self.accumulated_text = ""
        self.last_text_signature = ""
        if self.current_block == "text":
            self.current_block = None
        return events

    def _close_reasoning_block(self) -> List[RunResponseEvent]:
        """Flush current reasoning block into content parts."""
        events: List[RunResponseEvent] = []
        if self.current_block == "reasoning" and self.accumulated_thinking:
            reasoning_content = ReasoningContent(
                thinking=self.accumulated_thinking,
                signature=self.last_thinking_signature or "",
            )
            if self.last_thinking_signature:
                reasoning_content.provider_options = {
                    "google": {"thoughtSignature": self.last_thinking_signature}
                }
            self.content_parts.append(reasoning_content)
            events.append(RunResponseEvent(type=EventType.THINKING_STOP))

        self.accumulated_thinking = ""
        self.last_thinking_signature = ""
        if self.current_block == "reasoning":
            self.current_block = None
        return events

    def flush(self) -> List[RunResponseEvent]:
        """Flush any active block at the end of the stream."""
        if self.current_block == "text":
            return self._close_text_block()
        if self.current_block == "reasoning":
            return self._close_reasoning_block()
        return []
