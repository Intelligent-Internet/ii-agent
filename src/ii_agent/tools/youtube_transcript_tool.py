from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from typing import Any, Optional
from ii_agent.llm.message_history import MessageHistory
import yt_dlp
import aiohttp
import asyncio


class YoutubeTranscriptTool(LLMTool):
    name = "youtube_video_transcript"
    description = """This tool retrieves and returns the transcript of a YouTube video.
    It supports both manually created subtitles and automatically generated captions,
    prioritizing manual subtitles when available."""

    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Youtube Video URL",
            },
        },
        "required": ["url"],
    }
    output_type = "string"

    def __init__(self):
        super().__init__()

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "skip_download": True,
            }

            # Run yt_dlp in thread pool since it's not async
            loop = asyncio.get_event_loop()
            info = await loop.run_in_executor(
                None, 
                lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(url, download=False)
            )
            
            # Get manual or auto subtitles
            subtitles = info.get("subtitles", {})
            automatic_captions = info.get("automatic_captions", {})

            # Choose manual subtitles first, otherwise fallback to auto captions
            subtitle_list = subtitles.get("en", []) or automatic_captions.get("en", [])

            if not subtitle_list:
                return ToolImplOutput(
                    tool_output="No subtitles available for the requested language.",
                    tool_result_message="No subtitles found",
                    auxiliary_data={"success": False}
                )

            # Get the first subtitle URL (usually VTT format)
            subtitle_url = subtitle_list[0]["url"]

            # Download subtitle text using aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(subtitle_url) as response:
                    response.raise_for_status()
                    subtitle_data = await response.json()
                    
            events = subtitle_data.get("events", [])
            subtitle_text = ""
            for event in events:
                if "segs" in event:
                    for seg in event["segs"]:
                        subtitle_text += seg.get("utf8", "")
                        
            return ToolImplOutput(
                tool_output=subtitle_text, 
                tool_result_message="Successfully extracted transcript",
                auxiliary_data={"success": True}
            )

        except Exception as e:
            error_msg = f"Error fetching subtitles: {str(e)}"
            return ToolImplOutput(
                tool_output=error_msg,
                tool_result_message="Failed to extract transcript",
                auxiliary_data={"success": False, "error": str(e)}
            )
