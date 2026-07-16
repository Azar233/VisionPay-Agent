"""add agent handoffs

Revision ID: a9c4e1d7b2f6
Revises: f6a7b8c9d0e1
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e1d7b2f6"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_handoffs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("handoff_uuid", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_uuid", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handoff_uuid"),
    )
    for column in ("handoff_uuid", "user_id", "session_uuid", "domain", "action", "status", "expires_at"):
        op.create_index(f"ix_agent_handoffs_{column}", "agent_handoffs", [column], unique=column == "handoff_uuid")


def downgrade() -> None:
    for column in ("expires_at", "status", "action", "domain", "session_uuid", "user_id", "handoff_uuid"):
        op.drop_index(f"ix_agent_handoffs_{column}", table_name="agent_handoffs")
    op.drop_table("agent_handoffs")
