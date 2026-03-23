from typing import Any, Literal, TYPE_CHECKING
import asyncio
import base64
import mimetypes
import logging
from urllib.parse import unquote
from fastmcp import Client
from fastmcp.exceptions import ToolError
from ii_tool.tools.base import (
    BaseTool,
    ToolResult,
    TextContent,
    ImageContent,
    ToolConfirmationDetails,
)

if TYPE_CHECKING:
    from ii_sandbox_server.client.client import SandboxClient

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT = 300  # 5 minutes – reduced from 1800s; the tool_manager
# applies its own shorter timeout (120s) first; this acts as a hard backstop
# in case asyncio cancellation cannot propagate into the MCP HTTP call.

# Image extensions for detection
IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff', '.svg'}


def _is_image_path(path: str) -> bool:
    """Check if a path looks like an image file."""
    if not isinstance(path, str):
        return False
    # URL decode the path to handle %3A, %2C etc.
    decoded = unquote(path)
    lower = decoded.lower()
    return any(lower.endswith(ext) for ext in IMAGE_EXTENSIONS)


def _get_mime_type(path: str) -> str:
    """Get MIME type for an image path."""
    decoded = unquote(path)
    mime_type, _ = mimetypes.guess_type(decoded)
    return mime_type or 'image/png'


async def _read_image_from_sandbox(
    sandbox_client: "SandboxClient",
    sandbox_id: str,
    file_path: str,
) -> bytes | None:
    """Read an image file from the sandbox container.

    Args:
        sandbox_client: The sandbox client for API calls
        sandbox_id: The sandbox container ID
        file_path: Path to the file in the sandbox

    Returns:
        File contents as bytes, or None if failed
    """
    try:
        content = await sandbox_client.download_file(sandbox_id, file_path, format="bytes")
        if isinstance(content, bytes) and len(content) > 0:
            return content
        return None
    except Exception as e:
        logger.warning(f"Failed to read file from sandbox: {file_path}, error: {e}")
        return None


async def with_retry(func, *args, retries=2, delay=1, **kwargs):
    """Wrapper function to retry async operations"""
    last_exception = None
    for attempt in range(retries + 1):  # retries + 1 for initial attempt
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < retries:  # Don't sleep on the last attempt
                await asyncio.sleep(delay)
            else:
                raise last_exception


