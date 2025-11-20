"""OpenAI provider using official SDK with Responses API."""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from string import Template
from typing import AsyncIterator, List, Literal, Optional, Dict, Any, Tuple, Union
from pydantic import BaseModel, Field

import anyio
import openai
from sqlalchemy import select, or_
from openai.types.responses.response_output_text_param import (
    AnnotationContainerFileCitation,
)
from openai.types.containers import FileRetrieveResponse
from openai.types.responses import (
    Response,
    ResponseCodeInterpreterToolCall,
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseReasoningItem,
    ResponseTextDeltaEvent,
    ResponseTextDoneEvent,
    ResponseFunctionCallArgumentsDeltaEvent,
    ResponseFunctionCallArgumentsDoneEvent,
    ResponseOutputItemAddedEvent,
    ResponseOutputItemDoneEvent,
    ResponseContentPartAddedEvent,
    ResponseContentPartDoneEvent,
    ResponseCreatedEvent,
    ResponseCompletedEvent,
    ResponseInProgressEvent,
    ResponseFailedEvent,
    ResponseErrorEvent,
    ResponseReasoningTextDeltaEvent,
    ResponseReasoningTextDoneEvent,
    ResponseReasoningSummaryTextDeltaEvent,
    ResponseReasoningSummaryTextDoneEvent,
    ResponseRefusalDeltaEvent,
    ResponseRefusalDoneEvent,
    ResponseCodeInterpreterCallCodeDeltaEvent,
    ResponseCodeInterpreterCallCodeDoneEvent,
    ResponseCodeInterpreterCallCompletedEvent,
    ResponseFileSearchCallCompletedEvent,
    ResponseWebSearchCallCompletedEvent,
    ResponseOutputText,
    ResponseOutputRefusal,
    ResponseCodeInterpreterCallInProgressEvent,
)
from openai.types import FileObject
from ii_agent.core.config.llm_config import APITypes, LLMConfig
from ii_agent.core.storage.locations import get_session_file_path
from ii_agent.metrics.models import TokenUsage
from ii_agent.server.chat.base import LLMClient
from ii_agent.server.chat.models import (
    RunResponseEvent,
    RunResponseOutput,
    EventType,
    CodeBlockContent,
    ContentPart,
    Message,
    MessageRole,
    ReasoningContent,
    TextContent,
    ToolCall,
    FinishReason,
    TextResultContent,
    JsonResultContent,
    ExecutionDeniedContent,
    ErrorTextContent,
    ErrorJsonContent,
    ArrayResultContent,
    TextContentPart,
    ImageDataContentPart,
    FileDataContentPart,
)

from ii_agent.db.models import FileUpload
from ii_agent.db.llm_provider import ProviderContainer, ProviderFile
from ii_agent.db.manager import get_db_session_local
from ii_agent.server.shared import storage

logger = logging.getLogger(__name__)


class OpenAIResponseParams(BaseModel):
    """Pydantic model for OpenAI Responses API parameters."""

    model: str = Field(..., description="Model to use for generation")
    input: Union[str, List[Dict[str, Any]]] = Field(
        ..., description="Input messages or text"
    )
    instructions: Optional[str] = Field(None, description="System instructions")
    tools: Optional[List[Dict[str, Any]]] = Field(None, description="Available tools")
    temperature: Optional[float] = Field(None, description="Sampling temperature")
    stream: bool = Field(False, description="Enable streaming")
    max_output_tokens: Optional[int] = Field(
        None, description="Maximum tokens to generate"
    )
    reasoning: Optional[dict[str, Any]] = Field(None, description="Reasoning config")
    previous_response_id: Optional[str] = Field(
        None, description="Previous response ID"
    )

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


