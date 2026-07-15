"""merge dataset versioning and payment history heads

Revision ID: f6a7b8c9d0e1
Revises: e8f2a6c9d1b3, c1d8c16da319
Create Date: 2026-07-15
"""

from typing import Sequence, Union


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = (
    "e8f2a6c9d1b3",
    "c1d8c16da319",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Join both migration branches without additional schema changes."""


def downgrade() -> None:
    """Return to the two independent migration heads."""