class MCPTool(BaseTool):
    def __init__(
        self,
        mcp_client: Client,
        name: str,
        display_name: str,
        description: str,
        input_schema: dict[str, Any],
        read_only: bool,
        type: Literal[
            "function", "openai_custom"
        ] = "function",  # check https://platform.openai.com/docs/guides/function-calling#context-free-grammars
        sandbox_client: "SandboxClient | None" = None,
        sandbox_id: str | None = None,
    ):
        # MCP information
        self.mcp_client = mcp_client

        # Tool information
        self.name = name
        self.display_name = display_name
        self.description = description
        self.read_only = read_only

        # Sandbox access for reading files from sandbox container
        self.sandbox_client = sandbox_client
        self.sandbox_id = sandbox_id

        if type == "function":
            self.input_schema = input_schema
        else:
            self.format = (
                input_schema  # HACK: this way we can pass format as input_schemas
            )

    def should_confirm_execute(
        self, tool_input: dict[str, Any]
    ) -> ToolConfirmationDetails | bool:
        return ToolConfirmationDetails(
            type="mcp",
            message=f"Do you want to execute the MCP tool {self.name} with input {tool_input}?",
        )

    async def _process_image_inputs(self, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Process tool_input to handle image data from sandbox files.

        External MCP servers cannot access files inside the sandbox container.
        This method bridges that gap by:

        1. Converting local file paths to base64 dicts - because MCP servers
           can only handle remote URLs (http/https) or inline base64 data,
           not local sandbox paths like /workspace/uploads/file.png

        2. Filling empty base64 fields in image dicts - when a dict has
           {"base64": "", "media_type": "image/..."}, find an associated
           path and populate the data

        The approach is schema-agnostic: it recursively walks the entire
        structure and applies these transformations wherever applicable.

        Args:
            tool_input: The original tool input dictionary

        Returns:
            Processed tool_input with sandbox images converted to base64
        """
        if not self.sandbox_client or not self.sandbox_id:
            return tool_input

        def _is_local_path(s: str) -> bool:
            """Check if string is a local path (not a remote URL)."""
            return not s.startswith(('http://', 'https://'))

        # First pass: collect all local image paths found anywhere in the structure
        def _collect_local_image_paths(obj: Any) -> list[str]:
            """Recursively collect local image path strings from the structure."""
            paths = []
            if isinstance(obj, str) and _is_image_path(obj) and _is_local_path(obj):
                paths.append(obj)
            elif isinstance(obj, dict):
                for v in obj.values():
                    paths.extend(_collect_local_image_paths(v))
            elif isinstance(obj, list):
                for item in obj:
                    paths.extend(_collect_local_image_paths(item))
            return paths

        all_local_paths = _collect_local_image_paths(tool_input)

        # Second pass: recursively process the structure
        async def _process_value(obj: Any, candidate_paths: list[str] | None = None) -> Any:
            """Recursively process a value, converting local paths and filling base64."""
            candidates = candidate_paths if candidate_paths is not None else all_local_paths

            if isinstance(obj, dict):
                # Check if this dict is an image object needing base64 data
                base64_val = obj.get("base64")
                media_type = obj.get("media_type", "")

                # Pattern: {"base64": "", "media_type": "image/..."} - fill empty base64
                if base64_val in ("", None) and isinstance(media_type, str) and "image/" in media_type:
                    # Try to find a path - first in this dict, then from candidates
                    image_path = None
                    for key in ("path", "file_path", "image_path", "file", "url"):
                        val = obj.get(key)
                        if isinstance(val, str) and _is_image_path(val) and _is_local_path(val):
                            image_path = val
                            break

                    # Fallback to first candidate path if no path in dict
                    if not image_path and candidates:
                        image_path = candidates[0]

                    if image_path:
                        image_data = await _read_image_from_sandbox(
                            self.sandbox_client, self.sandbox_id, image_path
                        )
                        if image_data:
                            logger.info(f"Populated base64 for image object from: {image_path}")
                            return {
                                **obj,
                                "base64": base64.b64encode(image_data).decode('utf-8'),
                            }

                # Recursively process dict values
                return {k: await _process_value(v, candidates) for k, v in obj.items()}

            elif isinstance(obj, list):
                # Recursively process list items, converting local paths to base64 dicts
                processed_items = []
                for item in obj:
                    if isinstance(item, str) and _is_image_path(item) and _is_local_path(item):
                        # Convert local path string to base64 dict
                        image_data = await _read_image_from_sandbox(
                            self.sandbox_client, self.sandbox_id, item
                        )
                        if image_data:
                            logger.info(f"Converted local path to base64 dict: {item}")
                            processed_items.append({
                                "base64": base64.b64encode(image_data).decode('utf-8'),
                                "media_type": _get_mime_type(item),
                            })
                        else:
                            # Keep original if we couldn't read the file
                            processed_items.append(item)
                    else:
                        processed_items.append(await _process_value(item, candidates))
                return processed_items

            # Return other types unchanged (including remote URLs which MCP can fetch)
            return obj

        return await _process_value(tool_input)

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        try:
            # Process image inputs - convert paths to base64 data from sandbox
            processed_input = await self._process_image_inputs(tool_input)

            async with self.mcp_client:
                mcp_results = await with_retry(
                    self.mcp_client.call_tool,
                    self.name,
                    processed_input,
                    timeout=DEFAULT_TIMEOUT,
                )

                llm_content = []
                has_image_content = False
                for mcp_result in mcp_results.content:
                    if mcp_result.type == "text":
                        llm_content.append(
                            TextContent(type="text", text=mcp_result.text)
                        )
                    elif mcp_result.type == "image":
                        llm_content.append(
                            ImageContent(
                                type="image",
                                data=mcp_result.data,
                                mime_type=mcp_result.mimeType,
                            )
                        )
                        has_image_content = True
                    else:
                        raise ValueError(f"Unknown result type: {mcp_result.type}")

                user_display_content = None
                is_error = False
                # Logic for our internal tools
                if mcp_results.structured_content is not None:
                    user_display_content = mcp_results.structured_content.get(
                        "user_display_content"
                    )
                    is_error = mcp_results.structured_content.get("is_error")
                # For external tools (like MCP) or internal tools that don't have a user_display_content
                if not user_display_content:
                    if not has_image_content:
                        user_display_content = "\n".join(
                            [content.text for content in llm_content]
                        )
                    else:
                        user_display_content = [
                            content.model_dump() for content in llm_content
                        ]

                return ToolResult(
                    llm_content=llm_content,
                    user_display_content=user_display_content,
                    is_error=is_error,
                )
        except ToolError as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                llm_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}\n\nPlease analyze the error message to determine if it's due to incorrect input parameters or an internal tool issue. If the error is due to incorrect input, retry with the correct parameters. Otherwise, try an alternative approach and inform the user about the issue.",
                user_display_content=f"Error while calling tool {self.name} with input {tool_input}: {str(e)}",
                is_error=True,
            )
