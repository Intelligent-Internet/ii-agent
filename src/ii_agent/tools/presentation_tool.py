import asyncio
from ii_agent.core.event import EventType, RealtimeEvent
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.tools.image_search_tool import ImageSearchTool
from ii_agent.tools.base import LLMTool
from ii_agent.utils import WorkspaceManager
from ii_agent.tools.bash_tool import create_bash_tool
from ii_agent.tools.str_replace_tool_relative import StrReplaceEditorTool

from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.base import ToolImplOutput

from typing import Any, Optional

from copy import deepcopy


class PresentationTool(LLMTool):
    """A tool for creating and managing presentations.

    This tool allows the agent to create, update, and manage slide presentations.
    It provides functionality to initialize a presentation, add/edit/delete slides,
    and finalize the presentation with consistent styling and formatting.
    The tool uses reveal.js as the presentation framework and supports various
    content elements like text, images, charts, and icons.
    """

    name = "presentation"
    description = """\
* Presentation tool is a comprehensive suite for crafting stunning, professional presentations with meticulous attention to detail.
* First-time users must initialize the presentation using the `init` action to set up the required framework and structure.
* During initialization, all the slides titles/names need to be provided and 'init' action will create a skeleton of the presentation with all the slides
* The presentation structure follows a strategic flow:
    - Opening with a captivating title slide that establishes the presentation's theme and purpose
    - Closing with a powerful conclusion slide that reinforces core messages and key takeaways
* Core functionality includes:
    - Creating new slides
    - Updating slide content
    - Deleting slides as needed
    - Finalizing the presentation
* Each slide action requires comprehensive documentation:
    - Content Requirements:
        * Do not make the slide too long, if the slide is too long, split it into multiple slides
        * Maintain slide-height consistency across all slides, the slide should fit into a single 1280x720px screen
        * Detailed context and background information
        * Supporting data points and statistics
        * Relevant historical context
        * Source materials and references
        * Supporting media assets (images, videos, etc.)
    - Design Specifications:
        * Title treatment and typography hierarchy
        * Visual element placement and styling:
            - Icons and their positioning
            - Data visualization components
            - Interactive elements
        * Media integration:
            - Image URLs and optimization
            - Video content sources
            - Animation assets
        * Visual design elements:
            - Color palette and scheme
            - Visual hierarchy and flow
            - Spacing and layout
        * Engagement features:
            - Transition effects
            - Animation sequences
            - Interactive elements
* The `final_check` action enables comprehensive quality assurance:
    - Content accuracy verification
    - Design consistency check
"""
    PROMPT = """
You are a presentation design expert, responsible for creating stunning, professional presentations that captivate audiences.
Working directory: "." (You can only work inside the working directory with relative paths)

* The presentation should contain a maximum of 10 slides, unless stated otherwise.
* During initialization, you will have access to a reveal.js directory in the workspace, in which index.html contains the code that represents your full presentation
* During initialization, you must update the index.html file to include all the slides by using nested presentation inside an iframe tag. 
* This action will create place holder for other actions only
* IMPORTANT: In init action, you must not create any slides, only update the index.html file.
action = init
<section>
    <iframe src="slides/introduction.html" allowfullscreen scrolling="auto"></iframe>
</section>
....
<section>
    <iframe src="slides/conclusion.html" allowfullscreen scrolling="auto"></iframe>
</section>

* All the following actions will create an html file in the ./presentation/reveal.js/slides directory, and only update the index.html file if needed

* Each slide should be a masterpiece of visual design, following these principles:
  - Create a clear visual hierarchy that guides the viewer's attention
  - Set overflow-y to auto to allow scrolling for long slides
  - Use whitespace strategically to create breathing room and emphasize key elements
  - Implement a consistent color scheme
  - Choose typography that enhances readability
  - Use the image_search tool to find images that are relevant to the slide, if you cannot use the image_search tool avoid using images unless you are provided the urls
  - Select and integrate high-quality visual elements that reinforce key messages
  - Implement subtle, purposeful animations that enhance content without overwhelming
  - Strategically place icons to improve visual communication and navigation
  - Create clear, impactful data visualizations using charts and graphs
  - Curate relevant images that strengthen understanding of key concepts
  - Incorporate video content and animations to demonstrate complex ideas
* Each slide must follow these technical specifications:
  - Use modern CSS techniques for layout:
    * Do not make the slide too long, if the slide is too long, split it into multiple slides
    * Maintain slide-height consistency across all slides, the slide should fit into a single 1280x720px screen
    * Flexbox for one-dimensional layouts
    * CSS Grid for complex two-dimensional layouts
    * CSS Custom Properties for consistent theming
    * Set overflow-y to auto to allow scrolling for long slides
  - Implement responsive design principles:
    * Use relative units (rem/em) for typography and spacing
    * Create fluid layouts that adapt to different screen sizes
    * Set appropriate breakpoints for different devices
  - Apply visual polish:
    * Add subtle shadows and depth effects
    * Use smooth transitions between states
    * Implement micro-interactions for better engagement
    * Ensure proper contrast ratios for accessibility

* The presentation must maintain visual consistency:
  - Use a cohesive color palette throughout
  - Maintain consistent typography and spacing
  - Apply uniform styling to similar elements
  - Create a clear visual language that ties all slides together

* Leverage modern web technologies:
  - Use Tailwind CSS for rapid, consistent styling
  - Incorporate FontAwesome for professional icons
  - Implement Chart.js for beautiful data visualization
  - Add custom CSS animations for smooth transitions

  * Recheck the presentation after each action to ensure all CSS styles are properly applied, overflow-y is set to auto,  and image URLs if any are correctly formatted and accessible

* The final_check action is crucial for presentation perfection:
  - Reread each slide to ensure all CSS styles are properly applied and image URLs are correctly formatted and accessible
  - Ensure the content and color scheme are consistent across all slides
"""

    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "The detail description of how to update the presentation.",
            },
            "action": {
                "type": "string",
                "description": "The action to perform on the presentation.",
                "enum": ["init", "create", "update", "delete", "final_check"],
            },
            "images": {
                "type": "array",
                "description": "List of image URLs and their descriptions to be used in the presentation slides.",
                "items": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "URL of an image"},
                        "description": {
                            "type": "string",
                            "description": "Description of what the image represents or how it should be used",
                        },
                    },
                    "required": ["url", "description"],
                },
            },
        },
        "required": ["description", "action"],
    }

    def __init__(
        self,
        client,
        workspace_manager: WorkspaceManager,
        message_queue: asyncio.Queue,
        context_manager: ContextManager,
        ask_user_permission: bool = False,
    ):
        super().__init__()
        self.client = client
        self.workspace_manager = workspace_manager
        self.message_queue = message_queue
        self.bash_tool = create_bash_tool(ask_user_permission, workspace_manager.root)
        self.tools = [
            self.bash_tool,
            StrReplaceEditorTool(workspace_manager=workspace_manager),
        ]
        image_search_tool = ImageSearchTool()
        if image_search_tool.is_available():
            self.tools.append(image_search_tool)
        self.history = MessageHistory(context_manager=context_manager)
        self.tool_params = [tool.get_tool_param() for tool in self.tools]
        self.max_turns = 200

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        action = tool_input["action"]
        description = tool_input["description"]

        if action == "init":
            self.history = MessageHistory()

            # Clone the reveal.js repository to the specified path
            clone_result = await self.bash_tool.run_impl(
                {
                    "command": f"git clone https://github.com/khoangothe/reveal.js.git {self.workspace_manager.root}/presentation/reveal.js"
                }
            )

            if not clone_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Failed to clone reveal.js repository: {clone_result.content}",
                    f"Failed to clone reveal.js repository: {clone_result.content}",
                    auxiliary_data={"success": False},
                )

            # Install dependencies
            install_result = await self.bash_tool.run_impl(
                {
                    "command": f"cd {self.workspace_manager.root}/presentation/reveal.js && npm install && cd {self.workspace_manager.root}"
                }
            )

            if not install_result.auxiliary_data.get("success", False):
                return ToolImplOutput(
                    f"Failed to install dependencies: {install_result.content}",
                    f"Failed to install dependencies: {install_result.content}",
                    auxiliary_data={"success": False},
                )

        # Handle other actions (create, update, delete, final_refinement)
        # Add description to history
        instruction = f"Perform '{action}' on presentation at path './presentation/reveal.js' with description: {description}"
        self.history.add_user_prompt(instruction)
        self.interrupted = False

        remaining_turns = self.max_turns
        while remaining_turns > 0:
            self.history.truncate()
            remaining_turns -= 1

            delimiter = "-" * 45 + "PRESENTATION AGENT" + "-" * 45
            print(f"\n{delimiter}\n")

            # Get tool parameters for available tools
            tool_params = [tool.get_tool_param() for tool in self.tools]

            # Check for duplicate tool names
            tool_names = [param.name for param in tool_params]
            sorted_names = sorted(tool_names)
            for i in range(len(sorted_names) - 1):
                if sorted_names[i] == sorted_names[i + 1]:
                    raise ValueError(f"Tool {sorted_names[i]} is duplicated")

            current_messages = self.history.get_messages_for_llm()

            # Generate response using the client
            model_response, _ = self.client.generate(
                messages=current_messages,
                max_tokens=8192,
                tools=tool_params,
                system_prompt=self.PROMPT,
            )

            print(model_response)

            # Add the raw response to the canonical history
            self.history.add_assistant_turn(model_response)

            # Handle tool calls
            pending_tool_calls = self.history.get_pending_tool_calls()

            if len(pending_tool_calls) == 0:
                # No tools were called, so assume the task is complete
                return ToolImplOutput(
                    tool_output=self.history.get_last_assistant_text_response(),
                    tool_result_message="Task completed",
                    auxiliary_data={"success": True},
                )

            if len(pending_tool_calls) > 1:
                raise ValueError("Only one tool call per turn is supported")

            assert len(pending_tool_calls) == 1
            tool_call = pending_tool_calls[0]
            self.message_queue.put_nowait(
                RealtimeEvent(
                    type=EventType.TOOL_CALL,
                    content={
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "tool_input": tool_call.tool_input,
                    },
                )
            )

            try:
                tool = next(t for t in self.tools if t.name == tool_call.tool_name)
            except StopIteration as exc:
                raise ValueError(
                    f"Tool with name {tool_call.tool_name} not found"
                ) from exc

            # Execute the tool
            result = tool.run(tool_call.tool_input, deepcopy(self.history))

            # Handle both string results and tuples
            if isinstance(result, tuple):
                tool_result, _ = result
            else:
                tool_result = result

            self.history.add_tool_call_result(tool_call, tool_result)

            self.message_queue.put_nowait(
                RealtimeEvent(
                    type=EventType.TOOL_RESULT,
                    content={
                        "tool_call_id": tool_call.tool_call_id,
                        "tool_name": tool_call.tool_name,
                        "result": tool_result,
                    },
                )
            )

        # If we exit the loop without returning, we've hit max turns
        return ToolImplOutput(
            tool_output=f"Action '{action}' did not complete after {self.max_turns} turns",
            tool_result_message=f"Action '{action}' exceeded maximum turns",
            auxiliary_data={"success": False},
        )
