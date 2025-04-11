import unittest
from unittest.mock import patch, MagicMock
from tools.visit_webpage import VisitWebpageTool


class TestVisitWebpageTool(unittest.TestCase):
    def setUp(self):
        self.tool = VisitWebpageTool(max_output_length=1000)

    @patch('tools.visit_webpage.requests.get')
    @patch('tools.visit_webpage.markdownify')
    def test_successful_webpage_visit(self, mock_markdownify, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Test Page</h1><p>Test content</p></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Setup markdownify to return a formatted string
        mock_markdownify.return_value = "# Test Page\n\nTest content"
        
        # Call the tool
        result = self.tool.run_impl({"url": "https://example.com"})
        
        # Verify the result
        self.assertEqual(result, "# Test Page\n\nTest content")
        
        # Verify the mocks were called correctly
        mock_get.assert_called_once_with("https://example.com", timeout=20)
        mock_markdownify.assert_called_once_with("<html><body><h1>Test Page</h1><p>Test content</p></body></html>")

    @patch('tools.visit_webpage.requests.get')
    def test_timeout_error(self, mock_get):
        # Setup mock to raise a timeout exception
        mock_get.side_effect = TimeoutError("Request timed out")
        
        # Call the tool
        result = self.tool.run_impl({"url": "https://example.com"})
        
        # Verify the result
        self.assertEqual(result, "The request timed out. Please try again later or check the URL.")

    @patch('tools.visit_webpage.requests.get')
    def test_request_exception(self, mock_get):
        # Setup mock to raise a request exception
        mock_get.side_effect = Exception("Connection error")
        
        # Call the tool
        result = self.tool.run_impl({"url": "https://example.com"})
        
        # Verify the result
        self.assertEqual(result, "An unexpected error occurred: Connection error")

    @patch('tools.visit_webpage.requests.get')
    def test_http_error(self, mock_get):
        # Setup mock to raise an HTTP error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response
        
        # Call the tool
        result = self.tool.run_impl({"url": "https://example.com"})
        
        # Verify the result
        self.assertEqual(result, "Error fetching the webpage: 404 Not Found")

    @patch('tools.visit_webpage.importlib.import_module')
    def test_missing_dependencies(self, mock_import):
        # Setup mock to raise an import error
        mock_import.side_effect = ImportError("No module named 'requests'")
        
        # Create a new tool instance to trigger the import error
        with self.assertRaises(ImportError) as context:
            VisitWebpageTool()
        
        # Verify the error message
        self.assertIn("You must install packages `markdownify` and `requests`", str(context.exception))

    @patch('tools.visit_webpage.requests.get')
    @patch('tools.visit_webpage.markdownify')
    def test_content_truncation(self, mock_markdownify, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.text = "<html><body><h1>Test Page</h1><p>Test content</p></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        # Setup markdownify to return a long string
        long_content = "# Test Page\n\n" + "Test content\n" * 1000
        mock_markdownify.return_value = long_content
        
        # Create a tool with a small max_output_length
        tool = VisitWebpageTool(max_output_length=100)
        
        # Call the tool
        result = tool.run_impl({"url": "https://example.com"})
        
        # Verify the result is truncated
        self.assertLess(len(result), len(long_content))
        self.assertIn("...", result)  # Check for truncation indicator


if __name__ == '__main__':
    unittest.main() 