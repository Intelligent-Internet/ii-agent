import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from os import getenv
from typing import Any, Dict, List, Optional, Type, Union
from uuid import uuid4

import httpcore
import httpx
from pydantic import BaseModel

from ii_agent.agents.exceptions import ModelProviderError
from ii_agent.files.media import Image
from ii_agent.agents.models.base import Model
from ii_agent.agents.models.message import Message
from ii_agent.agents.models.metrics import Metrics
from ii_agent.settings.llm import Provider
from ii_agent.agents.models.response import ModelResponse
from ii_agent.agents.runs.agent import RunOutput
from ii_agent.core.logger import logger

try:
    from google import genai
    from google.genai import Client as GeminiClient, types as genai_types
    from google.genai.errors import ClientError, ServerError
    from google.genai._interactions import APIConnectionError as GenaiAPIConnectionError
    from google.genai.interactions import (
        InteractionSSEEvent,
        InteractionStartEvent,
        # InteractionEvent,
        ContentStart,
        ContentDelta,
        Usage,
        ContentStop,
        Interaction,
    )
    from google.genai.types import (
        Part,
    )
except ImportError:
    raise ImportError(
        "`google-genai` not installed or not at the latest version. Please install it using `pip install -U google-genai`"
    )


def _normalize_function_definition(tool: Any) -> Optional[Dict[str, Any]]:
    """Convert Function objects or dicts into a standard dict representation."""

    if tool is None:
        return None

    if isinstance(tool, dict):
        if "function" in tool and isinstance(tool["function"], dict):
            return tool["function"]
        return tool

    if hasattr(tool, "to_dict"):
        try:
            data = tool.to_dict()  # type: ignore
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    if hasattr(tool, "model_dump"):
        data = tool.model_dump(exclude_none=True)  # type: ignore
        if isinstance(data, dict):
            return data

    return None


