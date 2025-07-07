"""Add sandbox column

Revision ID: d6e272e1eb0d
Revises: a89eabebd4fa
Create Date: 2025-07-07 12:32:40.767696

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6e272e1eb0d"
down_revision: Union[str, None] = "a89eabebd4fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("session", sa.Column("sandbox_id", sa.String(), nullable=True))

    op.execute("""
        UPDATE session
        SET sandbox_id = id
        WHERE sandbox_id IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("session", "sandbox_id")
