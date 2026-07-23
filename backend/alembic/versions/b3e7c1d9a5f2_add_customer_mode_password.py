"""add customer mode exit password

Revision ID: b3e7c1d9a5f2
Revises: a5c9e2f4b7d1
Create Date: 2026-07-23
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b3e7c1d9a5f2"
down_revision: Union[str, Sequence[str], None] = "a5c9e2f4b7d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "customer_mode_password_hash",
            sa.String(length=255),
            nullable=True,
            comment="顾客展示模式退出密码哈希；为空时使用系统默认密码",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "customer_mode_password_hash")
