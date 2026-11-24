"""Vlag voor automatisch gekozen logo's.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("providers") as b:
        b.add_column(sa.Column("logo_auto", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("providers") as b:
        b.drop_column("logo_auto")
