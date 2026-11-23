"""Full-text zoekindex (SQLite FTS5) over geëxtraheerde documentpagina's.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS page_fts USING fts5("
        "text, content='document_pages', content_rowid='id', tokenize='unicode61 remove_diacritics 2')"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS page_fts_ai AFTER INSERT ON document_pages BEGIN "
        "INSERT INTO page_fts(rowid, text) VALUES (new.id, new.text); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS page_fts_ad AFTER DELETE ON document_pages BEGIN "
        "INSERT INTO page_fts(page_fts, rowid, text) VALUES('delete', old.id, old.text); END"
    )
    op.execute(
        "CREATE TRIGGER IF NOT EXISTS page_fts_au AFTER UPDATE ON document_pages BEGIN "
        "INSERT INTO page_fts(page_fts, rowid, text) VALUES('delete', old.id, old.text); "
        "INSERT INTO page_fts(rowid, text) VALUES (new.id, new.text); END"
    )


def downgrade() -> None:
    for t in ("page_fts_ai", "page_fts_ad", "page_fts_au"):
        op.execute(f"DROP TRIGGER IF EXISTS {t}")
    op.execute("DROP TABLE IF EXISTS page_fts")
