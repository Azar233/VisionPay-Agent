"""add user nickname

Revision ID: a5c9e2f4b7d1
Revises: e4b7c9d2a6f1
Create Date: 2026-07-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a5c9e2f4b7d1"
down_revision: Union[str, Sequence[str], None] = "e4b7c9d2a6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "nickname",
            sa.String(length=50),
            nullable=True,
            comment="展示昵称，可重复、可修改",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "nickname")
