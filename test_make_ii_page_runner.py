"""
Test runner for make_ii_page module.
"""

import unittest
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import the test module
from make_ii_page.test_make_ii_page import TestMakeIIPage

if __name__ == "__main__":
    unittest.main()