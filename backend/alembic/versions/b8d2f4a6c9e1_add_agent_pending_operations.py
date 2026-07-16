"""add agent pending operations

Revision ID: b8d2f4a6c9e1
Revises: a9c4e1d7b2f6
Create Date: 2026-07-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8d2f4a6c9e1"
down_revision: Union[str, Sequence[str], None] = "a9c4e1d7b2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_pending_operations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("operation_uuid", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_uuid", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=50), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("risk_level", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("impact", sa.JSON(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("preview_idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("execution_idempotency_key", sa.String(length=100), nullable=True),
        sa.Column("confirmation_token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(), nullable=False),
        sa.Column("token_consumed_at", sa.DateTime(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("executed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_uuid", name="uq_agent_pending_operations_uuid"),
        sa.UniqueConstraint(
            "user_id",
            "preview_idempotency_key",
            name="uq_agent_pending_operations_user_preview_key",
        ),
    )
    for column in (
        "operation_uuid", "user_id", "session_uuid", "domain", "action", "status",
        "request_fingerprint", "execution_idempotency_key", "token_expires_at",
    ):
        op.create_index(
            f"ix_agent_pending_operations_{column}",
            "agent_pending_operations",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in reversed((
        "operation_uuid", "user_id", "session_uuid", "domain", "action", "status",
        "request_fingerprint", "execution_idempotency_key", "token_expires_at",
    )):
        op.drop_index(f"ix_agent_pending_operations_{column}", table_name="agent_pending_operations")
    op.drop_table("agent_pending_operations")
