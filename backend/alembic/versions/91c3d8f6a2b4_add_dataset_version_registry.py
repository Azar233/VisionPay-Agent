"""add dataset version registry

Revision ID: 91c3d8f6a2b4
Revises: 7c4a1f2d9b60
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "91c3d8f6a2b4"
down_revision: Union[str, None] = "7c4a1f2d9b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=False, comment="所属检测场景"),
        sa.Column("parent_id", sa.Integer(), nullable=True, comment="派生自哪个数据集版本"),
        sa.Column("version", sa.String(length=50), nullable=False, comment="数据集版本号"),
        sa.Column("name", sa.String(length=150), nullable=False, comment="数据集显示名称"),
        sa.Column("description", sa.Text(), nullable=True, comment="版本说明"),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="draft",
            nullable=False,
            comment="draft/ready/archived",
        ),
        sa.Column("is_current", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("data_yaml_path", sa.String(length=1000), nullable=False),
        sa.Column("manifest_path", sa.String(length=1000), nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("class_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("train_image_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("val_image_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("test_image_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("train_annotation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("val_annotation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("test_annotation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("validation_report", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("validated_at", sa.DateTime(), nullable=True),
        sa.Column("frozen_at", sa.DateTime(), nullable=True),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["detection_scenes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scene_id", "version", name="uq_dataset_versions_scene_version"),
    )
    op.create_index("ix_dataset_versions_scene_id", "dataset_versions", ["scene_id"])
    op.create_index("ix_dataset_versions_parent_id", "dataset_versions", ["parent_id"])
    op.create_index("ix_dataset_versions_status", "dataset_versions", ["status"])
    op.create_index("ix_dataset_versions_is_current", "dataset_versions", ["is_current"])
    op.create_index("ix_dataset_versions_content_hash", "dataset_versions", ["content_hash"])
    op.create_index("ix_dataset_versions_created_by", "dataset_versions", ["created_by"])
    op.create_index(
        "uq_dataset_versions_current_scene",
        "dataset_versions",
        ["scene_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )

    op.create_table(
        "dataset_class_mappings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), nullable=False),
        sa.Column("class_index", sa.Integer(), nullable=False, comment="YOLO class_id"),
        sa.Column("product_key", sa.String(length=100), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("class_name", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"],
            ["dataset_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "class_index",
            name="uq_dataset_class_mappings_version_index",
        ),
        sa.UniqueConstraint(
            "dataset_version_id",
            "product_key",
            name="uq_dataset_class_mappings_version_product",
        ),
    )
    op.create_index(
        "ix_dataset_class_mappings_dataset_version_id",
        "dataset_class_mappings",
        ["dataset_version_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_dataset_class_mappings_dataset_version_id",
        table_name="dataset_class_mappings",
    )
    op.drop_table("dataset_class_mappings")
    op.drop_index("uq_dataset_versions_current_scene", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_created_by", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_content_hash", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_is_current", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_status", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_parent_id", table_name="dataset_versions")
    op.drop_index("ix_dataset_versions_scene_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
