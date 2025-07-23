"""Add new column runtime_id

Revision ID: b940c8b61543
Revises: a89eabebd4fa
Create Date: 2025-07-23 11:22:31.059770

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b940c8b61543"
down_revision: Union[str, None] = "a89eabebd4fa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("session", sa.Column("runtime_id", sa.String(), nullable=True))

    op.execute("""
        UPDATE session
        SET runtime_id = id
        WHERE runtime_id IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("session", "runtime_id")
