"""Database engine, session factory, and ORM base.

Single source of truth for all database infrastructure:
- ``Base`` — declarative base for models
- ``get_engine()`` / ``shutdown_engine()`` — async engine singleton
- ``get_session_factory()`` — session factory singleton
- ``get_db_session_local()`` — session context manager (auto-commit/rollback)
- ``get_db_dependency()`` — FastAPI Depends() compatible generator
- ``run_migrations()`` — Alembic migrations
"""

import logging
import ssl
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncGenerator, Generic, TypeVar
from urllib.parse import parse_qs, urlparse
import uuid

from sqlalchemy import DateTime, exc, func, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ii_agent.core.config.settings import get_settings

logger = logging.getLogger(__name__)

TimestampColumn = DateTime(timezone=True)


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        default=uuid.uuid4,
    )

    created_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        TimestampColumn,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _prepare_asyncpg_url(database_url: str) -> tuple[str, dict]:
    """Strip SSL query params that asyncpg doesn't understand and convert
    them into a proper ssl.SSLContext in connect_args."""
    connect_args: dict = {}
    if "+asyncpg" not in database_url:
        return database_url, connect_args

    parsed = urlparse(database_url)
    if not parsed.query:
        return database_url, connect_args

    query_params = parse_qs(parsed.query)

    clean_params = []
    for key, values in query_params.items():
        if key not in ("sslmode", "channel_binding", "ssl"):
            for value in values:
                clean_params.append(f"{key}={value}")

    clean_query = "&".join(clean_params) if clean_params else ""
    database_url = database_url.split("?")[0]
    if clean_query:
        database_url += "?" + clean_query

    encoding_params = "client_encoding=utf8"
    if "?" in database_url:
        database_url += "&" + encoding_params
    else:
        database_url += "?" + encoding_params

    if "sslmode" in query_params:
        sslmode = query_params["sslmode"][0]
        if sslmode in ("require", "verify-ca", "verify-full"):
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            connect_args["ssl"] = ssl_context

    return database_url, connect_args


# ---------------------------------------------------------------------------
# Engine & session factory singletons
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Get or create the async engine (lazy singleton)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.database.url:
            raise ValueError("DATABASE_URL not configured")

        database_url, connect_args = _prepare_asyncpg_url(settings.database.url)

        # Defense-in-depth: idle_in_transaction_session_timeout makes
        # PostgreSQL terminate any session that holds an open transaction
        # without activity for >60s. Converts "silent permanent connection
        # leak" (e.g. the 2026-04-24 set_timeout self-deadlock) into a
        # noisy, recoverable failure so the same bug class cannot quietly
        # exhaust QueuePool again. Read-only / autocommit sessions are not
        # affected. We do NOT set statement_timeout or lock_timeout here
        # because legitimate slow queries (large session loads, migrations
        # invoked through this engine in tests) would falsely trip them.
        server_settings = connect_args.setdefault("server_settings", {})
        server_settings.setdefault("idle_in_transaction_session_timeout", "60000")

        _engine = create_async_engine(
            database_url,
            echo=False,
            connect_args=connect_args,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_timeout=settings.database.pool_timeout,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory (lazy singleton)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def shutdown_engine() -> None:
    """Dispose the engine and reset singletons."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        logger.info("Database engine disposed")
    _engine = None
    _session_factory = None


# ---------------------------------------------------------------------------
# Session context managers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_db_session_local() -> AsyncGenerator[AsyncSession, None]:
    """Session context manager with auto-commit/rollback."""
    factory = get_session_factory()
    async with factory() as db:
        try:
            yield db
            await db.commit()
        except exc.SQLAlchemyError:
            await db.rollback()
            raise


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Depends() compatible generator."""
    async with get_db_session_local() as session:
        yield session


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


def run_migrations() -> None:
    """Run database migrations using Alembic."""
    from ii_agent.core.config.settings import II_AGENT_DIR

    try:
        from alembic import command
        from alembic.config import Config

        project_root = II_AGENT_DIR.parent.parent
        alembic_cfg = Config(project_root / "alembic.ini")
        migrations_path = project_root / "migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_path))

        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


# ---------------------------------------------------------------------------
# Base repository
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    """Typed base repository providing common data-access patterns.

    ``T`` must be a subclass of :class:`Base`.

    Subclasses set ``model`` as a class variable::

        class FileRepository(BaseRepository[FileUpload]):
            model = FileUpload
    """

    model: type[T]

    async def get_by_id(self, db: AsyncSession, entity_id: Any) -> T | None:
        """Fetch a single entity by primary key."""
        result = await db.execute(select(self.model).where(self.model.id == entity_id))
        return result.scalar_one_or_none()

    async def save(self, db: AsyncSession, entity: T) -> T:
        """Add a new entity, flush, and refresh from DB."""
        db.add(entity)
        await db.flush()
        await db.refresh(entity)
        return entity

    async def update(self, db: AsyncSession, entity: T) -> T:
        """Flush pending changes on a tracked entity and refresh."""
        await db.flush()
        await db.refresh(entity)
        return entity
