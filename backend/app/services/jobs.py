"""Eenvoudige achtergrondtaken in een eigen thread met voortgang in de database.

Lange acties (webonderzoek, PDF's ophalen, AI-analyses) lopen zo niet tegen time-outs van de
hostingdienst aan. Eén taak tegelijk per soort voorkomt dat het geheugen volloopt."""
from __future__ import annotations

import gc
import logging
import threading
from datetime import datetime, timedelta
from typing import Callable

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Job

log = logging.getLogger("vetera.jobs")
_lock = threading.Lock()


class Progress:
    def __init__(self, job_id: int):
        self.job_id = job_id

    def __call__(self, step: str | None = None, done: int | None = None, total: int | None = None) -> None:
        db = SessionLocal()
        try:
            j = db.get(Job, self.job_id)
            if step is not None:
                j.step = step[:300]
            if done is not None:
                j.done = done
            if total is not None:
                j.total = total
            db.commit()
        finally:
            db.close()


def start_job(kind: str, func: Callable, *args, **kwargs) -> int:
    """Start ``func(db, progress, *args, **kwargs)`` op de achtergrond; het resultaat (dict) wordt bewaard."""
    db = SessionLocal()
    try:
        # Opruimen: oude taken en taken die bij een herstart zijn blijven hangen
        for j in db.scalars(select(Job).where(Job.status.in_(["wachtrij", "bezig"]),
                                              Job.created_at < datetime.now() - timedelta(hours=3))):
            j.status, j.error = "fout", "Afgebroken (de server is waarschijnlijk herstart)."
        job = Job(kind=kind, status="wachtrij", step="In de wachtrij")
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    def runner():
        with _lock:  # één zware taak tegelijk
            db2 = SessionLocal()
            try:
                j = db2.get(Job, job_id)
                j.status, j.step = "bezig", "Bezig…"
                db2.commit()
                result = func(db2, Progress(job_id), *args, **kwargs)
                j = db2.get(Job, job_id)
                j.status, j.result, j.finished_at, j.step = "klaar", result, datetime.now(), "Klaar"
                db2.commit()
            except Exception as exc:  # noqa: BLE001
                log.exception("Taak %s mislukt", kind)
                db2.rollback()
                j = db2.get(Job, job_id)
                j.status, j.finished_at = "fout", datetime.now()
                j.error = str(exc)[:1000] or type(exc).__name__
                db2.commit()
            finally:
                db2.close()
                gc.collect()

    threading.Thread(target=runner, daemon=True, name=f"job-{kind}-{job_id}").start()
    return job_id


def mark_interrupted() -> None:
    """Bij het starten van de server: taken die nog 'bezig' waren zijn afgebroken."""
    db = SessionLocal()
    try:
        for j in db.scalars(select(Job).where(Job.status.in_(["wachtrij", "bezig"]))):
            j.status, j.error, j.finished_at = "fout", "Afgebroken doordat de server opnieuw is gestart.", datetime.now()
        db.commit()
    finally:
        db.close()
