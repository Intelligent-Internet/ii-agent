import asyncio
from locale import currency

from .utils import truncate_content
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from index import Agent, AnthropicProvider, BrowserConfig

from typing import Optional, Any

class BrowserUse(LLMTool):
    name = "browser_use"
    description = (
        "Use this tool to visit a specific web page and extract information based on a given query."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The specific information you want to extract from the web page.",
            },
            "url": {
                "type": "string",
                "description": "The url of the webpage to visit.",
            }
        },
        "required": ["query", "url"],
    }
    output_type = "string"

    def __init__(self, message_queue: asyncio.Queue):
        self.message_queue = message_queue

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        llm = AnthropicProvider(
            model="claude-3-7-sonnet",
            enable_thinking=False, 
            thinking_token_budget=2048)
    
        # Create an agent with the LLM
        agent = Agent(
            llm=llm, 
            browser_config=BrowserConfig(start_at_url=tool_input['url']), 
            log_dir="logs/browser_use/",
            message_queue=self.message_queue,
            vision_only=True
        )

        async def _run():
            try:
                output = await agent.run(
                    prompt=tool_input['query']
                )
                if output.result.error:
                    return "Error: " + output.result.error
                return output.result.content
            except:
                return "Unexpected error"
       
        try:
            # Try to get the existing event loop
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # If no event loop exists, create a new one
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        try:
            text = loop.run_until_complete(_run())
        finally:
            # Clean up the event loop if we created it
            if loop.is_running():
                loop.close()
                
        return ToolImplOutput(
            text,
            tool_result_message=f"Browsed {tool_input['url']} and found the following information: {text}",
            auxiliary_data={"success": True},
        )

        