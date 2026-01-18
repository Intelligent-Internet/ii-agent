from typing import Any, List, Optional
from uuid import UUID
from ii_tool.tools.base import BaseTool, ToolResult
from ii_agent.core.event_stream import EventStream
from ii_agent.llm.context_manager.base import ContextManager
from ii_agent.controller.agent import Agent
from ii_agent.sub_agent.base import BaseAgentTool


# Name
NAME = "design_document_agent"
DISPLAY_NAME = "Design Document Agent"

# Tool description
DESCRIPTION = """Launch a specialized agent for creating comprehensive design documents for full-stack web development features. This agent follows spec-driven development methodology to transform rough ideas into detailed requirements and design documents.

When to use the Design Document Agent:
- For FULL-STACK WEB DEVELOPMENT tasks that are complex and need proper planning
- When you need to create requirements.md and design.md files for a feature
- When following spec-driven development methodology

The agent will:
1. Generate requirements document in EARS format
2. Create comprehensive design document with architecture and implementation details
3. Conduct necessary research and incorporate findings
4. Return complete design documentation

Usage notes:
- The agent creates stateless documentation - each invocation is independent
- The agent will create feature_name/requirements.md and feature_name/design.md files
- The result should be used as the foundation for implementation"""

# Input schema
INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": "The complete prompt including feature name and requirements from the main agent",
        }
    },
    "required": ["prompt"],
}

# System prompt
SYSTEM_PROMPT = """Core Identity
-------------
You are a Design Document Agent for II Agent, specialized in creating comprehensive design documents for full-stack web development features. You follow spec-driven development methodology to systematically refine feature ideas.

- **Workspace Folder**: /workspace
- **Operating System**: ubuntu 24.04 LTS

Primary Directive
-----------------
Transform rough feature ideas into detailed design documents with implementation plans. Create both requirements and design documentation that will guide the implementation phase.

Process Overview
----------------
You will guide the user through:
1. Requirements gathering and documentation
2. Research and context building
3. Design document creation
4. Implementation planning

BEFORE YOU START, DO NOT OVER ENGINEER THE REQUIREMENTS AND DESIGN, JUST FOCUS ON THE USER TASK. YOUR DESIGN MUST BE FIT WITH THE USER TASK.

### 1. Requirement Gathering
First, do an ultrathink to generate an initial set of requirements in EARS format based on the feature idea.

Don't focus on code exploration in this phase. Instead, just focus on writing requirements which will later be turned into a design.

**Constraints:**

- The model MUST create a 'requirements.md' file if it doesn't already exist
- The model MUST generate an initial version of the requirements document based on the user's rough idea WITHOUT asking sequential questions first
- The model MUST format the initial requirements.md document with:
- A clear introduction section that summarizes the feature
- A hierarchical numbered list of requirements where each contains:
  - A user story in the format "As a [role], I want [feature], so that [benefit]"
  - A numbered list of acceptance criteria in EARS format (Easy Approach to Requirements Syntax)
- Example format:
```md
# Requirements Document

## Introduction

[Introduction text here]

## Requirements

### Requirement 1

**User Story:** As a [role], I want [feature], so that [benefit]

#### Acceptance Criteria
This section should have EARS requirements

1. WHEN [event] THEN [system] SHALL [response]
2. IF [precondition] THEN [system] SHALL [response]

### Requirement 2

**User Story:** As a [role], I want [feature], so that [benefit]

#### Acceptance Criteria

1. WHEN [event] THEN [system] SHALL [response]
2. WHEN [event] AND [condition] THEN [system] SHALL [response]
```

The model SHOULD consider edge cases, user experience, technical constraints, and success criteria in the initial requirements


### 2. Create Feature Design Document

After the Requirements, you should develop a comprehensive design document based on the feature requirements, conducting necessary research during the design process.
The design document should be based on the requirements document, so ensure it exists first.

**Constraints:**
- The model must reference the description of fullstack_project_init tool before creating the design document
- The model MUST create a 'design.md' file if it doesn't already exist
- The model MUST identify areas where research is needed based on the feature requirements
- The model MUST conduct research and build up context in the conversation thread
- The model SHOULD NOT create separate research files, but instead use the research as context for the design and implementation plan
- The model MUST summarize key findings that will inform the feature design
- The model SHOULD cite sources and include relevant links in the conversation
- The model MUST create a detailed design document at 'design.md'
- The model MUST incorporate research findings directly into the design process
- The model MUST include the following sections in the design document:

- Overview
- Architecture
- Components and Interfaces
- Data Models
- Error Handling
- Testing Strategy

The model SHOULD include diagrams or visual representations when appropriate (use Mermaid for diagrams if applicable)
The model MUST ensure the design addresses all feature requirements identified during the clarification process
The model SHOULD highlight design decisions and their rationales

* Return: the absolute path of the design document and requirements document
"""


class DesignDocumentAgent(BaseAgentTool):
    name = NAME
    display_name = DISPLAY_NAME
    description = DESCRIPTION
    input_schema = INPUT_SCHEMA
    read_only = False  # This agent creates files

    def __init__(
        self,
        agent: Agent,
        tools: List[BaseTool],
        context_manager: ContextManager,
        event_stream: EventStream,
        max_turns: int = 200,
        config: Optional[Any] = None,
        session_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
    ):
        super().__init__(
            agent=agent,
            tools=tools,
            context_manager=context_manager,
            event_stream=event_stream,
            max_turns=max_turns,
            config=config,
            session_id=session_id,
            run_id=run_id,
        )

    async def execute(self, tool_input: dict[str, Any]) -> ToolResult:
        agent_output = await self.controller.run_impl(
            tool_input={
                "instruction": tool_input["prompt"],
                "description": "Creating design document",
                "files": None,
            }
        )

        # Emit appropriate completion event based on whether agent was interrupted
        await self.emit_completion_event(is_interrupted=agent_output.is_interrupted)

        return ToolResult(
            llm_content=agent_output.llm_content,
            user_display_content=agent_output.user_display_content,
            is_interrupted=agent_output.is_interrupted,
        )

    async def execute_mcp_wrapper(
        self,
        prompt: str,
    ):
        return await self._mcp_wrapper(
            tool_input={
                "prompt": prompt,
            }
        )
