"""Add answer_regions to worksheets and clear table.

Revision ID: 001
Revises:
Create Date: 2025-03-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Clear worksheets so we can add a NOT NULL column with default if needed
    op.execute("DELETE FROM worksheets")

    # Add answer_regions (list of [start_pct, end_pct] stored as JSON)
    op.add_column(
        "worksheets",
        sa.Column(
            "answer_regions",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("worksheets", "answer_regions")
