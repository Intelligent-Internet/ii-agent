"""Tests for indentation utilities in file_edit_utils.py."""

import pytest
from utils.indent_utils import (
    IndentType,
    detect_indent_type,
    detect_line_indent,
    normalize_indent,
    apply_indent_type,
    force_normalize_indent,
)


class TestIndentUtils:
    """Test class for indentation utilities."""

    def test_detect_line_indent(self):
        """Test detect_line_indent function."""
        # Empty line
        assert detect_line_indent("") == (0, 0)
        assert detect_line_indent("\n") == (0, 0)

        # No indentation
        assert detect_line_indent("def test():") == (0, 0)
        assert detect_line_indent("print('hello')") == (0, 0)

        # Space indentation
        assert detect_line_indent("    print('hello')") == (0, 4)
        assert detect_line_indent("  print('hello')") == (0, 2)
        assert detect_line_indent("   print('hello')") == (0, 3)

        # Tab indentation
        assert detect_line_indent("\tprint('hello')") == (1, 0)
        assert detect_line_indent("\t\tprint('hello')") == (2, 0)
        assert detect_line_indent("\t\t\tprint('hello')") == (3, 0)

        # Mixed indentation (tabs then spaces)
        assert detect_line_indent("\t print('hello')") == (1, 1)
        assert detect_line_indent("\t  print('hello')") == (1, 2)
        assert detect_line_indent("\t\t  print('hello')") == (2, 2)

        # Regular spaces
        assert detect_line_indent("  print('hello')") == (0, 2)

    def test_detect_indent_type_spaces(self):
        """Test detecting space indentation."""
        # 2-space indentation
        code = "def test():\n  print('hello')\n  if True:\n    print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.size == 2
        assert indent_type == IndentType.space(2)

        # 4-space indentation
        code = "def test():\n    print('hello')\n    if True:\n        print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.size == 4
        assert indent_type == IndentType.space(4)

        # 3-space indentation (non-standard)
        code = "def test():\n   print('hello')\n   if True:\n      print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.size == 3
        assert indent_type == IndentType.space(3)

        # 8-space indentation (large)
        code = "def test():\n        print('hello')\n        if True:\n                print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.size == 8
        assert indent_type == IndentType.space(8)

    def test_detect_indent_type_tabs(self):
        """Test detecting tab indentation."""
        code = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.size == 1
        assert indent_type == IndentType.tab(1)

    def test_detect_indent_type_mixed(self):
        """Test detecting indentation in mixed code (should prefer the most common)."""
        # More spaces than tabs - should be mixed with spaces as most used
        code = "def test():\n    print('hello')\n    if True:\n        print('world')\n\tprint('tab')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.is_mixed
        assert indent_type.most_used == IndentType.space(4)

        # More tabs than spaces - should be mixed with tabs as most used
        code = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')\n    print('space')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.is_mixed
        assert indent_type.most_used == IndentType.tab()

        # Equal number of space and tab indents - should use spaces as most used since they have consistent size
        code = "def test():\n    print('hello')\n\tprint('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.is_mixed
        assert indent_type.most_used == IndentType.space(4)

        # Complex mixed indentation - more space indents than tabs
        code = """def test_function():
    # Level 1 (4 spaces)
    if condition:
\t\t# Level 2 (2 tabs)
\t\tfor item in items:
            # Level 3 (12 spaces)
            print(item)
    # Back to level 1
    return result"""
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.is_mixed
        assert indent_type.most_used == IndentType.space(
            4
        )  # More lines use 4-space indentation

    def test_detect_indent_type_consecutive_lines(self):
        """Test detecting indentation based on differences between consecutive lines."""
        # Code with varying indentation levels that should detect 2-space indents
        code = """def test_function():
  # Level 1 (2 spaces)
  if condition:
    # Level 2 (4 spaces)
    for item in items:
      # Level 3 (6 spaces)
      print(item)
  # Back to level 1
  return result"""
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type == IndentType.space(2)

        # Code with varying indentation levels that should detect 4-space indents
        code = """def test_function():
    # Level 1 (4 spaces)
    if condition:
        # Level 2 (8 spaces)
        for item in items:
            # Level 3 (12 spaces)
            print(item)
    # Back to level 1
    return result"""
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type == IndentType.space(4)

        # Code with tab indentation and varying levels
        code = """def test_function():
\t# Level 1 (1 tab)
\tif condition:
\t\t# Level 2 (2 tabs)
\t\tfor item in items:
\t\t\t# Level 3 (3 tabs)
\t\t\tprint(item)
\t# Back to level 1
\treturn result"""
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type == IndentType.tab(1)

    def test_detect_indent_type_edge_cases(self):
        """Test edge cases for indent detection."""
        # Empty string
        assert detect_indent_type("") is None

        # No indentation
        assert detect_indent_type("def test():\npass") is None

        # None input
        assert detect_indent_type(None) is None

        # Single line with indentation
        assert detect_indent_type("def test():\n    pass") == IndentType.space(4)

        # Code with only comments
        assert detect_indent_type("# This is a comment\n# Another comment") is None

        # Single space indentation (invalid and should not be detected)
        code = "def test():\n print('hello')\n print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type is None  # Single space is not a valid indentation pattern

        # Inconsistent space indentation (should use most common)
        code = "def test():\n   print('3 spaces')\n    print('4 spaces')\n   print('3 spaces again')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type == IndentType.space(3)

        # Tab with multiple spaces after (should be mixed with tab as most used)
        code = "def test():\n\t    print('tab + spaces')\n\t    print('same')"
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type.is_mixed
        assert indent_type.most_used == IndentType.tab()

        # Code with only blank lines
        assert detect_indent_type("\n\n\n") is None

        # Code with only whitespace lines
        assert detect_indent_type("   \n    \n  ") is None

        # Regular space indentation
        code = "def test():\n  print('hello')"  # regular spaces
        indent_type = detect_indent_type(code)
        assert indent_type is not None
        assert indent_type == IndentType.space(2)  # Two spaces

        # Code with tabs and spaces on same line but tabs first
        code = "def test():\n\t  print('mixed')"
        indent_type = detect_indent_type(code)
        assert indent_type.is_mixed  # pyright: ignore[reportOptionalMemberAccess]
        assert (
            indent_type.most_used == IndentType.tab()  # pyright: ignore[reportOptionalMemberAccess]
        )  # Tab should be most used since it's the primary indent

        # Code with only one indented line but multiple levels
        code = "def test():\n        print('deep')"
        indent_type = detect_indent_type(code)
        assert indent_type == IndentType.space(8)

        # Code with carriage returns and newlines
        code = "def test():\r\n    print('hello')\r\n    print('world')"
        indent_type = detect_indent_type(code)
        assert indent_type == IndentType.space(4)

        # Code with extremely large indentation
        code = "def test():\n" + (" " * 16) + "print('very deep')"
        indent_type = detect_indent_type(code)
        assert indent_type == IndentType.space(16)

    def test_normalize_indent(self):
        """Test normalizing indentation to 4 spaces."""
        # 2-space indentation
        code = "def test():\n  print('hello')\n  if True:\n    print('world')"
        indent_type = IndentType.space(2)
        normalized = normalize_indent(code, indent_type)
        expected = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert normalized == expected

        # Tab indentation
        code = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')"
        indent_type = IndentType.tab(1)
        normalized = normalize_indent(code, indent_type)
        expected = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert normalized == expected

        # 3-space indentation (non-standard)
        code = "def test():\n   print('hello')\n   if True:\n      print('world')"
        indent_type = IndentType.space(3)
        normalized = normalize_indent(code, indent_type)
        expected = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert normalized == expected

        # 8-space indentation (large)
        code = "def test():\n        print('hello')\n        if True:\n                print('world')"
        indent_type = IndentType.space(8)
        normalized = normalize_indent(code, indent_type)
        expected = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert normalized == expected

        # Code with irregular indentation but consistent pattern
        code = "def test():\n  print('hello')\n  if True:\n    print('world')\n      print('extra indent')"
        indent_type = IndentType.space(2)
        normalized = normalize_indent(code, indent_type)
        expected = "def test():\n    print('hello')\n    if True:\n        print('world')\n            print('extra indent')"
        assert normalized == expected

    def test_normalize_indent_edge_cases(self):
        """Test edge cases for normalize_indent."""
        # Empty string
        assert normalize_indent("", IndentType.space(2)) == ""

        # None input
        assert normalize_indent(None, IndentType.space(2)) is None

        # No indentation
        code = "def test():\npass"
        assert normalize_indent(code, IndentType.space(2)) == code

        # Single line with indentation
        code = "def test():\n  pass"
        assert normalize_indent(code, IndentType.space(2)) == "def test():\n    pass"

        # Code with blank lines between indented lines
        code = "def test():\n  line1\n\n  line2"
        assert (
            normalize_indent(code, IndentType.space(2))
            == "def test():\n    line1\n\n    line2"
        )

        # Code with comments and string literals containing indentation
        code = "def test():\n  # Comment\n  print('    indented string')"
        expected = "def test():\n    # Comment\n    print('    indented string')"
        assert normalize_indent(code, IndentType.space(2)) == expected

        # Code with mixed indentation should raise an exception
        code = "def test():\n  line1\n\tline2"
        with pytest.raises(AssertionError):
            normalize_indent(code, IndentType.space(2))

        # Single space indentation
        code = "def test():\n print('one space')\n  print('two spaces')"
        indent_type = IndentType.space(1)
        normalized = normalize_indent(code, indent_type)
        expected = "def test():\n    print('one space')\n        print('two spaces')"
        assert normalized == expected

        # Tab with single space after (should preserve the space)
        code = "def test():\n\t print('tab + space')"
        indent_type = IndentType.tab(1)
        normalized = normalize_indent(code, indent_type)
        expected = "def test():\n     print('tab + space')"  # 4 spaces + 1 extra space
        assert normalized == expected

        # Multiple tabs with single space after (remainder < 2 limitation)
        code = "def test():\n\t\t print('deep')"  # 2 tabs + 1 space
        indent_type = IndentType.tab(1)
        normalized = normalize_indent(code, indent_type)
        expected = (
            "def test():\n         print('deep')"  # 8 spaces (2 tabs * 4) + 1 space
        )
        assert normalized == expected

        # Spaces with tab size indentation
        code = "def test():\n   print('3 spaces')"  # 3 spaces
        indent_type = IndentType.space(3)
        normalized = normalize_indent(code, indent_type)
        expected = "def test():\n    print('3 spaces')"  # Normalized to 4 spaces
        assert normalized == expected

    def test_apply_indent_type(self):
        """Test applying different indent types to normalized code."""
        # Normalized code (4 spaces)
        code = "def test():\n    print('hello')\n    if True:\n        print('world')"

        # Apply 2-space indentation with auto-detection
        indent_type = IndentType.space(2)
        modified = apply_indent_type(code, indent_type)
        expected = "def test():\n  print('hello')\n  if True:\n    print('world')"
        assert modified == expected

        # Apply tab indentation with explicit original type
        indent_type = IndentType.tab(1)
        original_type = IndentType.space(4)
        modified = apply_indent_type(code, indent_type, original_type)
        expected = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')"
        assert modified == expected

        # Apply 3-space indentation with auto-detection
        indent_type = IndentType.space(3)
        modified = apply_indent_type(code, indent_type)
        expected = "def test():\n   print('hello')\n   if True:\n      print('world')"
        assert modified == expected

        # Apply 8-space indentation with explicit original type
        indent_type = IndentType.space(8)
        original_type = IndentType.space(4)
        modified = apply_indent_type(code, indent_type, original_type)
        expected = "def test():\n        print('hello')\n        if True:\n                print('world')"
        assert modified == expected

        # Code with multiple indentation levels
        code = "def test():\n    print('hello')\n    if True:\n        print('world')\n        for i in range(10):\n            print(i)"

        # Apply 2-space indentation with auto-detection
        indent_type = IndentType.space(2)
        modified = apply_indent_type(code, indent_type)
        expected = "def test():\n  print('hello')\n  if True:\n    print('world')\n    for i in range(10):\n      print(i)"
        assert modified == expected

        # Test with same indent type returns original code
        code_2space = "def test():\n  print('hello')"
        modified = apply_indent_type(
            code_2space, IndentType.space(2), IndentType.space(2)
        )
        assert modified == code_2space

        # Test with mixed original type returns original code
        code_mixed = "def test():\n    print('hello')\n\tprint('world')"
        modified = apply_indent_type(code_mixed, IndentType.space(2))
        assert modified == code_mixed  # Should return original since it's mixed

    def test_apply_indent_type_edge_cases(self):
        """Test edge cases for apply_indent_type."""
        # Empty string
        assert apply_indent_type("", IndentType.space(2)) == ""
        assert apply_indent_type("", IndentType.space(2), IndentType.space(4)) == ""

        # None input
        assert apply_indent_type(None, IndentType.space(2)) is None
        assert apply_indent_type(None, IndentType.space(2), IndentType.space(4)) is None

        # No indentation
        code = "def test():\npass"
        assert apply_indent_type(code, IndentType.space(2)) == code
        assert apply_indent_type(code, IndentType.space(2), IndentType.space(4)) == code

        # Already 4 spaces (no change needed)
        code = "def test():\n    print('hello')"
        assert apply_indent_type(code, IndentType.space(4)) == code
        assert apply_indent_type(code, IndentType.space(4), IndentType.space(4)) == code

        # Code with blank lines between indented lines
        code = "def test():\n    line1\n\n    line2"
        expected = "def test():\n  line1\n\n  line2"
        assert apply_indent_type(code, IndentType.space(2)) == expected
        assert (
            apply_indent_type(code, IndentType.space(2), IndentType.space(4))
            == expected
        )

        # Code with comments and string literals containing indentation
        code = "def test():\n    # Comment\n    print('    indented string')"
        expected = "def test():\n  # Comment\n  print('    indented string')"
        assert apply_indent_type(code, IndentType.space(2)) == expected
        assert (
            apply_indent_type(code, IndentType.space(2), IndentType.space(4))
            == expected
        )

        # Code with very deep indentation
        code = "def test():\n    if True:\n        if True:\n            if True:\n                print('deep')"
        expected = "def test():\n\tif True:\n\t\tif True:\n\t\t\tif True:\n\t\t\t\tprint('deep')"
        assert apply_indent_type(code, IndentType.tab(1)) == expected
        assert (
            apply_indent_type(code, IndentType.tab(1), IndentType.space(4)) == expected
        )

        # Code with single space remainder
        code = "def test():\n    line1\n     extra_space"
        expected = "def test():\n  line1\n   extra_space"
        assert apply_indent_type(code, IndentType.space(2)) == expected
        assert (
            apply_indent_type(code, IndentType.space(2), IndentType.space(4))
            == expected
        )

        # Mixed indentation with tabs and spaces (should return original code)
        code = "def test():\n    line1\n\tline2"
        assert apply_indent_type(code, IndentType.space(2)) == code

        # Mixed indentation with tabs and spaces (should raise error with mixed type)
        with pytest.raises(AssertionError):
            apply_indent_type(code, IndentType.mixed())

        # Invalid original_indent_type (mixed)
        with pytest.raises(AssertionError):
            apply_indent_type(code, IndentType.space(2), IndentType.mixed())

        # Test with None original_indent_type (should auto-detect)
        code = "def test():\n    print('hello')"
        expected = "def test():\n\tprint('hello')"
        assert apply_indent_type(code, IndentType.tab(1), None) == expected

    def test_force_normalize_indent(self):
        """Test force_normalize_indent function."""
        # Empty string
        assert force_normalize_indent("") == ""

        # No indentation
        code = "def test():\npass"
        assert force_normalize_indent(code) == code

        # Tab indentation
        code = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')"
        expected = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert force_normalize_indent(code) == expected

        # Mixed indentation
        code = "def test():\n    print('hello')\n\tprint('world')"
        expected = "def test():\n    print('hello')\n    print('world')"
        assert force_normalize_indent(code) == expected

        # Multiple levels of tabs
        code = "def test():\n\tif True:\n\t\tif True:\n\t\t\tprint('deep')"
        expected = (
            "def test():\n    if True:\n        if True:\n            print('deep')"
        )
        assert force_normalize_indent(code) == expected

        # Empty lines
        code = "def test():\n\n\tprint('hello')\n\n\tprint('world')"
        expected = "def test():\n\n    print('hello')\n\n    print('world')"
        assert force_normalize_indent(code) == expected

        # Tabs with spaces after (spaces are preserved)
        code = "def test():\n\t  print('mixed')\n\t  print('indent')"
        expected = "def test():\n      print('mixed')\n      print('indent')"  # 4 spaces from tab + 2 original spaces
        assert force_normalize_indent(code) == expected

        # Already using 4 spaces
        code = "def test():\n    print('hello')\n    print('world')"
        assert force_normalize_indent(code) == code

    def test_end_to_end(self):
        """Test the full workflow: detect, normalize, and apply."""
        # Original code with 2-space indentation
        original = "def test():\n  print('hello')\n  if True:\n    print('world')"

        # Detect the indent type
        indent_type = detect_indent_type(original)
        assert indent_type is not None
        assert indent_type == IndentType.space(2)

        # Normalize to 4 spaces
        normalized = normalize_indent(original, indent_type)
        expected_normalized = (
            "def test():\n    print('hello')\n    if True:\n        print('world')"
        )
        assert normalized == expected_normalized

        # Apply tab indentation with auto-detection
        target_indent = IndentType.tab(1)
        final = apply_indent_type(normalized, target_indent)
        expected_final = "def test():\n\tprint('hello')\n\tif True:\n\t\tprint('world')"
        assert final == expected_final

        # Apply tab indentation with explicit original type
        final_explicit = apply_indent_type(
            normalized, target_indent, IndentType.space(4)
        )
        assert final_explicit == expected_final

        # Direct conversion from 2-space to tab
        final_direct = apply_indent_type(original, target_indent, indent_type)
        assert final_direct == expected_final

    def test_end_to_end_complex(self):
        """Test the full workflow with more complex code examples."""
        # Original code with tab indentation and multiple levels
        original = """def complex_function():
\tresult = []
\tfor i in range(10):
\t\tif i % 2 == 0:
\t\t\tresult.append(i)
\t\t\tfor j in range(i):
\t\t\t\tresult.append(j)
\treturn result"""

        # Detect the indent type
        indent_type = detect_indent_type(original)
        assert indent_type is not None
        assert indent_type == IndentType.tab(1)

        # Verify line-by-line indentation detection
        lines = original.splitlines()
        assert detect_line_indent(lines[1]) == (1, 0)  # \t
        assert detect_line_indent(lines[3]) == (2, 0)  # \t\t
        assert detect_line_indent(lines[4]) == (3, 0)  # \t\t\t

        # Normalize to 4 spaces
        normalized = normalize_indent(original, indent_type)
        expected_normalized = """def complex_function():
    result = []
    for i in range(10):
        if i % 2 == 0:
            result.append(i)
            for j in range(i):
                result.append(j)
    return result"""
        assert normalized == expected_normalized

        # Apply 2-space indentation with auto-detection
        target_indent = IndentType.space(2)
        final = apply_indent_type(normalized, target_indent)
        expected_final = """def complex_function():
  result = []
  for i in range(10):
    if i % 2 == 0:
      result.append(i)
      for j in range(i):
        result.append(j)
  return result"""
        assert final == expected_final

        # Apply 2-space indentation with explicit original type
        final_explicit = apply_indent_type(
            normalized, target_indent, IndentType.space(4)
        )
        assert final_explicit == expected_final

        # Direct conversion from tabs to 2 spaces
        final_direct = apply_indent_type(original, target_indent, indent_type)
        assert final_direct == expected_final

        # Test with mixed indentation
        mixed_code = """def mixed_function():
    result = []
\tfor i in range(10):
\t\tif i % 2 == 0:
            result.append(i)
\treturn result"""
        mixed_type = detect_indent_type(mixed_code)
        assert mixed_type.is_mixed  # pyright: ignore[reportOptionalMemberAccess]
        assert (
            mixed_type.most_used == IndentType.tab()  # pyright: ignore[reportOptionalMemberAccess]
        )  # More tab-indented lines (3 vs 2)

        # Applying new indent to mixed code should return original
        assert apply_indent_type(mixed_code, target_indent) == mixed_code

    def test_end_to_end_with_comments_and_blank_lines(self):
        """Test the full workflow with code containing comments and blank lines."""
        # Original code with 3-space indentation, comments and blank lines
        original = """def process_data(data):
   # Initialize result
   result = {}

   # Process each item
   for item in data:
      # Skip empty items
      if not item:
         continue

      # Process valid items
      key, value = item.split(':')
      result[key.strip()] = value.strip()

   return result"""

        # Detect the indent type
        indent_type = detect_indent_type(original)
        assert indent_type is not None
        assert indent_type == IndentType.space(3)

        # Normalize to 4 spaces
        normalized = normalize_indent(original, indent_type)
        expected_normalized = """def process_data(data):
    # Initialize result
    result = {}

    # Process each item
    for item in data:
        # Skip empty items
        if not item:
            continue

        # Process valid items
        key, value = item.split(':')
        result[key.strip()] = value.strip()

    return result"""
        assert normalized == expected_normalized

        # Apply tab indentation
        target_indent = IndentType.tab(1)
        final = apply_indent_type(normalized, target_indent)
        expected_final = """def process_data(data):
\t# Initialize result
\tresult = {}

\t# Process each item
\tfor item in data:
\t\t# Skip empty items
\t\tif not item:
\t\t\tcontinue

\t\t# Process valid items
\t\tkey, value = item.split(':')
\t\tresult[key.strip()] = value.strip()

\treturn result"""
        assert final == expected_final

    def test_indenttype_properties(self):
        """Test IndentType class properties and methods."""
        # Test space indentation
        space_indent = IndentType.space(2)
        assert space_indent.size == 2
        assert not space_indent.is_tab
        assert not space_indent.is_mixed
        assert space_indent.is_space

        # Test tab indentation
        tab_indent = IndentType.tab()
        assert tab_indent.size == 1
        assert tab_indent.is_tab
        assert not tab_indent.is_mixed
        assert not tab_indent.is_space

        # Test mixed indentation without most_used
        mixed_indent = IndentType.mixed()
        assert mixed_indent.is_mixed
        assert not mixed_indent.is_tab
        assert not mixed_indent.is_space
        assert mixed_indent.size == 1  # Mixed type always has size 1
        assert mixed_indent.most_used is None

        # Test mixed indentation with space as most_used
        mixed_space = IndentType.mixed(most_used=IndentType.space(4))
        assert mixed_space.is_mixed
        assert mixed_space.most_used == IndentType.space(4)
        assert mixed_space.most_used.size == 4  # pyright: ignore[reportOptionalMemberAccess]

        # Test mixed indentation with tab as most_used
        mixed_tab = IndentType.mixed(most_used=IndentType.tab())
        assert mixed_tab.is_mixed
        assert mixed_tab.most_used == IndentType.tab()
        assert mixed_tab.most_used.size == 1  # pyright: ignore[reportOptionalMemberAccess]

        # Test equality
        assert IndentType.space(4) == IndentType.space(4)
        assert IndentType.tab() == IndentType.tab()
        assert IndentType.mixed() == IndentType.mixed()
        assert IndentType.mixed(most_used=IndentType.space(4)) == IndentType.mixed(
            most_used=IndentType.space(4)
        )
        assert IndentType.mixed(most_used=IndentType.tab()) == IndentType.mixed(
            most_used=IndentType.tab()
        )

        # Test inequality
        assert IndentType.space(2) != IndentType.space(4)
        assert IndentType.space(4) != IndentType.tab()
        assert IndentType.mixed() != IndentType.tab()
        assert IndentType.mixed() != IndentType.space(4)
        assert IndentType.mixed(most_used=IndentType.space(4)) != IndentType.mixed()
        assert IndentType.mixed(most_used=IndentType.space(4)) != IndentType.mixed(
            most_used=IndentType.tab()
        )
        assert IndentType.mixed(most_used=IndentType.space(2)) != IndentType.mixed(
            most_used=IndentType.space(4)
        )

        # Test string representation
        assert str(IndentType.space(4)) == "IndentType(space, size=4)"
        assert str(IndentType.tab()) == "IndentType(tab)"
        assert str(IndentType.mixed()) == "IndentType(mixed)"
        assert (
            str(IndentType.mixed(most_used=IndentType.space(4)))
            == "IndentType(mixed, most_used=IndentType(space, size=4))"
        )
        assert (
            str(IndentType.mixed(most_used=IndentType.tab()))
            == "IndentType(mixed, most_used=IndentType(tab))"
        )

        # Test with non-standard sizes
        large_space = IndentType.space(16)
        assert large_space.size == 16
        assert large_space.is_space
        assert not large_space.is_tab
        assert not large_space.is_mixed

        # Test equality with different instances
        space4_a = IndentType.space(4)
        space4_b = IndentType.space(4)
        assert space4_a == space4_b
        assert hash(space4_a) == hash(space4_b)  # Should have same hash if equal

        # Test inequality
        assert IndentType.space(2) != IndentType.tab()
        assert IndentType.tab() != IndentType.mixed()
        assert IndentType.space(8) != IndentType.space(4)

        # Test identity
        assert IndentType.mixed() is not IndentType.mixed()  # Different instances
        assert IndentType.space(4) is not IndentType.space(4)  # Different instances
