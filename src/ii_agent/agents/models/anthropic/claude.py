import json
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass
from os import getenv
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from uuid import uuid4

import httpcore
import httpx
from pydantic import BaseModel

from ii_agent.agents.exceptions import ModelProviderError, ModelRateLimitError
from ii_agent.files.media import Image
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Citations, DocumentCitation, Message, UrlCitation
from ii_agent.agents.models.metrics import Metrics
from ii_agent.settings.llm import Provider
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.runs.agent import RunOutput
from ii_agent.agents.utils.http import get_default_async_client
from ii_agent.core.logger import logger

try:
    from anthropic import Anthropic as AnthropicClient
    from anthropic import (
        APIConnectionError,
        APIStatusError,
        RateLimitError,
    )
    from anthropic import (
        AsyncAnthropic as AsyncAnthropicClient,
    )
    from anthropic.lib.streaming._beta_types import (
        BetaRawContentBlockStartEvent,
        ParsedBetaContentBlockStopEvent,
        ParsedBetaMessageStopEvent,
    )
    from anthropic.types import (
        CitationPageLocation,
        CitationsWebSearchResultLocation,
        ContentBlockDeltaEvent,
        ContentBlockStartEvent,
        ContentBlockStopEvent,
        MessageDeltaUsage,
        # MessageDeltaEvent,  # Currently broken
        MessageStopEvent,
        Usage,
    )
    from anthropic.types import (
        Message as AnthropicMessage,
    )

except ImportError as e:
    raise ImportError(
        "`anthropic` not installed. Please install it with `pip install anthropic`"
    ) from e

# Import Beta types
try:
    from anthropic.types.beta import BetaRawContentBlockDeltaEvent
    from anthropic.types.beta.beta_message import BetaMessage
    from anthropic.types.beta.beta_usage import BetaUsage
except ImportError as e:
    raise ImportError(
        "`anthropic` not installed or missing beta components. Please install with `pip install anthropic`"
    ) from e


ROLE_MAP = {
    "system": "system",
    "developer": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "user",
}


@dataclass
class MCPServerConfiguration:
    """Simple representation of an MCP server for Anthropic requests."""

    name: str
    url: str
    api_key: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None


def _normalize_tool_definition(tool: Any) -> Optional[Dict[str, Any]]:
    if tool is None:
        return None
    if isinstance(tool, dict):
        return tool.get("function") if "function" in tool else tool
    if hasattr(tool, "to_dict"):
        try:
            data = tool.to_dict()  # type: ignore
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    if hasattr(tool, "model_dump"):
        try:
            data = tool.model_dump(exclude_none=True)  # type: ignore
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def format_tools_for_model(tools: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Convert agent tool definitions into Anthropic's expected schema."""

    formatted: List[Dict[str, Any]] = []
    for tool in tools or []:
        definition = _normalize_tool_definition(tool)
        if not definition:
            continue
        name = definition.get("name")
        if not name:
            continue
        description = definition.get("description")
        parameters = definition.get("parameters") or {
            "type": "object",
            "properties": {},
        }
        formatted.append(
            {
                "name": name,
                "description": description,
                "input_schema": parameters,
            }
        )
    return formatted


def _format_image_for_message(image: Image) -> Optional[Dict[str, Any]]:
    """
    Add an image to a message by converting it to base64 encoded format.
    """
    using_filetype = False

    import base64

    # 'imghdr' was deprecated in Python 3.11: https://docs.python.org/3/library/imghdr.html
    # 'filetype' used as a fallback
    try:
        import imghdr
    except ImportError:
        try:
            import filetype

            using_filetype = True
        except ImportError:
            raise ImportError(
                "`filetype` not installed. Please install using `pip install filetype`"
            )

    type_mapping = {
        "jpeg": "image/jpeg",
        "jpg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
        "heic": "image/jpeg",
        "heif": "image/jpeg",
    }

    try:
        img_type = None

        # Case 0: Image is an Anthropic uploaded file
        if image.content is not None and hasattr(image.content, "id"):
            content_bytes = image.content

        # Case 1: Image is a URL
        if image.url is not None:
            content_bytes = image.get_content_bytes()  # type: ignore

            # If image URL has a suffix, use it as the type (without dot)
            import os
            from urllib.parse import urlparse

            if image.url:
                parsed_url = urlparse(image.url)
                _, ext = os.path.splitext(parsed_url.path)
                if ext:
                    img_type = ext.lstrip(".").lower()

        # Case 3: Image is a bytes object
        elif image.content is not None:
            content_bytes = image.content

        # Case 4: Image has a local/sandbox filepath
        elif image.filepath is not None:
            content_bytes = image.get_content_bytes()

        else:
            logger.error(f"Unsupported image type: {type(image)}")
            return None

        if not img_type:
            if using_filetype:
                kind = filetype.guess(content_bytes)
                if kind:
                    img_type = kind.extension
            else:
                img_type = imghdr.what(None, h=content_bytes)  # type: ignore

        # Fallback: imghdr/filetype may not recognise HEIC — use magic bytes
        if not img_type and content_bytes is not None:
            from ii_agent.agents.utils.heic import is_heic_format

            if is_heic_format(image_bytes=content_bytes):
                img_type = "heic"

        if not img_type:
            logger.error("Unable to determine image type")
            return None

        media_type = type_mapping.get(img_type)
        if not media_type:
            logger.error(f"Unsupported image type: {img_type}")
            return None

        # Convert HEIC/HEIF to JPEG since Anthropic API doesn't support them natively
        if img_type in ("heic", "heif"):
            try:
                from ii_agent.agents.utils.heic import convert_heic_to_jpeg

                # Anthropic limit: ~3.75 MB raw (5 MB base64)
                max_size = int(5 * 1024 * 1024 * 3 / 4)
                content_bytes, _ = convert_heic_to_jpeg(content_bytes, max_size=max_size)
            except ImportError:
                logger.error("pillow-heif not installed, cannot convert HEIC image")
                return None
            except Exception as e:
                logger.error(f"Failed to convert HEIC to JPEG: {e}")
                return None

        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.b64encode(content_bytes).decode("utf-8"),  # type: ignore
            },
        }
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        return None


