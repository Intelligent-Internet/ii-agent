"""DuckDB database initialization and configuration."""

import os
from pathlib import Path
from typing import Optional
import duckdb
from duckdb import DuckDBPyConnection

from ii_agent.core.config.ii_agent_config import config


class DuckDBManager:
    """DuckDB database manager with vector search capabilities."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to local file in config directory
            db_dir = Path.home() / ".ii_agent" / "data"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "ii_agent.duckdb")

        self.db_path = db_path
        self.connection: Optional[DuckDBPyConnection] = None
        self._initialize_connection()
        self._setup_extensions()
        self._create_tables()

    def _initialize_connection(self):
        """Initialize DuckDB connection with optimal settings."""
        self.connection = duckdb.connect(self.db_path)

        # Configure for performance
        self.connection.execute("PRAGMA threads=4")
        self.connection.execute("PRAGMA memory_limit='2GB'")
        self.connection.execute("PRAGMA enable_progress_bar=false")

        # Enable vector similarity search extension
        try:
            self.connection.execute("INSTALL vss")
            self.connection.execute("LOAD vss")
            self.connection.execute("SET enable_progress_bar = false")
        except Exception as e:
            print(f"Warning: Could not load vss extension: {e}")

    def _setup_extensions(self):
        """Setup required DuckDB extensions."""
        extensions = [
            'fts',  # Full-text search
            'json',  # JSON support
            'parquet',  # Parquet file support
        ]

        for ext in extensions:
            try:
                self.connection.execute(f"INSTALL {ext}")
                self.connection.execute(f"LOAD {ext}")
            except Exception as e:
                print(f"Warning: Could not install/load extension {ext}: {e}")

    def _create_tables(self):
        """Create necessary database tables."""
        # Users table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR PRIMARY KEY,
                email VARCHAR UNIQUE,
                credits INTEGER DEFAULT 0,
                bonus_credits INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Sessions table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                title VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Chat messages table with vector support
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR,
                role VARCHAR,
                content TEXT,
                embedding FLOAT[],
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Create vector index if vss extension is available
        try:
            self.connection.execute("""
                CREATE INDEX IF NOT EXISTS chat_messages_embedding_idx
                ON chat_messages USING HNSW (embedding) WITH (metric = 'cosine')
            """)
        except Exception:
            print("Warning: Could not create vector index (vss extension not available)")

        # Files table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id VARCHAR PRIMARY KEY,
                session_id VARCHAR,
                file_name VARCHAR,
                file_size INTEGER,
                storage_path VARCHAR,
                content_type VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

        # Vector stores table for RAG
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS vector_stores (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                provider VARCHAR,
                vector_store_id VARCHAR,
                embedding_model VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # Projects table
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id VARCHAR PRIMARY KEY,
                user_id VARCHAR,
                session_id VARCHAR,
                name VARCHAR,
                description TEXT,
                status VARCHAR DEFAULT 'active',
                framework VARCHAR,
                database_json JSON,
                storage_json JSON,
                secrets_json JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)

    def get_connection(self) -> DuckDBPyConnection:
        """Get the DuckDB connection."""
        if self.connection is None:
            raise RuntimeError("Database connection not initialized")
        return self.connection

    def close(self):
        """Close the database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def vector_search(
        self,
        query_embedding: list,
        table: str = "chat_messages",
        embedding_column: str = "embedding",
        limit: int = 10,
        where_clause: Optional[str] = None
    ):
        """
        Perform vector similarity search.

        Args:
            query_embedding: Query vector
            table: Table to search in
            embedding_column: Column containing embeddings
            limit: Maximum results to return
            where_clause: Optional WHERE clause for filtering

        Returns:
            List of similar vectors with distances
        """
        if not self.connection:
            raise RuntimeError("Database connection not initialized")

        try:
            # Convert embedding to string for SQL
            embedding_str = f"[{','.join(map(str, query_embedding))}]"

            base_query = f"""
                SELECT *, array_cosine_similarity({embedding_column}, {embedding_str}::FLOAT[]) as similarity
                FROM {table}
            """

            if where_clause:
                base_query += f" WHERE {where_clause}"

            base_query += f" ORDER BY similarity DESC LIMIT {limit}"

            result = self.connection.execute(base_query).fetchall()
            return result

        except Exception as e:
            print(f"Vector search failed, falling back to basic query: {e}")
            # Fallback to basic query if vector search fails
            query = f"SELECT * FROM {table}"
            if where_clause:
                query += f" WHERE {where_clause}"
            query += f" LIMIT {limit}"
            return self.connection.execute(query).fetchall()

    def execute_sql(self, query: str, params: Optional[tuple] = None):
        """Execute SQL query with optional parameters."""
        if not self.connection:
            raise RuntimeError("Database connection not initialized")

        return self.connection.execute(query, params or ())

    def get_table_info(self, table_name: str):
        """Get information about a table structure."""
        if not self.connection:
            raise RuntimeError("Database connection not initialized")

        return self.connection.execute(f"DESCRIBE {table_name}").fetchall()


# Global database manager instance
_duckdb_manager: Optional[DuckDBManager] = None


def get_duckdb_manager() -> DuckDBManager:
    """Get the global DuckDB manager instance."""
    global _duckdb_manager
    if _duckdb_manager is None:
        _duckdb_manager = DuckDBManager()
    return _duckdb_manager


def close_duckdb_manager():
    """Close the global DuckDB manager."""
    global _duckdb_manager
    if _duckdb_manager:
        _duckdb_manager.close()
        _duckdb_manager = None


def init_duckdb_database(db_path: Optional[str] = None) -> DuckDBManager:
    """Initialize DuckDB database and return manager."""
    global _duckdb_manager
    _duckdb_manager = DuckDBManager(db_path)
    return _duckdb_manager