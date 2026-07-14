"""add mock payment orders

Revision ID: 7c4a1f2d9b60
Revises: 42de18617828
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4a1f2d9b60"
down_revision: Union[str, None] = "42de18617828"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mock_payment_orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_uuid", sa.String(length=36), nullable=False),
        sa.Column("payment_token", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("items_snapshot", sa.JSON(), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("paid_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mock_payment_orders_order_uuid", "mock_payment_orders", ["order_uuid"], unique=True)
    op.create_index("ix_mock_payment_orders_payment_token", "mock_payment_orders", ["payment_token"], unique=True)
    op.create_index("ix_mock_payment_orders_status", "mock_payment_orders", ["status"], unique=False)
    op.create_index("ix_mock_payment_orders_expires_at", "mock_payment_orders", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mock_payment_orders_expires_at", table_name="mock_payment_orders")
    op.drop_index("ix_mock_payment_orders_status", table_name="mock_payment_orders")
    op.drop_index("ix_mock_payment_orders_payment_token", table_name="mock_payment_orders")
    op.drop_index("ix_mock_payment_orders_order_uuid", table_name="mock_payment_orders")
    op.drop_table("mock_payment_orders")
