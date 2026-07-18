"""fix(db): force add missing columns to ragas_evaluation

Revision ID: e520f7a5f420
Revises: 5e6f1e695d19
Create Date: 2026-07-11 02:59:44.096499

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e520f7a5f420'
down_revision: Union[str, Sequence[str], None] = '5e6f1e695d19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Menggunakan raw SQL dengan 'IF NOT EXISTS' agar aman dijalankan di lokal Anda 
    # (yang mungkin sudah Anda tambahkan manual) maupun di lokal tim Anda.
    op.execute("""
        ALTER TABLE ragas_evaluation 
        ADD COLUMN IF NOT EXISTS faithfulness_summary TEXT,
        ADD COLUMN IF NOT EXISTS faithfulness_qa TEXT;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Menghapus kolom jika migrasi di-rollback
    op.drop_column('ragas_evaluation', 'faithfulness_summary')
    op.drop_column('ragas_evaluation', 'faithfulness_qa')
