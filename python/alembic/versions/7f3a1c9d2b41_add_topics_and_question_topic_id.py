"""add topics table and question.topic_id

Revision ID: 7f3a1c9d2b41
Revises: 32778e2f404c
Create Date: 2026-07-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7f3a1c9d2b41"
down_revision: Union[str, None] = "32778e2f404c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("grade", sa.String(), nullable=False),
        sa.Column("unit", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topics_subject", "topics", ["subject"])
    op.create_index("ix_topics_grade", "topics", ["grade"])

    with op.batch_alter_table("questions") as batch_op:
        batch_op.add_column(sa.Column("topic_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_questions_topic_id", ["topic_id"])
        batch_op.create_foreign_key("fk_questions_topic_id", "topics", ["topic_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch_op:
        batch_op.drop_constraint("fk_questions_topic_id", type_="foreignkey")
        batch_op.drop_index("ix_questions_topic_id")
        batch_op.drop_column("topic_id")
    op.drop_index("ix_topics_grade", table_name="topics")
    op.drop_index("ix_topics_subject", table_name="topics")
    op.drop_table("topics")
