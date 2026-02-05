#!/usr/bin/env python3
"""Create a user with email/password login.

Usage:
    python scripts/create_user.py --email admin@local.dev --password secret123
    python scripts/create_user.py --email admin@local.dev --password secret123 --role admin
    python scripts/create_user.py --email admin@local.dev --password secret123 --db-url postgresql://...
"""

import argparse
import os
import secrets
import string
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine, select, Column, String, Boolean, Float, Index
from sqlalchemy import TIMESTAMP
from sqlalchemy.orm import Session, declarative_base

import bcrypt

Base = declarative_base()
TimestampColumn = TIMESTAMP(timezone=True)


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    avatar = Column(String, nullable=True)
    role = Column(String, default="user")
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(TimestampColumn)
    updated_at = Column(TimestampColumn)
    last_login_at = Column(TimestampColumn, nullable=True)
    login_provider = Column(String, nullable=True)
    credits = Column(Float, nullable=False)
    bonus_credits = Column(Float, nullable=False, default=0.0)
    subscription_plan = Column(String, nullable=True)
    __table_args__ = (Index("idx_users_email", "email"),)


class APIKey(Base):
    __tablename__ = "api_keys"
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False)
    api_key = Column(String, nullable=False, unique=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(TimestampColumn)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_api_key(prefix: str = "ii", length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    remaining = max(8, length - len(prefix) - 1)
    random_part = "".join(secrets.choice(alphabet) for _ in range(remaining))
    return f"{prefix}_{random_part}"


def get_database_url(cli_url: str | None) -> str:
    if cli_url:
        return cli_url
    env_url = os.getenv("DATABASE_URL", "")
    if env_url:
        # Convert async driver to sync if needed
        return env_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    return "postgresql://postgres:postgres@localhost:5432/ii_agent"


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a user with email/password login")
    parser.add_argument("--email", required=True, help="User email address")
    parser.add_argument("--password", required=True, help="User password")
    parser.add_argument("--first-name", default="", help="First name")
    parser.add_argument("--last-name", default="", help="Last name")
    parser.add_argument("--role", default="user", choices=["user", "admin"], help="User role")
    parser.add_argument("--credits", type=float, default=300.0, help="Initial credits (default 300)")
    parser.add_argument("--db-url", default=None, help="Database URL (default: DATABASE_URL env or localhost)")
    args = parser.parse_args()

    db_url = get_database_url(args.db_url)
    engine = create_engine(db_url, echo=False)

    with Session(engine) as db:
        existing = db.execute(
            select(User).where(User.email == args.email.strip().lower())
        ).scalar_one_or_none()

        if existing:
            existing.password_hash = hash_password(args.password)
            existing.login_provider = "password"
            db.commit()
            print(f"Updated password for existing user: {existing.email} (id={existing.id})")
            return

        now = datetime.now(timezone.utc)

        user = User(
            id=str(uuid.uuid4()),
            email=args.email.strip().lower(),
            password_hash=hash_password(args.password),
            first_name=args.first_name,
            last_name=args.last_name,
            role=args.role,
            is_active=True,
            email_verified=True,
            credits=args.credits,
            bonus_credits=0.0,
            created_at=now,
            updated_at=now,
            login_provider="password",
            subscription_plan="free",
        )
        db.add(user)
        db.flush()

        api_key = APIKey(
            id=str(uuid.uuid4()),
            user_id=user.id,
            api_key=generate_api_key(),
            is_active=True,
            created_at=now,
        )
        db.add(api_key)
        db.commit()

        print(f"Created user: {user.email} (id={user.id}, role={user.role})")
        print(f"API key: {api_key.api_key}")


if __name__ == "__main__":
    main()
