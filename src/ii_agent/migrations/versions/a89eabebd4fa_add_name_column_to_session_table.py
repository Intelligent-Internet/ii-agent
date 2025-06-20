"""Add name column to session table

Revision ID: a89eabebd4fa
Revises: 512f8dca3732
Create Date: 2025-06-11 17:59:41.494613

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a89eabebd4fa'
down_revision: Union[str, None] = '512f8dca3732'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('session', sa.Column('name', sa.String(), nullable=True))
    op.execute("""
        UPDATE session
        SET name = (
            SELECT event.event_payload->>'content'->>'text'
            FROM event
            WHERE event.session_id = session.id
            AND event.event_type = 'user_message'
            ORDER BY event.timestamp ASC
            LIMIT 1
        ) WHERE name IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('session', 'name')
