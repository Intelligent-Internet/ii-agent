#!/usr/bin/env python3
"""
Rewrite all http://localhost:PORT URLs to http://192.168.2.2:PORT in stored data.

This fixes URLs that are inaccessible from remote machines (e.g., guest Windows PC)
because DockerSandbox.expose_port() historically hardcoded 'localhost'.

Tables affected:
  - application_events.content (JSONB) - 602 rows with localhost URLs
  - slide_contents.slide_content (JSON/text) - 1 row
  - chat_messages.content (JSONB) - 5 rows

URL categories:
  - http://localhost:8000  -> backend API (slide assets, file endpoints)
  - http://localhost:30xxx -> sandbox exposed ports (live preview, apps)
  - http://localhost:4000  -> sandbox app port
  - http://localhost:1236  -> old E2B image_search (dead links, but rewrite for consistency)

Usage:
    uv run python scripts/local/rewrite_localhost_urls.py [--dry-run] [--host 192.168.2.2]
"""

import argparse
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


DB_URL = "postgresql+asyncpg://iiagent:iiagent@localhost:5433/iiagentdev"
DEFAULT_HOST = "192.168.2.2"


async def rewrite_urls(host: str, dry_run: bool) -> None:
    engine = create_async_engine(DB_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    old = "http://localhost:"
    new = f"http://{host}:"

    async with async_session() as session:
        # 1. application_events - content is JSONB, cast to text, replace, cast back
        result = await session.execute(
            text("""
                SELECT count(*) FROM application_events
                WHERE content::text LIKE :pattern
            """),
            {"pattern": f"%{old}%"},
        )
        ae_count = result.scalar()
        print(f"application_events: {ae_count} rows to update")

        if not dry_run and ae_count > 0:
            await session.execute(
                text("""
                    UPDATE application_events
                    SET content = replace(content::text, :old, :new)::jsonb
                    WHERE content::text LIKE :pattern
                """),
                {"old": old, "new": new, "pattern": f"%{old}%"},
            )
            print(f"  -> Updated {ae_count} rows")

        # 2. slide_contents - slide_content column (varchar, not JSONB)
        result = await session.execute(
            text("""
                SELECT count(*) FROM slide_contents
                WHERE slide_content LIKE :pattern
            """),
            {"pattern": f"%{old}%"},
        )
        sc_count = result.scalar()
        print(f"slide_contents: {sc_count} rows to update")

        if not dry_run and sc_count > 0:
            await session.execute(
                text("""
                    UPDATE slide_contents
                    SET slide_content = replace(slide_content, :old, :new)
                    WHERE slide_content LIKE :pattern
                """),
                {"old": old, "new": new, "pattern": f"%{old}%"},
            )
            print(f"  -> Updated {sc_count} rows")

        # 3. chat_messages - content column (JSONB)
        result = await session.execute(
            text("""
                SELECT count(*) FROM chat_messages
                WHERE content::text LIKE :pattern
            """),
            {"pattern": f"%{old}%"},
        )
        cm_count = result.scalar()
        print(f"chat_messages: {cm_count} rows to update")

        if not dry_run and cm_count > 0:
            await session.execute(
                text("""
                    UPDATE chat_messages
                    SET content = replace(content::text, :old, :new)::jsonb
                    WHERE content::text LIKE :pattern
                """),
                {"old": old, "new": new, "pattern": f"%{old}%"},
            )
            print(f"  -> Updated {cm_count} rows")

        total = ae_count + sc_count + cm_count
        if dry_run:
            print(f"\nDRY RUN: {total} total rows would be updated ({old} -> {new})")
        else:
            await session.commit()
            print(f"\nCOMMITTED: {total} rows updated ({old} -> {new})")


def main():
    parser = argparse.ArgumentParser(description="Rewrite localhost URLs in database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would change without updating"
    )
    parser.add_argument(
        "--host", default=DEFAULT_HOST, help=f"Target host (default: {DEFAULT_HOST})"
    )
    args = parser.parse_args()

    asyncio.run(rewrite_urls(args.host, args.dry_run))


if __name__ == "__main__":
    main()
