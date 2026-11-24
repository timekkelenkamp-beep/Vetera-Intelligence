"""Dekkingsniveaus per bevinding en per product.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("findings") as b:
        b.add_column(sa.Column("coverage_level", sa.String(30), nullable=True))
        b.create_index("ix_findings_coverage_level", ["coverage_level"])
    op.create_table(
        "product_coverages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(30), nullable=False),
        sa.Column("offered", sa.Boolean()),
        sa.Column("local_name", sa.String(200)),
        sa.Column("document_version_id", sa.Integer(), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("page_number", sa.Integer()),
        sa.Column("quote", sa.Text()),
        sa.Column("origin", sa.String(20), nullable=False, server_default="handmatig"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.UniqueConstraint("product_id", "level"),
    )
    op.create_index("ix_product_coverages_product_id", "product_coverages", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_product_coverages_product_id", "product_coverages")
    op.drop_table("product_coverages")
    with op.batch_alter_table("findings") as b:
        b.drop_index("ix_findings_coverage_level")
        b.drop_column("coverage_level")
