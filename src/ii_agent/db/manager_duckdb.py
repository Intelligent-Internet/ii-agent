"""DuckDB-specific database manager implementation."""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor

from .duckdb_init import get_duckdb_manager, DuckDBManager


def async_wrap(func):
    """Wrap synchronous DuckDB calls in asyncio.to_thread()."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.to_thread(func, *args, **kwargs)
    return wrapper


class DuckDBDatabaseManager:
    """DuckDB-specific database manager with async wrapper and thread pool."""

    def __init__(self, max_workers: int = 4):
        self.duckdb_manager = get_duckdb_manager()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="duckdb_pool"
        )
        self._loop = None

    def _execute_query_sync(self, query: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute a query and return results as list of dictionaries (sync)."""
        conn = self.duckdb_manager.get_connection()
        result = conn.execute(query, params or ())

        # Convert to list of dictionaries
        columns = [desc[0] for desc in result.description]
        rows = result.fetchall()

        return [dict(zip(columns, row)) for row in rows]

    def _execute_write_sync(self, query: str, params: Optional[tuple] = None):
        """Execute a write query (sync)."""
        conn = self.duckdb_manager.get_connection()
        conn.execute(query, params or ())

    def _get_loop(self):
        """Get or create event loop reference."""
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    async def execute_query(self, query: str, params: Optional[tuple] = None) -> List[Dict]:
        """Execute a query and return results as list of dictionaries."""
        loop = self._get_loop()
        return await loop.run_in_executor(
            self._executor,
            self._execute_query_sync,
            query,
            params
        )

    async def execute_write(self, query: str, params: Optional[tuple] = None):
        """Execute a write query."""
        loop = self._get_loop()
        await loop.run_in_executor(
            self._executor,
            self._execute_write_sync,
            query,
            params
        )

    # Users operations
    async def create_user(self, user_id: str, email: str) -> Dict:
        """Create a new user."""
        query = """
            INSERT INTO users (id, email, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (user_id, email))
        return result[0] if result else None

    async def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user by ID."""
        query = "SELECT * FROM users WHERE id = ?"
        result = await self.execute_query(query, (user_id,))
        return result[0] if result else None

    async def update_user_credits(self, user_id: str, credits: int, bonus_credits: int = None) -> bool:
        """Update user credits."""
        if bonus_credits is not None:
            query = """
                UPDATE users
                SET credits = ?, bonus_credits = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (credits, bonus_credits, user_id)
        else:
            query = """
                UPDATE users
                SET credits = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            params = (credits, user_id)

        await self.execute_write(query, params)
        return True

    # Sessions operations
    async def create_session(self, session_id: str, user_id: str, title: str = None) -> Dict:
        """Create a new session."""
        query = """
            INSERT INTO sessions (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (session_id, user_id, title))
        return result[0] if result else None

    async def get_session(self, session_id: str) -> Optional[Dict]:
        """Get session by ID."""
        query = "SELECT * FROM sessions WHERE id = ?"
        result = await self.execute_query(query, (session_id,))
        return result[0] if result else None

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's sessions."""
        query = """
            SELECT * FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """
        return await self.execute_query(query, (user_id, limit))

    # Chat messages operations
    async def create_chat_message(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        embedding: Optional[List[float]] = None
    ) -> Dict:
        """Create a new chat message."""
        query = """
            INSERT INTO chat_messages (id, session_id, role, content, embedding, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (
            message_id, session_id, role, content, embedding
        ))
        return result[0] if result else None

    async def get_chat_messages(
        self,
        session_id: str,
        limit: int = 100,
        role: Optional[str] = None
    ) -> List[Dict]:
        """Get chat messages for a session."""
        query = """
            SELECT * FROM chat_messages
            WHERE session_id = ?
        """
        params = [session_id]

        if role:
            query += " AND role = ?"
            params.append(role)

        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        return await self.execute_query(query, tuple(params))

    async def vector_search_messages(
        self,
        session_id: str,
        query_embedding: List[float],
        limit: int = 10,
        role_filter: Optional[str] = None
    ) -> List[Dict]:
        """Search chat messages using vector similarity."""
        def _search():
            where_clause = f"session_id = '{session_id}'"
            if role_filter:
                where_clause += f" AND role = '{role_filter}'"

            return self.duckdb_manager.vector_search(
                query_embedding=query_embedding,
                table="chat_messages",
                where_clause=where_clause,
                limit=limit
            )

        loop = self._get_loop()
        return await loop.run_in_executor(self._executor, _search)

    # Files operations
    async def create_file(
        self,
        file_id: str,
        session_id: str,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str
    ) -> Dict:
        """Create a new file record."""
        query = """
            INSERT INTO files (id, session_id, file_name, file_size, storage_path, content_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (
            file_id, session_id, file_name, file_size, storage_path, content_type
        ))
        return result[0] if result else None

    async def get_files_by_session(self, session_id: str) -> List[Dict]:
        """Get files for a session."""
        query = "SELECT * FROM files WHERE session_id = ? ORDER BY created_at DESC"
        return await self.execute_query(query, (session_id,))

    async def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file by ID."""
        query = "SELECT * FROM files WHERE id = ?"
        result = await self.execute_query(query, (file_id,))
        return result[0] if result else None

    # Vector stores operations
    async def create_vector_store(
        self,
        store_id: str,
        user_id: str,
        provider: str,
        vector_store_id: str,
        embedding_model: str
    ) -> Dict:
        """Create a new vector store record."""
        query = """
            INSERT INTO vector_stores (id, user_id, provider, vector_store_id, embedding_model, created_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (
            store_id, user_id, provider, vector_store_id, embedding_model
        ))
        return result[0] if result else None

    async def get_vector_stores_by_user(self, user_id: str) -> List[Dict]:
        """Get vector stores for a user."""
        query = "SELECT * FROM vector_stores WHERE user_id = ? ORDER BY created_at DESC"
        return await self.execute_query(query, (user_id,))

    # Projects operations
    async def create_project(
        self,
        project_id: str,
        user_id: str,
        session_id: str,
        name: str,
        description: Optional[str] = None,
        framework: Optional[str] = None
    ) -> Dict:
        """Create a new project."""
        query = """
            INSERT INTO projects (id, user_id, session_id, name, description, framework,
                                database_json, storage_json, secrets_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, '{}', '{}', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.execute_query(query, (
            project_id, user_id, session_id, name, description, framework
        ))
        return result[0] if result else None

    async def get_project(self, project_id: str) -> Optional[Dict]:
        """Get project by ID."""
        query = "SELECT * FROM projects WHERE id = ?"
        result = await self.execute_query(query, (project_id,))
        return result[0] if result else None

    async def get_user_projects(self, user_id: str, limit: int = 50) -> List[Dict]:
        """Get user's projects."""
        query = """
            SELECT * FROM projects
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """
        return await self.execute_query(query, (user_id, limit))

    async def update_project_json(
        self,
        project_id: str,
        database_json: Optional[Dict] = None,
        storage_json: Optional[Dict] = None,
        secrets_json: Optional[Dict] = None
    ) -> bool:
        """Update project JSON fields."""
        updates = []
        params = []

        if database_json is not None:
            updates.append("database_json = ?")
            params.append(str(database_json))

        if storage_json is not None:
            updates.append("storage_json = ?")
            params.append(str(storage_json))

        if secrets_json is not None:
            updates.append("secrets_json = ?")
            params.append(str(secrets_json))

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"
            params.append(project_id)

            await self.execute_write(query, tuple(params))

        return True

    # Health check
    async def health_check(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            result = await self.execute_query("SELECT 1 as status")
            return {"status": "healthy", "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e), "timestamp": datetime.now().isoformat()}

    # Migration support
    async def run_migration(self, migration_sql: str):
        """Run a migration SQL script."""
        await self.execute_write(migration_sql)

    async def get_current_schema_version(self) -> Optional[int]:
        """Get current schema version."""
        try:
            result = await self.execute_query("""
                SELECT MAX(CAST(version AS INTEGER)) as max_version
                FROM (
                    SELECT CASE
                        WHEN sql LIKE '%version%' THEN
                            regexp_extract(sql, r'version[^\d]*(\d+)', 1)
                        ELSE '0'
                    END as version
                    FROM sqlite_master
                    WHERE sql IS NOT NULL
                )
            """)
            return result[0]['max_version'] if result else 0
        except Exception:
            return 0

    def shutdown(self):
        """Shutdown the thread pool executor."""
        if self._executor:
            self._executor.shutdown(wait=True)
            self._executor = None

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get thread pool statistics."""
        if self._executor:
            return {
                "max_workers": self._executor._max_workers,
                "pool_type": "ThreadPoolExecutor",
                "thread_name_prefix": "duckdb_pool"
            }
        return {"status": "shutdown"}

    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.shutdown()
        except:
            pass


# Global instance
_duckdb_db_manager: Optional[DuckDBDatabaseManager] = None


def get_duckdb_db_manager(max_workers: int = 4) -> DuckDBDatabaseManager:
    """Get the global DuckDB database manager."""
    global _duckdb_db_manager
    if _duckdb_db_manager is None:
        _duckdb_db_manager = DuckDBDatabaseManager(max_workers=max_workers)
    return _duckdb_db_manager


def shutdown_duckdb_manager():
    """Shutdown the global DuckDB manager and thread pool."""
    global _duckdb_db_manager
    if _duckdb_db_manager:
        _duckdb_db_manager.shutdown()
        _duckdb_db_manager = None