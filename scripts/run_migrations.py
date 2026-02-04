#!/usr/bin/env python
"""
Standalone Migration Runner

Run database migrations without requiring full ii-agent dependencies.

Usage:
    # With DATABASE_URL environment variable:
    export DATABASE_URL="postgresql://user:pass@host:5432/ii_agent"
    python scripts/run_migrations.py

    # Or pass directly:
    python scripts/run_migrations.py --database-url "postgresql://..."

    # Check current state:
    python scripts/run_migrations.py --current

    # Show pending migrations:
    python scripts/run_migrations.py --pending
"""

import argparse
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def get_database_url(args_url: str = None) -> str:
    """Get database URL from args or environment."""
    url = args_url or os.getenv("DATABASE_URL")

    if not url:
        print("ERROR: DATABASE_URL not set")
        print()
        print("Set it via:")
        print("  export DATABASE_URL='postgresql://user:pass@host:5432/ii_agent'")
        print("  or")
        print("  python scripts/run_migrations.py --database-url 'postgresql://...'")
        sys.exit(1)

    # Ensure sync URL (not async)
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    elif "+aiosqlite" in url:
        url = url.replace("+aiosqlite", "")

    return url


def run_alembic(database_url: str, command: str, *args):
    """Run alembic command."""
    from alembic import command as alembic_command
    from alembic.config import Config

    # Create alembic config
    alembic_ini = Path(__file__).parent.parent / "src" / "ii_agent" / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

    # Run command
    cmd_func = getattr(alembic_command, command)
    cmd_func(alembic_cfg, *args)


def main():
    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--database-url",
        help="Database URL (defaults to DATABASE_URL env var)",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Show current migration revision",
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Show pending migrations",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Run all pending migrations (default)",
    )
    parser.add_argument(
        "--revision",
        help="Upgrade to specific revision (default: head)",
        default="head",
    )
    parser.add_argument(
        "--downgrade",
        help="Downgrade to specific revision",
    )

    args = parser.parse_args()

    database_url = get_database_url(args.database_url)
    print(f"Database: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print()

    try:
        if args.current:
            print("Current revision:")
            run_alembic(database_url, "current")
        elif args.pending:
            print("Migration history:")
            run_alembic(database_url, "history")
        elif args.downgrade:
            print(f"Downgrading to: {args.downgrade}")
            run_alembic(database_url, "downgrade", args.downgrade)
            print("Downgrade complete!")
        else:
            # Default: upgrade
            print(f"Upgrading to: {args.revision}")
            run_alembic(database_url, "upgrade", args.revision)
            print("Upgrade complete!")

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
