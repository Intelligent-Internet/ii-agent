from ii_agent.tools.base import ToolImplOutput


def format_screenshot_tool_output(screenshot: str, msg: str, log: str = None) -> ToolImplOutput:
    tool_output = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot,
            },
        },
        {"type": "text", "text": msg},
    ]
    
    if log:
        tool_output.append({
            "type": "text",
            "text": log
        })
        
    return ToolImplOutput(
        tool_output=tool_output,
        tool_result_message=msg,
    )
    
def get_console_logs(browser, param):
    logs = None
    if param:
        captured = browser.captured_logs
        url = browser.current_page.url
        logs = '\n\n'.join(captured.get(url, []))
    return logs
