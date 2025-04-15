"""File writing tool.

This tool allows writing or appending content to files.
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from utils.common import (
    DialogMessages,
    LLMTool,
    ToolImplOutput,
)


class FileWriteTool(LLMTool):
    name = "file_write"
    description = "Overwrite or append content to a file. Use for creating new files, appending content, or modifying existing files."
    input_schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": "Absolute path of the file to write to"
            },
            "content": {
                "type": "string",
                "description": "Text content to write"
            },
            "append": {
                "type": "boolean",
                "description": "(Optional) Whether to use append mode"
            },
            "leading_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a leading newline"
            },
            "trailing_newline": {
                "type": "boolean",
                "description": "(Optional) Whether to add a trailing newline"
            },
            "sudo": {
                "type": "boolean",
                "description": "(Optional) Whether to use sudo privileges"
            }
        },
        "required": ["file", "content"]
    }

    def run_impl(
        self,
        tool_input: dict[str, Any],
        dialog_messages: Optional[DialogMessages] = None,
    ) -> ToolImplOutput:
        file_path = tool_input["file"]
        content = tool_input["content"]
        append = tool_input.get("append", False)
        leading_newline = tool_input.get("leading_newline", False)
        trailing_newline = tool_input.get("trailing_newline", False)
        sudo = tool_input.get("sudo", False)
        
        # Add newlines if requested
        if leading_newline:
            content = "\n" + content
        if trailing_newline:
            content = content + "\n"
        
        # Determine write mode
        mode = "a" if append else "w"
        
        if sudo:
            # Use sudo to write to the file
            try:
                # Create a temporary file with the content
                temp_file = "/tmp/file_write_temp"
                with open(temp_file, "w") as f:
                    f.write(content)
                
                # Use sudo to copy the temporary file to the target location
                cmd = f"sudo cp {temp_file} {file_path}"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                # Check if the command was successful
                if result.returncode != 0:
                    return ToolImplOutput(
                        f"Error writing to {file_path} with sudo: {result.stderr}",
                        f"Error writing to {file_path} with sudo: {result.stderr}"
                    )
                
                # Remove the temporary file
                os.remove(temp_file)
                
                return ToolImplOutput(
                    f"Successfully wrote to {file_path} with sudo privileges",
                    f"Successfully wrote to {file_path} with sudo privileges"
                )
            
            except Exception as e:
                return ToolImplOutput(
                    f"Error writing to {file_path}: {str(e)}",
                    f"Error writing to {file_path}: {str(e)}"
                )
        else:
            # Normal file writing without sudo
            try:
                # Ensure the directory exists
                directory = os.path.dirname(file_path)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                
                # Write to the file
                with open(file_path, mode) as f:
                    f.write(content)
                
                action = "appended to" if append else "wrote"
                return ToolImplOutput(
                    f"Successfully {action} {file_path}",
                    f"Successfully {action} {file_path}"
                )
            
            except Exception as e:
                return ToolImplOutput(
                    f"Error writing to {file_path}: {str(e)}",
                    f"Error writing to {file_path}: {str(e)}"
                )

    def get_tool_start_message(self, tool_input: dict[str, Any]) -> str:
        action = "Appending to" if tool_input.get("append", False) else "Writing to"
        return f"{action} file: {tool_input['file']}"
