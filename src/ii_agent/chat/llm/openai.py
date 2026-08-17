"""OpenAI provider using official SDK with Responses API."""

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Tuple, Union

import openai
from openai.types import FileObject
from openai.types.containers import FileRetrieveResponse
from openai.types.responses import (
    Response,
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterCallCompletedEvent,
    ResponseCodeInterpreterCallInProgressEvent,
    ResponseCodeInterpreterToolCall,
    ResponseCompletedEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseErrorEvent,
    ResponseFailedEvent,
    ResponseFileSearchCallCompletedEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseFunctionToolCall,
    ResponseInProgressEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseOutputMessage,
    ResponseOutputRefusal,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningTextDoneEvent,
    ResponseRefusalDeltaEvent,
    ResponseRefusalDoneEvent,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseWebSearchCallCompletedEvent,
)
from openai.types.responses.response_output_text_param import (
    AnnotationContainerFileCitation,
)
from pydantic import BaseModel, Field
from sqlalchemy import or_, select

from ii_agent.billing.schemas import TokenUsage
from ii_agent.chat.base import LLMClient
from ii_agent.chat.providers.models import ChatProviderContainer, ChatProviderFile
from ii_agent.chat.prompts.openai_system_prompt import template
from ii_agent.chat.types import (
    ArrayResultContent,
    BinaryContent,
    CodeBlockContent,
    ContentPart,
    ErrorJsonContent,
    ErrorTextContent,
    EventType,
    ExecutionDeniedContent,
    FileDataContentPart,
    FileUrlContentPart,
    FinishReason,
    ImageDataContentPart,
    ImageUrlContentPart,
    JsonResultContent,
    Message,
    MessageRole,
    ReasoningContent,
    RunResponseEvent,
    RunResponseOutput,
    StorybookProgressContent,
    StorybookResultContent,
    TextContent,
    TextContentPart,
    TextResultContent,
    ToolCall,
)
from ii_agent.settings.llm import Provider
from ii_agent.settings.llm.schemas import ModelConfig
from ii_agent.core.db import get_db_session_local
from ii_agent.core.storage.client import get_storage
from ii_agent.core.storage.path_resolver import path_resolver
from ii_agent.files.models import FileAsset, SessionAsset
from ii_agent.files.types import AssetType

logger = logging.getLogger(__name__)


class OpenAIResponseParams(BaseModel):
    """Pydantic model for OpenAI Responses API parameters."""

    model: str = Field(..., description="Model to use for generation")
    input: Union[str, List[Dict[str, Any]]] = Field(..., description="Input messages or text")
    instructions: Optional[str] = Field(None, description="System instructions")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Available tools")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    stream: bool = Field(False, description="Enable streaming")
    max_output_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    reasoning: Optional[dict[str, Any]] = Field(None, description="Reasoning config")
    previous_response_id: Optional[str] = Field(None, description="Previous response ID")

    class Config:
        extra = "allow"  # Allow additional fields

    def to_dict(self, exclude_none: bool = True) -> Dict[str, Any]:
        """Convert to dictionary for API request, excluding None values by default."""
        return self.model_dump(exclude_none=exclude_none)


class FileResponseObject(BaseModel):
    """Pydantic model for OpenAI Responses API parameters."""

    id: str
    provider_file_id: str
    provider: Literal["openai", "anthropic"]
    content_type: str
    file_name: str
    file_size: Optional[int] = 0
    raw_file_object: Optional[FileObject | FileRetrieveResponse] = None


class ContainerFile(BaseModel):
    """Pydantic model for OpenAI Responses API parameters."""

    container_id: Optional[str]
    files: List[FileResponseObject]

    def get_container_file_ids(self):
        f_ids = []
        for f in self.files:
            if f.content_type.startswith("image") or f.content_type.endswith("pdf"):
                continue
            f_ids.append(f.provider_file_id)

        return f_ids

    def get_image_file_ids(self):
        f_ids = []
        for f in self.files:
            if f.content_type.startswith("image"):
                f_ids.append(f.provider_file_id)
        return f_ids

    def get_pdf_file_ids(self):
        f_ids = []
        for f in self.files:
            if f.content_type.endswith("pdf"):
                f_ids.append(f.provider_file_id)
        return f_ids


