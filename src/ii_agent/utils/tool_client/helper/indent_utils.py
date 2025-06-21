from collections import defaultdict
from dataclasses import dataclass
from typing import Literal, Tuple


@dataclass(frozen=True)
class IndentType:
    """Class representing indentation type with size attribute."""

    type: Literal["space", "tab", "mixed"]
    size: int = 4
    most_used: "IndentType | None" = None  # Tracks predominant indent type for mixed

    @property
    def is_tab(self) -> bool:
        return self.type == "tab"

    @property
    def is_mixed(self) -> bool:
        return self.type == "mixed"

    @property
    def is_space(self) -> bool:
        return self.type == "space"

    @classmethod
    def space(cls, size: int = 4) -> "IndentType":
        """Create a space indentation type with the specified size."""
        return cls(type="space", size=size)

    @classmethod
    def tab(cls, size: int = 1) -> "IndentType":
        """Create a tab indentation type (size is typically 1)."""
        return cls(type="tab", size=size)

    @classmethod
    def mixed(cls, most_used: "IndentType | None" = None) -> "IndentType":
        """Create a mixed indentation type."""
        return cls(type="mixed", size=1, most_used=most_used)

    def __repr__(self):
        if self.is_mixed:
            most_used_str = f", most_used={self.most_used}" if self.most_used else ""
            return f"IndentType({self.type}{most_used_str})"
        if self.is_tab:
            return f"IndentType({self.type})"
        return f"IndentType({self.type}, size={self.size})"


def detect_line_indent(line: str) -> Tuple[int, int]:
    """Detect the indentation of a line.

    Returns:
        Tuple of (num_tabs, num_spaces_after_tabs)
    """
    if not line:
        return (0, 0)

    # Count leading tabs
    num_tabs = 0
    for char in line:
        if char != "\t":
            break
        num_tabs += 1

    # Count spaces after tabs
    num_spaces = 0
    for char in line[num_tabs:]:
        if char != " ":
            break
        num_spaces += 1

    return (num_tabs, num_spaces)


def detect_indent_type(code: str | None) -> IndentType | None:
    """Detect the indentation type (spaces or tabs) and size used in the code.

    If the code contains mixed indentation, it will return MIXED.
    If the code contains only spaces, it will return SPACE with the most common difference as size.
    If the code contains only tabs, it will return TAB.
    If the code contains both tabs and spaces, it will return MIXED.
    If the code contains invalid mixed indentation (e.g. " \t"), it will return MIXED.

    Args:
        code: The source code to analyze

    Returns:
        IndentType with the detected indentation type and size, or None if no indentation is detected
    """
    if not code or not isinstance(code, str):
        return None

    lines = code.splitlines()
    space_diff_counts = defaultdict(int)
    tab_indents = 0
    space_indents = 0
    mixed_indent_in_one_line = False
    prev_indent_level = 0
    prev_indent_type = "space"

    for line in lines:
        if not line.strip():
            continue

        num_tabs, num_spaces = detect_line_indent(line)
        if num_tabs == 0 and num_spaces == 0:
            continue

        if num_tabs > 0:
            if num_spaces > 0:
                mixed_indent_in_one_line = True
            tab_indents += 1
            current_indent_type = "tab"
        else:
            space_indents += 1
            current_indent_type = "space"
            if prev_indent_type == "space":
                diff = abs(num_spaces - prev_indent_level)
                if diff > 1:
                    space_diff_counts[diff] += 1

        prev_indent_level = num_spaces if num_spaces > 0 else num_tabs
        prev_indent_type = current_indent_type

    if mixed_indent_in_one_line or (tab_indents > 0 and space_indents > 0):
        if tab_indents > space_indents:
            most_used = IndentType.tab()
        else:
            if space_diff_counts:
                most_common_diff = max(space_diff_counts.items(), key=lambda x: x[1])[0]
                most_used = IndentType.space(most_common_diff)
            else:
                most_used = IndentType.space()
        return IndentType.mixed(most_used=most_used)
    elif tab_indents > 0:
        return IndentType.tab()
    elif space_diff_counts:
        most_common_diff = max(space_diff_counts.items(), key=lambda x: x[1])[0]
        return IndentType.space(most_common_diff)
    else:
        return None


def force_normalize_indent(code: str) -> str:
    """Normalize to 4 spaces regardless what is the original indentation."""
    lines = code.splitlines()
    normalized_lines = []
    for line in lines:
        if not line.strip():
            normalized_lines.append(line.strip())
            continue

        num_tabs, num_spaces = detect_line_indent(line)
        normalized_lines.append(" " * (4 * num_tabs) + " " * num_spaces + line.lstrip())
    return "\n".join(normalized_lines)


