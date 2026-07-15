"""add stable product catalog and dataset file index

Revision ID: e8f2a6c9d1b3
Revises: c4e7b9a1d2f0
Create Date: 2026-07-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f2a6c9d1b3"
down_revision: Union[str, None] = "c4e7b9a1d2f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_key", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("sku_name", sa.String(length=200), nullable=True),
        sa.Column("barcode", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("extra_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_key"),
        sa.UniqueConstraint("barcode"),
    )
    op.create_index("ix_products_product_key", "products", ["product_key"], unique=True)
    op.create_index("ix_products_barcode", "products", ["barcode"], unique=True)
    op.create_index("ix_products_is_active", "products", ["is_active"])

    op.add_column("dataset_class_mappings", sa.Column("product_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_dataset_class_mappings_product_id",
        "dataset_class_mappings",
        ["product_id"],
    )
    op.create_foreign_key(
        "fk_dataset_class_mappings_product_id",
        "dataset_class_mappings",
        "products",
        ["product_id"],
        ["id"],
    )

    op.add_column("product_prices", sa.Column("product_id", sa.Integer(), nullable=True))
    op.create_index("ix_product_prices_product_id", "product_prices", ["product_id"], unique=True)
    op.create_foreign_key(
        "fk_product_prices_product_id",
        "product_prices",
        "products",
        ["product_id"],
        ["id"],
    )

    op.create_table(
        "dataset_images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.Integer(), nullable=False),
        sa.Column("split", sa.String(length=20), nullable=False),
        sa.Column("relative_path", sa.String(length=1000), nullable=False),
        sa.Column("label_relative_path", sa.String(length=1000), nullable=True),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_version_id",
            "relative_path",
            name="uq_dataset_images_version_path",
        ),
    )
    op.create_index("ix_dataset_images_dataset_version_id", "dataset_images", ["dataset_version_id"])
    op.create_index("ix_dataset_images_split", "dataset_images", ["split"])
    op.create_index("ix_dataset_images_checksum", "dataset_images", ["checksum"])

    op.create_table(
        "dataset_annotations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_image_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("class_index", sa.Integer(), nullable=False),
        sa.Column("x_center", sa.Float(), nullable=False),
        sa.Column("y_center", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=30), server_default="imported", nullable=False),
        sa.ForeignKeyConstraint(["dataset_image_id"], ["dataset_images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dataset_annotations_dataset_image_id", "dataset_annotations", ["dataset_image_id"])
    op.create_index("ix_dataset_annotations_product_id", "dataset_annotations", ["product_id"])
    op.create_index("ix_dataset_annotations_class_index", "dataset_annotations", ["class_index"])


def downgrade() -> None:
    op.drop_table("dataset_annotations")
    op.drop_table("dataset_images")
    op.drop_constraint("fk_product_prices_product_id", "product_prices", type_="foreignkey")
    op.drop_index("ix_product_prices_product_id", table_name="product_prices")
    op.drop_column("product_prices", "product_id")
    op.drop_constraint(
        "fk_dataset_class_mappings_product_id",
        "dataset_class_mappings",
        type_="foreignkey",
    )
    op.drop_index("ix_dataset_class_mappings_product_id", table_name="dataset_class_mappings")
    op.drop_column("dataset_class_mappings", "product_id")
    op.drop_table("products")
