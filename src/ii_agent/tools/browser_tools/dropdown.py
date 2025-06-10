import json

from typing import Any, Optional
from ii_agent.browser.browser import Browser
from ii_agent.tools.base import ToolImplOutput
from ii_agent.tools.browser_tools import BrowserTool, utils
from ii_agent.llm.message_history import MessageHistory


class BrowserGetSelectOptionsTool(BrowserTool):
    name = "browser_get_select_options"
    description = """Get all available options from a dropdown/select element.

Use this tool when you need to:
- See what choices are available in a dropdown menu
- Find the exact text of options before selecting
- Understand all possible values in a select field
- Choose from a list of countries, states, categories, etc.

Workflow:
1. Use browser_view to find select elements
2. Use this tool to get all options from a specific select element
3. Use browser_select_dropdown_option to choose your desired option

Returns:
- List of all option values and their display text
- Information needed to make a selection

Note: Only works with HTML <select> elements, not custom dropdown implementations."""
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
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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
        state = await self.browser.update_state()

        return utils.format_screenshot_tool_output(state.screenshot, msg)


class BrowserSelectDropdownOptionTool(BrowserTool):
    name = "browser_select_dropdown_option"
    description = """Select a specific option from a dropdown/select element by its text.

Use this tool to choose an option from a dropdown menu after viewing available options.

Workflow:
1. Use browser_view to identify the select element
2. Use browser_get_select_options to see available choices
3. Use this tool to select your desired option by its exact text

Use cases:
- Selecting countries, states, or regions
- Choosing categories or types from dropdown lists
- Setting preferences or configuration options
- Selecting dates, times, or other predefined values

Important:
- Use the exact option text as shown by browser_get_select_options
- Text matching is case-sensitive
- Only works with HTML <select> elements

Note: After selection, the form may update dynamically, so consider using browser_view to see changes."""
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
        super().__init__(browser)

    async def _run(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
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
            state = await self.browser.update_state()
            return utils.format_screenshot_tool_output(state.screenshot, msg)
        else:
            error_msg = result.get("error", "Unknown error")
            if "availableOptions" in result:
                available = result.get("availableOptions", [])
                error_msg += f". Available options: {', '.join(available)}"

            return ToolImplOutput(tool_output=error_msg, tool_result_message=error_msg)
