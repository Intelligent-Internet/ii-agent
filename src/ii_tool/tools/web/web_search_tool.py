"""WebSearch tool for performing web searches."""

from typing import Annotated, Optional, List
from pydantic import Field
from ii_tool.tools.base import BaseTool


DESCRIPTION = """
- Allows Claude to search the web and use the results to inform responses
- Provides up-to-date information for current events and recent data
- Returns search result information formatted as search result blocks
- Use this tool for accessing information beyond Claude's knowledge cutoff
- Searches are performed automatically within a single API call

Usage notes:
  - Domain filtering is supported to include or block specific websites
  - Web search is only available in the US
  - Account for \"Today's date\" in <env>
"""

class WebSearchTool(BaseTool):
    """Tool for searching the web with domain filtering capabilities."""
    
    name = "WebSearch"
    description = DESCRIPTION

    def run_impl(
        self,
        query: Annotated[str, Field(description="The search query to use")],
        allowed_domains: Annotated[Optional[List[str]], Field(description="Only include search results from these domains")],
        blocked_domains: Annotated[Optional[List[str]], Field(description="Never include search results from these domains")],
    ):
        return