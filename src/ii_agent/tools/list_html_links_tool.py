# src/ii_agent/tools/list_html_links_tool.py
import re
from pathlib import Path
from typing import Any, Optional, Set
from urllib.parse import urlparse

from ii_agent.llm.message_history import MessageHistory  # Or DialogMessages
from ii_agent.tools.base import LLMTool, ToolImplOutput
from ii_agent.utils import WorkspaceManager


class ListHtmlLinksTool(LLMTool):
    name = "list_html_links"
    description = (
        "Scans a specified HTML file (or all HTML files in a directory) "
        "and lists all unique local HTML file names linked within them. "
        "This helps verify which pages are being referenced."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "The relative path to an HTML file or a directory within the workspace to scan.",
            }
        },
        "required": ["path"],
    }

    def __init__(self, workspace_manager: WorkspaceManager):
        super().__init__()
        self.workspace_manager = workspace_manager

    def _extract_links_from_file(self, file_path: Path) -> Set[str]:
        links = set()
        if (
            not file_path.exists()
            or not file_path.is_file()
            or file_path.suffix.lower() != ".html"
        ):
            return links

        html_content = file_path.read_text(errors="ignore")
        # Basic regex, consider BeautifulSoup for robustness
        for match in re.finditer(
            r'<a\s+(?:[^>]*?\s+)?href="([^"]*)"', html_content, re.IGNORECASE
        ):
            href = match.group(1)
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue

            parsed_href = urlparse(href)
            if parsed_href.scheme or parsed_href.netloc:  # Skip absolute URLs
                continue

            # Consider only .html files or files without extensions (potential routes)
            if href.endswith(".html") or "." not in Path(href).name:
                # We only care about the filename for this simple tool
                links.add(Path(href).name)
        return links

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        relative_path_str = tool_input["path"]
        ws_path = self.workspace_manager.workspace_path(Path(relative_path_str))

        all_found_links = set()

        if not ws_path.exists():
            return ToolImplOutput(
                f"Error: Path not found: {relative_path_str}",
                f"Path not found: {relative_path_str}",
                {"success": False},
            )

        if ws_path.is_file():
            if ws_path.suffix.lower() == ".html":
                all_found_links.update(self._extract_links_from_file(ws_path))
            else:
                return ToolImplOutput(
                    f"Error: Specified path '{relative_path_str}' is not an HTML file.",
                    "Path is not HTML",
                    {"success": False},
                )
        elif ws_path.is_dir():
            for item in ws_path.rglob("*.html"):  # Recursively find all HTML files
                if item.is_file():
                    all_found_links.update(self._extract_links_from_file(item))
        else:
            return ToolImplOutput(
                f"Error: Path is neither a file nor a directory: {relative_path_str}",
                "Invalid path type",
                {"success": False},
            )

        if not all_found_links:
            return ToolImplOutput(
                f"No local HTML links found in '{relative_path_str}'.",
                "No links found.",
                {"success": True, "linked_files": []},
            )

        output_message = (
            f"Found the following unique local HTML file names linked from '{relative_path_str}': "
            f"{sorted(list(all_found_links))}. "
            "Please cross-reference this list with your planned files (e.g., in todo.md) and create any missing ones."
        )
        return ToolImplOutput(
            output_message,
            f"Link scan complete for {relative_path_str}.",
            {"success": True, "linked_files": sorted(list(all_found_links))},
        )
