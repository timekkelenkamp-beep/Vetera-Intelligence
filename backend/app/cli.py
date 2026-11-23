"""Opdrachtregel: python -m app.cli <opdracht>

  weekly-check   Voer de geplande broncontrole uit (voor Windows Taakplanner)
  catch-up       Voer een inhaalcontrole uit als de laatste controle is gemist
  backup         Maak een lokale back-up
  migrate        Voer databasemigraties uit
"""
from __future__ import annotations

import sys

from .db import SessionLocal
from .services.migrate import upgrade_database


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "help"
    upgrade_database()
    if cmd in ("weekly-check", "catch-up"):
        from .services.monitor import run_monitor, schedule_status
        db = SessionLocal()
        try:
            if cmd == "catch-up" and not schedule_status(db)["overdue"]:
                print("Geen inhaalcontrole nodig.")
                return 0
            run = run_monitor(db, "gepland" if cmd == "weekly-check" else "inhaal")
            print(f"Broncontrole {run.status}: {run.summary}")
            return 0 if run.status == "voltooid" else 1
        finally:
            db.close()
    if cmd == "backup":
        from .routers.system import make_backup
        print(f"Back-up gemaakt: {make_backup()}")
        return 0
    if cmd == "migrate":
        print("Database is bijgewerkt.")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
