import unittest
from unittest.mock import patch, MagicMock
from tools.web_search import DuckDuckGoSearchTool


class TestDuckDuckGoSearchTool(unittest.TestCase):
    def setUp(self):
        self.tool = DuckDuckGoSearchTool(max_results=5)

    @patch('tools.web_search.DDGS')
    def test_successful_search(self, mock_ddgs_class):
        # Setup mock DDGS instance
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        
        # Setup mock search results
        mock_results = [
            {
                'title': 'Test Result 1',
                'href': 'https://example.com/1',
                'body': 'This is the first test result.'
            },
            {
                'title': 'Test Result 2',
                'href': 'https://example.com/2',
                'body': 'This is the second test result.'
            }
        ]
        mock_ddgs.text.return_value = mock_results
        
        # Call the tool
        result = self.tool.forward("test query")
        
        # Verify the result format
        expected_result = "## Search Results\n\n[Test Result 1](https://example.com/1)\nThis is the first test result.\n\n[Test Result 2](https://example.com/2)\nThis is the second test result."
        self.assertEqual(result, expected_result)
        
        # Verify the mock was called correctly
        mock_ddgs.text.assert_called_once_with("test query", max_results=5)

    @patch('tools.web_search.DDGS')
    def test_no_results(self, mock_ddgs_class):
        # Setup mock DDGS instance
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        
        # Setup mock to return empty results
        mock_ddgs.text.return_value = []
        
        # Call the tool and expect an exception
        with self.assertRaises(Exception) as context:
            self.tool.forward("test query")
        
        # Verify the error message
        self.assertIn("No results found", str(context.exception))

    @patch('tools.web_search.importlib.import_module')
    def test_missing_dependencies(self, mock_import):
        # Setup mock to raise an import error
        mock_import.side_effect = ImportError("No module named 'duckduckgo_search'")
        
        # Create a new tool instance to trigger the import error
        with self.assertRaises(ImportError) as context:
            DuckDuckGoSearchTool()
        
        # Verify the error message
        self.assertIn("You must install package `duckduckgo_search`", str(context.exception))

    @patch('tools.web_search.DDGS')
    def test_custom_max_results(self, mock_ddgs_class):
        # Setup mock DDGS instance
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        
        # Setup mock search results
        mock_results = [
            {
                'title': 'Test Result',
                'href': 'https://example.com',
                'body': 'This is a test result.'
            }
        ]
        mock_ddgs.text.return_value = mock_results
        
        # Create a tool with custom max_results
        tool = DuckDuckGoSearchTool(max_results=1)
        
        # Call the tool
        result = tool.forward("test query")
        
        # Verify the result
        self.assertIn("Test Result", result)
        
        # Verify the mock was called with the correct max_results
        mock_ddgs.text.assert_called_once_with("test query", max_results=1)

    @patch('tools.web_search.DDGS')
    def test_ddgs_kwargs(self, mock_ddgs_class):
        # Setup mock DDGS instance
        mock_ddgs = MagicMock()
        mock_ddgs_class.return_value = mock_ddgs
        
        # Setup mock search results
        mock_results = [
            {
                'title': 'Test Result',
                'href': 'https://example.com',
                'body': 'This is a test result.'
            }
        ]
        mock_ddgs.text.return_value = mock_results
        
        # Create a tool with custom kwargs
        tool = DuckDuckGoSearchTool(region='wt-wt', safesearch='on')
        
        # Call the tool
        result = tool.forward("test query")
        
        # Verify the result
        self.assertIn("Test Result", result)
        
        # Verify the DDGS was initialized with the correct kwargs
        mock_ddgs_class.assert_called_once_with(region='wt-wt', safesearch='on')


if __name__ == '__main__':
    unittest.main() 