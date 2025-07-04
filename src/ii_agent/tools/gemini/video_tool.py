from typing import Any, Optional
from google.genai import types
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.gemini import GeminiTool
from ii_agent.utils.workspace_manager import WorkspaceManager


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

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        query = tool_input["query"]

        try:
            response = self.client.models.generate_content(
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
