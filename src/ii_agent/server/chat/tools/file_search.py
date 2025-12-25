import json
import logging
from typing import List

from openai import AsyncOpenAI
from openai.types.shared_params.comparison_filter import ComparisonFilter
from openai.types.shared_params.compound_filter import CompoundFilter
from ii_agent.server.chat.models import ErrorTextContent, JsonResultContent
from ii_agent.server.llm_settings.service import get_system_llm_config

from .base import BaseTool, ToolInfo, ToolCallInput, ToolResponse

logger = logging.getLogger(__name__)


class FileSearchTool(BaseTool):
    """Execute Python code using OpenAI's Code Interpreter via Responses API."""

    def __init__(
        self,
        session_id: str,
        vector_store_id: str,
        user_id: str,
    ):
        self.llm_config = get_system_llm_config(model_id="default")
        self.vector_store_id = vector_store_id
        self.session_id = session_id
        self.user_id = user_id
        self._name = "file_search"

        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.llm_config.api_key.get_secret_value(),
            base_url=self.llm_config.base_url if self.llm_config.base_url else None,
        )

    @property
    def name(self) -> str:
        return self._name

    def info(self) -> ToolInfo:
        return ToolInfo(
            name=self._name,
            description=(
                "Search through uploaded documents and files to find relevant information, "
                "extract specific details, or answer questions based on file contents. "
                "Uses semantic search to understand context and meaning.\n\n"
                "Returns the top 3 most relevant results. If the initial results don't contain "
                "the information you need, call this tool again with a more specific or refined query.\n\n"
                "Supported file formats:\n"
                "- Documents: .pdf, .docx, .txt, .md, .rtf\n"
                "- Other: .tex, .pptx\n\n"
                "Use this for:\n"
                "- Finding specific information within documents\n"
                "- Answering questions about uploaded file contents\n"
                "- Extracting relevant passages or data points\n"
                "- Summarizing sections of documents\n"
                "- Comparing information across multiple files\n"
                "- Locating code snippets or functions\n"
                "- Cross-referencing details from different documents"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "A clear search query or question about the uploaded files. "
                            "Be specific about what information you're looking for. "
                            "Examples:\n"
                            "- 'What is the total revenue mentioned in the Q3 report?'\n"
                            "- 'Find all references to the authentication system'\n"
                            "- 'What are the key findings in the research paper?'\n"
                            "- 'List all API endpoints defined in the documentation'\n"
                            "- 'What does the contract say about termination clauses?'\n"
                            "- 'Find the implementation of the login function'\n"
                            "- 'Compare the pricing models mentioned in both documents'"
                        ),
                    },
                    "file_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional list of specific file names to search within. "
                            "Use this to narrow the search scope to particular files when you know "
                            "which documents contain the relevant information. "
                            "Examples:\n"
                            "- ['contract.pdf', 'amendment.pdf'] - Search in contract and its amendment\n"
                            "- ['api_docs.md'] - Search only in API documentation"
                        ),
                    },
                },
            },
            required=["query"],
        )

    def _build_filters(self, file_names: List[str] | None = None) -> ComparisonFilter | CompoundFilter:
        """Build filters for the file search request.

        Note: Vector stores are user-scoped (shared across sessions for deduplication),
        so we only filter by user_id, not session_id. Files may have been uploaded
        in a different session but should still be searchable.
        """
        # Only filter by user_id since vector store is user-scoped
        # Files uploaded in previous sessions should still be searchable
        user_filter: ComparisonFilter = {
            "type": "eq",
            "key": "user_id",
            "value": self.user_id,
        }

        if file_names:
            # If file names specified, use compound filter
            filters: list[ComparisonFilter] = [user_filter]
            for file_name in file_names:
                filters.append({
                    "type": "eq",
                    "key": "file_name",
                    "value": file_name,
                })
            logger.debug(f"Filters built with file_names: {filters}")
            return {
                "type": "and",
                "filters": filters,
            }

        logger.debug(f"Filter built: user_id={self.user_id}")
        return user_filter

    async def run(self, tool_call: ToolCallInput) -> ToolResponse:
        """Execute code using OpenAI Responses API with code interpreter."""
        try:
            params = json.loads(tool_call.input)
            query = params["query"]
            file_names = params.get("file_names")  # Optional parameter
        except (json.JSONDecodeError, KeyError) as e:
            return ToolResponse(
                output=ErrorTextContent(value=f"Invalid tool input: {e}")
            )

        try:
            # Get files from parent message
            filters = self._build_filters(file_names=file_names)
            response = await self.client.vector_stores.search(
                vector_store_id=self.vector_store_id,
                query=query,
                filters=filters,
                max_num_results=3,  # Limit to 3 results to prevent context overflow; LLM can refine query if needed
                ranking_options={"ranker": "auto"},
            )
            search_results = response.data
            if isinstance(search_results, list):
                results = [m.model_dump() for m in search_results]
            else:
                results = [search_results.model_dump()]

            return ToolResponse(output=JsonResultContent(value=results))

        except Exception as e:
            logger.error(f"Code interpreter error: {e}", exc_info=True)
            return ToolResponse(
                output=ErrorTextContent(value=f"File search failed: {str(e)}")
            )
