from typing import Any, Optional
from google.genai import types
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.gemini import GeminiTool
from ii_agent.utils import WorkspaceManager


SUPPORTED_FORMATS = ["mp3", "wav", "aiff", "aac", "oog", "flac"]


class AudioTranscribeTool(GeminiTool):
    name = "audio_transcribe"
    description = f"Transcribe an audio to text. Supported formats: {', '.join(SUPPORTED_FORMATS)}"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Local audio file path"},
        },
        "required": ["file_path"],
    }

    def __init__(
        self, workspace_manager: WorkspaceManager, model: Optional[str] = None
    ):
        super().__init__(workspace_manager, model)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        query = "Provide a transcription of the audio"

        abs_path = str(self.workspace_manager.workspace_path(file_path))
        with open(abs_path, "rb") as f:
            audio_bytes = f.read()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=types.Content(
                    parts=[
                        types.Part(text=query),
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/mp3",
                        ),
                    ]
                ),
            )
            output = response.text
        except Exception as e:
            output = "Error analyzing the audio file, try again later."
            print(e)

        return ToolImplOutput(output, output)


class AudioUnderstandingTool(GeminiTool):
    name = "audio_understanding"
    description = f"""Use this tool to understand an audio file.
- Describe, summarize, or answer questions about audio content
- Analyze specific segments of the audio

Provide one query at a time. Supported formats: {", ".join(SUPPORTED_FORMATS)}
"""

    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Local audio file path",
            },
            "query": {
                "type": "string",
                "description": "Query about the audio file",
            },
        },
        "required": ["file_path", "query"],
    }
    output_type = "string"

    def __init__(
        self, workspace_manager: WorkspaceManager, model: Optional[str] = None
    ):
        super().__init__(workspace_manager, model)

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        query = tool_input["query"]
        abs_path = str(self.workspace_manager.workspace_path(file_path))
        with open(abs_path, "rb") as f:
            audio_bytes = f.read()
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=types.Content(
                    parts=[
                        types.Part(text=query),
                        types.Part.from_bytes(
                            data=audio_bytes,
                            mime_type="audio/mp3",
                        ),
                    ]
                ),
            )
            output = response.text
        except Exception as e:
            output = "Error analyzing the audio file, try again later."
            print(e)

        return ToolImplOutput(output, output)
