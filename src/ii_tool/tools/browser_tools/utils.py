from ii_agent.tools.base import ToolImplOutput


def format_screenshot_tool_output(screenshot: str, msg: str) -> ToolImplOutput:
    return ToolImplOutput(
        tool_output=[
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot,
                },
            },
            {"type": "text", "text": msg},
        ],
        tool_result_message=msg,
    )