class OpenAIProvider(LLMClient):
    """Provider for OpenAI models using official SDK with Responses API."""

    CONTAINER_TTL_MINUTES = 20
    FILE_TTL_SECONDS = 6 * 60 * 60  # 6 hours

    def __init__(self, llm_config: ModelConfig):
        """Initialize OpenAI provider."""
        self.llm_config = llm_config
        self.model_name = llm_config.model

        api_key = llm_config.api_key.get_secret_value() if llm_config.api_key else None

        # Initialize client (Azure or standard)
        if llm_config.azure_endpoint:
            self.client = openai.AsyncAzureOpenAI(
                api_key=api_key,
                azure_endpoint=llm_config.azure_endpoint,
                api_version=llm_config.azure_api_version,
                max_retries=1,
            )
        else:
            base_url = llm_config.base_url or "https://api.openai.com/v1"
            self.client = openai.AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                max_retries=1,
            )

    async def get_or_create_container(self, session_id: uuid.UUID) -> ChatProviderContainer:
        """Ensure an OpenAI container exists for the given session.

        Uses dedicated provider_containers table:
        1. Query existing container from provider_containers table
        2. Check if container exists and is active via OpenAI API
        3. If not, create a new container
        4. Save to provider_containers table

        Returns:
            Tuple of (container_id, is_new_container):
            - container_id: The container ID if successful, None otherwise
            - is_new_container: True if a new container was created, False if reusing existing
        """
        async with get_db_session_local() as db_session:
            try:
                # Check if container already exists in database (only non-deleted)
                result = await db_session.execute(
                    select(ChatProviderContainer)
                    .where(
                        ChatProviderContainer.session_id == session_id,
                        ChatProviderContainer.provider == Provider.OPENAI.value,
                        ChatProviderContainer.status == "running",
                    )
                    .order_by(ChatProviderContainer.created_at.desc())
                    .limit(1)
                )

                container = result.scalar_one_or_none()
                should_create_new = False
                now = datetime.now(timezone.utc)
                if container:
                    if (now - container.created_at) < timedelta(minutes=self.CONTAINER_TTL_MINUTES):
                        return container

                    old_container_provider = await self.client.containers.retrieve(
                        container.container_id
                    )
                    if old_container_provider.status in ["expired", "deleted"]:
                        should_create_new = True
                        container.status = old_container_provider.status
                else:
                    should_create_new = True

                if should_create_new:
                    response = await self.client.containers.create(
                        name=session_id,
                        expires_after={
                            "anchor": "last_active_at",
                            "minutes": self.CONTAINER_TTL_MINUTES,
                        },
                    )

                    new_container = ChatProviderContainer(
                        session_id=session_id,
                        provider=Provider.OPENAI.value,
                        container_id=response.id,
                        status=response.status,
                        name=response.name,
                        expires_at=now + timedelta(minutes=self.CONTAINER_TTL_MINUTES),
                        raw_container_object=response.model_dump(),
                    )

                    db_session.add(new_container)
                    await db_session.flush()
                    await db_session.refresh(new_container)

                    return new_container

            except Exception as _:
                logger.error(
                    f"Could not create new container for session {session_id}",
                )
                raise

            return None

    async def _upload_single_file(self, file_info: FileAsset) -> FileResponseObject:
        """Upload a single file to OpenAI."""
        try:
            file_content = await get_storage().read(file_info.storage_path)
            try:
                file_obj = await self.client.files.create(
                    file=(
                        file_info.file_name,
                        file_content,
                        file_info.content_type,
                    ),
                    purpose="user_data",
                    expires_after={
                        "anchor": "created_at",
                        "seconds": self.FILE_TTL_SECONDS,
                    },
                )
            finally:
                file_content.close()

            return FileResponseObject(
                id=file_info.id,
                provider_file_id=file_obj.id,
                provider=Provider.OPENAI.value,
                raw_file_object=file_obj,
                content_type=file_info.content_type,
                file_name=file_info.file_name,
            )

        except Exception:
            logger.exception("Failed to upload file %s to OpenAI", file_info.id)

        return None

    async def upload_files(
        self,
        user_message: Message,
    ) -> List[FileResponseObject]:
        """Upload files from a user message concurrently to OpenAI."""

        if not user_message.file_ids:
            return []

        # assume last user message always new message.
        async with get_db_session_local() as db_session:
            now = datetime.now(timezone.utc)
            existing_result = await db_session.execute(
                select(ChatProviderFile).where(
                    ChatProviderFile.file_id.in_(user_message.file_ids),
                    ChatProviderFile.session_id == user_message.session_id,
                    ChatProviderFile.provider == Provider.OPENAI.value,
                    or_(
                        ChatProviderFile.expires_at.is_(None),
                        ChatProviderFile.created_at > (now - timedelta(self.FILE_TTL_SECONDS)),
                    ),
                )
            )

            existing_provider_files = {
                provider_file.file_id: provider_file.provider_file_id
                for provider_file in existing_result.scalars().all()
            }

            result = await db_session.execute(
                select(FileAsset).where(FileAsset.id.in_(user_message.file_ids))
            )
            file_uploads: List[FileAsset] = result.scalars().all()

        files_to_upload: List[FileAsset] = [
            f for f in file_uploads if f.id not in existing_provider_files
        ]

        if not files_to_upload:
            return []

        upload_tasks = [
            asyncio.create_task(self._upload_single_file(file_info))
            for file_info in files_to_upload
        ]

        upload_results = await asyncio.gather(*upload_tasks)
        new_provider_records: List[FileResponseObject] = [
            res for res in upload_results if res is not None
        ]

        if len(new_provider_records) == 0:
            return []

        try:
            async with get_db_session_local() as db_session:
                provider_files = []
                for file_response in new_provider_records:
                    provider_file = ChatProviderFile(
                        file_id=file_response.id,
                        provider=Provider.OPENAI.value,
                        session_id=user_message.session_id,
                        provider_file_id=file_response.provider_file_id,
                        raw_file_object=file_response.raw_file_object.model_dump(),
                        expires_at=datetime.fromtimestamp(
                            file_response.raw_file_object.expires_at,
                            tz=timezone.utc,
                        ),
                    )
                    db_session.add(provider_file)
                    provider_files.append(file_response)
                await db_session.commit()

            return provider_files

        except Exception as e:
            logger.exception(f"Error while create file provider, {e}")
            return []

    def _get_content_type(self, filename: str) -> str:
        """Determine content type from filename.

        Returns OpenAI supported MIME types based on official documentation.
        """
        file_lower = filename.lower()

        # Image formats
        if "png" in file_lower or file_lower.endswith(".png"):
            return "image/png"
        elif "jpg" in file_lower or "jpeg" in file_lower or file_lower.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        elif "gif" in file_lower or file_lower.endswith(".gif"):
            return "image/gif"
        elif "webp" in file_lower or file_lower.endswith(".webp"):
            return "image/webp"
        elif file_lower.endswith((".heic", ".heif")):
            return "image/jpeg"  # HEIC is converted to JPEG before sending

        # Programming languages
        elif file_lower.endswith(".c"):
            return "text/x-c"
        elif file_lower.endswith(".cpp"):
            return "text/x-c++"
        elif file_lower.endswith(".cs"):
            return "text/x-csharp"
        elif file_lower.endswith(".go"):
            return "text/x-golang"
        elif file_lower.endswith(".java"):
            return "text/x-java"
        elif file_lower.endswith(".php"):
            return "text/x-php"
        elif file_lower.endswith(".py"):
            return "text/x-python"
        elif file_lower.endswith(".rb"):
            return "text/x-ruby"
        elif file_lower.endswith(".sh"):
            return "application/x-sh"
        elif file_lower.endswith(".ts"):
            return "application/typescript"

        # Web formats
        elif file_lower.endswith(".css"):
            return "text/css"
        elif file_lower.endswith(".html"):
            return "text/html"
        elif file_lower.endswith(".js"):
            return "text/javascript"

        # Document formats
        elif file_lower.endswith(".json"):
            return "application/json"
        elif file_lower.endswith(".md"):
            return "text/markdown"
        elif file_lower.endswith(".pdf"):
            return "application/pdf"
        elif file_lower.endswith(".tex"):
            return "text/x-tex"
        elif file_lower.endswith(".txt"):
            return "text/plain"

        # Office formats
        elif file_lower.endswith(".doc"):
            return "application/msword"
        elif file_lower.endswith(".docx"):
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif file_lower.endswith(".pptx"):
            return "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        # Default to text/plain for unknown types
        return "text/plain"

    def _convert_messages(
        self, messages: List[Message], container_files: ContainerFile
    ) -> List[Dict[str, Any]]:
        """Convert Message objects to OpenAI Responses API format."""
        openai_messages = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                text_part = msg.content()
                if text_part:
                    openai_messages.append(
                        {
                            "type": "message",
                            "role": "system",
                            "content": [{"type": "input_text", "text": text_part.text}],
                        }
                    )

            elif msg.role == MessageRole.USER:
                content = []
                # Process all parts in message
                for part in msg.parts:
                    if isinstance(part, TextContent):
                        content.append({"type": "input_text", "text": part.text})
                    elif isinstance(part, BinaryContent):
                        # Handle BinaryContent (small PDF/images)
                        if part.mime_type.startswith("image"):
                            content.append(
                                {
                                    "type": "input_image",
                                    "image_url": f"data:image/jpeg;base64,{part.to_base64()}",
                                }
                            )
                        elif part.mime_type == "application/pdf":
                            content.append(
                                {
                                    "type": "input_file",
                                    "filename": part.path.split("/")[-1],
                                    "file_data": part.to_base64("openai"),
                                }
                            )
                        else:
                            logger.warning(f"Unsupported BinaryContent mime_type: {part.mime_type}")

                if content:
                    openai_messages.append({"type": "message", "role": "user", "content": content})

            elif msg.role == MessageRole.ASSISTANT:
                # Assistant messages with tool calls should be converted to function_call items
                text_part = msg.content()
                tool_calls = msg.tool_calls()
                # code_interpreter = msg.code_interpreter()
                # Add text content if present
                if text_part:
                    openai_messages.append(
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": text_part.text}],
                        }
                    )

                # Add tool calls as function_call items
                for tc in tool_calls:
                    if tc.finished:
                        openai_messages.append(
                            {
                                "type": "function_call",
                                "call_id": tc.id,
                                "name": tc.name,
                                "arguments": tc.input,
                            }
                        )

            elif msg.role == MessageRole.TOOL:
                # Tool result messages - Responses API format
                for result in msg.tool_results():
                    output = result.output
                    content_value = None

                    # Handle different output types using isinstance
                    if isinstance(output, (TextResultContent, ErrorTextContent)):
                        content_value = output.value
                    elif isinstance(output, ExecutionDeniedContent):
                        content_value = output.reason or "Tool execution denied."
                    elif isinstance(output, (JsonResultContent, ErrorJsonContent)):
                        import json

                        content_value = json.dumps(output.value)
                    elif isinstance(output, ArrayResultContent):
                        # Handle array content with different types
                        content_parts = []
                        for item in output.value:
                            if isinstance(item, TextContentPart):
                                content_parts.append({"type": "input_text", "text": item.text})
                            elif isinstance(item, ImageDataContentPart):
                                content_parts.append(
                                    {
                                        "type": "input_image",
                                        "image_url": f"data:{item.media_type};base64,{item.data}",
                                    }
                                )
                            elif isinstance(item, FileDataContentPart):
                                content_parts.append(
                                    {
                                        "type": "input_file",
                                        "filename": item.filename or "data",
                                        "file_data": f"data:{item.mime_type};base64,{item.data}",
                                    }
                                )
                            elif isinstance(item, ImageUrlContentPart):
                                content_parts.append(
                                    {
                                        "type": "input_text",
                                        "text": f"![Generated Image]({item.url})",
                                    }
                                )
                            elif isinstance(item, FileUrlContentPart):
                                content_parts.append(
                                    {
                                        "type": "input_text",
                                        "text": f"![Generated File]({item.url})",
                                    }
                                )
                            else:
                                logger.warning(f"Unsupported tool content part type: {item.type}")
                        content_value = content_parts
                    elif isinstance(output, StorybookProgressContent):
                        import json

                        progress_info = {
                            "type": "storybook_progress",
                            "storybook_id": output.storybook_id,
                            "storybook_name": output.storybook_name,
                            "total_pages": output.total_pages,
                            "completed_pages": output.completed_pages,
                            "current_page": output.current_page,
                            "status": output.status,
                            "generating_pages": output.generating_pages,
                            "error_message": output.error_message,
                        }
                        content_value = json.dumps(progress_info)
                    elif isinstance(output, StorybookResultContent):
                        # Handle storybook result - convert to structured text for LLM
                        import json

                        storybook_info = {
                            "type": "storybook",
                            "storybook_id": output.storybook_id,
                            "storybook_name": output.storybook_name,
                            "page_count": len(output.pages),
                            "pages": [
                                {
                                    "page_number": p.page_number,
                                    "image_url": p.image_url,
                                    "text_content": p.text_content,
                                }
                                for p in output.pages
                            ],
                        }
                        content_value = json.dumps(storybook_info)
                    else:
                        # Fallback for unknown types
                        logger.warning(f"Unknown tool result output type: {type(output)}")
                        content_value = str(output)

                    openai_messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": result.tool_call_id,
                            "output": content_value,
                        }
                    )

        return openai_messages

    async def _download_file_citations(
        self,
        file_citations: List[AnnotationContainerFileCitation],
        session_id: uuid.UUID,
    ) -> ContainerFile:
        """
        Download files from OpenAI container file citations and store them as FileAsset records.

        Args:
            file_citations: List of AnnotationContainerFileCitation objects from OpenAI
            session_id: Session ID for associating files

        Returns:
            ContainerFile object with downloaded file information
        """
        if not file_citations:
            return ContainerFile(container_id=None, files=[])

        file_objects = []

        async with get_db_session_local() as db_session:
            # Get user_id from session
            from ii_agent.sessions.models import Session

            result = await db_session.execute(select(Session).where(Session.id == session_id))
            session = result.scalar_one_or_none()
            if not session:
                logger.error(f"Session {session_id} not found")
                return ContainerFile(container_id=None, files=[])

            user_id = session.user_id
            container_id = None
            for citation in file_citations:
                try:
                    # Extract file_id from citation
                    file_id = citation.file_id
                    if not file_id:
                        logger.warning("File citation missing file_id, skipping")
                        continue

                    # Retrieve file metadata from OpenAI
                    file_obj = await self.client.containers.files.retrieve(
                        file_id=file_id, container_id=citation.container_id
                    )
                    container_id = citation.container_id
                    file_name = file_obj.path.split("/")[-1]
                    # Determine content type from file name
                    content_type = self._get_content_type(file_name)

                    # Download file content from OpenAI
                    # content.retrieve() returns HttpxBinaryResponseContent with .content property
                    file_content_response = await self.client.containers.files.content.retrieve(
                        file_id=file_obj.id, container_id=citation.container_id
                    )
                    # Get bytes content directly (async read)
                    file_bytes = await file_content_response.aread()

                    # Generate storage path under user prefix
                    import io
                    import uuid

                    file_uuid = str(uuid.uuid4())
                    ext = file_name.rsplit(".", 1)[-1] if "." in file_name else "bin"
                    asset_type = AssetType.from_content_type(content_type)
                    storage_path = path_resolver.user_file(user_id, asset_type, file_uuid, ext)

                    # Create file-like object from bytes
                    file_obj_io = io.BytesIO(file_bytes)

                    # Store file in storage backend (async)
                    await get_storage().write(storage_path, file_obj_io, content_type)

                    # Create FileAsset record
                    file_upload = FileAsset(
                        id=file_uuid,
                        user_id=user_id,
                        file_name=file_name,
                        file_size=len(file_bytes),
                        storage_path=storage_path,
                        content_type=content_type,
                    )
                    db_session.add(file_upload)
                    # Link to session
                    db_session.add(SessionAsset(session_id=session_id, asset_id=file_uuid))

                    # Create FileResponseObject
                    file_response = FileResponseObject(
                        id=file_uuid,
                        provider_file_id=file_id,
                        provider=Provider.OPENAI.value,
                        content_type=content_type,
                        file_name=file_name,
                        raw_file_object=file_obj,
                        file_size=len(file_bytes),
                    )
                    file_objects.append(file_response)

                    logger.info(f"Downloaded and stored file citation: {file_name} ({file_id})")
                    await db_session.commit()
                except Exception as e:
                    logger.error(
                        f"Failed to download file citation {getattr(citation, 'file_id', 'unknown')}: {e}",
                        exc_info=True,
                    )
                    continue

            # Commit all file uploads

        return ContainerFile(container_id=container_id, files=file_objects)

    async def _get_files_within_session(
        self, session_id: uuid.UUID, container_id: str
    ) -> ContainerFile:
        async with get_db_session_local() as db_session:
            now = datetime.now(timezone.utc)
            result = await db_session.execute(
                select(ChatProviderFile, FileAsset)
                .join(FileAsset, ChatProviderFile.file_id == FileAsset.id)
                .where(
                    ChatProviderFile.session_id == session_id,
                    ChatProviderFile.provider == Provider.OPENAI.value,
                    or_(
                        ChatProviderFile.expires_at.is_(None),
                        ChatProviderFile.created_at
                        > (now - timedelta(seconds=self.FILE_TTL_SECONDS)),
                    ),
                )
                .order_by(ChatProviderFile.created_at.desc())
            )

            file_objects = []
            for provider_file, file_upload in result.all():
                file_obj = FileResponseObject(
                    id=provider_file.file_id,
                    provider_file_id=provider_file.provider_file_id,
                    provider=provider_file.provider,
                    content_type=file_upload.content_type,
                    raw_file_object=provider_file.raw_file_object,
                    file_name=file_upload.file_name,
                )
                file_objects.append(file_obj)

        return ContainerFile(container_id=container_id, files=file_objects)

    def _convert_tools(
        self,
        tools: Optional[List[Dict[str, Any]]],
        container_file: ContainerFile,
        is_code_interpreter_enabled: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Convert tools from Chat Completions format to Responses API format.

        Chat Completions format (nested):
        {
            "type": "function",
            "function": {
                "name": str,
                "description": str,
                "parameters": dict
            }
        }

        Responses API format (flat):
        {
            "type": "function",
            "name": str,
            "description": str,
            "parameters": dict
        }
        """
        converted_tools = []

        if tools:
            for tool in tools:
                # Check if it's already in Responses API format (flat - has 'name' at top level)
                if "name" in tool:
                    converted_tools.append(tool)
                # Convert from Chat Completions format (nested - has 'function' key)
                elif "function" in tool and isinstance(tool["function"], dict):
                    func = tool["function"]
                    converted_tools.append(
                        {
                            "type": "function",
                            "name": func.get("name"),
                            "description": func.get("description"),
                            "parameters": func.get("parameters"),
                        }
                    )
                else:
                    # Unknown format, pass as-is and let API validate
                    converted_tools.append(tool)

        if is_code_interpreter_enabled:
            f_ids = container_file.get_container_file_ids()
            code_interpreter_tool = {
                "type": "code_interpreter",
                "container": {"type": "auto"},
            }
            if f_ids:
                code_interpreter_tool["container"]["file_ids"] = f_ids

            converted_tools.append(code_interpreter_tool)
            logger.info(f"Added code_interpreter tool with container tool: {code_interpreter_tool}")

        return converted_tools if converted_tools else None

    async def send(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        provider_options: Optional[Dict[str, Any]] = None,
        is_code_interpreter_enabled: bool = False,
        session_id: Optional[str] = None,
    ) -> RunResponseOutput:
        """Send messages and get complete response using Responses API.

        Args:
            messages: List of messages to send
            tools: Optional list of tools
            is_code_interpreter_enabled: Whether code interpreter is enabled
            session_id: Session ID for container management
            provider_options: Reserved for provider-specific request options
        """
        # Ensure container exists if code interpreter is enabled
        container_id = None
        if is_code_interpreter_enabled:
            await self.get_or_create_container(session_id)

        file_ids_to_upload = []
        # Upload only files from the latest user message
        if messages and messages[-1].role == MessageRole.USER:
            latest_msg = messages[-1]
            if latest_msg.file_ids:
                file_ids_to_upload.extend(latest_msg.file_ids)

        # Convert messages to input format
        openai_messages = self._convert_messages(messages, None)

        # Extract system message as instructions
        instructions = template.substitute(current_date=datetime.now().strftime("%Y-%m-%d"))
        openai_opts = (provider_options or {}).get("openai", {})
        user_messages = []

        for msg in openai_messages:
            if msg["role"] != "system":
                user_messages.append(msg)

        # Convert tools to Responses API format (with container if code interpreter enabled)
        openai_tools = None
        if container_id:
            openai_tools = self._convert_tools(
                tools,
                is_code_interpreter_enabled=is_code_interpreter_enabled,
                container_id=container_id,
            )

        # Build params using Pydantic model
        reasoning_config = (
            {"effort": "medium", "summary": "auto"} if self.llm_config.cot_model else None
        )
        params = OpenAIResponseParams(
            model=self.model_name,
            input=user_messages if user_messages else [],
            instructions=instructions,
            tools=openai_tools,
            stream=False,
            max_output_tokens=openai_opts.get("max_output_tokens"),
            reasoning=reasoning_config,
        )

        response: Response = await self.client.responses.create(**params.to_dict())

        # Extract content and tool calls from response.output
        content: Optional[str] = None
        tool_calls: List[ToolCall] = []

        for output_item in response.output:
            # Extract text content from message
            if output_item.type == "message":
                for content_part in output_item.content:
                    if isinstance(content_part, ResponseOutputText):
                        if content is None:
                            content = content_part.text
                        else:
                            content += content_part.text
                    elif isinstance(content_part, ResponseOutputRefusal):
                        if content is None:
                            content = content_part.refusal
                        else:
                            content += content_part.refusal

            # Extract function calls
            elif output_item.type == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=output_item.call_id,
                        name=output_item.name,
                        input=output_item.arguments,
                        finished=True,
                    )
                )

        # Extract usage with proper token details
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_write_tokens=0,
                cache_read_tokens=getattr(response.usage.input_tokens_details, "cached_tokens", 0),
                model_name=self.llm_config.model,
                total_tokens=response.usage.total_tokens,
            )

        # Map status to finish reason
        finish_reason_map = {
            "completed": (FinishReason.END_TURN if not tool_calls else FinishReason.TOOL_USE),
            "failed": FinishReason.ERROR,
            "incomplete": FinishReason.MAX_TOKENS,
            "cancelled": FinishReason.ERROR,
        }
        finish_reason = finish_reason_map.get(response.status, FinishReason.UNKNOWN)

        return RunResponseOutput(
            content=content,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def stream(
        self,
        messages: List[Message],
        session_id: uuid.UUID,
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
        provider_options: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response with granular events using Responses API.

        Args:
            messages: List of messages to send
            tools: Optional list of tools
            is_code_interpreter_enabled: Enable code interpreter tool
            session_id: Session ID for container management
            provider_options: Reserved for provider-specific request options
        """
        # Ensure container exists if code interpreter is enabled
        # container_id = None

        # if is_code_interpreter_enabled:
        # container = await self.get_or_create_container(session_id)
        # container_id = container.container_id

        last_user_msg: Optional[Message] = None
        # Upload only files from the latest user message
        if messages and messages[-1].role == MessageRole.USER:
            last_user_msg = messages[-1]

        if last_user_msg and last_user_msg.file_ids:
            logger.info(
                "Uploading %d files for session %s",
                len(last_user_msg.file_ids),
                session_id,
            )
            await self.upload_files(user_message=last_user_msg)

        container_files = await self._get_files_within_session(
            session_id=session_id, container_id=None
        )
        # Convert messages to input format
        openai_messages = self._convert_messages(messages, container_files)

        previous_response_id = None
        if messages:
            # Scan backwards to find last assistant message
            for message in reversed(messages):
                if message.role == MessageRole.ASSISTANT:
                    previous_response_id = (
                        (message.provider_metadata or {})
                        .get(Provider.OPENAI.value, {})
                        .get("response_id")
                    )
                    break  # Stop after finding first (last) assistant message
        # Extract system message as instructions
        instructions = template.substitute(current_date=datetime.now().strftime("%Y-%m-%d"))
        openai_opts = (provider_options or {}).get("openai", {})
        # Convert tools to Responses API format (with container if code interpreter enabled)
        openai_tools = self._convert_tools(
            tools,
            container_file=container_files,
            is_code_interpreter_enabled=is_code_interpreter_enabled,
        )

        # Build params using Pydantic model
        reasoning_config = (
            {"effort": "medium", "summary": "auto"} if self.llm_config.cot_model else None
        )
        params = OpenAIResponseParams(
            model=self.model_name,
            input=openai_messages,
            instructions=instructions,
            tools=openai_tools,
            stream=True,
            max_output_tokens=openai_opts.get("max_output_tokens"),
            reasoning=reasoning_config,
            previous_response_id=previous_response_id,
        )

        params_dict = params.to_dict()

        try:
            stream = await self.client.responses.create(**params_dict)
        except Exception as e:
            logger.error(f"Failed to create stream with params: {params_dict}")
            logger.error(f"Error details: {str(e)}")
            raise

        content_started = False
        tool_call_tracking = {}  # Track tool calls for delta events only

        async for event in stream:
            # Text content delta
            if isinstance(event, ResponseTextDeltaEvent):
                if not content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_START)
                    content_started = True
                yield RunResponseEvent(type=EventType.CONTENT_DELTA, content=event.delta)

            # Text content done
            elif isinstance(event, ResponseTextDoneEvent):
                if content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_STOP)

            # Reasoning content delta (for o1/o3/o4 models - full reasoning)
            elif isinstance(event, ResponseReasoningTextDeltaEvent):
                yield RunResponseEvent(type=EventType.THINKING_DELTA, thinking=event.delta)

            # Reasoning content done
            elif isinstance(event, ResponseReasoningTextDoneEvent):
                logger.debug(event.model_dump_json())
                pass  # Complete reasoning available in final response

            elif isinstance(event, ResponseReasoningSummaryTextDeltaEvent):
                yield RunResponseEvent(type=EventType.THINKING_DELTA, thinking=event.delta)

            # Reasoning summary done
            elif isinstance(event, ResponseReasoningSummaryTextDoneEvent):
                pass  # Complete reasoning summary available in final response

            # Refusal delta
            elif isinstance(event, ResponseRefusalDeltaEvent):
                yield RunResponseEvent(type=EventType.CONTENT_DELTA, content=event.delta)

            # Refusal done
            elif isinstance(event, ResponseRefusalDoneEvent):
                if content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_STOP)

            # Output item added (function call started)
            elif isinstance(event, ResponseOutputItemAddedEvent):
                # Check if this is a function call
                if event.item.type == "function_call":
                    item_id = event.item.id
                    tool_call_tracking[item_id] = {
                        "call_id": event.item.call_id,
                        "name": event.item.name,
                        "arguments": "",
                    }
                    yield RunResponseEvent(
                        type=EventType.TOOL_USE_START,
                        tool_call=ToolCall(
                            id=event.item.call_id,
                            name=event.item.name,
                            input="",
                            finished=False,
                        ),
                    )
            # elif event.item.type == "reasoning":
            #     yield ProviderEvent(type=EventType.THINKING_DELTA, thinking=event.delta)

            # Function call arguments delta (streaming arguments)
            elif isinstance(event, ResponseFunctionCallArgumentsDeltaEvent):
                item_id = event.item_id
                if item_id in tool_call_tracking:
                    # tool_call_tracking[item_id]["arguments"] += event.delta
                    yield RunResponseEvent(
                        type=EventType.TOOL_USE_DELTA,
                        tool_call=ToolCall(
                            id=tool_call_tracking[item_id]["call_id"],
                            name=tool_call_tracking[item_id]["name"],
                            input=event.delta,
                            finished=False,
                        ),
                    )

            # Function call arguments done (complete arguments available)
            elif isinstance(event, ResponseFunctionCallArgumentsDoneEvent):
                item_id = event.item_id
                if item_id in tool_call_tracking:
                    current_tool = tool_call_tracking[item_id]
                    tool_call_tracking[item_id]["arguments"] = event.arguments
                    yield RunResponseEvent(
                        type=EventType.TOOL_USE_STOP,
                        tool_call=ToolCall(
                            id=tool_call_tracking[item_id]["call_id"],
                            name=current_tool["name"],
                            input=event.arguments,
                            finished=True,
                        ),
                    )

            # Output item done
            elif isinstance(event, ResponseOutputItemDoneEvent):
                # Final confirmation that output item is complete
                logger.debug(f"Output item done: {event.item.type}")

            # Content part added
            elif isinstance(event, ResponseContentPartAddedEvent):
                logger.debug(f"Content part added at index {event.content_index}, event: {event}")

            # Content part done
            elif isinstance(event, ResponseContentPartDoneEvent):
                logger.debug(f"Content part done at index {event.content_index}, event: {event}")

            elif isinstance(event, ResponseCodeInterpreterCallInProgressEvent):
                logger.debug(f"Code interpreter start: {event}")
                yield RunResponseEvent(type=EventType.CONTENT_START)
                yield RunResponseEvent(type=EventType.CONTENT_DELTA, content="```python\n")

            # Code interpreter events
            elif isinstance(event, ResponseCodeInterpreterCallCodeDeltaEvent):
                logger.debug(f"Code interpreter delta: {event.delta}")
                yield RunResponseEvent(type=EventType.CONTENT_DELTA, content=event.delta)

            elif isinstance(event, ResponseCodeInterpreterCallCodeDoneEvent):
                yield RunResponseEvent(type=EventType.CONTENT_DELTA, content="\n```")

                logger.debug(f"Code interpreter done: {event.code}")
                yield RunResponseEvent(type=EventType.CONTENT_STOP)

            elif isinstance(event, ResponseCodeInterpreterCallCompletedEvent):
                logger.debug(f"Code interpreter completed for item {event.item_id}")

            # File search completed
            elif isinstance(event, ResponseFileSearchCallCompletedEvent):
                logger.debug(f"File search completed for item {event.item_id}")

            # Web search completed
            elif isinstance(event, ResponseWebSearchCallCompletedEvent):
                logger.debug(f"Web search completed for item {event.item_id}")

            # Response created
            elif isinstance(event, ResponseCreatedEvent):
                logger.debug(f"Response created: {event.response.id}")

            # Response in progress
            elif isinstance(event, ResponseInProgressEvent):
                logger.debug(f"Response in progress: {event.response.status}")

            # Response completed
            elif isinstance(event, ResponseCompletedEvent):
                if content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_STOP)

                content_parts, file_citations = (
                    self._extract_content_part_file_citation_from_response(event.response)
                )

                # Extract usage with proper token details
                usage = TokenUsage()
                if event.response.usage:
                    # Extract cache tokens from input_tokens_details
                    cache_read = 0

                    if event.response.usage:
                        cache_read = getattr(
                            event.response.usage.input_tokens_details,
                            "cached_tokens",
                            0,
                        )

                    # Extract reasoning tokens from output_tokens_details
                    reasoning_tokens = 0
                    if (
                        hasattr(event.response.usage, "output_tokens_details")
                        and event.response.usage.output_tokens_details
                    ):
                        reasoning_tokens = getattr(
                            event.response.usage.output_tokens_details,
                            "reasoning_tokens",
                            0,
                        )

                    usage = TokenUsage(
                        input_tokens=event.response.usage.input_tokens,
                        output_tokens=event.response.usage.output_tokens,
                        cache_write_tokens=0,
                        cache_read_tokens=cache_read,
                        input_token_details=event.response.usage.input_tokens_details.model_dump(),
                        output_token_details=event.response.usage.output_tokens_details.model_dump(),
                        model_name=self.llm_config.model,
                        total_tokens=event.response.usage.total_tokens,
                    )

                    logger.info(
                        f"Usage - Input: {usage.input_tokens}, Output: {usage.output_tokens}, Reasoning: {reasoning_tokens}, Cache read: {cache_read}"
                    )

                have_tool_call = any(isinstance(part, ToolCall) for part in content_parts)

                # Determine finish reason based on response status and tool calls
                finish_reason = FinishReason.END_TURN
                if have_tool_call:
                    finish_reason = FinishReason.TOOL_USE
                elif event.response.status == "failed":
                    finish_reason = FinishReason.ERROR
                elif event.response.status == "incomplete":
                    finish_reason = FinishReason.MAX_TOKENS

                container_files = None
                if len(file_citations) > 0:
                    container_files = await self._download_file_citations(
                        file_citations=file_citations, session_id=session_id
                    )

                provider_metadata = {Provider.OPENAI.value: {"response_id": event.response.id}}
                yield RunResponseEvent(
                    type=EventType.COMPLETE,
                    response=RunResponseOutput(
                        content=content_parts,
                        usage=usage,
                        finish_reason=finish_reason,
                        files=(
                            container_files.model_dump(exclude_none=True).get("files")
                            if container_files
                            else None
                        ),
                        provider_metadata=provider_metadata,
                    ),
                )

            # Response failed
            elif isinstance(event, ResponseFailedEvent):
                error_msg = f"Response failed: {event.response.status}"
                logger.error(error_msg)
                yield RunResponseEvent(
                    type=EventType.ERROR,
                    error=Exception(error_msg),
                )

            # Error event
            elif isinstance(event, ResponseErrorEvent):
                error_msg = f"Error: {event.message} (code: {event.code})"
                logger.error(error_msg)
                yield RunResponseEvent(
                    type=EventType.ERROR,
                    error=Exception(error_msg),
                )

    def model(self) -> Dict[str, Any]:
        """Get model metadata."""
        return {"id": self.model_name, "name": self.model_name}

    def _extract_content_part_file_citation_from_response(
        self, response: Response
    ) -> Tuple[List[ContentPart], List[AnnotationContainerFileCitation]]:
        content_parts = []
        file_citations = []
        for output_item in response.output:
            match output_item:
                case ResponseOutputMessage():
                    for content_part in output_item.content:
                        if isinstance(content_part, ResponseOutputText):
                            content_parts.append(TextContent(text=content_part.text))
                            if content_part.annotations:
                                for annotation in content_part.annotations:
                                    if annotation.type == "container_file_citation":
                                        file_citations.append(annotation)
                        elif isinstance(content_part, ResponseOutputRefusal):
                            content_parts.append(TextContent(text=content_part.refusal))
                case ResponseCodeInterpreterToolCall():
                    logger.debug(
                        f"Code interpreter call completed: {output_item.id}, status: {output_item.status}"
                    )
                    content_parts.append(
                        CodeBlockContent(
                            id=output_item.id,
                            content=output_item.code,
                            status=output_item.status,
                            outputs=output_item.outputs,
                            container_id=output_item.container_id,
                        )
                    )

                case ResponseFunctionToolCall():
                    content_parts.append(
                        ToolCall(
                            id=output_item.call_id,
                            name=output_item.name,
                            input=output_item.arguments,
                            finished=True,
                        )
                    )
                case ResponseReasoningItem():
                    for summary in output_item.summary:
                        content_parts.append(
                            ReasoningContent(
                                thinking=summary.text,
                                provider_options={
                                    "openai": {
                                        "item_id": output_item.id,
                                        "encrypted_content": output_item.encrypted_content,
                                    }
                                },
                            )
                        )
                case _:
                    logger.warning(f"Unknown output item type: {type(output_item)}")

        return content_parts, file_citations
