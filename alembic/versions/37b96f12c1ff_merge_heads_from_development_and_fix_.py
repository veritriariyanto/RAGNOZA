"""merge heads from development and fix branch

Revision ID: 37b96f12c1ff
Revises: 332ebde9ada4, da434c6d8c6f
Create Date: 2026-06-09 09:24:55.425258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37b96f12c1ff'
down_revision: Union[str, Sequence[str], None] = ('332ebde9ada4', 'da434c6d8c6f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
