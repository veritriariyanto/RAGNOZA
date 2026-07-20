"""add pasal_filter_bypass_reason to rag_process

Revision ID: 715180c724e7
Revises: e520f7a5f420
Create Date: 2026-07-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '715180c724e7'
down_revision: Union[str, Sequence[str], None] = 'e520f7a5f420'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    File revisi ini sempat hilang dari repo (tidak pernah ter-commit ke git)
    padahal sudah dijalankan di database — alembic_version di DB menunjuk ke
    revision_id ini, tapi file-nya tidak ada, sehingga rantai migrasi macet.
    Direkonstruksi di sini (idempotent via IF NOT EXISTS) agar `alembic
    upgrade head` bisa jalan lagi tanpa menyentuh data yang sudah ada.
    """
    op.execute("""
        ALTER TABLE rag_process
        ADD COLUMN IF NOT EXISTS pasal_filter_bypass_reason TEXT;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('rag_process', 'pasal_filter_bypass_reason')
