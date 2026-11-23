"""Voert databasemigraties uit (Alembic) en zaait de basisconfiguratie."""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from ..config import BACKEND_DIR
from ..db import SessionLocal, get_engine
from .seed import seed_defaults


def upgrade_database() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    with get_engine().begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
