"""
MDX Parser module.

This module provides functionality to parse MDX content, extracting frontmatter metadata
and the main content.
"""

import re
import yaml
from typing import Dict, Any, Tuple

from .exceptions import MDXParsingError


def parse_mdx_content(mdx_content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse MDX content to extract frontmatter metadata and main content.

    Args:
        mdx_content (str): The raw MDX content

    Returns:
        Tuple[Dict[str, Any], str]: A tuple containing the metadata dictionary and the main content

    Raises:
        MDXParsingError: If there's an error parsing the MDX content
    """
    try:
        # Check if the content has frontmatter (delimited by ---)
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n'
        frontmatter_match = re.search(frontmatter_pattern, mdx_content, re.DOTALL)

        if frontmatter_match:
            # Extract frontmatter and content
            frontmatter_text = frontmatter_match.group(1)
            content = mdx_content[frontmatter_match.end():]
            
            # Parse frontmatter as YAML
            try:
                metadata = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError as e:
                raise MDXParsingError(f"Error parsing frontmatter YAML: {str(e)}")
        else:
            # No frontmatter found
            metadata = {}
            content = mdx_content

        return metadata, content
    except Exception as e:
        if isinstance(e, MDXParsingError):
            raise
        raise MDXParsingError(f"Error parsing MDX content: {str(e)}")


def process_mdx_content(content: str) -> str:
    """
    Process MDX content to handle MDX-specific syntax.

    Args:
        content (str): The MDX content to process

    Returns:
        str: The processed content

    Note:
        This is a basic implementation. For a full MDX parser, consider using
        dedicated libraries like mdx-js.
    """
    # Process JSX components in MDX
    # This is a simplified implementation
    
    # Replace import statements
    content = re.sub(r'import\s+.*?\s+from\s+[\'"].*?[\'"];?\s*\n?', '', content)
    
    # Process basic JSX components (simplified)
    content = re.sub(r'<([A-Z][a-zA-Z]*)[^>]*>(.*?)</\1>', r'\2', content, flags=re.DOTALL)
    
    return content