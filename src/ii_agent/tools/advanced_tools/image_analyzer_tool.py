# src/ii_agent/tools/image_analyzer_tool.py
import base64
import os
from pathlib import Path
from typing import Any, Optional
import mimetypes # To guess image type

from ii_agent.tools.base import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from ii_agent.utils import WorkspaceManager
from ii_agent.llm.openai import OpenAIDirectClient # Re-use or create new client instance

# Configure OpenAI client specifically for this tool if needed, or reuse/pass one
# For simplicity here, we'll create a new instance inside the method.
# In a production scenario, you might want to pass a pre-configured client.
import openai

class ImageAnalyzerTool(LLMTool):
    name = "image_analyzer"
    description = "Analyzes the content of an image file located in the workspace using OpenAI's vision model and returns a textual description."
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The relative path to the image file within the workspace (e.g., 'uploads/screenshot.png').",
            },
            "prompt": {
                "type": "string",
                "description": "Optional. A specific question or instruction for analyzing the image (e.g., 'Describe the user interface', 'What objects are in this picture?'). Defaults to 'Describe this image in detail.'",
            }
        },
        "required": ["file_path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager, model_name: str = "gpt-4o"):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.model_name = model_name
        # Consider initializing the client here if you want to reuse it across calls
        # self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    def _encode_image(self, image_path: Path) -> tuple[Optional[str], Optional[str]]:
        """Encodes the image file to base64 and guesses mime type."""
        try:
            with open(image_path, "rb") as image_file:
                encoded = base64.b64encode(image_file.read()).decode('utf-8')
                mime_type, _ = mimetypes.guess_type(image_path)
                if mime_type and mime_type.startswith("image/"):
                     return f"data:{mime_type};base64,{encoded}", None
                else:
                    # Fallback or error if mime type unknown/not image
                    return f"data:application/octet-stream;base64,{encoded}", f"Could not determine specific image type for {image_path.name}, using generic type."
        except Exception as e:
            return None, f"Error encoding image file {image_path.name}: {str(e)}"

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        relative_file_path = tool_input["file_path"]
        user_prompt = tool_input.get("prompt", "Describe this image in detail.")
        
        # Get absolute path within the workspace
        full_file_path = self.workspace_manager.workspace_path(Path(relative_file_path))

        if not full_file_path.exists():
            return ToolImplOutput(f"Error: Image file not found at {relative_file_path}", f"File not found: {relative_file_path}", {"success": False})
        if not full_file_path.is_file():
            return ToolImplOutput(f"Error: Path {relative_file_path} is not a file.", f"Path is not a file: {relative_file_path}", {"success": False})

        # Encode the image
        base64_image_data, encoding_warning = self._encode_image(full_file_path)
        if not base64_image_data:
            return ToolImplOutput(f"Error: {encoding_warning}", f"Failed encoding image: {relative_file_path}", {"success": False})

        try:
            client = openai.AzureOpenAI(
                api_key=os.getenv("OPENAI_API_KEY", "3ijnMBqM7teOPw6Mxt74cuna85TiEn8evkuoQnPD9AK6FGnsgYSBJQQJ99BAACHYHv6XJ3w3AAAAACOGbVlY"),
                azure_endpoint=os.getenv("OPENAI_AZURE_ENDPOINT", "https://test27653533018.cognitiveservices.azure.com/"),
                api_version=os.getenv("OPENAI_API_VERSION", "2024-12-01-preview"),
            )

            response = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": base64_image_data},
                            },
                        ],
                    }
                ],
                max_tokens=4096,
            )

            description = response.choices[0].message.content if response.choices[0].message.content else "No description generated."
            
            tool_result_message = f"Successfully analyzed image {relative_file_path}."
            if encoding_warning:
                tool_result_message += f" Note: {encoding_warning}"
                
            return ToolImplOutput(
                description,
                tool_result_message,
                {"success": True}
            )

        except openai.APIError as e:
             error_msg = f"OpenAI API error analyzing image {relative_file_path}: {e}"
             return ToolImplOutput(error_msg, f"API Error for {relative_file_path}", {"success": False, "error": str(e)})
        except Exception as e:
            error_msg = f"Unexpected error analyzing image {relative_file_path}: {str(e)}"
            return ToolImplOutput(error_msg, f"Error analyzing {relative_file_path}", {"success": False, "error": str(e)})