"""add user_id to mock_payment_orders

Revision ID: c1d8c16da319
Revises: 7c4a1f2d9b60
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d8c16da319"
down_revision: Union[str, None] = "7c4a1f2d9b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mock_payment_orders", sa.Column("user_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_mock_payment_orders_user_id",
        "mock_payment_orders",
        "users",
        ["user_id"],
        ["id"],
    )

    op.create_index("ix_mock_payment_orders_user_id", "mock_payment_orders", ["user_id"], unique=False)
    op.create_index("ix_mock_payment_orders_created_at", "mock_payment_orders", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mock_payment_orders_created_at", table_name="mock_payment_orders")
    op.drop_index("ix_mock_payment_orders_user_id", table_name="mock_payment_orders")

    op.drop_constraint("fk_mock_payment_orders_user_id", "mock_payment_orders", type_="foreignkey")

    op.drop_column("mock_payment_orders", "user_id")
