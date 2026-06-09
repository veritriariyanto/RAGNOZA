"""fix migration dummy

Revision ID: 332ebde9ada4
Revises: None
Create Date: 2026-06-03 02:50:31.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '332ebde9ada4'
down_revision: Union[str, None] = None  # Ganti None dengan ID sebelum revisi ini jika ada parent-nya
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Biarkan kosong (pass) karena skema DB sebenarnya sudah ada di Postgres Anda
    pass


def downgrade() -> None:
    pass