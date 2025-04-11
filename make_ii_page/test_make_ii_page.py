"""
Tests for the make_ii_page module.
"""

import os
import tempfile
import unittest
from pathlib import Path

from .make_ii_page import make_ii_page, save_ii_page
from .exceptions import MDXFileNotFoundError, MDXParsingError


class TestMakeIIPage(unittest.TestCase):
    """Test cases for make_ii_page functionality."""

    def setUp(self):
        """Set up test fixtures."""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        
        # Create a sample MDX file
        self.sample_mdx_path = os.path.join(self.temp_dir.name, "sample.mdx")
        with open(self.sample_mdx_path, "w", encoding="utf-8") as f:
            f.write("""---
title: Sample MDX File
description: A sample MDX file for testing
author: Test Author
date: 2023-01-01
---

# Sample MDX Content

This is a sample MDX file with some **bold** and *italic* text.

<CustomComponent prop="value">
  This is inside a custom component.
</CustomComponent>

## Section 2

More content here.
""")

    def tearDown(self):
        """Tear down test fixtures."""
        # Clean up temporary directory
        self.temp_dir.cleanup()

    def test_make_ii_page_basic(self):
        """Test basic functionality of make_ii_page."""
        # Call the function
        ii_page = make_ii_page(self.sample_mdx_path)
        
        # Check the result
        self.assertIsInstance(ii_page, dict)
        self.assertIn("metadata", ii_page)
        self.assertIn("content", ii_page)
        self.assertIn("source", ii_page)
        
        # Check metadata
        self.assertEqual(ii_page["metadata"]["title"], "Sample MDX File")
        self.assertEqual(ii_page["metadata"]["author"], "Test Author")
        
        # Check content
        self.assertIn("Sample MDX Content", ii_page["content"])
        
        # Check source
        self.assertEqual(ii_page["source"]["path"], self.sample_mdx_path)
        self.assertEqual(ii_page["source"]["type"], "mdx")

    def test_make_ii_page_file_not_found(self):
        """Test make_ii_page with a non-existent file."""
        with self.assertRaises(MDXFileNotFoundError):
            make_ii_page("/path/to/nonexistent/file.mdx")

    def test_save_ii_page(self):
        """Test saving an II Page to a file."""
        # Create an II Page
        ii_page = make_ii_page(self.sample_mdx_path)
        
        # Save it
        output_path = os.path.join(self.temp_dir.name, "output.ii.json")
        saved_path = save_ii_page(ii_page, output_path)
        
        # Check the result
        self.assertEqual(saved_path, output_path)
        self.assertTrue(os.path.exists(output_path))
        
        # Check default path generation
        default_path = save_ii_page(ii_page)
        self.assertTrue(os.path.exists(default_path))
        self.assertEqual(Path(default_path).suffix, ".json")


if __name__ == "__main__":
    unittest.main()