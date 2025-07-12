"""FastAPI server for file system operations using FileSystemManager."""

import logging
from typing import Optional, List, Dict, Any, Annotated
from threading import Lock

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn




class TodoManager:
    """Manages the todo list state across productivity tools."""
    
    def __init__(self):
        self._todos: List[Dict[str, Any]] = []
        self._lock = Lock()
    
    def get_todos(self) -> List[Dict[str, Any]]:
        """Get the current list of todos."""
        with self._lock:
            return self._todos.copy()
    
    def set_todos(self, todos: List[Dict[str, Any]]) -> None:
        """Set the entire todo list."""
        # Validate todo structure
        for todo in todos:
            if not isinstance(todo, dict):
                raise ValueError("Each todo must be a dictionary")
            
            # Required fields
            if 'content' not in todo:
                raise ValueError("Each todo must have a 'content' field")
            if 'status' not in todo:
                raise ValueError("Each todo must have a 'status' field")
            if 'priority' not in todo:
                raise ValueError("Each todo must have a 'priority' field")
            if 'id' not in todo:
                raise ValueError("Each todo must have an 'id' field")
            
            # Validate status
            if todo['status'] not in ['pending', 'in_progress', 'completed']:
                raise ValueError(f"Invalid status '{todo['status']}'. Must be 'pending', 'in_progress', or 'completed'")
            
            # Validate priority
            if todo['priority'] not in ['high', 'medium', 'low']:
                raise ValueError(f"Invalid priority '{todo['priority']}'. Must be 'high', 'medium', or 'low'")
            
            # Ensure content is not empty
            if not todo['content'].strip():
                raise ValueError("Todo content cannot be empty")
        
        # Ensure only one task is in_progress
        in_progress_count = sum(1 for todo in todos if todo['status'] == 'in_progress')
        if in_progress_count > 1:
            raise ValueError("Only one task can be in_progress at a time")
        
        with self._lock:
            self._todos = [todo.copy() for todo in todos]
    
    def clear_todos(self) -> None:
        """Clear all todos."""
        with self._lock:
            self._todos = []


# Global instance to be shared across tools
_global_manager: TodoManager | None = None


def get_todo_manager() -> TodoManager:
    """Get the global todo manager instance."""
    global _global_manager
    if _global_manager is None:
        _global_manager = TodoManager()
    return _global_manager


class TodoReadTool:
    def run_impl(self):
        """Read and return the current todo list."""
        manager = get_todo_manager()
        todos = manager.get_todos()
        
        if not todos:
            return "No todos found"
        
        return f"Remember to continue to use update and read from the todo list as you make progress. Here is the current list: {todos}"


class TodoWriteTool:
    def run_impl(
        self,
        todos: Annotated[List[Dict[str, Any]], Field(description="The updated todo list. Each todo should have `content`, `status` (one of 'pending', 'in_progress', 'completed'), `priority` (one of 'low', 'medium', 'high'), and `id` (starts from 1) keys.")],
    ):
        """Write/update the todo list."""
        manager = get_todo_manager()
        
        try:
            # Set the new todo list (validation happens inside set_todos)
            manager.set_todos(todos)
            
            # Return the updated list
            return "Todos have been modified successfully. Ensure that you continue to use the todo list to track your progress. Please proceed with the current tasks if applicable"
        except ValueError as e:
            return f"Error updating todo list: {e}"

class TodoWriteSchema(BaseModel):
    todos: List[Dict[str, Any]]

class TodoServer:
    """FastAPI server for todo operations."""

    def __init__(
        self,
        allowed_origins: Optional[List[str]] = None,
    ):
        self.app = FastAPI(
            title="Todo Server",
            description="HTTP API for todo operations",
            version="1.0.0",
        )

        # Add CORS middleware
        if allowed_origins is None:
            allowed_origins = ["*"]

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Setup routes
        self._setup_routes()

        self.todo_read_tool = TodoReadTool()
        self.todo_write_tool = TodoWriteTool()

    def _setup_routes(self):
        """Setup all API routes."""

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return {"status": "ok", "message": "Todo Server is running"}

        @self.app.get("/todo_read")
        async def todo_read():
            """Read the current todo list."""
            return {"message": self.todo_read_tool.run_impl()}

        # Input a list of dictionaries
        @self.app.post("/todo_write")
        async def todo_write(todo_write_schema: TodoWriteSchema):
            """
            Update the todo list with a new list of todos.
            Expects a JSON body: a list of todo dicts, each with 'content', 'status', 'priority', and 'id'.
            """
            try:
                todos = todo_write_schema.todos
                if not isinstance(todos, list):
                    raise ValueError("Request body must be a list of todos")
                message = self.todo_write_tool.run_impl(todos)
                return {"message": message}
            except Exception as e:
                return JSONResponse(
                    status_code=400,
                    content={"error": f"Failed to update todos: {e}"},
                )


    def run(self, host: str = "0.0.0.0", port: int = 8002, **kwargs):
        """Run the FastAPI server."""
        uvicorn.run(self.app, host=host, port=port, **kwargs)


def create_app(
    allowed_origins: Optional[List[str]] = None,
) -> FastAPI:
    """Factory function to create the FastAPI app."""
    server = TodoServer(
        allowed_origins=allowed_origins,
    )
    return server.app


def main():
    """Main entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Todo Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8003, help="Port to bind to")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create and run server
    server = TodoServer()
    server.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()