def format_function_definitions(tools: Optional[List[Any]]) -> List[Dict[str, Any]]:
    """Convert OpenAI function definitions into Gemini Tool declarations."""

    declarations = []
    for tool in tools or []:
        func = _normalize_function_definition(tool)
        if not func:
            continue
        name = func.get("name")
        if not name:
            continue
        description = func.get("description")
        parameters = func.get("parameters")
        declarations.append(
            {
                "type": tool["type"],
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        )

    return declarations


def _resolve_mime_type(image: Image) -> Optional[str]:
    """Resolve MIME type from image metadata, falling back to format field."""
    mime_type = image.mime_type
    if not mime_type and getattr(image, "format", None):
        mime_type = f"image/{image.format.lower()}"
    return mime_type


def format_image_for_message(image: Image) -> Optional[Dict[str, Any]]:
    from ii_agent.agents.utils.heic import convert_heic_to_jpeg, is_heic_format

    mime_type = _resolve_mime_type(image)

    # Case 1: Image is a URL
    # Download the image from the URL and add it as base64 encoded data
    if image.url is not None:
        # For HEIC URLs, download and convert before sending
        if is_heic_format(mime_type=mime_type, url=image.url):
            try:
                import base64

                content_bytes = image.get_content_bytes()
                if not content_bytes:
                    logger.error("Failed to download HEIC image from URL")
                    return None
                jpeg_bytes, mime_type = convert_heic_to_jpeg(content_bytes)
                return {
                    "type": "image",
                    "mime_type": mime_type,
                    "data": base64.b64encode(jpeg_bytes).decode("utf-8"),
                }
            except Exception as e:
                logger.error(f"Failed to convert HEIC URL to JPEG: {e}")
                return None

        image_data = {
            "type": "image",
            "mime_type": mime_type,
            "uri": image.url,
        }
        return image_data

    # Case 2: Image is raw bytes
    elif image.content is not None and isinstance(image.content, bytes):
        import base64

        content_bytes = image.content

        # Convert HEIC/HEIF to JPEG
        if is_heic_format(mime_type=mime_type, image_bytes=content_bytes):
            try:
                content_bytes, mime_type = convert_heic_to_jpeg(content_bytes)
            except Exception as e:
                logger.error(f"Failed to convert HEIC to JPEG: {e}")
                return None

        image_data = {
            "type": "image",
            "mime_type": mime_type,
            "data": base64.b64encode(content_bytes).decode("utf-8"),
        }
        return image_data

    # Case 3: Image has a local/sandbox filepath
    elif image.filepath is not None:
        import base64

        content_bytes = image.get_content_bytes()
        if not content_bytes:
            logger.error(f"Failed to read image from filepath: {image.filepath}")
            return None

        if is_heic_format(mime_type=mime_type, image_bytes=content_bytes):
            try:
                content_bytes, mime_type = convert_heic_to_jpeg(content_bytes)
            except Exception as e:
                logger.error(f"Failed to convert HEIC to JPEG: {e}")
                return None

        image_data = {
            "type": "image",
            "mime_type": mime_type,
            "data": base64.b64encode(content_bytes).decode("utf-8"),
        }
        return image_data

    else:
        logger.warning(f"Unknown image type: {type(image)}")
        return None


def prepare_response_schema(response_format: Type[BaseModel]) -> Dict[str, Any]:
    """Generate the JSON schema Gemini expects for structured outputs."""

    return response_format.model_json_schema()


@dataclass
class GeminiInteractions(Model):
    """
    Gemini model class for Google's Generative AI Interactions API.

    The Interactions API provides server-side state management and improved
    performance through automatic caching when using previous_interaction_id.

    Vertex AI:
    - You will need Google Cloud credentials to use the Vertex AI API. Run `gcloud auth application-default login` to set credentials.
    - Set `vertexai` to `True` to use the Vertex AI API.
    - Set your `project_id` (or set `GOOGLE_CLOUD_PROJECT` environment variable) and `location` (optional).
    - Set `http_options` (optional) to configure the HTTP options.

    Based on https://googleapis.github.io/python-genai/
    """

    id: str = "gemini-3-flash-preview"
    name: str = "GeminiInteractions"
    provider: Provider = Provider.GOOGLE

    supports_native_structured_outputs: bool = True

    # Request parameters
    function_declarations: Optional[List[Any]] = None
    generation_config: Optional[Any] = None
    safety_settings: Optional[List[Any]] = None
    generative_model_kwargs: Optional[Dict[str, Any]] = None
    search: bool = False
    grounding: bool = False
    grounding_dynamic_threshold: Optional[float] = None
    url_context: bool = False
    timeout: Optional[float] = None
    vertexai_search: bool = False
    vertexai_search_datastore: Optional[str] = None

    # Gemini File Search capabilities
    file_search_store_names: Optional[List[str]] = None
    file_search_metadata_filter: Optional[str] = None

    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_output_tokens: Optional[int] = None
    stop_sequences: Optional[list[str]] = None
    logprobs: Optional[bool] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    seed: Optional[int] = None
    response_modalities: Optional[list[str]] = None  # "TEXT", "IMAGE", and/or "AUDIO"
    speech_config: Optional[dict[str, Any]] = None
    thinking_budget: Optional[int] = None  # Thinking budget for Gemini 2.5 models
    thinking_summaries: Optional[str] = None  # Include thought summaries in response
    thinking_level: Optional[str] = None  # "low", "high"
    request_params: Optional[Dict[str, Any]] = None

    # Client parameters
    api_key: Optional[str] = None
    vertexai: bool = False
    project_id: Optional[str] = None
    location: Optional[str] = None
    client_params: Optional[Dict[str, Any]] = None

    # Gemini client
    client: Optional[GeminiClient] = None

    # The role to map the Gemini response
    role_map = {
        "model": "assistant",
    }

    # The role to map the Message
    reverse_role_map = {
        "assistant": "model",
        "tool": "user",
    }

    def get_client(self) -> GeminiClient:
        """
        Returns an instance of the GeminiClient client.

        Returns:
            GeminiClient: The GeminiClient client.
        """
        if self.client:
            return self.client
        client_params: Dict[str, Any] = {}
        vertexai = self.vertexai or getenv("GOOGLE_GENAI_USE_VERTEXAI", "false").lower() == "true"

        if not vertexai:
            self.api_key = self.api_key or getenv("GOOGLE_API_KEY")
            if not self.api_key:
                logger.error(
                    "GOOGLE_API_KEY not set. Please set the GOOGLE_API_KEY environment variable."
                )
            client_params["api_key"] = self.api_key
        else:
            logger.info("Using Vertex AI API")
            client_params["vertexai"] = True
            project_id = self.project_id or getenv("GOOGLE_CLOUD_PROJECT")
            if not project_id:
                logger.error(
                    "GOOGLE_CLOUD_PROJECT not set. Please set the GOOGLE_CLOUD_PROJECT environment variable."
                )
            location = self.location or getenv("GOOGLE_CLOUD_LOCATION")
            if not location:
                logger.error(
                    "GOOGLE_CLOUD_LOCATION not set. Please set the GOOGLE_CLOUD_LOCATION environment variable."
                )
            client_params["project"] = project_id
            client_params["location"] = location

        client_params = {k: v for k, v in client_params.items() if v is not None}

        if self.client_params:
            client_params.update(self.client_params)

        # Configure httpx async client with proper timeout for long streaming responses
        timeout_seconds = self.timeout or 600.0
        async_http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout=timeout_seconds),
            http2=True,
            follow_redirects=True,
        )
        http_options = genai_types.HttpOptions(
            timeout=int(timeout_seconds * 1000),  # Convert to milliseconds
            httpx_async_client=async_http_client,
        )
        client_params["http_options"] = http_options

        self.client = genai.Client(**client_params)
        return self.client

    def get_request_params(
        self,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Returns the request keyword arguments for the Interactions API client.
        """
        request_params = {}

        generation_config = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "seed": self.seed,
            "stop_sequences": self.stop_sequences,
            "thinking_level": self.thinking_level,
            "thinking_summaries": self.thinking_summaries,
            "top_p": self.top_p,
            "tool_choice": tool_choice,
        }

        generation_config = {k: v for k, v in generation_config.items() if v is not None}

        # Filter out None values
        if self.request_params:
            request_params.update(self.request_params)

        if generation_config:
            request_params["generation_config"] = generation_config
        if self.timeout is not None:
            request_params["timeout"] = self.timeout

        if request_params:
            logger.debug(
                f"Calling {self.provider} with request parameters: {request_params}",
                log_level=2,
            )
        # TODO: support builtin tools config
        return request_params

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
        Invokes the model with a list of messages using the Interactions API and returns the response.
        """
        # Extract previous_interaction_id first to determine which messages to format
        previous_interaction_id = None
        for msg in reversed(messages):
            if (
                msg.role == "assistant"
                and hasattr(msg, "provider_data")
                and msg.provider_data
                and "interaction_id" in msg.provider_data
            ):
                previous_interaction_id = msg.provider_data["interaction_id"]
                break

        formatted_messages, system_message = self._format_messages(
            messages, previous_interaction_id
        )

        request_kwargs = self.get_request_params(tool_choice=tool_choice)

        func_tools = format_function_definitions(tools=tools)

        try:
            if run_response and run_response.metrics:
                run_response.metrics.set_time_to_first_token()

            assistant_message.metrics.start_timer()
            provider_response = await self.get_client().aio.interactions.create(
                system_instruction=system_message,
                model=self.id,
                input=formatted_messages,
                tools=func_tools,
                previous_interaction_id=previous_interaction_id,
                stream=False,
                **request_kwargs,
            )
            assistant_message.metrics.stop_timer()

            model_response = self._parse_provider_response(
                provider_response, response_format=response_format
            )

            return model_response

        except (ClientError, ServerError) as e:
            logger.error("Error from Gemini API", exc_info=True)
            raise ModelProviderError(
                message=str(e.response) if hasattr(e, "response") else str(e),
                status_code=e.code if hasattr(e, "code") and e.code is not None else 502,
                model_name=self.name,
                model_id=self.id,
            ) from e
        except GenaiAPIConnectionError as e:
            logger.error("Connection error while calling Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Connection error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpcore.ReadError as e:
            logger.error("httpcore read error while calling Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Network read error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except (httpx.ReadError, httpx.TimeoutException, httpx.StreamError) as e:
            logger.error("httpx error while calling Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Network error: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except RuntimeError as e:
            # Handle "Cannot send a request, as the client has been closed"
            if "client has been closed" in str(e):
                logger.error("HTTP client closed error while calling Gemini API", exc_info=True)
                self.client = None
                raise ModelProviderError(
                    message=f"HTTP client closed: {str(e)}",
                    model_name=self.name,
                    model_id=self.id,
                ) from e
            raise
        except Exception as e:
            logger.error("Unknown error from Gemini API", exc_info=True)
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
        Invokes the model with a list of messages using the Interactions API and returns the response as a stream.
        """
        # Extract previous_interaction_id first to determine which messages to format
        previous_interaction_id = None
        for msg in reversed(messages):
            if (
                msg.role == "assistant"
                and hasattr(msg, "provider_data")
                and msg.provider_data
                and "interaction_id" in msg.provider_data
            ):
                previous_interaction_id = msg.provider_data["interaction_id"]
                break

        formatted_messages, system_message = self._format_messages(
            messages, previous_interaction_id
        )

        request_kwargs = self.get_request_params(tool_choice=tool_choice)

        func_tools = format_function_definitions(tools=tools)

        try:
            if run_response and run_response.metrics:
                run_response.metrics.set_time_to_first_token()

            assistant_message.metrics.start_timer()

            async_stream = await self.get_client().aio.interactions.create(
                model=self.id,
                system_instruction=system_message,
                tools=func_tools,
                input=formatted_messages,
                previous_interaction_id=previous_interaction_id,
                stream=True,
                **request_kwargs,
            )

            event_state = {"state": None}
            accumulators = {"reasoning_content": "", "content": ""}
            async for chunk in async_stream:
                model_response = self._parse_provider_response_delta(
                    chunk, event_state, accumulators
                )
                yield model_response

            assistant_message.metrics.stop_timer()

        except (ClientError, ServerError) as e:
            logger.error("Error from Gemini API", exc_info=True)
            raise ModelProviderError(
                message=str(e.response) if hasattr(e, "response") else str(e),
                status_code=e.code if hasattr(e, "code") and e.code is not None else 502,
                model_name=self.name,
                model_id=self.id,
            ) from e
        except GenaiAPIConnectionError as e:
            logger.error("Connection error while streaming Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Connection error during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except httpcore.ReadError as e:
            logger.error("httpcore read error while streaming Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Network read error during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except (httpx.ReadError, httpx.TimeoutException, httpx.StreamError) as e:
            logger.error("httpx error while streaming Gemini API", exc_info=True)
            raise ModelProviderError(
                message=f"Network error during streaming: {str(e)}",
                model_name=self.name,
                model_id=self.id,
            ) from e
        except Exception as e:
            logger.error("Unknown error from Gemini API", exc_info=True)
            raise ModelProviderError(message=str(e), model_name=self.name, model_id=self.id) from e

    def _format_messages(
        self, messages: List[Message], previous_interaction_id: Optional[str] = None
    ):
        """
        Converts a list of Message objects to the Gemini Interactions API format.

        For Interactions API, the input format accepts:
        - Simple strings
        - List of content objects with type/data
        - Turn-based conversation history

        Args:
            messages (List[Message]): The list of messages to convert.
            previous_interaction_id (Optional[str]): If provided, only include messages after
                the assistant message containing this interaction_id.
        """
        formatted_messages: List[Any] = []
        system_message = None

        # Filter messages if using previous_interaction_id
        messages_to_format = messages
        if previous_interaction_id is not None:
            # Find the assistant message with the interaction_id
            for idx, msg in enumerate(reversed(messages)):
                if (
                    msg.role == "assistant"
                    and hasattr(msg, "provider_data")
                    and msg.provider_data
                    and msg.provider_data.get("interaction_id") == previous_interaction_id
                ):
                    # Only include messages after this one
                    msg_index = len(messages) - idx - 1
                    messages_to_format = messages[msg_index + 1 :]
                    logger.debug(
                        f"Using previous_interaction_id: {previous_interaction_id}, "
                        f"sending {len(messages_to_format)} messages"
                    )
                    break

        for message in messages_to_format:
            role = message.role
            if role in ["system", "developer"]:
                system_message = message.content
                continue

            # Set the role for the message according to Gemini's requirements
            role = self.reverse_role_map.get(role, role)
            content = message.get_content()

            # Handle assistant messages with tool calls (function calls)
            if role == "model" and message.tool_calls is not None and len(message.tool_calls) > 0:
                # Add text content first if present
                contents = []
                if content is not None and isinstance(content, str) and content:
                    contents.append({"role": role, "content": {"type": "text", "text": content}})

                if message.provider_data and "thought_signature" in message.provider_data:
                    thought_signature = message.provider_data["thought_signature"]
                    contents.append(
                        {
                            "role": role,
                            "content": {
                                "type": "thought",
                                "signature": thought_signature,
                                "summary": [{"type": "text", "text": message.reasoning_content}],
                            },
                        }
                    )

                # For Interactions API, function calls are added as Content with function_call parts
                for tool_call in message.tool_calls:
                    contents.append(
                        {
                            "role": role,
                            "content": {
                                "type": "function_call",
                                "name": tool_call["function"]["name"],
                                "id": tool_call["id"],  # FIX: ID is at top level, not in function
                                "arguments": json.loads(tool_call["function"]["arguments"]),
                            },
                        }
                    )

                formatted_messages.extend(contents)

                continue

            # Handle tool result messages (function_result in Interactions API)
            elif message.role == "tool":
                fn_results = []
                if message.tool_calls is not None and len(message.tool_calls) > 0:
                    for idx, tool_call in enumerate(message.tool_calls):
                        if isinstance(content, list) and idx < len(content):
                            tc_content = content[idx]
                        else:
                            tc_content = message.get_content()
                            if tc_content is None:
                                tc_content = tool_call.get("content")
                                if tc_content is None:
                                    tc_content = content

                        name = tool_call.get("tool_name", "unknown")
                        fn = {
                            "type": "function_result",
                            "name": name,
                            "call_id": tool_call.get("id"),
                            "result": tc_content,
                        }
                        fn_results.append(fn)
                else:
                    fn = {
                        "type": "function_result",
                        "name": message.tool_name,
                        "call_id": message.tool_call_id,
                        "result": content,
                        "is_error": message.tool_call_error,
                    }
                    fn_results.append(fn)

                if fn_results:
                    formatted_messages.append({"role": role, "content": fn_results})

                continue

            # Handle regular user/assistant messages with multimodal content
            message_parts: List[Part] = []

            # Add images (only for user messages)
            if role == "user":
                if message.content is not None:
                    message_parts.append({"type": "text", "text": content})
                if message.images is not None:
                    for image in message.images:
                        image_dict = format_image_for_message(image)
                        if image_dict:
                            message_parts.append(image_dict)

                # Handle files - append sandbox file paths to message content
                if message.files:
                    file_paths = [str(f.filepath) for f in message.files if f.filepath]
                    if file_paths:
                        files_text = "\n\nAttached files:\n" + "\n".join(
                            f" - {p}" for p in file_paths
                        )
                        message_parts.append({"type": "text", "text": files_text})

            # Create the formatted message
            if message_parts:
                formatted_messages.append({"role": role, "content": message_parts})

        return formatted_messages, system_message

    def format_function_call_results(
        self,
        messages: List[Message],
        function_call_results: List[Message],
        **kwargs,
    ) -> None:
        """
        Format function call results for Gemini Interactions API.

        For combined messages:
        - content: list of content from results
        - tool_calls[i]["content"]: content for API sending
        """
        combined_original_content: List = []
        combined_function_result: List = []
        message_metrics = Metrics()

        if len(function_call_results) > 0:
            for idx, result in enumerate(function_call_results):
                combined_original_content.append(result.content)
                content = result.get_content()
                combined_function_result.append(
                    {
                        "tool_call_id": result.tool_call_id,
                        "tool_name": result.tool_name,
                        "content": content,
                    }
                )
                message_metrics += result.metrics

        if combined_original_content:
            messages.append(
                Message(
                    role="user",
                    content=combined_original_content,
                    tool_calls=combined_function_result,
                    metrics=message_metrics,
                )
            )

    def _parse_provider_response(self, interaction: Interaction, **kwargs) -> ModelResponse:
        """
        Parse the Gemini Interactions API response into a ModelResponse.

        The Interactions API returns responses with an 'outputs' array containing:
        - type: "thought" - reasoning with signature and optional summary
        - type: "text" - text content with optional annotations
        - type: "function_call" - tool calls with id, name, and arguments

        Example response:
        {
            "id": "v1_...",
            "outputs": [
                {"type": "thought", "signature": "...", "summary": null},
                {"type": "text", "text": "..."}
            ],
            "usage": {...}
        }

        Args:
            interaction: Raw response from Gemini Interactions API

        Returns:
            ModelResponse: Parsed response data
        """
        model_response = ModelResponse()

        # Store interaction ID for continuity
        if hasattr(interaction, "id") and interaction.id:
            if model_response.provider_data is None:
                model_response.provider_data = {}
            model_response.provider_data["interaction_id"] = interaction.id

        # Set role from interaction
        if hasattr(interaction, "role") and interaction.role:
            model_response.role = self.role_map.get(interaction.role, interaction.role)

        # Parse outputs array
        if hasattr(interaction, "outputs") and interaction.outputs:
            for output in interaction.outputs:
                output_type = getattr(output, "type", None)

                # Handle thought (reasoning) output
                if output_type == "thought":
                    # Store thought signature
                    signature = getattr(output, "signature", None)
                    if signature:
                        if model_response.provider_data is None:
                            model_response.provider_data = {}
                        model_response.provider_data["thought_signature"] = signature

                    # Store thought summary if present
                    summary = getattr(output, "summary", None)
                    if summary:
                        if model_response.reasoning_content is None:
                            model_response.reasoning_content = summary
                        else:
                            model_response.reasoning_content += summary

                # Handle text output
                elif output_type == "text":
                    text_content = getattr(output, "text", None)
                    if text_content:
                        if model_response.content is None:
                            model_response.content = text_content
                        else:
                            model_response.content += text_content

                    # Handle annotations if present (for citations, etc.)
                    annotations = getattr(output, "annotations", None)
                    if annotations:
                        if model_response.provider_data is None:
                            model_response.provider_data = {}
                        model_response.provider_data["annotations"] = annotations

                # Handle function call output
                elif output_type == "function_call":
                    call_id = getattr(output, "id", None) or str(uuid4())
                    func_name = getattr(output, "name", None)
                    func_args = getattr(output, "arguments", None)

                    tool_call = {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": func_name,
                            "arguments": json.dumps(func_args) if func_args else "",
                        },
                    }
                    model_response.tool_calls.append(tool_call)

        # Extract usage metadata if present
        if hasattr(interaction, "usage") and interaction.usage is not None:
            model_response.response_usage = self._get_metrics(interaction.usage)

        # If we have no content but have a role, add a default empty content
        if model_response.role and model_response.content is None and not model_response.tool_calls:
            model_response.content = ""

        return model_response

    def _parse_provider_response_delta(
        self,
        interaction_event: InteractionSSEEvent,
        event_state: dict[str, Any] = None,
        accumulators: dict[str, Any] = None,
    ) -> ModelResponse:
        """
        Parse the Gemini Interactions API streaming response into ModelResponse objects.

        Args:
            interaction_event: Raw response chunk from Gemini
            event_state: tracking state from response

        Returns:
            ModelResponse: Parsed response delta
        """
        model_response = ModelResponse()

        if isinstance(interaction_event, ContentStop):
            if event_state.get("state") == "reasoning_delta":
                model_response.delta_status = "reasoning_done"
                model_response.reasoning_content = accumulators["reasoning_content"]
                accumulators["reasoning_content"] = ""
            if event_state.get("state") == "content_delta":
                model_response.delta_status = "content_done"
                model_response.content = accumulators["content"]
                accumulators["content"] = ""
            if event_state.get("state") == "function_call_delta":
                pass
            event_state["state"] = None

        if isinstance(interaction_event, InteractionStartEvent):
            # Store the response ID for continuity
            if interaction_event.event_type == "interaction.start":
                if model_response.provider_data is None:
                    model_response.provider_data = {}
                model_response.provider_data["interaction_id"] = interaction_event.interaction.id
            if interaction_event.event_type == "interaction.complete":
                model_response.response_usage = self._get_metrics(
                    interaction_event.interaction.usage
                )
                event_state["state"] = None
                accumulators["content"] = ""
                accumulators["reasoning_content"] = ""

        if isinstance(interaction_event, ContentStart):
            if interaction_event.content.type == "thought":
                event_state["state"] = "reasoning_delta"
                model_response.delta_status = "reasoning_started"

            if interaction_event.content.type == "text":
                event_state["state"] = "content_delta"
                model_response.delta_status = "content_started"

            if interaction_event.content.type == "function_call":
                event_state["state"] = "function_call_delta"

        if isinstance(interaction_event, ContentDelta):
            model_response.is_delta = True
            if interaction_event.delta.type == "thought_summary":
                if interaction_event.delta.content.type == "text":
                    model_response.reasoning_content = interaction_event.delta.content.text
                    accumulators["reasoning_content"] += interaction_event.delta.content.text

            if interaction_event.delta.type == "thought_signature":
                if model_response.provider_data is None:
                    model_response.provider_data = {}
                model_response.provider_data["thought_signature"] = (
                    interaction_event.delta.signature
                )

            if interaction_event.delta.type == "text":
                model_response.content = interaction_event.delta.text
                accumulators["content"] += interaction_event.delta.text

            if interaction_event.delta.type == "function_call":
                tool_use = interaction_event.delta  # type: ignore
                tool_name = tool_use.name  # type: ignore
                tool_input = tool_use.arguments  # type: ignore

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

        return model_response

    def __deepcopy__(self, memo):
        """
        Creates a deep copy of the Gemini model instance but sets the client to None.

        This is useful when we need to copy the model configuration without duplicating
        the client connection.

        This overrides the base class implementation.
        """
        from copy import copy, deepcopy

        # Create a new instance without calling __init__
        cls = self.__class__
        new_instance = cls.__new__(cls)

        # Update memo with the new instance to avoid circular references
        memo[id(self)] = new_instance

        # Deep copy all attributes except client and unpickleable attributes
        for key, value in self.__dict__.items():
            # Skip client and other unpickleable attributes
            if key in {
                "client",
                "response_format",
                "_tools",
                "_functions",
                "_function_call_stack",
            }:
                continue

            # Try deep copy first, fall back to shallow copy, then direct assignment
            try:
                setattr(new_instance, key, deepcopy(value, memo))
            except Exception:
                try:
                    setattr(new_instance, key, copy(value))
                except Exception:
                    setattr(new_instance, key, value)

        # Explicitly set client to None
        setattr(new_instance, "client", None)

        return new_instance

    def _get_metrics(self, response_usage: Usage) -> Metrics:
        """
        Parse the given Google Gemini usage into an Metrics object.

        Args:
            response_usage: Usage data from Google Gemini

        Returns:
            Metrics: Parsed metrics data
        """
        metrics = Metrics()

        metrics.input_tokens = response_usage.total_input_tokens or 0
        metrics.output_tokens = response_usage.total_output_tokens or 0
        metrics.reasoning_tokens = response_usage.total_thought_tokens or 0
        metrics.total_tokens = response_usage.total_tokens

        metrics.cache_read_tokens = response_usage.total_cached_tokens
        # raw metrics
        metrics.additional_metrics = response_usage.model_dump()
        return metrics
