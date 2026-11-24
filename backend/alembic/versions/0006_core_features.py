"""Kernkenmerken voor het overzicht.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

CORE = ["acc_min_leeftijd_bestuurder", "acc_dagelijks_gebruik", "geb_km_beperking", "geb_evenementen", "geb_buitenland",
        "waa_taxatie", "waa_totaal_verlies", "dek_diefstal", "dek_transport", "dek_pechhulp", "er_standaard",
        "col_meerdere_voertuigen"]


def upgrade() -> None:
    with op.batch_alter_table("features") as b:
        b.add_column(sa.Column("is_core", sa.Boolean(), nullable=False, server_default="0"))
    keys = ", ".join(f"'{k}'" for k in CORE)
    op.execute(f"UPDATE features SET is_core = 1 WHERE key IN ({keys})")


def downgrade() -> None:
    with op.batch_alter_table("features") as b:
        b.drop_column("is_core")
