"""add title to rag_process

Revision ID: d4336dff1d77
Revises: e520f7a5f420
Create Date: 2026-07-12 23:25:40.918824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4336dff1d77'
down_revision: Union[str, Sequence[str], None] = '715180c724e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE rag_process
        ADD COLUMN IF NOT EXISTS title VARCHAR;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rag_process', 'title')