SYSTEM_PROMPT_TEMPLATE = """
system_message:
role: system
model: gpt-5
---
You are ChatGPT, a large language model based on the GPT-5 model and trained by OpenAI.
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
- Text processing and parsing, data extraction, analysis from files (CSV, JSON, XML, PDF.etc)
- Any task requiring code execution

# Mermaid blocks
- When you want to create a mermaid diagram, MUST generate markdown that can be pasted into a mermaid.js viewer

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


class OpenAIProvider(LLMClient):
    """Provider for OpenAI models using official SDK with Responses API."""

    CONTAINER_TTL_MINUTES = 20
    FILE_TTL_SECONDS = 6 * 60 * 60  # 6 hours

    def __init__(self, llm_config: LLMConfig):
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

    async def get_or_create_container(self, session_id: str) -> ProviderContainer:
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
                    select(ProviderContainer)
                    .where(
                        ProviderContainer.session_id == session_id,
                        ProviderContainer.provider == APITypes.OPENAI.value,
                        ProviderContainer.status == "running",
                    )
                    .order_by(ProviderContainer.created_at.desc())
                    .limit(1)
                )

                container = result.scalar_one_or_none()
                should_create_new = False
                now = datetime.now(timezone.utc)
                if container:
                    if (now - container.created_at) < timedelta(
                        minutes=self.CONTAINER_TTL_MINUTES
                    ):
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

                    new_container = ProviderContainer(
                        session_id=session_id,
                        provider=APITypes.OPENAI.value,
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

    async def _upload_single_file(self, file_info: FileUpload) -> FileResponseObject:
        """Upload a single file to OpenAI."""
        try:
            file_content = await anyio.to_thread.run_sync(
                storage.read, file_info.storage_path
            )
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
                provider=APITypes.OPENAI.value,
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
                select(ProviderFile).where(
                    ProviderFile.file_id.in_(user_message.file_ids),
                    ProviderFile.session_id == user_message.session_id,
                    ProviderFile.provider == APITypes.OPENAI.value,
                    or_(
                        ProviderFile.expires_at.is_(None),
                        ProviderFile.created_at
                        > (now - timedelta(self.FILE_TTL_SECONDS)),
                    ),
                )
            )

            existing_provider_files = {
                provider_file.file_id: provider_file.provider_file_id
                for provider_file in existing_result.scalars().all()
            }

            result = await db_session.execute(
                select(FileUpload).where(FileUpload.id.in_(user_message.file_ids))
            )
            file_uploads: List[FileUpload] = result.scalars().all()

        files_to_upload: List[FileUpload] = [
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
                    provider_file = ProviderFile(
                        file_id=file_response.id,
                        provider=APITypes.OPENAI.value,
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
        elif (
            "jpg" in file_lower
            or "jpeg" in file_lower
            or file_lower.endswith((".jpg", ".jpeg"))
        ):
            return "image/jpeg"
        elif "gif" in file_lower or file_lower.endswith(".gif"):
            return "image/gif"
        elif "webp" in file_lower or file_lower.endswith(".webp"):
            return "image/webp"

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
                # Add text content
                text_part = msg.content()
                if text_part:
                    content.append({"type": "input_text", "text": text_part.text})
                # Load and add files if file_ids present
                # TODO: Poor performance, should be improved
                for c_fid in container_files.get_image_file_ids():
                    content.append(
                        {
                            "type": "input_image",
                            "file_id": c_fid,
                        }
                    )
                for c_fid in container_files.get_pdf_file_ids():
                    content.append({"type": "input_file", "file_id": c_fid})

                if content:
                    openai_messages.append(
                        {"type": "message", "role": "user", "content": content}
                    )

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
                            "content": [
                                {"type": "output_text", "text": text_part.text}
                            ],
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
                                content_parts.append(
                                    {"type": "input_text", "text": item.text}
                                )
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
                            else:
                                logger.warning(
                                    f"Unsupported tool content part type: {item.type}"
                                )
                        content_value = content_parts
                    else:
                        # Fallback for unknown types
                        logger.warning(
                            f"Unknown tool result output type: {type(output)}"
                        )
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
        session_id: str,
    ) -> ContainerFile:
        """
        Download files from OpenAI container file citations and store them as FileUpload records.

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
            from ii_agent.db.models import Session

            result = await db_session.execute(
                select(Session).where(Session.id == session_id)
            )
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
                    file_content_response = (
                        await self.client.containers.files.content.retrieve(
                            file_id=file_obj.id, container_id=citation.container_id
                        )
                    )
                    # Get bytes content directly (async read)
                    file_bytes = await file_content_response.aread()

                    # Generate storage path
                    import uuid
                    import io

                    file_uuid = str(uuid.uuid4())
                    storage_path = get_session_file_path(
                        session_id=session_id,
                        file_id=file_uuid,
                        file_name=file_name,
                    )

                    # Create file-like object from bytes (storage.write expects file-like object)
                    file_obj_io = io.BytesIO(file_bytes)

                    # Store file in our storage backend (blocking I/O operation)
                    # Note: storage.write signature is write(content, path, content_type)
                    await anyio.to_thread.run_sync(
                        storage.write, file_obj_io, storage_path, content_type
                    )

                    # Create FileUpload record
                    file_upload = FileUpload(
                        id=file_uuid,
                        user_id=user_id,
                        session_id=session_id,
                        file_name=file_name,
                        file_size=len(file_bytes),
                        storage_path=storage_path,
                        content_type=content_type,
                    )
                    db_session.add(file_upload)

                    # Create FileResponseObject
                    file_response = FileResponseObject(
                        id=file_uuid,
                        provider_file_id=file_id,
                        provider=APITypes.OPENAI.value,
                        content_type=content_type,
                        file_name=file_name,
                        raw_file_object=file_obj,
                        file_size=len(file_bytes),
                    )
                    file_objects.append(file_response)

                    logger.info(
                        f"Downloaded and stored file citation: {file_name} ({file_id})"
                    )
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
        self, session_id: str, container_id: str
    ) -> ContainerFile:
        async with get_db_session_local() as db_session:
            now = datetime.now(timezone.utc)
            result = await db_session.execute(
                select(ProviderFile, FileUpload)
                .join(FileUpload, ProviderFile.file_id == FileUpload.id)
                .where(
                    ProviderFile.session_id == session_id,
                    ProviderFile.provider == APITypes.OPENAI.value,
                    or_(
                        ProviderFile.expires_at.is_(None),
                        ProviderFile.created_at
                        > (now - timedelta(seconds=self.FILE_TTL_SECONDS)),
                    ),
                )
                .order_by(ProviderFile.created_at.desc())
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
            logger.info(
                f"Added code_interpreter tool with container tool: {code_interpreter_tool}"
            )

        return converted_tools if converted_tools else None

    async def send(
        self,
        messages: List[Message],
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
        session_id: Optional[str] = None,
    ) -> RunResponseOutput:
        """Send messages and get complete response using Responses API.

        Args:
            messages: List of messages to send
            tools: Optional list of tools
            is_code_interpreter_enabled: Whether code interpreter is enabled
            session_id: Session ID for container management
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
        instructions = template.substitute(
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
        user_messages = []

        for msg in openai_messages:
            if msg["role"] != "system":
                user_messages.append(msg)

        # Convert tools to Responses API format (with container if code interpreter enabled)
        openai_tools = self._convert_tools(
            tools,
            is_code_interpreter_enabled=is_code_interpreter_enabled,
            container_id=container_id,
        )

        # Build params using Pydantic model
        params = OpenAIResponseParams(
            model=self.model_name,
            input=user_messages if user_messages else [],
            instructions=instructions,
            tools=openai_tools,
            stream=False,
            reasoning={"effort": "medium", "summary": "auto"},
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
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                cache_write_tokens=0,
                cache_read_tokens=getattr(
                    response.usage.input_tokens_details, "cached_tokens", 0
                ),
                model_name=self.llm_config.model,
                total_tokens=response.usage.total_tokens,
            )

        # Map status to finish reason
        finish_reason_map = {
            "completed": (
                FinishReason.END_TURN if not tool_calls else FinishReason.TOOL_USE
            ),
            "failed": FinishReason.ERROR,
            "incomplete": FinishReason.MAX_TOKENS,
            "cancelled": FinishReason.ERROR,
        }
        finish_reason = finish_reason_map.get(response.status, FinishReason.UNKNOWN)

        return RunResponseOutput(
            content=content,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def stream(
        self,
        messages: List[Message],
        session_id: str,
        tools: Optional[List[Any]] = None,
        is_code_interpreter_enabled: bool = False,
    ) -> AsyncIterator[RunResponseEvent]:
        """Stream response with granular events using Responses API.

        Args:
            messages: List of messages to send
            tools: Optional list of tools
            is_code_interpreter_enabled: Enable code interpreter tool
            session_id: Session ID for container management
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
                        .get(APITypes.OPENAI.value, {})
                        .get("response_id")
                    )
                    break  # Stop after finding first (last) assistant message
        # Extract system message as instructions
        instructions = template.substitute(
            current_date=datetime.now().strftime("%Y-%m-%d")
        )
        # Convert tools to Responses API format (with container if code interpreter enabled)
        openai_tools = self._convert_tools(
            tools,
            container_file=container_files,
            is_code_interpreter_enabled=is_code_interpreter_enabled,
        )

        # Build params using Pydantic model
        params = OpenAIResponseParams(
            model=self.model_name,
            input=openai_messages,
            instructions=instructions,
            tools=openai_tools,
            stream=True,
            reasoning={"effort": "medium", "summary": "auto"},
            previous_response_id=previous_response_id,
        )

        params_dict = params.to_dict()
        logger.info(
            f"Sending request to OpenAI Responses API with params keys: {list(params_dict.keys())}"
        )
        logger.info(f"Full params: {params.model_dump_json()}")

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
                yield RunResponseEvent(
                    type=EventType.CONTENT_DELTA, content=event.delta
                )

            # Text content done
            elif isinstance(event, ResponseTextDoneEvent):
                if content_started:
                    yield RunResponseEvent(type=EventType.CONTENT_STOP)

            # Reasoning content delta (for o1/o3/o4 models - full reasoning)
            elif isinstance(event, ResponseReasoningTextDeltaEvent):
                yield RunResponseEvent(
                    type=EventType.THINKING_DELTA, thinking=event.delta
                )

            # Reasoning content done
            elif isinstance(event, ResponseReasoningTextDoneEvent):
                logger.debug(event.model_dump_json())
                pass  # Complete reasoning available in final response

            elif isinstance(event, ResponseReasoningSummaryTextDeltaEvent):
                yield RunResponseEvent(
                    type=EventType.THINKING_DELTA, thinking=event.delta
                )

            # Reasoning summary done
            elif isinstance(event, ResponseReasoningSummaryTextDoneEvent):
                pass  # Complete reasoning summary available in final response

            # Refusal delta
            elif isinstance(event, ResponseRefusalDeltaEvent):
                yield RunResponseEvent(
                    type=EventType.CONTENT_DELTA, content=event.delta
                )

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
                logger.debug(
                    f"Content part added at index {event.content_index}, event: {event}"
                )

            # Content part done
            elif isinstance(event, ResponseContentPartDoneEvent):
                logger.debug(
                    f"Content part done at index {event.content_index}, event: {event}"
                )

            elif isinstance(event, ResponseCodeInterpreterCallInProgressEvent):
                logger.debug(f"Code interpreter start: {event}")
                yield RunResponseEvent(type=EventType.CONTENT_START)
                yield RunResponseEvent(
                    type=EventType.CONTENT_DELTA, content="```python\n"
                )

            # Code interpreter events
            elif isinstance(event, ResponseCodeInterpreterCallCodeDeltaEvent):
                logger.debug(f"Code interpreter delta: {event.delta}")
                yield RunResponseEvent(
                    type=EventType.CONTENT_DELTA, content=event.delta
                )

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
                    self._extract_content_part_file_citation_from_response(
                        event.response
                    )
                )

                # Extract usage with proper token details
                usage = TokenUsage()
                if event.response.usage:
                    # Extract cache tokens from input_tokens_details
                    cache_creation = 0
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
                        prompt_tokens=event.response.usage.input_tokens,
                        completion_tokens=event.response.usage.output_tokens,
                        cache_creation_tokens=cache_creation,
                        cache_read_tokens=cache_read,
                        input_token_details=event.response.usage.input_tokens_details.model_dump(),
                        output_token_details=event.response.usage.output_tokens_details.model_dump(),
                        model_name=self.llm_config.model,
                        total_tokens=event.response.usage.total_tokens,
                    )

                    logger.info(
                        f"Usage - Input: {usage.prompt_tokens}, Output: {usage.completion_tokens}, Reasoning: {reasoning_tokens}, Cache read: {cache_read}"
                    )

                have_tool_call = any(
                    isinstance(part, ToolCall) for part in content_parts
                )

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

                provider_metadata = {
                    APITypes.OPENAI.value: {"response_id": event.response.id}
                }
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
