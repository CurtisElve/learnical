"""removed identifier from worksheet

Revision ID: 9b60b1f6a726
Revises: fc280a4882fb
Create Date: 2026-03-13 17:43:10.491591

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b60b1f6a726'
down_revision: Union[str, None] = 'fc280a4882fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