def format_messages(
    messages: List[Message],
    cache_conversation: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Convert internal messages into Anthropic chat format.

    Args:
        messages: List of messages to format
        cache_conversation: If True, add cache_control to the last turn boundary
            for multi-turn prompt caching

    Returns:
        Tuple of (chat_messages, system_message)
        - chat_messages: List of formatted messages for Anthropic API
        - system_message: Combined system message string or None
    """
    system_messages: List[str] = []
    chat_messages: List[Dict[str, Any]] = []

    # Track pending tool results to group them
    pending_tool_results: List[Dict[str, Any]] = []

    for message in messages:
        role = message.role
        content = message.get_content()

        if role == "system":
            if content:
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            system_messages.append(str(item["text"]))
                        else:
                            system_messages.append(str(item))
                else:
                    system_messages.append(str(content))
            continue

        anthropic_role = ROLE_MAP.get(role, "user")

        # Handle tool results - collect them instead of adding immediately
        if anthropic_role == "user" and message.tool_call_id:
            tool_result_content = content
            if isinstance(tool_result_content, str):
                tool_result_content = [{"type": "text", "text": tool_result_content}]
            elif isinstance(tool_result_content, list):
                tool_result_content = tool_result_content
            elif tool_result_content is None:
                tool_result_content = ""

            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": tool_result_content,
                }
            )
            continue  # Don't add to chat_messages yet

        # If we hit a non-tool message and have pending tool results, handle them
        if pending_tool_results:
            if anthropic_role == "assistant":
                # Flush as separate user message before assistant
                chat_messages.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []
            # For regular user messages, we'll merge tool_results with their content below

        parts: List[Dict[str, Any]] = []

        # If this is a user message and we have pending tool_results, prepend them
        if anthropic_role == "user" and pending_tool_results:
            parts.extend(pending_tool_results)
            pending_tool_results = []

        # Handle thinking/reasoning content for assistant messages
        if anthropic_role == "assistant":
            reasoning_content = getattr(message, "reasoning_content", None)
            redacted_reasoning_content = getattr(message, "redacted_reasoning_content", None)
            provider_data = getattr(message, "provider_data", {})
            signature = provider_data.get("signature") if provider_data else None

            # Priority: reasoning_content with signature > redacted_reasoning_content > reasoning_content without signature
            if reasoning_content and signature:
                # Full thinking with signature
                parts.append(
                    {
                        "type": "thinking",
                        "thinking": str(reasoning_content),
                        "signature": signature,
                    }
                )
            elif redacted_reasoning_content:
                # Redacted thinking (no signature needed)
                parts.append(
                    {
                        "type": "redacted_thinking",
                        "redacted_thinking": str(redacted_reasoning_content),
                    }
                )
            elif reasoning_content:
                # Fallback: use reasoning_content as redacted if no signature
                parts.append(
                    {
                        "type": "redacted_thinking",
                        "redacted_thinking": str(reasoning_content),
                    }
                )

        # Regular text content
        if isinstance(content, str) and content.strip():
            parts.append({"type": "text", "text": content})
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append({"type": "text", "text": str(item["text"])})
                else:
                    parts.append({"type": "text", "text": json.dumps(item)})
        elif content:
            parts.append({"type": "text", "text": str(content)})

        # Assistant tool calls
        if anthropic_role == "assistant" and message.tool_calls:
            for tool_call in message.tool_calls:
                tool_name = (
                    tool_call.get("tool_name")
                    or tool_call.get("name")
                    or tool_call.get("function", {}).get("name")
                    or "tool"
                )
                tool_input = (
                    tool_call.get("tool_args")
                    or tool_call.get("arguments")
                    or tool_call.get("function", {}).get("arguments")
                    or {}
                )
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except Exception:
                        pass

                parts.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.get("id") or tool_call.get("tool_call_id") or str(uuid4()),
                        "name": tool_name,
                        "input": tool_input,
                    }
                )

        if role == "user":
            if message.images is not None:
                for image in message.images:
                    image_content = _format_image_for_message(image)
                    if image_content:
                        parts.append(image_content)

            # Handle files - append sandbox file paths to message content
            if message.files:
                file_paths = [str(f.filepath) for f in message.files if f.filepath]
                if file_paths:
                    files_text = "\n\nAttached files:\n" + "\n".join(f" - {p}" for p in file_paths)
                    parts.append({"type": "text", "text": files_text})

        chat_messages.append({"role": ROLE_MAP[message.role], "content": parts})

    # Flush any remaining tool results at the end
    if pending_tool_results:
        chat_messages.append({"role": "user", "content": pending_tool_results})

    # Add cache_control to the turn boundary (last message before current user input)
    # This caches all previous conversation history for multi-turn caching
    if cache_conversation and len(chat_messages) >= 2:
        # Find the last assistant message or tool_result before the final user message
        # Cache breakpoint should be at the end of the previous "turn"
        for i in range(len(chat_messages) - 2, -1, -1):
            msg = chat_messages[i]
            # Cache at the last assistant message or the tool_result that follows it
            if msg["role"] == "assistant" or (
                msg["role"] == "user"
                and isinstance(msg.get("content"), list)
                and any(c.get("type") == "tool_result" for c in msg["content"])
            ):
                # Add cache_control to the last content block
                if isinstance(msg.get("content"), list) and msg["content"]:
                    msg["content"][-1]["cache_control"] = {"type": "ephemeral"}
                break

    system_message = "\n\n".join(system_messages) if system_messages else None
    return chat_messages, system_message


@dataclass
class Claude(Model):
    """
    A class representing Anthropic Claude model.

    For more information, see: https://docs.anthropic.com/en/api/messages
    """

    id: str = "claude-sonnet-4-5-20250929"
    name: str = "Claude"
    provider: Provider = Provider.ANTHROPIC

    # Request parameters
    max_tokens: Optional[int] = 8192
    thinking: Optional[Dict[str, Any]] = None
    temperature: Optional[float] = None
    stop_sequences: Optional[List[str]] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    cache_system_prompt: Optional[bool] = False
    cache_conversation: Optional[bool] = False  # Enable multi-turn prompt caching
    extended_cache_time: Optional[bool] = False
    request_params: Optional[Dict[str, Any]] = None

    # Anthropic beta and experimental features
    betas: Optional[List[str]] = None  # Enables specific experimental or newly released features.
    context_management: Optional[Dict[str, Any]] = None
    mcp_servers: Optional[List[MCPServerConfiguration]] = None
    skills: Optional[List[Dict[str, str]]] = (
        None  # e.g., [{"type": "anthropic", "skill_id": "pptx", "version": "latest"}]
    )

    # Client parameters
    api_key: Optional[str] = None
    auth_token: Optional[str] = None
    default_headers: Optional[Dict[str, Any]] = None
    timeout: Optional[float] = None
    http_client: Optional[Union[httpx.Client, httpx.AsyncClient]] = None
    client_params: Optional[Dict[str, Any]] = None

    client: Optional[AnthropicClient] = None
    async_client: Optional[AsyncAnthropicClient] = None

    def __post_init__(self):
        # Set up skills configuration if skills are enabled
        if self.skills:
            self._setup_skills_configuration()

    def _get_client_params(self) -> Dict[str, Any]:
        client_params: Dict[str, Any] = {}

        self.api_key = self.api_key or getenv("ANTHROPIC_API_KEY")
        self.auth_token = self.auth_token or getenv("ANTHROPIC_AUTH_TOKEN")
        if not (self.api_key or self.auth_token):
            logger.error(
                "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set. Please set the ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN environment variable."
            )

        # Add API key to client parameters
        client_params["api_key"] = self.api_key
        client_params["auth_token"] = self.auth_token
        if self.timeout is not None:
            client_params["timeout"] = self.timeout

        # Add additional client parameters
        if self.client_params is not None:
            client_params.update(self.client_params)
        if self.default_headers is not None:
            client_params["default_headers"] = self.default_headers
        return client_params

    def _setup_skills_configuration(self) -> None:
        """
        Set up configuration for Claude Agent Skills.
        Automatically configures betas array with required values.

        Skills enable document creation capabilities (PowerPoint, Excel, Word, PDF).
        For more information, see: https://docs.claude.com/en/docs/agents-and-tools/agent-skills/quickstart
        """
        # Required betas for skills
        required_betas = ["code-execution-2025-08-25", "skills-2025-10-02"]

        # Initialize or merge betas
        if self.betas is None:
            self.betas = required_betas
        else:
            # Add required betas if not present
            for beta in required_betas:
                if beta not in self.betas:
                    self.betas.append(beta)

    def _ensure_additional_properties_false(self, schema: Dict[str, Any]) -> None:
        """
        Recursively ensure all object types have additionalProperties: false.
        """
        if isinstance(schema, dict):
            if schema.get("type") == "object":
                schema["additionalProperties"] = False

            # Recursively process nested schemas
            for key, value in schema.items():
                if key in ["properties", "items", "allOf", "anyOf", "oneOf"]:
                    if isinstance(value, dict):
                        self._ensure_additional_properties_false(value)
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                self._ensure_additional_properties_false(item)

    def _build_output_format(
        self, response_format: Optional[Union[Dict, Type[BaseModel]]]
    ) -> Optional[Dict[str, Any]]:
        """
        Build Anthropic output_format parameter from response_format.

        Args:
            response_format: Pydantic model or dict format

        Returns:
            Dict with output_format structure or None
        """
        if response_format is None:
            return None

        # Handle Pydantic BaseModel
        if isinstance(response_format, type) and issubclass(response_format, BaseModel):
            try:
                # Try to use Anthropic SDK's transform_schema helper if available
                from anthropic import transform_schema

                schema = transform_schema(response_format.model_json_schema())
            except (ImportError, AttributeError):
                # Fallback to direct schema conversion
                schema = response_format.model_json_schema()
                # Ensure additionalProperties is False
                if isinstance(schema, dict):
                    if "additionalProperties" not in schema:
                        schema["additionalProperties"] = False
                    # Recursively ensure all object types have additionalProperties: false
                    self._ensure_additional_properties_false(schema)

            return {"type": "json_schema", "schema": schema}

        # Handle dict format (already in correct structure)
        elif isinstance(response_format, dict):
            return response_format

        return None

    def get_async_client(self) -> AsyncAnthropicClient:
        """
        Returns an instance of the async Anthropic client.
        """
        if self.async_client and not self.async_client.is_closed():
            return self.async_client

        _client_params = self._get_client_params()
        if self.http_client:
            if isinstance(self.http_client, httpx.AsyncClient):
                _client_params["http_client"] = self.http_client
            else:
                logger.warning(
                    "http_client is not an instance of httpx.AsyncClient. Using default global httpx.AsyncClient."
                )
                # Use global async client when user http_client is invalid
                _client_params["http_client"] = get_default_async_client()
        else:
            # Use global async client when no custom http_client is provided
            _client_params["http_client"] = get_default_async_client()
        self.async_client = AsyncAnthropicClient(**_client_params)
        return self.async_client

    def get_request_params(
        self,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate keyword arguments for API requests.
        """
        _request_params: Dict[str, Any] = {}
        if self.max_tokens:
            _request_params["max_tokens"] = self.max_tokens
        if self.thinking:
            _request_params["thinking"] = self.thinking
        if self.temperature:
            _request_params["temperature"] = self.temperature
        if self.stop_sequences:
            _request_params["stop_sequences"] = self.stop_sequences
        if self.top_p:
            _request_params["top_p"] = self.top_p
        if self.top_k:
            _request_params["top_k"] = self.top_k

        # Build betas list - include existing betas and add new one if needed
        betas_list = list(self.betas) if self.betas else None

        # Include betas if any are present
        if betas_list:
            _request_params["betas"] = betas_list

        if self.context_management:
            _request_params["context_management"] = self.context_management
        if self.mcp_servers:
            _request_params["mcp_servers"] = [
                {k: v for k, v in asdict(server).items() if v is not None}
                for server in self.mcp_servers
            ]
        if self.skills:
            _request_params["container"] = {"skills": self.skills}
        if self.request_params:
            _request_params.update(self.request_params)

        return _request_params

    def _prepare_request_kwargs(
        self,
        system_message: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare the request keyword arguments for the API call.

        Args:
            system_message (str): The concatenated system messages.
            tools: Optional list of tools
            response_format: Optional response format (Pydantic model or dict)

        Returns:
            Dict[str, Any]: The request keyword arguments.
        """
        # Pass response_format and tools to get_request_params for beta header handling
        request_kwargs = self.get_request_params(
            response_format=response_format, tools=tools
        ).copy()
        if system_message:
            if self.cache_system_prompt:
                cache_control = (
                    {"type": "ephemeral", "ttl": "1h"}
                    if self.extended_cache_time is not None and self.extended_cache_time is True
                    else {"type": "ephemeral"}
                )
                request_kwargs["system"] = [
                    {
                        "text": system_message,
                        "type": "text",
                        "cache_control": cache_control,
                    }
                ]
            else:
                request_kwargs["system"] = [{"text": system_message, "type": "text"}]

        # Add code execution tool if skills are enabled
        if self.skills:
            code_execution_tool = {
                "type": "code_execution_20250825",
                "name": "code_execution",
            }
            if tools:
                # Add code_execution to existing tools, code execution is needed for generating and processing files
                tools = tools + [code_execution_tool]
            else:
                tools = [code_execution_tool]

        # Format tools (this will handle strict mode)
        if tools:
            request_kwargs["tools"] = format_tools_for_model(tools)

        # Build output_format if response_format is provided
        output_format = self._build_output_format(response_format)
        if output_format:
            request_kwargs["output_format"] = output_format

        if request_kwargs:
            logger.debug(
                f"Calling {self.provider} with request parameters: {request_kwargs}",
                log_level=2,
            )
        return request_kwargs

    async def ainvoke(
        self,
        messages: List[Message],
        assistant_message: Message,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        run_response: Optional[RunOutput] = None,
    ) -> ModelResponse:
        """
        Send an asynchronous request to the Anthropic API to generate a response.
        """
        try:
            if run_response and run_response.metrics:
                run_response.metrics.set_time_to_first_token()

            chat_messages, system_message = format_messages(
                messages,
                cache_conversation=self.cache_conversation or False,
            )
            request_kwargs = self._prepare_request_kwargs(
                system_message, tools=tools, response_format=response_format
            )

            # for non stream, max_tokens params will response error:
            request_kwargs.pop("max_tokens", None)
            if request_kwargs.get("thinking"):
                request_kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": 8192,
                }

            assistant_message.metrics.start_timer()
            provider_response = await self.get_async_client().beta.messages.create(
                max_tokens=16384,
                model=self.id,
                messages=chat_messages,  # type: ignore
                stream=False,
                **request_kwargs,
            )

            assistant_message.metrics.stop_timer()

            # Parse the response into an ModelResponse object
            model_response = self._parse_provider_response(
                provider_response, response_format=response_format
            )  # type: ignore

            return model_response

        except APIConnectionError as e:
            logger.error(f"Connection error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=e.message, model_name=self.name, model_id=self.id
            ) from e
        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded: {str(e)}")
            raise ModelRateLimitError(
                message=e.message, model_name=self.name, model_id=self.id
            ) from e
        except APIStatusError as e:
            logger.error(f"Claude API error (status {e.status_code}): {str(e)}")
            raise ModelProviderError(
                message=e.message,
                status_code=e.status_code,
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpcore.ReadError as e:
            logger.error(f"HTTP read error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Network read error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.ReadError as e:
            logger.error(f"HTTPX read error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Network read error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Timeout while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Request timeout: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.StreamError as e:
            logger.error(f"Stream error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Stream error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.RemoteProtocolError as e:
            logger.error(f"HTTP/2 protocol error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"HTTP/2 stream reset: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error calling Claude API: {str(e)}")
            raise ModelProviderError(message=str(e), model_name=self.name, model_id=self.id) from e

    async def ainvoke_stream(
        self,
        messages: List[Message],
        assistant_message: Message,
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
        run_response: Optional[RunOutput] = None,
    ) -> AsyncIterator[ModelResponse]:
        """
        Stream an asynchronous response from the Anthropic API.
        Args:
            messages (List[Message]): A list of messages to send to the model.
        Returns:
            AsyncIterator[ModelResponse]: An async iterator of processed model responses.
        Raises:
            APIConnectionError: If there are network connectivity issues
            RateLimitError: If the API rate limit is exceeded
            APIStatusError: For other API-related errors
        """
        try:
            if run_response and run_response.metrics:
                run_response.metrics.set_time_to_first_token()

            chat_messages, system_message = format_messages(
                messages,
                cache_conversation=self.cache_conversation or False,
            )
            request_kwargs = self._prepare_request_kwargs(
                system_message, tools=tools, response_format=response_format
            )
            assistant_message.metrics.start_timer()
            async with self.get_async_client().beta.messages.stream(
                model=self.id,
                messages=chat_messages,  # type: ignore
                **request_kwargs,
            ) as stream:
                async for chunk in stream:
                    yield self._parse_provider_response_delta(chunk)  # type: ignore

            assistant_message.metrics.stop_timer()

        except APIConnectionError as e:
            logger.error(f"Connection error while calling Claude API: {str(e)}")
            raise ModelProviderError(
                message=e.message, model_name=self.name, model_id=self.id
            ) from e
        except RateLimitError as e:
            logger.warning(f"Rate limit exceeded: {str(e)}")
            raise ModelRateLimitError(
                message=e.message, model_name=self.name, model_id=self.id
            ) from e
        except APIStatusError as e:
            logger.error(f"Claude API error (status {e.status_code}): {str(e)}")
            raise ModelProviderError(
                message=e.message,
                status_code=e.status_code,
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpcore.ReadError as e:
            logger.error(f"HTTP read error while streaming Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Network read error during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.ReadError as e:
            logger.error(f"HTTPX read error while streaming Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Network read error during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Timeout while streaming Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Request timeout during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.StreamError as e:
            logger.error(f"Stream error while streaming Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"Stream error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpx.RemoteProtocolError as e:
            logger.error(f"HTTP/2 protocol error while streaming Claude API: {str(e)}")
            raise ModelProviderError(
                message=f"HTTP/2 stream reset: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error calling Claude API: {str(e)}")
            raise ModelProviderError(message=str(e), model_name=self.name, model_id=self.id) from e

    def get_system_message_for_model(self, tools: Optional[List[Any]] = None) -> Optional[str]:
        if tools is not None and len(tools) > 0:
            tool_call_prompt = (
                "Do not reflect on the quality of the returned search results in your response\n\n"
            )
            return tool_call_prompt
        return None

    def _parse_provider_response(
        self,
        response: Union[AnthropicMessage, BetaMessage],
        response_format: Optional[Union[Dict, Type[BaseModel]]] = None,
        **kwargs,
    ) -> ModelResponse:
        """
        Parse the Claude response into a ModelResponse.

        Args:
            response: Raw response from Anthropic
            response_format: Optional response format

        Returns:
            ModelResponse: Parsed response data
        """
        model_response = ModelResponse()

        # Add role (Claude always uses 'assistant')
        model_response.role = response.role or "assistant"

        if response.content:
            for block in response.content:
                if block.type == "text":
                    text_content = block.text

                    if model_response.content is None:
                        model_response.content = text_content
                    else:
                        model_response.content += text_content

                    # Capture citations from the response
                    if block.citations is not None:
                        if model_response.citations is None:
                            model_response.citations = Citations(raw=[], urls=[], documents=[])
                        for citation in block.citations:
                            model_response.citations.raw.append(citation.model_dump())  # type: ignore
                            # Web search citations
                            if isinstance(citation, CitationsWebSearchResultLocation):
                                model_response.citations.urls.append(  # type: ignore
                                    UrlCitation(url=citation.url, title=citation.cited_text)
                                )
                            # Document citations
                            elif isinstance(citation, CitationPageLocation):
                                model_response.citations.documents.append(  # type: ignore
                                    DocumentCitation(
                                        document_title=citation.document_title,
                                        cited_text=citation.cited_text,
                                    )
                                )
                elif block.type == "thinking":
                    model_response.reasoning_content = block.thinking
                    model_response.provider_data = {
                        "signature": block.signature,
                    }
                elif block.type == "redacted_thinking":
                    model_response.redacted_reasoning_content = block.data

        # Extract tool calls from the response
        if response.stop_reason == "tool_use":
            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    function_def = {"name": tool_name}
                    if tool_input:
                        function_def["arguments"] = json.dumps(tool_input)

                    model_response.extra = model_response.extra or {}

                    model_response.tool_calls.append(
                        {
                            "id": block.id,
                            "type": "function",
                            "function": function_def,
                        }
                    )

        # Add usage metrics
        if response.usage is not None:
            model_response.response_usage = self._get_metrics(response.usage)

        # Capture context management information if present
        if self.context_management is not None and hasattr(response, "context_management"):
            if response.context_management is not None:  # type: ignore
                model_response.provider_data = model_response.provider_data or {}
                if hasattr(response.context_management, "model_dump"):
                    model_response.provider_data["context_management"] = (
                        response.context_management.model_dump()
                    )  # type: ignore
                else:
                    model_response.provider_data["context_management"] = response.context_management  # type: ignore
        # Extract file IDs if skills are enabled
        if self.skills and response.content:
            file_ids: List[str] = []
            for block in response.content:
                if block.type == "bash_code_execution_tool_result":
                    if hasattr(block, "content") and hasattr(block.content, "content"):
                        if isinstance(block.content.content, list):
                            for output_block in block.content.content:
                                if hasattr(output_block, "file_id"):
                                    file_ids.append(output_block.file_id)

            if file_ids:
                if model_response.provider_data is None:
                    model_response.provider_data = {}
                model_response.provider_data["file_ids"] = file_ids

        return model_response

    def _parse_provider_response_delta(
        self,
        response: Union[
            ContentBlockStartEvent,
            ContentBlockDeltaEvent,
            ContentBlockStopEvent,
            MessageStopEvent,
            BetaRawContentBlockDeltaEvent,
            BetaRawContentBlockStartEvent,
            ParsedBetaContentBlockStopEvent,
            ParsedBetaMessageStopEvent,
        ],
    ) -> ModelResponse:
        """
        Parse the Claude streaming response into ModelProviderResponse objects.

        Args:
            response: Raw response chunk from Anthropic

        Returns:
            ModelResponse: Iterator of parsed response data
        """
        model_response = ModelResponse()

        if isinstance(response, (ContentBlockStartEvent, BetaRawContentBlockStartEvent)):
            if response.content_block.type == "thinking":
                model_response.delta_status = "reasoning_started"
                model_response.reasoning_content = response.content_block.thinking
            if response.content_block.type == "redacted_reasoning_content":
                model_response.redacted_reasoning_content = response.content_block.data
                model_response.delta_status = "reasoning_started"
            if response.content_block.type == "text":
                model_response.delta_status = "content_started"
                model_response.content = response.content_block.text

        if isinstance(response, (ContentBlockDeltaEvent, BetaRawContentBlockDeltaEvent)):
            model_response.is_delta = True
            # Handle text content
            if response.delta.type == "text_delta":
                model_response.content = response.delta.text

            # Handle thinking content
            elif response.delta.type == "thinking_delta":
                model_response.reasoning_content = response.delta.thinking

        if isinstance(response, (ContentBlockStopEvent, ParsedBetaContentBlockStopEvent)):
            if response.content_block.type == "thinking":
                model_response.is_delta = False
                model_response.delta_status = "reasoning_done"
                model_response.reasoning_content = response.content_block.thinking

                model_response.provider_data = {
                    "signature": response.content_block.signature,
                }
            if response.content_block.type == "text":
                model_response.is_delta = False
                model_response.delta_status = "content_done"
                model_response.content = response.content_block.text

            if response.content_block.type == "tool_use":  # type: ignore
                tool_use = response.content_block  # type: ignore
                tool_name = tool_use.name  # type: ignore
                tool_input = tool_use.input  # type: ignore

                function_def = {"name": tool_name}
                if tool_input:
                    function_def["arguments"] = json.dumps(tool_input)

                model_response.extra = model_response.extra or {}

                model_response.tool_calls = [
                    {
                        "id": tool_use.id,  # type: ignore
                        "type": "function",
                        "function": function_def,
                    }
                ]

        # Capture citations from the final response
        if isinstance(response, (MessageStopEvent, ParsedBetaMessageStopEvent)):
            # In streaming mode, content has already been emitted via ContentBlockDeltaEvent chunks
            model_response.citations = Citations(raw=[], urls=[], documents=[])

            # Accumulate text content (but don't set model_response.content)
            # The text was already streamed via ContentBlockDeltaEvent chunks
            accumulated_text = ""

            for block in response.message.content:  # type: ignore
                # Handle text blocks
                if block.type == "text":
                    accumulated_text += block.text  # type: ignore

                # Handle citations
                citations = getattr(block, "citations", None)
                if not citations:
                    continue
                for citation in citations:
                    model_response.citations.raw.append(citation.model_dump())  # type: ignore
                    # Web search citations
                    if isinstance(citation, CitationsWebSearchResultLocation):
                        model_response.citations.urls.append(
                            UrlCitation(url=citation.url, title=citation.cited_text)
                        )  # type: ignore
                    # Document citations
                    elif isinstance(citation, CitationPageLocation):
                        model_response.citations.documents.append(  # type: ignore
                            DocumentCitation(
                                document_title=citation.document_title,
                                cited_text=citation.cited_text,
                            )
                        )

            # Capture context management information if present
            if self.context_management is not None and hasattr(
                response.message, "context_management"
            ):  # type: ignore
                context_mgmt = response.message.context_management  # type: ignore
                if context_mgmt is not None:
                    model_response.provider_data = model_response.provider_data or {}
                    if hasattr(context_mgmt, "model_dump"):
                        model_response.provider_data["context_management"] = (
                            context_mgmt.model_dump()
                        )
                    else:
                        model_response.provider_data["context_management"] = context_mgmt

        if (
            hasattr(response, "message")
            and hasattr(response.message, "usage")
            and response.message.usage is not None
        ):  # type: ignore
            model_response.response_usage = self._get_metrics(response.message.usage)  # type: ignore

        return model_response

    def _get_metrics(self, response_usage: Union[Usage, MessageDeltaUsage, BetaUsage]) -> Metrics:
        """
        Parse the given Anthropic-specific usage into an Metrics object.

        Args:
            response_usage: Usage data from Anthropic

        Returns:
            Metrics: Parsed metrics data
        """
        metrics = Metrics()

        metrics.input_tokens = response_usage.input_tokens or 0
        metrics.output_tokens = response_usage.output_tokens or 0
        metrics.total_tokens = metrics.input_tokens + metrics.output_tokens
        metrics.cache_read_tokens = response_usage.cache_read_input_tokens or 0
        metrics.cache_write_tokens = response_usage.cache_creation_input_tokens or 0

        # Anthropic-specific additional fields
        if response_usage.server_tool_use:
            metrics.provider_metrics = {
                "server_tool_use": response_usage.server_tool_use.model_dump()
            }
        if isinstance(response_usage, Usage):
            if response_usage.service_tier:
                metrics.provider_metrics = metrics.provider_metrics or {}
                metrics.provider_metrics["service_tier"] = response_usage.service_tier

        return metrics
