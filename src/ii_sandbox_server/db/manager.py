from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, List
import ssl
from urllib.parse import urlparse, parse_qs
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession as DBSession

from ii_sandbox_server.logger import logger
from ii_sandbox_server.db.model import Sandbox


def run_migrations():
    try:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("~/.ii_sandbox_server/alembic.ini")
        migrations_path = "~/.ii_sandbox_server/migrations"
        alembic_cfg.set_main_option("script_location", str(migrations_path))

        command.upgrade(alembic_cfg, "head")

    except Exception as e:
        logger.error(f"Error running migrations: {e}")
        raise


# run_migrations()

# TODO: move this to config
import os
# Default to PostgreSQL, but allow override via environment variable
database_url = os.getenv(
    "SANDBOX_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/ii_sandbox"
)

# Parse the database URL to handle SSL parameters for asyncpg
connect_args = {}

if "+asyncpg" in database_url:
    # Parse the URL to extract SSL parameters
    parsed = urlparse(database_url)
    if parsed.query:
        query_params = parse_qs(parsed.query)

        # Remove SSL-related parameters from the URL
        clean_params = []
        for key, values in query_params.items():
            if key not in ['sslmode', 'channel_binding', 'ssl']:
                for value in values:
                    clean_params.append(f"{key}={value}")

        # Reconstruct the URL without SSL parameters
        clean_query = '&'.join(clean_params) if clean_params else ''
        database_url = database_url.split('?')[0]
        if clean_query:
            database_url += '?' + clean_query

        # Configure SSL for asyncpg based on sslmode parameter
        if 'sslmode' in query_params:
            sslmode = query_params['sslmode'][0]
            if sslmode in ['require', 'verify-ca', 'verify-full']:
                # Create SSL context
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                connect_args['ssl'] = ssl_context

engine = create_async_engine(
    database_url,
    echo=False,
    future=True,
    connect_args=connect_args,
    pool_size=20,
    max_overflow=0,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30
)
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


@asynccontextmanager
async def get_db() -> AsyncGenerator[DBSession, None]:
    """Get a database session as a context manager.

    Yields:
        A database session that will be automatically committed or rolled back
    """
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise


class SandboxTable:
    """Table class for sandbox operations following Open WebUI pattern."""

    async def create_sandbox(
        self,
        sandbox_id: str,
        provider: str,
        provider_sandbox_id: str,
        user_id: str,
        status: str = "initializing",
    ) -> Sandbox:
        """Create a new sandbox.

        Args:
            sandbox_id: The internal sandbox UUID
            provider: The provider name (e.g., 'e2b')
            provider_sandbox_id: The provider's sandbox ID
            user_id: The user ID who owns the sandbox
            status: Initial status of the sandbox

        Returns:
            The created sandbox
        """
        async with get_db() as db:
            db_sandbox = Sandbox(
                id=sandbox_id,
                provider=provider,
                provider_sandbox_id=provider_sandbox_id,
                user_id=user_id,
                status=status,
            )
            db.add(db_sandbox)
            await db.flush()
            return db_sandbox

    async def get_sandbox_by_id(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get a sandbox by its internal ID.

        Args:
            sandbox_id: The internal sandbox ID

        Returns:
            The sandbox if found, None otherwise
        """
        async with get_db() as db:
            result = await db.execute(select(Sandbox).where(Sandbox.id == sandbox_id))
            return result.scalar_one_or_none()

    async def get_sandbox_by_provider_id(
        self, provider_sandbox_id: str
    ) -> Optional[Sandbox]:
        """Get a sandbox by its provider ID.

        Args:
            provider_sandbox_id: The provider's sandbox ID

        Returns:
            The sandbox if found, None otherwise
        """
        async with get_db() as db:
            result = await db.execute(
                select(Sandbox).where(Sandbox.sandbox_id == provider_sandbox_id)
            )
            return result.scalar_one_or_none()

    async def update_sandbox_status(
        self, sandbox_id: str, status: Optional[str] = None, **kwargs
    ) -> bool:
        """Update a sandbox's status and optional timestamp fields.

        Args:
            sandbox_id: The internal sandbox ID
            status: New status to set (optional)
            **kwargs: Optional timestamp fields (started_at, stopped_at, etc.)

        Returns:
            True if updated successfully, False if not found
        """
        async with get_db() as db:
            result = await db.execute(select(Sandbox).where(Sandbox.id == sandbox_id))
            db_sandbox = result.scalar_one_or_none()
            if db_sandbox:
                if status is not None:
                    db_sandbox.status = status

                from datetime import datetime, timezone

                # Update timestamp fields if provided
                for field, value in kwargs.items():
                    if hasattr(db_sandbox, field):
                        if value is True:  # Set current timestamp
                            setattr(db_sandbox, field, datetime.now(timezone.utc))
                        elif value is not None:
                            setattr(db_sandbox, field, value)

                await db.flush()
                return True
            return False

    async def update_last_activity(self, sandbox_id: str) -> bool:
        """Update the last activity timestamp for a sandbox.

        Args:
            sandbox_id: The internal sandbox ID

        Returns:
            True if updated successfully, False if not found
        """
        from datetime import datetime, timezone

        return await self.update_sandbox_status(
            sandbox_id, None, last_activity_at=datetime.now(timezone.utc)
        )

    async def list_user_sandboxes(
        self, user_id: str, status: Optional[str] = None
    ) -> List[Sandbox]:
        """List sandboxes for a user.

        Args:
            user_id: User ID
            status: Optional status filter

        Returns:
            List of sandboxes
        """
        async with get_db() as db:
            query = select(Sandbox).where(Sandbox.user_id == user_id)

            if status:
                query = query.where(Sandbox.status == status)

            query = query.order_by(Sandbox.created_at.desc())
            result = await db.execute(query)
            return result.scalars().all()

    async def delete_sandbox(self, sandbox_id: str) -> bool:
        """Delete a sandbox from the database.

        Args:
            sandbox_id: The internal sandbox ID

        Returns:
            True if deleted successfully, False if not found
        """
        async with get_db() as db:
            result = await db.execute(select(Sandbox).where(Sandbox.id == sandbox_id))
            db_sandbox = result.scalar_one_or_none()
            if db_sandbox:
                await db.delete(db_sandbox)
                return True
            return False

    async def get_all_sandboxes(self, exclude_deleted: bool = True) -> List[Sandbox]:
        """Get all sandboxes from the database.

        Args:
            exclude_deleted: If True, exclude sandboxes with 'deleted' status

        Returns:
            List of all sandboxes
        """
        async with get_db() as db:
            query = select(Sandbox)
            if exclude_deleted:
                query = query.where(Sandbox.status != "deleted")
            query = query.order_by(Sandbox.created_at.desc())
            result = await db.execute(query)
            return result.scalars().all()

    async def get_sandbox_with_user(self, sandbox_id: str) -> Optional[Sandbox]:
        """Get a sandbox with its user relationship loaded.

        Args:
            sandbox_id: The internal sandbox ID

        Returns:
            The sandbox with user loaded, or None if not found
        """
        async with get_db() as db:
            result = await db.execute(
                select(Sandbox)
                .where(Sandbox.id == sandbox_id)
                .options(selectinload(Sandbox.user))
            )
            return result.scalar_one_or_none()


Sandboxes = SandboxTable()
