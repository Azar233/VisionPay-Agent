"""link training and model versions to dataset versions

Revision ID: c4e7b9a1d2f0
Revises: 91c3d8f6a2b4
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e7b9a1d2f0"
down_revision: Union[str, None] = "91c3d8f6a2b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "training_tasks",
        sa.Column("dataset_version_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "training_tasks",
        sa.Column("dataset_content_hash", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_training_tasks_dataset_version_id",
        "training_tasks",
        ["dataset_version_id"],
    )
    op.create_foreign_key(
        "fk_training_tasks_dataset_version_id",
        "training_tasks",
        "dataset_versions",
        ["dataset_version_id"],
        ["id"],
    )

    op.add_column(
        "model_versions",
        sa.Column("dataset_version_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_model_versions_dataset_version_id",
        "model_versions",
        ["dataset_version_id"],
    )
    op.create_foreign_key(
        "fk_model_versions_dataset_version_id",
        "model_versions",
        "dataset_versions",
        ["dataset_version_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_model_versions_dataset_version_id",
        "model_versions",
        type_="foreignkey",
    )
    op.drop_index("ix_model_versions_dataset_version_id", table_name="model_versions")
    op.drop_column("model_versions", "dataset_version_id")

    op.drop_constraint(
        "fk_training_tasks_dataset_version_id",
        "training_tasks",
        type_="foreignkey",
    )
    op.drop_index("ix_training_tasks_dataset_version_id", table_name="training_tasks")
    op.drop_column("training_tasks", "dataset_content_hash")
    op.drop_column("training_tasks", "dataset_version_id")
