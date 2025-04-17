from copy import deepcopy
from typing import Any, Optional
from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)
from utils.llm_client import LLMClient, TextResult
from utils.workspace_manager import WorkspaceManager
from prompts.system_prompt import SYSTEM_PROMPT
import os
import logging
import datetime
import traceback


class WritingAgent(LLMTool):
    name = "writing_agent"
    description = """\
A specialized agent that generates writeups based on the parent agent's state and writes content to a specified file.
Use this tool regularly to save the pending context to a file after completing a sub-task.
Use this for creating comprehensive reports, documentation, articles, or any text content that needs to be written to a file.
"""
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The path where the content should be written.",
            },
            "instruction": {
                "type": "string",
                "description": "Instructions for generating the writeup.",
            },
            "content_type": {
                "type": "string",
                "description": "Type of content to generate (report, documentation, article, etc.)",
                "enum": ["report", "documentation", "article", "summary", "code", "other"]
            },
        },
        "required": ["file_path", "instruction"],
    }

    # Content type templates for different writing styles
    CONTENT_TYPE_TEMPLATES = {
        "report": {
            "structure": "executive_summary, introduction, main_findings, analysis, conclusion, recommendations, references",
            "style": "formal, factual, data-driven, comprehensive",
        },
        "documentation": {
            "structure": "overview, prerequisites, installation, usage, api_reference, examples, troubleshooting, references",
            "style": "clear, precise, step-by-step, comprehensive",
        },
        "article": {
            "structure": "headline, introduction, main_body, conclusion, references",
            "style": "engaging, informative, well-structured, interesting",
        },
        "summary": {
            "structure": "key_points, brief_overview, conclusion",
            "style": "concise, focused, highlighting essential information",
        },
        "code": {
            "structure": "purpose, dependencies, implementation, usage_examples, testing, comments",
            "style": "well-documented, maintainable, following best practices",
        },
        "other": {
            "structure": "appropriate_for_content",
            "style": "clear, well-organized, purpose-driven",
        }
    }

    def _get_system_prompt(self):
        """Get the system prompt for the writing agent.

        Returns:
            The system prompt with workspace root information
        """
        return SYSTEM_PROMPT.format(
            workspace_root=self.workspace_manager.root,
        )

    def __init__(
        self,
        client: LLMClient,
        workspace_manager: WorkspaceManager,
        parent_agent,
        logger_for_agent_logs: logging.Logger,
        max_output_tokens: int = 8192,
    ):
        """Initialize the writing agent.

        Args:
            client: The LLM client to use
            workspace_manager: Workspace manager for file operations
            parent_agent: The parent general agent that will hand off to this agent
            logger_for_agent_logs: Logger for agent activities
            max_output_tokens: Maximum tokens per generation
        """
        super().__init__()
        self.client = client
        self.workspace_manager = workspace_manager
        self.parent_agent = parent_agent
        self.logger_for_agent_logs = logger_for_agent_logs
        self.max_output_tokens = max_output_tokens
        self.dialog = DialogMessages(
            logger_for_agent_logs=logger_for_agent_logs,
            use_prompt_budgeting=True,
        )

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file_path"]
        instruction = tool_input["instruction"]
        content_type = tool_input.get("content_type", "other")

        # Log the start of the writing agent
        delimiter = "-" * 45 + " WRITING AGENT " + "-" * 45
        self.logger_for_agent_logs.info(f"\n{delimiter}\n")
        self.logger_for_agent_logs.info(f"Writing to file: {file_path}")
        self.logger_for_agent_logs.info(f"Content type: {content_type}")
        self.logger_for_agent_logs.info(f"Instruction: {instruction}")

        # Validate content type
        if content_type not in self.CONTENT_TYPE_TEMPLATES:
            self.logger_for_agent_logs.warning(f"Unknown content type: {content_type}, using 'other'")
            content_type = "other"

        try:
            # Always use a copy of the parent agent's dialog for context
            parent_dialog = deepcopy(self.parent_agent.dialog)
            parent_dialog.drop_tool_calls_from_final_turn()
            
            # Get the content type template
            template = self.CONTENT_TYPE_TEMPLATES[content_type]
            
            # Add writing instruction to the dialog
            writing_prompt = self._create_writing_prompt(instruction, file_path, content_type, template)
            parent_dialog.add_user_prompt(writing_prompt)

            # Generate content using the LLM with the parent's dialog context
            model_response, _ = self.client.generate(
                messages=parent_dialog.get_messages_for_llm_client(),
                max_tokens=self.max_output_tokens,
                system_prompt=self._get_system_prompt(),
            )
            
            parent_dialog.add_model_response(model_response)
            content = parent_dialog.get_last_model_text_response()
            
            # Check if the content is empty or too short
            if not content or len(content.strip()) < 10:
                error_message = f"Generated content was empty or too short: {content}"
                self.logger_for_agent_logs.error(error_message)
                return ToolImplOutput(
                    tool_output=error_message,
                    tool_result_message=error_message,
                )
            
            # Ensure the directory exists
            # dir_path = os.path.dirname(os.path.abspath(file_path))
            # if dir_path:  # Check if dirname is not empty (for files in current dir)
            #     os.makedirs(dir_path, exist_ok=True)
            # puth file_path in workspace folder
            file_path = os.path.join("workspace", file_path)
            
            
            # Write the content to the specified file
            with open(file_path, 'w') as f:
                f.write(content)
            
            # Get file size for logging
            file_size = os.path.getsize(file_path)
            file_size_kb = file_size / 1024
            
            result_message = f"Content successfully written to {file_path} ({file_size_kb:.2f} KB)"
            self.logger_for_agent_logs.info(f"\n{result_message}\n")
            
            # Return both the result message and the content
            return ToolImplOutput(
                tool_output=result_message,
                tool_result_message=result_message,
                auxiliary_data={"content": content, "file_path": file_path, "content_type": content_type}
            )
            
        except Exception as e:
            error_message = f"Error in writing agent: {str(e)}"
            self.logger_for_agent_logs.error(f"{error_message}\n{traceback.format_exc()}")
            return ToolImplOutput(
                tool_output=error_message,
                tool_result_message=error_message,
            )
    
    def _create_writing_prompt(self, instruction: str, file_path: str, content_type: str, template: dict) -> str:
        """Create a detailed writing prompt based on content type.
        
        Args:
            instruction: User's instruction
            file_path: Path where content will be written
            content_type: Type of content to generate
            template: Template for the content type
            
        Returns:
            A detailed writing prompt
        """
        # Check if the target file already exists
        existing_content = ""
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    existing_content = f.read()
        except Exception as e:
            self.logger_for_agent_logs.warning(f"Could not read existing file {file_path}: {str(e)}")
        
        existing_content_section = ""
        if existing_content:
            existing_content_section = f"""
Existing content in the file that you should incorporate or build upon:
```
{existing_content}
```

"""
        
        # Build the prompt
        prompt = f"""
Generate a well-structured {content_type} based on the following instruction:
{instruction}

{existing_content_section}
When creating this content, follow these guidelines:
1. Structure: {template['structure']}
2. Writing style: {template['style']}
3. Be comprehensive and detailed - provide thorough coverage of the topic
4. Use clear headings and organization where appropriate
5. Include relevant facts, data, or examples when available from the conversation history

Use the conversation history and context from the parent agent to create comprehensive content.
The content should be clear, well-formatted, and ready to be written to a file at {file_path}.
"""
        return prompt

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        content_type = tool_input.get("content_type", "content")
        return f"Writing agent started generating {content_type} with instruction: {tool_input['instruction']}"

    def write_content(self, file_path: str, instruction: str, content_type: str = "other") -> str:
        """Start a new writing task.

        Args:
            file_path: The path where the content should be written.
            instruction: Instructions for generating the writeup.
            content_type: Type of content to generate.

        Returns:
            The generated content.
        """
        tool_input = {
            "file_path": file_path,
            "instruction": instruction,
            "content_type": content_type,
        }
        return self.run(tool_input, self.dialog) 