def normalize_indent(code: str | None, indent_type: IndentType) -> str | None:
    """Normalize indentation in code to use 4 spaces.

    Args:
        code: The source code to normalize
        indent_type: The current indentation type and size

    Returns:
        Code with normalized indentation (4 spaces)

    Raises:
        AssertionError: If the code contains mixed indentation or if indent_type is MIXED
    """
    assert not indent_type.is_mixed, "Cannot normalize mixed indentation"
    if not code or not isinstance(code, str):
        return code

    lines = code.splitlines()
    normalized_lines = []

    for line in lines:
        if not line.strip():
            normalized_lines.append(line)
            continue

        num_tabs, num_spaces = detect_line_indent(line)
        if num_tabs == 0 and num_spaces == 0:
            normalized_lines.append(line)
            continue

        indent_level = 0
        remainder = 0
        if indent_type.is_tab:
            indent_level = num_tabs
            remainder = num_spaces
            assert line[: num_tabs + num_spaces] == "\t" * num_tabs + " " * num_spaces
        else:
            total_spaces = num_spaces + (num_tabs * indent_type.size)
            indent_level = total_spaces // indent_type.size
            remainder = total_spaces % indent_type.size
            assert line[: num_tabs + num_spaces] == " " * (num_tabs + num_spaces)

        assert remainder < 2, f"Unexpected remainder: {remainder} for line: {line}"
        new_indent = " " * (4 * indent_level) + " " * remainder
        normalized_line = new_indent + line.lstrip()
        normalized_lines.append(normalized_line)

    return "\n".join(normalized_lines)


def apply_indent_type(
    code: str | None,
    indent_type: IndentType,
    original_indent_type: IndentType | None = None,
) -> str | None:
    """Apply the specified indentation type to code.

    Args:
        code: The source code to modify
        indent_type: The target indentation type and size to apply
        original_indent_type: The original indentation type and size, if known

    Returns:
        Code with the specified indentation type applied
    """
    assert not indent_type.is_mixed, "Cannot apply mixed indentation"
    if not code or not isinstance(code, str):
        return code

    if original_indent_type is None:
        original_indent_type = detect_indent_type(code)
        if original_indent_type is None or original_indent_type.is_mixed:
            return code
        else:
            return apply_indent_type(code, indent_type, original_indent_type)

    if original_indent_type == indent_type:
        return code

    lines = code.splitlines()
    modified_lines = []

    for line in lines:
        if not line.strip():  # Empty line
            modified_lines.append(line)
            continue

        num_tabs, num_spaces = detect_line_indent(line)

        if original_indent_type.is_tab:
            indent_levels = num_tabs
            remainder = num_spaces
        else:
            assert num_tabs == 0, f"Unexpected tab in line: {line}"
            indent_levels = num_spaces // original_indent_type.size
            remainder = num_spaces % original_indent_type.size

        if indent_levels == 0:  # No indentation
            modified_lines.append(line)
            continue

        if indent_type.is_tab:
            new_indent = "\t" * indent_levels
        else:
            new_indent = " " * (indent_type.size * indent_levels)

        new_indent += " " * remainder

        modified_line = new_indent + line.lstrip()
        modified_lines.append(modified_line)

    return "\n".join(modified_lines)


def match_indent_by_first_line(code: str | None, line: str) -> str | None:
    """Match the indentation of the first line in code to the given line.
    All subsequent lines will be adjusted to maintain their relative indentation.

    Args:
        code: The source code to modify
        line: The line to match the indentation to

    Returns:
        Code with all lines indented relative to the new first line indentation
    """
    if not code or not isinstance(code, str):
        return code

    lines = code.splitlines()
    if not lines:
        return code

    # Get target and current indentation levels
    _, target_spaces = detect_line_indent(line)
    _, current_spaces = detect_line_indent(lines[0])

    # Calculate the indentation difference
    indent_diff = target_spaces - current_spaces

    modified_lines = []

    for line in lines:
        if not line.strip():  # Preserve empty lines
            modified_lines.append(line)
            continue

        _, num_spaces = detect_line_indent(line)
        new_indent_size = max(0, num_spaces + indent_diff)
        modified_lines.append(" " * new_indent_size + line.lstrip())

    return "\n".join(modified_lines)


def match_indent(code: str | None, code_to_match: str) -> str | None:
    if not code or not isinstance(code, str):
        return code

    indent_type = detect_indent_type(code_to_match)
    if indent_type is not None and indent_type.is_mixed:
        indent_type = indent_type.most_used
    if indent_type is not None:
        return apply_indent_type(code, indent_type)

    return code
