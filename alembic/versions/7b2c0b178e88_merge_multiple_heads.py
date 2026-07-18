"""merge multiple heads

Revision ID: 7b2c0b178e88
Revises: 37b96f12c1ff, 78610b14b032
Create Date: 2026-07-02 23:51:50.867643

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b2c0b178e88'
down_revision: Union[str, Sequence[str], None] = ('37b96f12c1ff', '78610b14b032')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
