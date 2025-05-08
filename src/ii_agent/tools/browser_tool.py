import asyncio
import json
from ii_agent.tools.base import (
    LLMTool,
    ToolImplOutput,
)
from ii_agent.llm.message_history import MessageHistory
from playwright.sync_api import TimeoutError
from ii_agent.browser.browser import Browser
from ii_agent.browser.utils import is_pdf_url
from ii_agent.core.event import EventType, RealtimeEvent
from asyncio import Queue
from typing import Any, Optional


def get_event_loop():
    try:
        # Try to get the existing event loop
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # If no event loop exists, create a new one
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


class BrowserNavigationTool(LLMTool):
    name = "browser_navigation"
    description = "Navigate browser to specified URL."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        url = tool_input["url"]

        async def _run():
            page = await self.browser.get_current_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolImplOutput(msg, msg)

            is_pdf = is_pdf_url(url)
            if is_pdf:
                await asyncio.sleep(3)
                await page.keyboard.press("Control+\\")
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(1.5)
            msg = f"Navigated to {url}"
            return ToolImplOutput(msg, msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserRestartTool(LLMTool):
    name = "browser_restart"
    description = "Restart browser and navigate to specified URL. Use when browser state needs to be reset else use browser_navigation tool."
    input_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "Complete URL to visit after restart. Must include protocol prefix.",
            }
        },
        "required": ["url"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            url = tool_input["url"]
            await self.browser.restart()
            page = await self.browser.get_current_page()
            try:
                await page.goto(url, wait_until="domcontentloaded")
            except TimeoutError:
                msg = f"Timeout error navigating to {url}"
                return ToolImplOutput(msg, msg)
            is_pdf = is_pdf_url(url)
            if is_pdf:
                await asyncio.sleep(3)
                await page.keyboard.press("Control+\\")
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(1.5)
                msg = f"Navigated to {url}"
                return ToolImplOutput(msg, msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserViewTool(LLMTool):
    name = "browser_view"
    description = "View content of the current browser page. Use for checking the latest state of previously opened pages."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser, message_queue: Queue | None = None):
        self.browser = browser
        self.message_queue = message_queue

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            state = await self.browser.update_state()

            if self.message_queue:
                self.message_queue.put_nowait(
                    RealtimeEvent(
                        type=EventType.BROWSER_USE,
                        content={
                            "url": state.url,
                            "screenshot": state.screenshot,
                            "screenshot_with_highlights": state.screenshot_with_highlights,
                        },
                    )
                )

            highlighted_elements = "<highlighted_elements>\n"
            if state.interactive_elements:
                for element in state.interactive_elements.values():
                    start_tag = f"[{element.index}]<{element.tag_name}"

                    if element.input_type:
                        start_tag += f' type="{element.input_type}"'

                    start_tag += ">"
                    element_text = element.text.replace("\n", " ")
                    highlighted_elements += (
                        f"{start_tag}{element_text}</{element.tag_name}>\n"
                    )
            highlighted_elements += "</highlighted_elements>"

            state_description = f"""Current URL: {state.url}

    Current viewport information:
    {highlighted_elements}

    Screenshot with bounding boxes and labels drawn around interactable elements:"""

            tool_output = [
                {"type": "text", "text": state_description},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": state.screenshot_with_highlights,
                    },
                },
            ]

            return ToolImplOutput(
                tool_output=tool_output, tool_result_message=state_description
            )

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserWaitTool(LLMTool):
    name = "browser_wait"
    description = "Use this action to wait for the page to load, if you see that the content on the clean screenshot is empty or loading UI elements such as skeleton screens. This action will wait for page to load. Then you can continue with your actions."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            await asyncio.sleep(1)
            page = await self.browser.get_current_page()
            is_pdf = is_pdf_url(page.url)
            if is_pdf:
                await page.keyboard.press("Control+\\")
                await asyncio.sleep(0.1)
            return ToolImplOutput(
                tool_output="Waited for page to load",
                tool_result_message="Waited for page to load",
            )

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserScrollDownTool(LLMTool):
    name = "browser_scroll_down"
    description = "Scroll down the current browser page."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            page = await self.browser.get_current_page()
            state = self.browser.get_state()
            is_pdf = is_pdf_url(state.url)
            if is_pdf:
                await page.keyboard.press("PageDown")
                await asyncio.sleep(0.1)
            else:
                await page.mouse.move(
                    state.viewport.width / 2, state.viewport.height / 2
                )
                await asyncio.sleep(0.1)
                await page.mouse.wheel(0, state.viewport.height * 0.8)
                await asyncio.sleep(0.1)

            tool_output = "Scrolled page down"
            return ToolImplOutput(
                tool_output=tool_output, tool_result_message=tool_output
            )

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserScrollUpTool(LLMTool):
    name = "browser_scroll_up"
    description = "Scroll up the current browser page."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            page = await self.browser.get_current_page()
            state = self.browser.get_state()
            is_pdf = is_pdf_url(state.url)
            if is_pdf:
                await page.keyboard.press("PageUp")
                await asyncio.sleep(0.1)
            else:
                await page.mouse.move(
                    state.viewport.width / 2, state.viewport.height / 2
                )
                await asyncio.sleep(0.1)
                await page.mouse.wheel(0, -state.viewport.height * 0.8)
                await asyncio.sleep(0.1)

            tool_output = "Scrolled page up"
            return ToolImplOutput(
                tool_output=tool_output, tool_result_message=tool_output
            )

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserClickTool(LLMTool):
    name = "browser_click"
    description = (
        "Click on an element on the current browser page with the given index."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the element to click on.",
            }
        },
        "required": ["index"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            index = int(tool_input["index"])
            state = self.browser.get_state()
            if index not in state.interactive_elements:
                return ToolImplOutput(
                    tool_output=f"Element with index {index} does not exist - retry or use alternative tool.",
                    tool_result_message=f"Element with index {index} does not exist - retry or use alternative tool.",
                )
            element = state.interactive_elements[index]
            initial_pages = (
                len(self.browser.context.pages) if self.browser.context else 0
            )

            page = await self.browser.get_current_page()
            await page.mouse.click(element.center.x, element.center.y)

            msg = f"Clicked element with index {index}: <{element.tag_name}></{element.tag_name}>"

            if self.browser.context and len(self.browser.context.pages) > initial_pages:
                new_tab_msg = "New tab opened - switching to it"
                msg += f" - {new_tab_msg}"
                await self.browser.switch_to_tab(-1)

            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserEnterTextTool(LLMTool):
    name = "browser_enter_text"
    description = "Enter text with a keyboard. Use it AFTER you have clicked on an input element. This action will override the current text in the element."
    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to enter with a keyboard."},
            "press_enter": {
                "type": "boolean",
                "description": "If True, `Enter` button will be pressed after entering the text. Use this when you think it would make sense to press `Enter` after entering the text, such as when you're submitting a form, performing a search, etc.",
            },
        },
        "required": ["text"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            text = tool_input["text"]
            press_enter = tool_input.get("press_enter", False)

            page = await self.browser.get_current_page()
            await page.keyboard.press("ControlOrMeta+a")

            await asyncio.sleep(0.1)
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.1)

            await page.keyboard.type(text)

            if press_enter:
                await page.keyboard.press("Enter")
                await asyncio.sleep(2)

            msg = f'Entered "{text}" on the keyboard. Make sure to double check that the text was entered to where you intended.'

            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserPressKeyTool(LLMTool):
    name = "browser_press_key"
    description = "Simulate key press in the current browser page. Use when specific keyboard operations are needed."
    input_schema = {
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "Key name to simulate (e.g., Enter, Tab, ArrowUp), supports key combinations (e.g., Control+Enter).",
            }
        },
        "required": ["key"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            key = tool_input["key"]
            page = await self.browser.get_current_page()
            await page.keyboard.press(key)
            await asyncio.sleep(0.5)

            msg = f'Pressed "{key}" on the keyboard.'
            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserGetSelectOptionsTool(LLMTool):
    name = "browser_get_select_options"
    description = "Get all options from a <select> element. Use this action when you need to get all options from a dropdown."
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the <select> element to get options from.",
            }
        },
        "required": ["index"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            index = int(tool_input["index"])

            # Get the page and element information
            page = await self.browser.get_current_page()
            interactive_elements = self.browser.get_state().interactive_elements

            # Verify the element exists and is a select
            if index not in interactive_elements:
                return ToolImplOutput(
                    tool_output=f"No element found with index {index}",
                    tool_result_message=f"No element found with index {index}",
                )

            element = interactive_elements[index]

            # Check if it's a select element
            if element.tag_name.lower() != "select":
                return ToolImplOutput(
                    tool_output=f"Element {index} is not a select element, it's a {element.tag_name}",
                    tool_result_message=f"Element {index} is not a select element, it's a {element.tag_name}",
                )

            # Use the unique ID to find the element
            options_data = await page.evaluate(
                """
            (args) => {
                // Find the select element using the unique ID
                const select = document.querySelector(`[data-browser-agent-id="${args.browserAgentId}"]`);
                if (!select) return null;
                
                // Get all options	
                return {
                    options: Array.from(select.options).map(opt => ({
                        text: opt.text,
                        value: opt.value,
                        index: opt.index
                    })),
                    id: select.id,
                    name: select.name
                };
            }
            """,
                {"browserAgentId": element.browser_agent_id},
            )

            # Process options from direct approach
            formatted_options = []
            for opt in options_data["options"]:
                encoded_text = json.dumps(opt["text"])
                formatted_options.append(f"{opt['index']}: option={encoded_text}")

            msg = "\n".join(formatted_options)
            msg += "\nIf you decide to use this select element, use the exact option name in select_dropdown_option"

            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserSelectDropdownOptionTool(LLMTool):
    name = "browser_select_dropdown_option"
    description = "Select an option from a <select> element by the text (name) of the option. Use this after get_select_options and when you need to select an option from a dropdown."
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the <select> element to select an option from.",
            },
            "option": {
                "type": "string",
                "description": "Text (name) of the option to select from the dropdown.",
            },
        },
        "required": ["index", "option"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            index = int(tool_input["index"])
            option = tool_input["option"]

            # Get the interactive element
            page = await self.browser.get_current_page()
            interactive_elements = self.browser.get_state().interactive_elements

            # Verify the element exists and is a select
            if index not in interactive_elements:
                return ToolImplOutput(
                    tool_output=f"No element found with index {index}",
                    tool_result_message=f"No element found with index {index}",
                )

            element = interactive_elements[index]

            # Check if it's a select element
            if element.tag_name.lower() != "select":
                return ToolImplOutput(
                    tool_output=f"Element {index} is not a select element, it's a {element.tag_name}",
                    tool_result_message=f"Element {index} is not a select element, it's a {element.tag_name}",
                )

            # Use JavaScript to select the option using the unique ID
            result = await page.evaluate(
                """
            (args) => {
                const uniqueId = args.uniqueId;
                const optionText = args.optionText;
                
                try {
                    // Find the select element by unique ID - works across frames too
                    function findElementByUniqueId(root, id) {
                        // Check in main document first
                        let element = document.querySelector(`[data-browser-agent-id="${id}"]`);
                        if (element) return element;
                    }
                    
                    const select = findElementByUniqueId(window, uniqueId);
                    if (!select) {
                        return { 
                            success: false, 
                            error: "Select element not found with ID: " + uniqueId 
                        };
                    }
                    
                    // Find the option with matching text
                    let found = false;
                    let selectedValue = null;
                    let selectedIndex = -1;
                    
                    for (let i = 0; i < select.options.length; i++) {
                        const opt = select.options[i];
                        if (opt.text === optionText) {
                            // Select this option
                            opt.selected = true;
                            found = true;
                            selectedValue = opt.value;
                            selectedIndex = i;
                            
                            // Trigger change event
                            const event = new Event('change', { bubbles: true });
                            select.dispatchEvent(event);
                            break;
                        }
                    }
                    
                    if (found) {
                        return { 
                            success: true, 
                            value: selectedValue, 
                            index: selectedIndex 
                        };
                    } else {
                        return { 
                            success: false, 
                            error: "Option not found: " + optionText,
                            availableOptions: Array.from(select.options).map(o => o.text)
                        };
                    }
                } catch (e) {
                    return { 
                        success: false, 
                        error: e.toString() 
                    };
                }
            }
            """,
                {"uniqueId": element.browser_agent_id, "optionText": option},
            )

            if result.get("success"):
                msg = f"Selected option '{option}' with value '{result.get('value')}' at index {result.get('index')}"
                return ToolImplOutput(tool_output=msg, tool_result_message=msg)
            else:
                error_msg = result.get("error", "Unknown error")
                if "availableOptions" in result:
                    available = result.get("availableOptions", [])
                    error_msg += f". Available options: {', '.join(available)}"

                return ToolImplOutput(
                    tool_output=error_msg, tool_result_message=error_msg
                )

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserSwitchTabTool(LLMTool):
    name = "browser_switch_tab"
    description = "Switch to a specific tab by tab index. Use this when you need to switch to a specific tab."
    input_schema = {
        "type": "object",
        "properties": {
            "index": {
                "type": "integer",
                "description": "Index of the tab to switch to.",
            }
        },
        "required": ["index"],
    }

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            index = int(tool_input["index"])
            await self.browser.switch_to_tab(index)
            await asyncio.sleep(0.5)
            msg = f"Switched to tab {index}"
            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())


class BrowserOpenNewTabTool(LLMTool):
    name = "browser_open_new_tab"
    description = "Open a new tab. Use this when you need to open a new tab."
    input_schema = {"type": "object", "properties": {}, "required": []}

    def __init__(self, browser: Browser):
        self.browser = browser

    def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        async def _run():
            await self.browser.create_new_tab()
            await asyncio.sleep(0.5)
            msg = "Opened a new tab"
            return ToolImplOutput(tool_output=msg, tool_result_message=msg)

        loop = get_event_loop()
        return loop.run_until_complete(_run())
