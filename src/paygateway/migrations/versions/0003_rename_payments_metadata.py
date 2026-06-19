"""rename payments.metadata_ to metadata

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("payments", "metadata_", new_column_name="metadata")


def downgrade() -> None:
    op.alter_column("payments", "metadata", new_column_name="metadata_")
