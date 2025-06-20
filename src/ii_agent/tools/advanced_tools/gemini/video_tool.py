from typing import Any, Optional
from google.genai import types
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.advanced_tools.gemini import GeminiTool
from ii_agent.utils import WorkspaceManager


class YoutubeVideoUnderstandingTool(GeminiTool):
    name = "youtube_video_understanding"
    description = """This tool is used to understand a Youtube video. Use this tool to:
- Describe, segment, and extract information from videos
- Answer questions about video content
- Refer to specific timestamps within a video

Provide one query at a time.
"""

    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Youtube Video URL",
            },
            "query": {
                "type": "string",
                "description": "Query about the video",
            },
        },
        "required": ["url", "query"],
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
        url = tool_input["url"]
        query = tool_input["query"]

        # Video understanding requires direct Gemini API for multimodal support
        if not self.gemini_client:
            return ToolImplOutput(
                "Error: Video understanding requires GEMINI_API_KEY to be set for multimodal support.",
                "Gemini API key required for video processing"
            )

        try:
            # Use direct Gemini API for video processing
            response = self.gemini_client.models.generate_content(
                model=self.model,
                contents=types.Content(
                    parts=[
                        types.Part(file_data=types.FileData(file_uri=url)),
                        types.Part(text=query),
                    ]
                ),
            )
            output = response.candidates[0].content.parts[0].text
        except Exception as e:
            output = "Error analyzing the Youtube video, try again later."
            print(e)

        return ToolImplOutput(output, output)
