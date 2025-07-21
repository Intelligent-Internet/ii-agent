import ast
import random
import re
import time
from typing import Any, Optional

from ii_agent.llm.base import ToolCall, ToolFormattedResult, ToolResult
from ii_agent.prompts.researcher_system_prompt import ConfigConstants


def parse_code_blobs(text: str) -> tuple[str, str]:
    """Extract code blocks from the LLM's output.

    If a valid code block is passed, it returns it directly.

    Args:
        text (`str`): LLM's output text to parse.
        tool_names (`List[str]`, optional): List of tool names to check in the code block.

    Returns:
        `tuple[str, str]`: Tuple of (text_before_code_block, code_block).
    """
    pattern = r"```\s*(?:py|python)\s*(.*?)\s*```"

    match = re.search(pattern, text, re.DOTALL)
    if match:
        text_before = text[: match.start()].strip()
        code_block = match.group(1).strip()
        return text_before, code_block

    # Maybe the LLM outputted a code blob directly
    try:
        ast.parse(text)
        return "", text
    except SyntaxError:
        pass

    return "", ""


def evaluate_ast_node(node: ast.AST) -> Any:
    """
    Recursively evaluate an AST node to extract its value.

    Args:
        node: An AST node representing a value

    Returns:
        The Python value represented by the node

    Raises:
        ValueError: If the node cannot be evaluated
    """
    # Handle simple literals directly
    if isinstance(node, ast.Constant):
        return node.value

    # Handle lists
    if isinstance(node, ast.List):
        return [evaluate_ast_node(elem) for elem in node.elts]

    # Handle dictionaries
    if isinstance(node, ast.Dict):
        keys = [evaluate_ast_node(k) for k in node.keys]
        values = [evaluate_ast_node(v) for v in node.values]
        return dict(zip(keys, values))

    # Handle tuples
    if isinstance(node, ast.Tuple):
        return tuple(evaluate_ast_node(elem) for elem in node.elts)

    # Handle sets
    if isinstance(node, ast.Set):
        return {evaluate_ast_node(elem) for elem in node.elts}

    if isinstance(node, ast.Name):
        # Handle special constants like True, False, None
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
        raise ValueError(f"Cannot evaluate name: {node.id}")

    # For more complex expressions, try using ast.literal_eval
    try:
        # Convert the node to source code
        code = ast.unparse(node)
        # Use ast.literal_eval to safely evaluate expressions
        return ast.literal_eval(code)
    except (AttributeError, ValueError) as exc:
        # For Python versions without ast.unparse or other issues
        raise ValueError(
            f"Cannot evaluate complex expression: {ast.dump(node)}"
        ) from exc


def evaluate_block(string: str) -> Optional["ToolCall"]:
    """
    Parse a string into an Action instance.

    Args:
        string: A string in format "action_name(arg1=value1, arg2=value2)"

    Returns:
        Action instance if parsing succeeds, None otherwise

    Raises:
        ValueError: If the string format is invalid
    """
    try:
        # Remove leading/trailing whitespace
        string = string.strip()

        # Check if string contains function call pattern
        if not (string.endswith(")") and "(" in string):
            raise ValueError(
                f"String must be in format 'name(arg1=value1, arg2=...)' but got {string}"
            )

        # Parse the AST
        tree = ast.parse(string)
        if not tree.body or not isinstance(tree.body[0].value, ast.Call):
            raise ValueError("String must contain a valid function call")

        call = tree.body[0].value
        name = getattr(call.func, "id", None)
        if not name:
            raise ValueError("Action name must be a valid identifier")

        # Process keyword arguments
        arguments = {}
        for keyword in call.keywords:
            if not keyword.arg:
                raise ValueError("All arguments must be named (keyword arguments)")

            # Extract the value using ast.literal_eval for complex structures
            value = evaluate_ast_node(keyword.value)
            arguments[keyword.arg] = value

        return ToolCall(
            tool_call_id=generate_tool_call_id(), tool_name=name, tool_input=arguments
        )

    except SyntaxError as e:
        raise ValueError(f"Invalid action string syntax: {str(e)}") from e
    except ValueError as e:
        raise ValueError(f"Invalid action string format: {str(e)}") from e
    except Exception as e:
        raise ValueError(f"Unexpected error parsing action string: {str(e)}") from e


def generate_tool_call_id() -> str:
    """Generate a unique ID for a tool call.

    Returns:
        A unique string ID combining timestamp and random number.
    """
    timestamp = int(time.time() * 1000)  # Current time in milliseconds
    random_num = random.randint(1000, 9999)  # Random 4-digit number
    return f"call_{timestamp}_{random_num}"


def format_tool_call(tool_call: ToolCall) -> str:
    """Format a ToolCall instance into a string."""
    return f"{ConfigConstants.CODE_BLOCK_START}\n{tool_to_string(tool_call)}\n{ConfigConstants.CODE_BLOCK_END}{ConfigConstants.END_CODE}"


def tool_to_string(tool_call: ToolCall) -> Optional[str]:
    """
    Convert ToolCall instance to a string in function call format.

    Returns:
        String in format "name(arg1=value1, arg2=value2)"
    """
    args = []
    if isinstance(tool_call.tool_input, dict):
        for key, value in tool_call.tool_input.items():
            # Handle string values with proper quoting
            if isinstance(value, str):
                arg_str = f'{key}="{value}"'
            # Handle other types (numbers, booleans, etc.) without quotes
            else:
                arg_str = f"{key}={value}"
            args.append(arg_str)

        args_str = ", ".join(args)
        return f"{tool_call.tool_name}({args_str})"


def format_tool_result(tool_result: ToolResult | ToolFormattedResult) -> str:
    """Format a ToolResult instance into a string."""
    suffix = ""
    if tool_result.tool_name == "visit_webpage":
        suffix = ConfigConstants.VISIT_WEBPAGE_SUFFIX
    elif tool_result.tool_name == "web_search":
        suffix = ConfigConstants.SEARCH_SUFFIX
    return f"{ConfigConstants.TOOL_RESPONSE_OPEN}\n{tool_result.tool_output}\n{ConfigConstants.TOOL_RESPONSE_CLOSE}\n{suffix}"
