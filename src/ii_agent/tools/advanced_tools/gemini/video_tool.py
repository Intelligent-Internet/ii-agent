from typing import Any, Optional
import base64
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

Note: This tool now uses OpenRouter API. Some models may have limitations with direct YouTube URL processing.
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

        try:
            # OpenRouter with OpenAI format - attempt to use the URL directly in text
            # Note: Direct YouTube URL processing may not be supported by all models through OpenRouter
            messages = [
                {
                    "role": "user", 
                    "content": f"Please analyze this YouTube video: {url}\n\nQuery: {query}\n\nNote: If you cannot directly access the video, please let me know and suggest alternative approaches."
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
            output = f"Error analyzing the YouTube video: {str(e)}. Note: Direct YouTube URL processing may not be supported through OpenRouter. You may need to download the video first or use alternative methods."
            print(f"Error in YouTube video analysis: {e}")

        return ToolImplOutput(output, output)
