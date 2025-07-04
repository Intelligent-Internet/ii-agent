from typing import Any, Optional
from ii_agent.core.storage.models.settings import Settings
from ii_agent.tools.base import (
    ToolImplOutput,
    LLMTool,
)
from ii_agent.llm.message_history import MessageHistory
from ii_agent.tools.clients.database_client import get_database_client


class DatabaseConnection(LLMTool):
    """Tool for getting a database connection"""

    name = "get_database_connection"
    description = "Get a database connection"

    input_schema = {
        "type": "object",
        "properties": {
            "database_name": {
                "type": "string",
                "description": "Name of the database to connect to",
            },
            "database_type": {
                "type": "string",
                "description": "Type of the database to connect to",
                "enum": ["postgres", "redis", "mysql"],
            },
        },
        "required": ["database_name", "database_type"],
    }

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def _get_database_connection(self, database_name: str, database_type: str) -> str:
        database_client = get_database_client(database_type, self.settings)
        return database_client.get_database_connection()

    async def run_impl(
        self,
        tool_input: dict[str, Any],
        message_history: Optional[MessageHistory] = None,
    ) -> ToolImplOutput:
        connection_string = self._get_database_connection(
            tool_input["database_name"], tool_input["database_type"]
        )

        return ToolImplOutput(
            connection_string,
            f"Connection string: {connection_string}",
        )
