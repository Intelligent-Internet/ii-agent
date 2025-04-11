"""
Make II Page from MDX file.

This module provides functionality to convert MDX files to II Pages.
"""

import os
import re
import json
import datetime
from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from .exceptions import MDXFileNotFoundError, MDXParsingError, IIPageCreationError
from .mdx_parser import parse_mdx_content


def make_ii_page(mdx_file_path: str) -> Dict[str, Any]:
    """
    Make a II Page from a local MDX file.

    Args:
        mdx_file_path (str): Absolute path of the source MDX file

    Returns:
        Dict[str, Any]: The processed II Page content with metadata

    Raises:
        MDXFileNotFoundError: If the MDX file does not exist
        MDXParsingError: If there's an error parsing the MDX content
        IIPageCreationError: If there's an error creating the II Page
    """
    # Validate file path
    if not os.path.isfile(mdx_file_path):
        raise MDXFileNotFoundError(f"MDX file not found: {mdx_file_path}")

    try:
        # Read MDX file content
        with open(mdx_file_path, 'r', encoding='utf-8') as file:
            mdx_content = file.read()

        # Parse MDX content
        metadata, content = parse_mdx_content(mdx_content)

        # Process content to create II Page
        ii_page = _process_to_ii_page(metadata, content, mdx_file_path)

        return ii_page
    except Exception as e:
        if isinstance(e, (MDXFileNotFoundError, MDXParsingError)):
            raise
        raise IIPageCreationError(f"Error creating II Page: {str(e)}")


def _process_to_ii_page(
    metadata: Dict[str, Any], 
    content: str, 
    source_path: str
) -> Dict[str, Any]:
    """
    Process parsed MDX content into an II Page format.

    Args:
        metadata (Dict[str, Any]): Metadata extracted from MDX frontmatter
        content (str): The main content of the MDX file
        source_path (str): The original MDX file path

    Returns:
        Dict[str, Any]: The processed II Page content with metadata
    """
    # Create a basic II Page structure
    ii_page = {
        "metadata": metadata,
        "content": content,
        "source": {
            "path": source_path,
            "type": "mdx",
            "lastModified": os.path.getmtime(source_path)
        }
    }

    # Add additional processing as needed for II Page format
    # This would depend on the specific requirements for II Pages

    return ii_page


def save_ii_page(ii_page: Dict[str, Any], output_path: Optional[str] = None) -> str:
    """
    Save the II Page to a file.

    Args:
        ii_page (Dict[str, Any]): The II Page content
        output_path (Optional[str]): Path to save the II Page. If None, a default path is generated.

    Returns:
        str: The path where the II Page was saved

    Raises:
        IIPageCreationError: If there's an error saving the II Page
    """
    if output_path is None:
        # Generate a default output path based on the source file
        source_path = ii_page.get("source", {}).get("path", "")
        if source_path:
            source_file = Path(source_path)
            output_path = str(source_file.with_suffix(".ii.json"))
        else:
            output_path = "output.ii.json"

    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        
        # Custom JSON encoder to handle dates and other complex types
        class CustomJSONEncoder(json.JSONEncoder):
            def default(self, obj):
                if isinstance(obj, (datetime.date, datetime.datetime)):
                    return obj.isoformat()
                return super().default(obj)
        
        # Save the II Page
        with open(output_path, 'w', encoding='utf-8') as file:
            json.dump(ii_page, file, indent=2, cls=CustomJSONEncoder)
        
        return output_path
    except Exception as e:
        raise IIPageCreationError(f"Error saving II Page: {str(e)}")