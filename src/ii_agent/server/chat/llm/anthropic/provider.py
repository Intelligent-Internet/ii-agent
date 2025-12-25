"""Anthropic provider using official SDK."""

from dataclasses import dataclass
import asyncio
from datetime import datetime
import io
import logging
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import AsyncIterator, List, Literal, Optional, Dict, Any

import anyio
import anthropic
from anthropic.types import (
    TextBlock,
    ToolUseBlock,
    Message as AnthropicMessage,
    ThinkingBlock as AnthropicThinkingBlock,
)
from anthropic.types.beta import (
    BetaBashCodeExecutionToolResultBlock,
    BetaCodeExecutionToolResultBlock,
    BetaMessage as AnthropicBetaMessage,
    BetaServerToolUseBlock,
    BetaTextBlock,
    BetaTextEditorCodeExecutionToolResultBlock,
    BetaThinkingBlock as AnthropicBetaThinkingBlock,
    BetaToolUseBlock,
)
from pydantic import BaseModel
from sqlalchemy import select

from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.storage.locations import get_session_file_path
from ii_agent.db.models import FileUpload, Session
from ii_agent.db.llm_provider import ProviderFile
from ii_agent.db.manager import get_db_session_local
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.chat.llm.anthropic.prompt import system_prompt_template
from ii_agent.server.shared import storage
from ii_agent.server.chat.base import (
    LLMClient,
)
from ii_agent.server.chat.models import (
    ContentPart,
    JsonResultContent,
    Message,
    ReasoningContent,
    TextContent,
    ToolCall,
    FinishReason,
    ToolResult,
    RunResponseEvent,
    RunResponseOutput,
    EventType,
)
from .prompt_converter import convert_to_anthropic_messages

logger = logging.getLogger(__name__)

CODEX_EXECUTION_TOOL = {"type": "code_execution_20250825", "name": "code_execution"}


class SkillConfig(BaseModel):
    type: Literal["anthropic", "custom"] = "anthropic"
    skill_id: str
    version: str = "latest"


@dataclass
class ContainerConfig(BaseModel):
    skills: List[SkillConfig]
    id: Optional[str] = None


class FileResponseObject(BaseModel):
    """Response object for uploaded files."""

    id: str
    provider_file_id: str
    provider: Literal["openai", "anthropic"]
    content_type: str
    file_name: str
    file_size: Optional[int] = 0
    raw_file_object: Optional[Dict[str, Any]] = None


