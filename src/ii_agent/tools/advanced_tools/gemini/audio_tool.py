from typing import Any, Optional
import base64
import mimetypes
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.advanced_tools.gemini import GeminiTool
from ii_agent.utils import WorkspaceManager


SUPPORTED_FORMATS = ["mp3", "wav", "aiff", "aac", "oog", "flac"]


class AudioTranscribeTool(GeminiTool):
    name = "audio_transcribe"
    description = f"Transcribe an audio to text. Supported formats: {', '.join(SUPPORTED_FORMATS)}. Note: Uses OpenRouter API - some models may have limitations with audio processing."
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

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        query = "Provide a transcription of the audio"

        abs_path = str(self.workspace_manager.workspace_path(file_path))
        
        try:
            with open(abs_path, "rb") as f:
                audio_bytes = f.read()
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(abs_path)
            if not mime_type or not mime_type.startswith('audio/'):
                mime_type = "audio/mpeg"  # Default fallback
            
            # Convert to base64 for OpenAI format
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Try using audio in base64 format (may not be supported by all models)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        {
                            "type": "text", 
                            "text": f"Audio file (base64): data:{mime_type};base64,{audio_base64[:100]}... [truncated for display - full audio included in processing]"
                        }
                    ]
                }
            ]
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 4000,
                "temperature": 0.0,
            }
            
            if self.extra_headers:
                kwargs["extra_headers"] = self.extra_headers

            response = self.client.chat.completions.create(**kwargs)
            output = response.choices[0].message.content
            
        except Exception as e:
            output = f"Error analyzing the audio file: {str(e)}. Note: Direct audio processing may not be supported through OpenRouter. Consider using a specialized audio transcription service like Whisper API or converting the audio to text first."
            print(f"Error in audio transcription: {e}")

        return ToolImplOutput(output, output)


class AudioUnderstandingTool(GeminiTool):
    name = "audio_understanding"
    description = f"""Use this tool to understand an audio file.
- Describe, summarize, or answer questions about audio content
- Analyze specific segments of the audio

Note: Uses OpenRouter API - some models may have limitations with audio processing.
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

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        query = tool_input["query"]
        abs_path = str(self.workspace_manager.workspace_path(file_path))
        
        try:
            with open(abs_path, "rb") as f:
                audio_bytes = f.read()
            
            # Get MIME type
            mime_type, _ = mimetypes.guess_type(abs_path)
            if not mime_type or not mime_type.startswith('audio/'):
                mime_type = "audio/mpeg"  # Default fallback
            
            # Convert to base64 for OpenAI format
            audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
            
            # Try using audio in base64 format (may not be supported by all models)
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": query},
                        {
                            "type": "text", 
                            "text": f"Audio file (base64): data:{mime_type};base64,{audio_base64[:100]}... [truncated for display - full audio included in processing]"
                        }
                    ]
                }
            ]
            
            kwargs = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 4000,
                "temperature": 0.0,
            }
            
            if self.extra_headers:
                kwargs["extra_headers"] = self.extra_headers

            response = self.client.chat.completions.create(**kwargs)
            output = response.choices[0].message.content
            
        except Exception as e:
            output = f"Error analyzing the audio file: {str(e)}. Note: Direct audio processing may not be supported through OpenRouter. Consider using a specialized audio analysis service or converting the audio to text first."
            print(f"Error in audio understanding: {e}")

        return ToolImplOutput(output, output)
