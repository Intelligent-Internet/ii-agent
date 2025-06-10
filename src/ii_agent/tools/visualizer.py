import mimetypes
from typing import Any, Optional

from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.llm.message_history import MessageHistory
from .utils import encode_image
from ii_agent.utils import WorkspaceManager


class DisplayImageTool(LLMTool):
    name = "display_image"
    description = """Display images from your workspace to the user in the conversation.

This tool loads and shows images directly in the chat interface, making them visible to the user.

Use this tool when you need to:
- Show generated images, charts, or visualizations to the user
- Display screenshots or diagrams you've created
- Present visual results from image processing tasks
- Show downloaded or created images for user review
- Display any image file from the workspace

Supported formats:
- Common image formats: PNG, JPG, JPEG, GIF, BMP, WebP
- SVG and other image types supported by browsers

Important notes:
- The image must exist in the workspace before displaying
- Path should be relative to the workspace root
- Images are displayed inline in the conversation
- Large images may be resized for display

Example usage:
- After generating a chart: display_image("charts/results.png")
- After downloading an image: display_image("downloads/example.jpg")
- After creating a visualization: display_image("output/graph.png")"""
    input_schema = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "The path to the image to load. This should be a local path to downloaded image.",
            },
        },
        "required": ["image_path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        self.workspace_manager = workspace_manager

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        image_path = tool_input["image_path"]

        if not isinstance(image_path, str):
            return ToolImplOutput(
                tool_output="Error: image_path must be a string",
                tool_result_message="Error: image_path must be a string",
            )

        try:
            # Convert relative path to absolute path using workspace_manager
            abs_path = str(self.workspace_manager.workspace_path(image_path))

            # Get mime type and encode image
            mime_type, _ = mimetypes.guess_type(abs_path)
            if not mime_type:
                mime_type = "image/png"  # Default to PNG if type cannot be determined

            base64_image = encode_image(abs_path)

            tool_output = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": base64_image,
                    },
                }
            ]

            return ToolImplOutput(
                tool_output=tool_output,
                tool_result_message=f"Successfully loaded image from {image_path}",
            )

        except Exception as e:
            error_msg = f"Failed to process image: {str(e)}"
            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