class AnthropicProvider(LLMClient):
    """Provider for Anthropic Claude models using official SDK."""

    def __init__(self, llm_config: LLMConfig):
        """Initialize Anthropic provider."""
        self.llm_config = llm_config
        self.model_name = llm_config.model
        self.enable_caching = getattr(llm_config, "enable_prompt_caching", True)

        # Initialize client (Vertex or standard)
        if llm_config.vertex_project_id and llm_config.vertex_region:
            self.client = anthropic.AsyncAnthropicVertex(
                project_id=llm_config.vertex_project_id,
                region=llm_config.vertex_region,
                timeout=60 * 5,
                max_retries=3,
            )
        else:
            # Support custom base_url for Anthropic-compatible APIs (e.g., Minimax)
            client_kwargs = {
                "api_key": llm_config.api_key.get_secret_value(),
                "timeout": 60 * 5,
                "max_retries": 3,
            }
            if llm_config.base_url:
                client_kwargs["base_url"] = llm_config.base_url

            self.client = anthropic.AsyncAnthropic(**client_kwargs)

    async def _upload_single_file(
        self, file_info: FileUpload
    ) -> Optional[FileResponseObject]:
        """Upload a single file to Anthropic Files API.

        Args:
            file_info: FileUpload record containing file metadata

        Returns:
            FileResponseObject with provider file ID, or None on failure
        """
        try:
            # Read file from storage backend
            file_content = await anyio.to_thread.run_sync(
                storage.read, file_info.storage_path
            )

            # Anthropic SDK requires a Path object, so write to temp file
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f"_{file_info.file_name}"
            ) as tmp:
                tmp.write(file_content.read())
                tmp_path = tmp.name

            try:
                # Upload to Anthropic Files API
                uploaded_file = await self.client.beta.files.upload(file=Path(tmp_path))

                # Serialize the file object to JSON-compatible dict
                raw_file_obj = None
                if hasattr(uploaded_file, "model_dump"):
                    raw_file_obj = uploaded_file.model_dump(mode="json")

                return FileResponseObject(
                    id=file_info.id,
                    provider_file_id=uploaded_file.id,
                    provider=APITypes.ANTHROPIC.value,
                    content_type=file_info.content_type,
                    file_name=file_info.file_name,
                    file_size=file_info.file_size,
                    raw_file_object=raw_file_obj,
                )
            finally:
                # Clean up temp file
                os.unlink(tmp_path)

        except Exception as e:
            logger.error(
                f"Failed to upload file {file_info.id} ({file_info.file_name}): {e}",
                exc_info=True,
            )
            return None

    async def upload_files(
        self, user_message: Message, session_id: str
    ) -> List[FileResponseObject]:
        """Upload files from user message to Anthropic Files API.

        Files are cached in the database to avoid re-uploading. Unlike OpenAI,
        Anthropic files persist until manually deleted (no automatic expiration).

        Args:
            user_message: Message containing file_ids
            session_id: Session ID for file tracking

        Returns:
            List of FileResponseObject with provider file IDs
        """
        if not user_message.file_ids:
            return []

        # Token budget for direct file upload to Anthropic context
        # Files exceeding this should use file_search tool with vector store instead
        MAX_DIRECT_UPLOAD_TOKENS = 50000  # Conservative budget for inline content

        # Token estimation ratios (characters per token)
        # Text-based files: ~4 chars/token
        # Binary formats (PDF, DOCX): estimate ~10-20% extractable text, then 4 chars/token
        TOKEN_RATIO_TEXT = 4.0  # chars per token for plain text
        TOKEN_RATIO_BINARY = 20.0  # chars per token for binary (conservative: assumes ~20% text extraction)

        # File types that are binary/document formats
        BINARY_CONTENT_TYPES = {
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-powerpoint",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        }

        def estimate_tokens(file_size: int, content_type: str) -> int:
            """Estimate token count from file size and content type."""
            if content_type in BINARY_CONTENT_TYPES:
                # Binary documents: assume ~20% text extraction efficiency
                return int(file_size / TOKEN_RATIO_BINARY)
            else:
                # Text-based files: direct character to token conversion
                return int(file_size / TOKEN_RATIO_TEXT)

        async with get_db_session_local() as db_session:
            # Check for existing provider files to avoid re-upload
            existing_result = await db_session.execute(
                select(ProviderFile).where(
                    ProviderFile.file_id.in_(user_message.file_ids),
                    ProviderFile.session_id == session_id,
                    ProviderFile.provider == APITypes.ANTHROPIC.value,
                )
            )

            existing_provider_files = {
                pf.file_id: pf for pf in existing_result.scalars().all()
            }

            # Get FileUpload records
            result = await db_session.execute(
                select(FileUpload).where(FileUpload.id.in_(user_message.file_ids))
            )
            file_uploads = result.scalars().all()

            # Filter files that need uploading (not already uploaded and under token limit)
            files_to_upload = []
            for f in file_uploads:
                if f.id in existing_provider_files:
                    continue

                # Estimate tokens for this file
                estimated_tokens = estimate_tokens(f.file_size or 0, f.content_type or "")

                if estimated_tokens > MAX_DIRECT_UPLOAD_TOKENS:
                    logger.info(
                        f"Skipping file {f.file_name} for Anthropic direct upload: "
                        f"estimated {estimated_tokens:,} tokens exceeds {MAX_DIRECT_UPLOAD_TOKENS:,} token limit. "
                        f"File indexed in vector store for file_search tool."
                    )
                    continue
                files_to_upload.append(f)

            # Upload new files concurrently
            upload_results = []
            if files_to_upload:
                upload_tasks = [
                    asyncio.create_task(self._upload_single_file(file_info))
                    for file_info in files_to_upload
                ]
                upload_results = await asyncio.gather(*upload_tasks)

                # Filter out None results (failed uploads)
                upload_results = [r for r in upload_results if r is not None]

                # Save ProviderFile records for successful uploads
                for file_response in upload_results:
                    provider_file = ProviderFile(
                        file_id=file_response.id,
                        provider=APITypes.ANTHROPIC.value,
                        session_id=session_id,
                        provider_file_id=file_response.provider_file_id,
                        raw_file_object=file_response.raw_file_object,
                        expires_at=None,  # Anthropic files don't auto-expire
                    )
                    db_session.add(provider_file)

                await db_session.commit()
                logger.info(
                    f"Uploaded {len(upload_results)} new files to Anthropic for session {session_id}"
                )

            # Build complete list of file responses (existing + newly uploaded)
            all_file_responses = []

            # Add existing files
            for file_id, pf in existing_provider_files.items():
                # Find corresponding FileUpload for metadata
                file_upload = next((f for f in file_uploads if f.id == file_id), None)
                if file_upload:
                    all_file_responses.append(
                        FileResponseObject(
                            id=file_id,
                            provider_file_id=pf.provider_file_id,
                            provider=APITypes.ANTHROPIC.value,
                            content_type=file_upload.content_type,
                            file_name=file_upload.file_name,
                            file_size=file_upload.file_size,
                            raw_file_object=pf.raw_file_object,
                        )
                    )

            # Add newly uploaded files
            all_file_responses.extend(upload_results)

            return all_file_responses

    def _convert_tools(
        self, tools: Optional[List[Dict[str, Any]]], has_skills: bool = False
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Convert OpenAI function format to Anthropic tools format.

        OpenAI format:
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web",
                "parameters": {"type": "object", "properties": {...}}
            }
        }

        Anthropic format:
        {
            "name": "web_search",
            "description": "Search the web",
            "input_schema": {"type": "object", "properties": {...}}
        }
        """
        if not (tools or has_skills):
            return None

        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool["function"]
                anthropic_tools.append(
                    {
                        "name": func["name"],
                        "description": func["description"],
                        "input_schema": func["parameters"],
                    }
                )

        if has_skills and CODEX_EXECUTION_TOOL not in anthropic_tools:
            anthropic_tools.append(CODEX_EXECUTION_TOOL)

        return anthropic_tools

    def _prepare_request_params(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        anthropic_options: Optional[Dict[str, Any]] = None,
        provider_files: Optional[List[FileResponseObject]] = None,
    ) -> tuple[Dict[str, Any], List[str]]:
        """Prepare request parameters and headers for Anthropic API calls.

        Args:
            messages: List of messages to convert
            tools: Optional list of tools
            anthropic_options: Optional Anthropic-specific options
            provider_files: Optional list of uploaded file responses

        Returns:
            Tuple of (params, betas)
        """
        system_prompt, anthropic_messages, warnings = convert_to_anthropic_messages(
            messages,
            # Tuesday, August 05, 2025. format
            system_prompt_template.substitute(
                current_date=datetime.now().strftime("%A, %B %d, %Y")
            ),
            enable_caching=self.enable_caching,
            provider_files=provider_files,
        )
        container_config = (
            anthropic_options.get("container") if anthropic_options else None
        )
        has_skills = (
            container_config is not None
            and container_config.get("skills") is not None
            and len(container_config["skills"]) > 0
        )

        params = {
            "model": self.model_name,
            "messages": anthropic_messages,
            "max_tokens": 8192,
        }

        if has_skills:
            container_config = ContainerConfig.model_validate(container_config)
            params["container"] = container_config.model_dump()

        # Log warnings if any
        if warnings:
            logger.debug(f"Cache control warnings: {warnings}")

        # Convert tools to Anthropic format
        anthropic_tools = self._convert_tools(tools, has_skills=has_skills)

        if system_prompt:
            params["system"] = system_prompt

        if anthropic_tools:
            params["tools"] = anthropic_tools
            # When using extended thinking with tools, only auto tool choice is supported
            params["tool_choice"] = {"type": "auto"}

        # Extended thinking configuration
        enable_thinking = (
            self.llm_config.thinking_tokens and self.llm_config.thinking_tokens >= 1024
        )

        # Add interleaved thinking beta header if using tools with extended thinking
        betas = []
        if enable_thinking:
            # Extended thinking is not compatible with temperature modifications
            # Minimum budget is 1,024 tokens, recommended 16k+ for complex tasks
            params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.llm_config.thinking_tokens,
            }
            if anthropic_tools:
                betas.append("interleaved-thinking-2025-05-14")
        else:
            # Only set temperature if extended thinking is disabled
            if self.llm_config.temperature is not None:
                params["temperature"] = self.llm_config.temperature

        if has_skills:
            betas.append("code-execution-2025-08-25")
            betas.append("skills-2025-10-02")
            betas.append("files-api-2025-04-14")

        return params, betas

    def _extract_content_part_from_message(
        self, message: AnthropicMessage | AnthropicBetaMessage
    ) -> List[ContentPart]:
        # Extract content
        content: List[ContentPart] = []

        for block in message.content:
            match block:
                case TextBlock() | BetaTextBlock():
                    content.append(
                        TextContent(
                            text=block.text,
                        )
                    )
                case ToolUseBlock() | BetaToolUseBlock():
                    content.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            input=json.dumps(block.input),
                            finished=True,
                        )
                    )
                case BetaServerToolUseBlock():
                    if block.name in [
                        "text_editor_code_execution",
                        "bash_code_execution",
                    ]:
                        content.append(
                            ToolCall(
                                id=block.id,
                                name="code_execution",
                                input=json.dumps({"type": block.name, **block.input}),
                                finished=True,
                                provider_executed=True,
                            )
                        )
                    else:
                        logger.warning(
                            f"Unknown server tool use block name: {block.name}"
                        )
                case AnthropicThinkingBlock() | AnthropicBetaThinkingBlock():
                    content.append(
                        ReasoningContent(
                            thinking=block.thinking,
                            signature=block.signature,
                        )
                    )
                case (
                    BetaTextEditorCodeExecutionToolResultBlock()
                    | BetaBashCodeExecutionToolResultBlock()
                    | BetaCodeExecutionToolResultBlock()
                ):
                    content.append(
                        ToolResult(
                            tool_call_id=block.tool_use_id,
                            name="code_execution",
                            output=JsonResultContent(value=block.content.model_dump()),
                        )
                    )
                case _:
                    logger.warning(f"Unknown content block type: {type(block)}")

        return content

    async def send(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        provider_options: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> RunResponseOutput:
        """Send messages and get complete response with extended thinking."""
        # Upload files from the last user message if any
        provider_files = []
        if messages:
            last_user_message = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_user_message = msg
                    break

            if last_user_message and last_user_message.file_ids and session_id:
                try:
                    provider_files = await self.upload_files(
                        last_user_message, session_id
                    )
                    logger.info(f"Uploaded {len(provider_files)} files for send")
                except Exception as e:
                    logger.error(f"Failed to upload files for send: {e}", exc_info=True)

        anthropic_options = (
            provider_options.get("anthropic", {}) if provider_options else {}
        )
        params, betas = self._prepare_request_params(
            messages, tools, anthropic_options, provider_files
        )

        response = await self.client.beta.messages.create(**params, betas=betas)

        # Extract usage
        usage = TokenUsage(
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            cache_write_tokens=response.usage.cache_creation_input_tokens or 0,
            cache_read_tokens=response.usage.cache_read_input_tokens or 0,
            model_name=self.llm_config.model,
        )

        # Map stop reason
        finish_reason_map = {
            "end_turn": FinishReason.END_TURN,
            "max_tokens": FinishReason.MAX_TOKENS,
            "tool_use": FinishReason.TOOL_USE,
            "stop_sequence": FinishReason.END_TURN,
            "pause_turn": FinishReason.PAUSE_TURN,
        }
        finish_reason = finish_reason_map.get(
            response.stop_reason, FinishReason.UNKNOWN
        )

        return RunResponseOutput(
            content=self._extract_content_part_from_message(response),
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
        """Stream response with granular events."""

        # Upload files from the last user message if any
        provider_files = []
        if messages:
            last_user_message = None
            for msg in reversed(messages):
                if msg.role == "user":
                    last_user_message = msg
                    break

            if last_user_message and last_user_message.file_ids and session_id:
                try:
                    provider_files = await self.upload_files(
                        last_user_message, session_id
                    )
                    logger.info(f"Uploaded {len(provider_files)} files for streaming")
                except Exception as e:
                    logger.error(
                        f"Failed to upload files for streaming: {e}", exc_info=True
                    )

        container_id = None
        for msg in reversed(messages):
            if msg.provider_metadata:
                anthropic_meta = msg.provider_metadata.get(APITypes.ANTHROPIC.value, {})
                container = anthropic_meta.get("container", {})
                if container and container.get("id"):
                    container_id = container["id"]
                    break

        ## NOTE: Currently hardcoding skills
        provider_options = (
            {
                "anthropic": {
                    "container": {
                        "skills": [
                            {
                                "type": "anthropic",
                                "skill_id": "pptx",
                                "version": "latest",
                            },
                            {
                                "type": "anthropic",
                                "skill_id": "xlsx",
                                "version": "latest",
                            },
                            {
                                "type": "anthropic",
                                "skill_id": "pdf",
                                "version": "latest",
                            },
                            {
                                "type": "anthropic",
                                "skill_id": "docx",
                                "version": "latest",
                            },
                        ],
                    }
                }
            }
            if isinstance(self.client, anthropic.AsyncAnthropic)
            else provider_options
        )  # Vertex does not support skills yet

        if container_id:
            provider_options["anthropic"]["container"]["id"] = container_id
            logger.info(f"Reusing container ID: {container_id} from previous messages")
        anthropic_options = (
            provider_options.get("anthropic", {}) if provider_options else {}
        )

        params, betas = self._prepare_request_params(
            messages, tools, anthropic_options, provider_files
        )

        logger.info(f"Preparing Anthropic API call with model: {params.get('model')}, betas: {betas}")
        logger.info(f"Message count: {len(params.get('messages', []))}, tools: {len(params.get('tools', []))}")

        accumulated_tool_calls = {}
        content_started = False
        current_tool_call_id = None  # Track the current tool call being processed

        logger.info("Starting Anthropic stream...")
        async with self.client.beta.messages.stream(**params, betas=betas) as stream:
            async for event in stream:
                # Content block start
                match event.type:
                    case "content_block_start":
                        part = event.content_block
                        block_type = part.type

                        match block_type:
                            case "thinking" | "redacted_thinking":
                                # Extended thinking block started
                                yield RunResponseEvent(type=EventType.THINKING_START)
                            case "text":
                                if not content_started:
                                    yield RunResponseEvent(type=EventType.CONTENT_START)
                                    content_started = True
                            case "tool_use":
                                # New tool call started
                                tool_call = ToolCall(
                                    id=part.id,
                                    name=part.name,
                                    input="",
                                    finished=False,
                                )
                                accumulated_tool_calls[part.id] = tool_call
                                current_tool_call_id = part.id  # Track current tool
                                yield RunResponseEvent(
                                    type=EventType.TOOL_USE_START, tool_call=tool_call
                                )
                            case "server_tool_use":
                                if part.name in [
                                    "code_execution",
                                    "text_editor_code_execution",
                                    "bash_code_execution",
                                ]:  # Currently only code execution
                                    tool_call = ToolCall(
                                        id=part.id,
                                        name="code_execution",
                                        input="",
                                        finished=False,
                                        provider_executed=True,
                                    )
                                    accumulated_tool_calls[part.id] = tool_call
                                    current_tool_call_id = part.id  # Track current tool
                                    yield RunResponseEvent(
                                        type=EventType.TOOL_USE_START,
                                        tool_call=tool_call,
                                    )
                            case (
                                "bash_code_execution_tool_result"
                                | "text_editor_code_execution_tool_result"
                            ):
                                logger.debug("ignore tool result in start event")
                            case _:
                                logger.warning(
                                    f"Unknown content block type: {block_type} in start event"
                                )

                    case "content_block_delta":
                        delta_type = event.delta.type
                        match delta_type:
                            case "text_delta":
                                text = event.delta.text
                                yield RunResponseEvent(
                                    type=EventType.CONTENT_DELTA, content=text
                                )
                            case "thinking_delta":
                                yield RunResponseEvent(
                                    type=EventType.THINKING_DELTA,
                                    thinking=event.delta.thinking,
                                )
                            case "input_json_delta":
                                # Tool call input delta - accumulate JSON for current tool
                                delta = event.delta.partial_json
                                if (
                                    current_tool_call_id
                                    and current_tool_call_id in accumulated_tool_calls
                                ):
                                    tool_name = (
                                        "code_execution"
                                        if tool_call.name
                                        in [
                                            "text_editor_code_execution",
                                            "bash_code_execution",
                                        ]
                                        else tool_call.name
                                    )
                                    tool_call = accumulated_tool_calls[
                                        current_tool_call_id
                                    ]
                                    if tool_call.input == "" and tool_call.name in [
                                        "text_editor_code_execution",
                                        "bash_code_execution",
                                    ]:
                                        delta = (
                                            f'{{"type": "{tool_call.name}",{delta[2:]}'
                                        )
                                    tool_call.input += delta
                                    yield RunResponseEvent(
                                        type=EventType.TOOL_USE_DELTA,
                                        tool_call=ToolCall(
                                            id=tool_call.id,
                                            name=tool_name,
                                            input=delta,
                                            finished=False,
                                        ),
                                    )
                                else:
                                    logger.warning(
                                        "Received input_json_delta but no current tool call is active."
                                    )
                            case "signature_delta":
                                # ignore signature deltas for now
                                continue
                            case _:
                                logger.warning(f"Unknown delta type: {delta_type}")
                    case "content_block_stop":
                        part = event.content_block
                        block_type = part.type
                        match block_type:
                            case "thinking" | "redacted_thinking":
                                if hasattr(part, "signature"):
                                    signature = part.signature
                                    yield RunResponseEvent(
                                        type=EventType.SIGNATURE_DELTA,
                                        signature=signature,
                                    )
                            case "text":
                                if content_started:
                                    yield RunResponseEvent(type=EventType.CONTENT_STOP)
                                    content_started = False
                            case "tool_use":
                                # Mark ONLY the current tool call as finished
                                if (
                                    current_tool_call_id
                                    and current_tool_call_id in accumulated_tool_calls
                                ):
                                    tool_call = accumulated_tool_calls[
                                        current_tool_call_id
                                    ]
                                    tool_call.finished = True
                                    yield RunResponseEvent(
                                        type=EventType.TOOL_USE_STOP,
                                        tool_call=tool_call,
                                    )
                                    current_tool_call_id = None
                            case "server_tool_use":
                                if (
                                    current_tool_call_id
                                    and current_tool_call_id in accumulated_tool_calls
                                ):
                                    tool_call = accumulated_tool_calls[part.id]
                                    logger.info(
                                        f"Server tool use stopped for tool call ID: {part.id}"
                                    )
                                    yield RunResponseEvent(
                                        type=EventType.TOOL_USE_STOP,
                                        tool_call=tool_call,
                                    )
                            case (
                                "bash_code_execution_tool_result"
                                | "text_editor_code_execution_tool_result"
                            ):
                                # Tool result - send as complete event
                                tool_result = ToolResult(
                                    tool_call_id=part.tool_use_id,
                                    name="code_execution",
                                    output=JsonResultContent(
                                        value=part.content.model_dump()
                                    ),
                                )
                                yield RunResponseEvent(
                                    type=EventType.TOOL_RESULT,
                                    tool_result=tool_result,
                                )
                            case _:
                                logger.warning(
                                    f"Unknown content block type: {block_type} in stop event"
                                )
                    case "message_stop":
                        # Get final message
                        message = await stream.get_final_message()

                        usage = TokenUsage(
                            prompt_tokens=message.usage.input_tokens,
                            completion_tokens=message.usage.output_tokens,
                            cache_write_tokens=getattr(
                                message.usage, "cache_creation_input_tokens", 0
                            ),
                            cache_read_tokens=getattr(
                                message.usage, "cache_read_input_tokens", 0
                            ),
                            model_name=self.llm_config.model,
                        )

                        finish_reason_map = {
                            "end_turn": FinishReason.END_TURN,
                            "max_tokens": FinishReason.MAX_TOKENS,
                            "tool_use": FinishReason.TOOL_USE,
                            "stop_sequence": FinishReason.END_TURN,
                        }
                        finish_reason = finish_reason_map.get(
                            message.stop_reason, FinishReason.UNKNOWN
                        )

                        provider_metadata = None
                        if message.container:
                            provider_metadata = {
                                "anthropic": {
                                    "container": message.container.model_dump(
                                        exclude={"expires_at"}
                                    )
                                }
                            }

                        file_ids = extract_file_ids(message)

                        files = await self._download_file_and_upload(
                            file_ids, session_id
                        )
                        logger.debug(f"Downloaded files: {files}")
                        yield RunResponseEvent(
                            type=EventType.COMPLETE,
                            response=RunResponseOutput(
                                content=self._extract_content_part_from_message(
                                    message
                                ),
                                usage=usage,
                                finish_reason=finish_reason,
                                files=files,
                                provider_metadata=provider_metadata,
                            ),
                        )
                    case (
                        "text"
                        | "thinking"
                        | "signature"
                        | "message_start"
                        | "message_delta"
                    ):
                        # These events are handled in their respective block events
                        continue
                    case _:
                        logger.debug(f"Unknown event type: {event.type}")

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {"id": self.model_name, "name": self.model_name}

    async def _download_file_and_upload(
        self, file_ids: List[str], session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Download files created by Anthropic code execution and store them locally.

        Args:
            file_ids: List of Anthropic file IDs to download
            session_id: Session ID for storing files

        Returns:
            List of file metadata dictionaries
        """
        if not file_ids:
            return []

        async with get_db_session_local() as db_session:
            # Get session to retrieve user_id
            result = await db_session.execute(
                select(Session).where(Session.id == session_id)
            )
            session = result.scalar_one_or_none()
            if not session:
                logger.error(f"Session {session_id} not found")
                return []

            user_id = session.user_id
            file_objects = []

            for file_id in file_ids:
                try:
                    # Retrieve file metadata from Anthropic
                    file_metadata = await self.client.beta.files.retrieve_metadata(
                        file_id=file_id
                    )

                    # Download file content from Anthropic
                    file_content_response = await self.client.beta.files.download(
                        file_id=file_id
                    )
                    # AsyncBinaryAPIResponse requires read() to get bytes
                    file_bytes = await file_content_response.read()

                    # Extract file info
                    file_name = file_metadata.filename
                    content_type = file_metadata.mime_type
                    file_size = len(file_bytes)

                    # Generate storage path
                    file_uuid = str(uuid.uuid4())
                    storage_path = get_session_file_path(
                        session_id=session_id,
                        file_id=file_uuid,
                        file_name=file_name,
                    )

                    # Create file-like object from bytes
                    file_obj_io = io.BytesIO(file_bytes)

                    # Store file in storage backend (GCS/local)
                    await anyio.to_thread.run_sync(
                        storage.write, file_obj_io, storage_path, content_type
                    )

                    # Create FileUpload record
                    file_upload = FileUpload(
                        id=file_uuid,
                        user_id=user_id,
                        session_id=session_id,
                        file_name=file_name,
                        file_size=file_size,
                        storage_path=storage_path,
                        content_type=content_type,
                    )
                    db_session.add(file_upload)

                    # Add to response list
                    file_objects.append(
                        {
                            "id": file_uuid,
                            "provider_file_id": file_id,
                            "file_name": file_name,
                            "content_type": content_type,
                            "file_size": file_size,
                        }
                    )

                    logger.info(
                        f"Downloaded and stored file from Anthropic: {file_name} ({file_id})"
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to download file {file_id}: {e}",
                        exc_info=True,
                    )
                    continue

            # Commit all file uploads
            await db_session.commit()

        return file_objects


def extract_file_ids(response):
    """
    Extract file IDs from code execution tool results.

    Handles both bash_code_execution and text_editor_code_execution results.
    Files created during code execution will have a file_id attribute that can be downloaded.

    Returns:
        List of unique file IDs (duplicates removed)
    """
    file_ids = set()  # Use set to automatically deduplicate
    for item in response.content:
        # Handle bash code execution results
        if item.type == "bash_code_execution_tool_result":
            content_item = item.content
            if content_item.type == "bash_code_execution_result":
                for file in content_item.content:
                    if hasattr(file, "file_id"):
                        file_ids.add(file.file_id)

        # Handle text editor code execution results
        elif item.type == "text_editor_code_execution_tool_result":
            content_item = item.content
            if content_item.type == "text_editor_code_execution_result":
                for file in content_item.content:
                    if hasattr(file, "file_id"):
                        file_ids.add(file.file_id)

    return list(file_ids)  # Convert back to list
