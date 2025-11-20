"""Async SQLite database manager with connection pooling and performance optimizations."""

import aiosqlite
import sqlite3
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime
from contextlib import asynccontextmanager
from dataclasses import dataclass

from ii_agent.core.config.ii_agent_config import config

logger = logging.getLogger(__name__)


@dataclass
class SQLiteConfig:
    """SQLite database configuration."""
    database_path: str
    enable_wal: bool = True
    enable_foreign_keys: bool = True
    journal_mode: str = "WAL"
    synchronous: str = "NORMAL"
    cache_size: int = 2000
    temp_store: str = "MEMORY"
    mmap_size: int = 268435456  # 256MB
    page_size: int = 4096
    connection_timeout: float = 30.0
    max_connections: int = 10
    busy_timeout: int = 30000  # 30 seconds


class AsyncSQLiteConnection:
    """Async SQLite connection wrapper with connection pooling."""

    def __init__(self, config: SQLiteConfig):
        self.config = config
        self._pool: asyncio.Queue[aiosqlite.Connection] = asyncio.Queue(maxsize=config.max_connections)
        self._created_connections = 0
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize connection pool."""
        # Create initial connection
        await self._create_connection()

        # Set up database schema and optimizations
        await self._setup_database()

    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new SQLite connection with optimizations."""
        conn = await aiosqlite.connect(
            self.config.database_path,
            timeout=self.config.connection_timeout
        )

        # Enable WAL mode for better concurrency
        if self.config.enable_wal:
            await conn.execute(f"PRAGMA journal_mode = {self.config.journal_mode}")

        # Enable foreign key constraints
        if self.config.enable_foreign_keys:
            await conn.execute("PRAGMA foreign_keys = ON")

        # Performance optimizations
        await conn.execute(f"PRAGMA synchronous = {self.config.synchronous}")
        await conn.execute(f"PRAGMA cache_size = {self.config.cache_size}")
        await conn.execute(f"PRAGMA temp_store = {self.config.temp_store}")
        await conn.execute(f"PRAGMA mmap_size = {self.config.mmap_size}")
        await conn.execute(f"PRAGMA page_size = {self.config.page_size}")
        await conn.execute(f"PRAGMA busy_timeout = {self.config.busy_timeout}")

        # Enable query planner optimizations
        await conn.execute("PRAGMA optimize")

        # Set row factory for dict-like access
        conn.row_factory = aiosqlite.Row

        return conn

    async def _setup_database(self):
        """Set up database schema and indexes."""
        async with self.get_connection() as conn:
            # Create tables if they don't exist
            await self._create_tables(conn)

            # Create indexes for performance
            await self._create_indexes(conn)

    async def _create_tables(self, conn: aiosqlite.Connection):
        """Create database tables."""
        # Users table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                credits INTEGER DEFAULT 0,
                bonus_credits INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Chat messages table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        # Files table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                storage_path TEXT,
                content_type TEXT,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        """)

        # Projects table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                session_id TEXT,
                name TEXT,
                description TEXT,
                status TEXT DEFAULT 'active',
                framework TEXT,
                database_json TEXT,
                storage_json TEXT,
                secrets_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deleted_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
            )
        """)

        # Project deployments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS project_deployments (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                snapshot_id TEXT,
                environment TEXT NOT NULL,
                deployment_status TEXT DEFAULT 'pending',
                is_active BOOLEAN DEFAULT FALSE,
                deployment_url TEXT,
                started_at TIMESTAMP,
                deployed_at TIMESTAMP,
                finished_at TIMESTAMP,
                deploy_duration_ms INTEGER,
                error_message TEXT,
                deployed_by_user_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (deployed_by_user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)

        # Vector stores table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_stores (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                vector_store_id TEXT NOT NULL,
                embedding_model TEXT,
                metadata TEXT,
                version INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                UNIQUE(user_id, provider, vector_store_id),
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        # Chat message embeddings for vector search
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS message_embeddings (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                embedding BLOB NOT NULL,
                embedding_model TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (message_id) REFERENCES chat_messages(id) ON DELETE CASCADE
            )
        """)

    async def _create_indexes(self, conn: aiosqlite.Connection):
        """Create performance indexes."""
        indexes = [
            # Users indexes
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",

            # Sessions indexes
            "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC)",

            # Chat messages indexes
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_chat_messages_role ON chat_messages(role)",

            # Files indexes
            "CREATE INDEX IF NOT EXISTS idx_files_session_id ON files(session_id)",
            "CREATE INDEX IF NOT EXISTS idx_files_created_at ON files(created_at)",

            # Projects indexes
            "CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)",
            "CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_projects_session_id ON projects(session_id)",

            # Project deployments indexes
            "CREATE INDEX IF NOT EXISTS idx_project_deployments_project_id ON project_deployments(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_project_deployments_environment ON project_deployments(environment)",
            "CREATE INDEX IF NOT EXISTS idx_project_deployments_status ON project_deployments(deployment_status)",

            # Vector stores indexes
            "CREATE INDEX IF NOT EXISTS idx_vector_stores_user_id ON vector_stores(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_vector_stores_provider ON vector_stores(provider)",
            "CREATE INDEX IF NOT EXISTS idx_vector_stores_expires_at ON vector_stores(expires_at)",

            # Message embeddings indexes
            "CREATE INDEX IF NOT EXISTS idx_message_embeddings_message_id ON message_embeddings(message_id)",
            "CREATE INDEX IF NOT EXISTS idx_message_embeddings_model ON message_embeddings(embedding_model)",
        ]

        for index_sql in indexes:
            await conn.execute(index_sql)

        # Run analyze to update query planner statistics
        await conn.execute("ANALYZE")

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[aiosqlite.Connection, None]:
        """Get a connection from the pool."""
        try:
            conn = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            async with self._lock:
                if self._created_connections < self.config.max_connections:
                    conn = await self._create_connection()
                    self._created_connections += 1
                else:
                    # Wait for a connection to become available
                    conn = await asyncio.wait_for(self._pool.get(), timeout=self.config.connection_timeout)

        try:
            yield conn
        finally:
            # Return connection to pool
            try:
                self._pool.put_nowait(conn)
            except asyncio.QueueFull:
                # Pool is full, close the connection
                await conn.close()
                self._created_connections -= 1

    async def close(self):
        """Close all connections in the pool."""
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            await conn.close()
        self._created_connections = 0

    async def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a SELECT query and return results."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_write(self, query: str, params: tuple = ()) -> int:
        """Execute a write query (INSERT, UPDATE, DELETE) and return rowcount."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params)
            await conn.commit()
            return cursor.rowcount

    async def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query multiple times with different parameters."""
        async with self.get_connection() as conn:
            cursor = await conn.executemany(query, params_list)
            await conn.commit()
            return cursor.rowcount

    async def execute_script(self, script: str):
        """Execute a SQL script."""
        async with self.get_connection() as conn:
            await conn.executescript(script)
            await conn.commit()


class AsyncSQLiteManager:
    """High-level async SQLite database manager."""

    def __init__(self, db_path: Optional[str] = None, config: Optional[SQLiteConfig] = None):
        if db_path is None:
            # Default to local file in config directory
            db_dir = Path.home() / ".ii_agent" / "data"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "ii_agent_async.db")

        self.db_path = db_path
        self.config = config or SQLiteConfig(database_path=db_path)
        self.connection: Optional[AsyncSQLiteConnection] = None

    async def initialize(self):
        """Initialize the database manager."""
        self.connection = AsyncSQLiteConnection(self.config)
        await self.connection.initialize()
        logger.info(f"Async SQLite database initialized: {self.db_path}")

    async def close(self):
        """Close the database manager."""
        if self.connection:
            await self.connection.close()
            self.connection = None
            logger.info("Async SQLite database closed")

    # User operations
    async def create_user(self, user_id: str, email: str) -> Dict[str, Any]:
        """Create a new user."""
        query = """
            INSERT INTO users (id, email, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.connection.execute_query(query, (user_id, email))
        return result[0] if result else None

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        query = "SELECT * FROM users WHERE id = ?"
        result = await self.connection.execute_query(query, (user_id,))
        return result[0] if result else None

    async def update_user_credits(self, user_id: str, credits: int, bonus_credits: Optional[int] = None) -> bool:
        """Update user credits."""
        if bonus_credits is not None:
            query = """
                UPDATE users
                SET credits = ?, bonus_credits = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            await self.connection.execute_write(query, (credits, bonus_credits, user_id))
        else:
            query = """
                UPDATE users
                SET credits = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """
            await self.connection.execute_write(query, (credits, user_id))
        return True

    # Session operations
    async def create_session(self, session_id: str, user_id: str, title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new session."""
        query = """
            INSERT INTO sessions (id, user_id, title, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.connection.execute_query(query, (session_id, user_id, title))
        return result[0] if result else None

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        query = "SELECT * FROM sessions WHERE id = ?"
        result = await self.connection.execute_query(query, (session_id,))
        return result[0] if result else None

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get user's sessions."""
        query = """
            SELECT * FROM sessions
            WHERE user_id = ?
            ORDER BY updated_at DESC
            LIMIT ?
        """
        return await self.connection.execute_query(query, (user_id, limit))

    # Chat message operations
    async def create_chat_message(
        self,
        message_id: str,
        session_id: str,
        role: str,
        content: str,
        embedding: Optional[bytes] = None,
        metadata: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new chat message."""
        query = """
            INSERT INTO chat_messages (id, session_id, role, content, embedding, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.connection.execute_query(
            query, (message_id, session_id, role, content, embedding, metadata)
        )
        return result[0] if result else None

    async def get_chat_messages(
        self,
        session_id: str,
        limit: int = 100,
        role: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get chat messages for a session."""
        query = "SELECT * FROM chat_messages WHERE session_id = ?"
        params = [session_id]

        if role:
            query += " AND role = ?"
            params.append(role)

        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)

        return await self.connection.execute_query(query, tuple(params))

    async def get_chat_messages_paginated(
        self,
        session_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Get paginated chat messages for a session."""
        query = """
            SELECT * FROM chat_messages
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
        """
        return await self.connection.execute_query(query, (session_id, limit, offset))

    # File operations
    async def create_file(
        self,
        file_id: str,
        session_id: str,
        file_name: str,
        file_size: int,
        storage_path: str,
        content_type: str,
        metadata: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new file record."""
        query = """
            INSERT INTO files (id, session_id, file_name, file_size, storage_path, content_type, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.connection.execute_query(
            query, (file_id, session_id, file_name, file_size, storage_path, content_type, metadata)
        )
        return result[0] if result else None

    async def get_files_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get files for a session."""
        query = "SELECT * FROM files WHERE session_id = ? ORDER BY created_at DESC"
        return await self.connection.execute_query(query, (session_id,))

    async def get_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file by ID."""
        query = "SELECT * FROM files WHERE id = ?"
        result = await self.connection.execute_query(query, (file_id,))
        return result[0] if result else None

    # Project operations
    async def create_project(
        self,
        project_id: str,
        user_id: str,
        session_id: Optional[str],
        name: str,
        description: Optional[str] = None,
        framework: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new project."""
        query = """
            INSERT INTO projects (id, user_id, session_id, name, description, framework, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            RETURNING *
        """
        result = await self.connection.execute_query(
            query, (project_id, user_id, session_id, name, description, framework)
        )
        return result[0] if result else None

    async def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID."""
        query = "SELECT * FROM projects WHERE id = ?"
        result = await self.connection.execute_query(query, (project_id,))
        return result[0] if result else None

    async def update_project_json(
        self,
        project_id: str,
        database_json: Optional[str] = None,
        storage_json: Optional[str] = None,
        secrets_json: Optional[str] = None
    ) -> bool:
        """Update project JSON fields."""
        updates = []
        params = []

        if database_json is not None:
            updates.append("database_json = ?")
            params.append(database_json)

        if storage_json is not None:
            updates.append("storage_json = ?")
            params.append(storage_json)

        if secrets_json is not None:
            updates.append("secrets_json = ?")
            params.append(secrets_json)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE projects SET {', '.join(updates)} WHERE id = ?"
            params.append(project_id)

            await self.connection.execute_write(query, tuple(params))

        return True

    # Database maintenance operations
    async def vacuum(self):
        """Run VACUUM to reclaim unused space."""
        async with self.connection.get_connection() as conn:
            await conn.execute("VACUUM")
            logger.info("Database VACUUM completed")

    async def analyze(self):
        """Run ANALYZE to update query planner statistics."""
        async with self.connection.get_connection() as conn:
            await conn.execute("ANALYZE")
            logger.info("Database ANALYZE completed")

    async def get_database_info(self) -> Dict[str, Any]:
        """Get database information and statistics."""
        async with self.connection.get_connection() as conn:
            # Get database size and page count
            size_info = await conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            size = await size_info.fetchone() or (0,)

            # Get table counts
            tables = ['users', 'sessions', 'chat_messages', 'files', 'projects']
            table_counts = {}
            for table in tables:
                count_result = await conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = await count_result.fetchone()
                table_counts[table] = count[0] if count else 0

            return {
                'database_path': self.db_path,
                'size_bytes': size[0],
                'size_mb': round(size[0] / (1024 * 1024), 2),
                'table_counts': table_counts,
                'max_connections': self.config.max_connections,
                'wal_enabled': self.config.enable_wal,
                'foreign_keys_enabled': self.config.enable_foreign_keys
            }

    async def health_check(self) -> Dict[str, Any]:
        """Check database health."""
        try:
            async with self.connection.get_connection() as conn:
                await conn.execute("SELECT 1")
                return {
                    "status": "healthy",
                    "timestamp": datetime.now().isoformat(),
                    "database_path": self.db_path
                }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


# Global instance
_async_sqlite_manager: Optional[AsyncSQLiteManager] = None


async def get_async_sqlite_manager() -> AsyncSQLiteManager:
    """Get the global async SQLite manager instance."""
    global _async_sqlite_manager
    if _async_sqlite_manager is None:
        _async_sqlite_manager = AsyncSQLiteManager()
        await _async_sqlite_manager.initialize()
    return _async_sqlite_manager


async def close_async_sqlite_manager():
    """Close the global async SQLite manager."""
    global _async_sqlite_manager
    if _async_sqlite_manager:
        await _async_sqlite_manager.close()
        _async_sqlite_manager = None


async def init_async_sqlite_database(db_path: Optional[str] = None, config: Optional[SQLiteConfig] = None) -> AsyncSQLiteManager:
    """Initialize async SQLite database and return manager."""
    global _async_sqlite_manager
    _async_sqlite_manager = AsyncSQLiteManager(db_path, config)
    await _async_sqlite_manager.initialize()
    return _async_sqlite_manager