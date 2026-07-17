"""add persistent structured chat context

Revision ID: d3f8a1c6e5b2
Revises: 39d0754cb071, b8d2f4a6c9e1
Create Date: 2026-07-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d3f8a1c6e5b2"
down_revision: Union[str, Sequence[str], None] = (
    "39d0754cb071",
    "b8d2f4a6c9e1",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "chat_sessions",
        sa.Column("context_state", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("chat_sessions", sa.Column("context_summary", sa.Text(), nullable=True))
    op.add_column(
        "chat_sessions",
        sa.Column("summarized_message_id", sa.Integer(), nullable=True),
    )
    op.alter_column("chat_sessions", "context_state", server_default=None)


def downgrade() -> None:
    op.drop_column("chat_sessions", "summarized_message_id")
    op.drop_column("chat_sessions", "context_summary")
    op.drop_column("chat_sessions", "context_state")
