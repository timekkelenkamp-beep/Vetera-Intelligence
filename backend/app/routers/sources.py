from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_db
from ..models import MonitorRun, Notification, Provider, Source, SourceCheck
from ..services.common import SOURCE_TYPES, VISIBILITY, apply_updates, audit, get_or_404, to_dict
from ..services.monitor import FetchError, run_monitor, schedule_status, validate_external_url

router = APIRouter(prefix="/api", tags=["bronnen", "monitor"])
FIELDS = ["url", "title", "provider_id", "product_id", "source_type", "document_type", "kind", "published_at",
          "version_label", "access_status", "permission_note", "visibility", "monitor_enabled", "notes"]
ENUMS = {"source_type": SOURCE_TYPES, "visibility": VISIBILITY,
         "access_status": {"toegestaan", "onbekend", "niet_toegestaan", "robots_blokkeert"},
         "kind": {"document", "pagina", "tarief", "calculator"}}


@router.get("/sources")
def list_sources(provider_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Source)
    if provider_id:
        stmt = stmt.where(Source.provider_id == provider_id)
    out = []
    for s in db.scalars(stmt.order_by(Source.updated_at.desc())):
        d = to_dict(s)
        d["provider_name"] = db.get(Provider, s.provider_id).name if s.provider_id else None
        out.append(d)
    return out


@router.post("/sources")
def create_source(data: dict, db: Session = Depends(get_db)):
    if data.get("url"):
        try:
            validate_external_url(data["url"])
        except FetchError as exc:
            raise HTTPException(422, str(exc)) from exc
        if db.scalars(select(Source).where(Source.url == data["url"].strip())).first():
            raise HTTPException(409, "Deze bron staat al in het register")
    s = Source()
    db.add(s)
    apply_updates(db, s, {"source_type": "niet_geverifieerd", **data}, FIELDS, "source",
                  date_fields=["published_at"], enums=ENUMS)
    db.flush()
    audit(db, "source", s.id, "aangemaakt", {"url": s.url})
    db.commit()
    return to_dict(s)


@router.patch("/sources/{sid}")
def update_source(sid: int, data: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, Source, sid, "Bron")
    if data.get("url") and data["url"] != s.url:
        try:
            validate_external_url(data["url"])
        except FetchError as exc:
            raise HTTPException(422, str(exc)) from exc
    apply_updates(db, s, data, FIELDS, "source", date_fields=["published_at"], enums=ENUMS)
    db.commit()
    return to_dict(s)


@router.delete("/sources/{sid}")
def delete_source(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, Source, sid, "Bron")
    audit(db, "source", s.id, "verwijderd", {"url": s.url})
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/sources/{sid}/checks")
def source_checks(sid: int, db: Session = Depends(get_db)):
    return [to_dict(c) for c in db.scalars(select(SourceCheck).where(SourceCheck.source_id == sid)
                                           .order_by(SourceCheck.checked_at.desc()).limit(50))]


# ---------------------------------------------------------------- monitor
def _bg_run(trigger: str, ids: list[int] | None):
    db = SessionLocal()
    try:
        run_monitor(db, trigger, ids)
    finally:
        db.close()


@router.get("/monitor/status")
def monitor_status(db: Session = Depends(get_db)):
    st = schedule_status(db)
    running = db.scalars(select(MonitorRun).where(MonitorRun.status == "bezig")).first()
    st["running"] = to_dict(running) if running else None
    from ..config import get_settings
    st["auto"] = get_settings().auto_monitor
    return st


@router.post("/monitor/run")
def monitor_run(data: dict, background: BackgroundTasks, db: Session = Depends(get_db)):
    if db.scalars(select(MonitorRun).where(MonitorRun.status == "bezig")).first():
        raise HTTPException(409, "Er loopt al een broncontrole")
    trigger = data.get("trigger") if data.get("trigger") in ("handmatig", "inhaal") else "handmatig"
    ids = data.get("source_ids")
    if data.get("sync"):
        return to_dict(run_monitor(db, trigger, ids))
    background.add_task(_bg_run, trigger, ids)
    return {"started": True}


@router.get("/monitor/runs")
def monitor_runs(db: Session = Depends(get_db)):
    return [to_dict(r) for r in db.scalars(select(MonitorRun).order_by(MonitorRun.started_at.desc()).limit(50))]


@router.get("/monitor/runs/{rid}")
def monitor_run_detail(rid: int, db: Session = Depends(get_db)):
    r = get_or_404(db, MonitorRun, rid, "Controle")
    d = to_dict(r)
    d["checks"] = []
    for c in db.scalars(select(SourceCheck).where(SourceCheck.run_id == rid)):
        x = to_dict(c)
        s = db.get(Source, c.source_id)
        x["source_title"] = (s.title or s.url) if s else None
        d["checks"].append(x)
    return d


# ---------------------------------------------------------------- meldingen
@router.get("/notifications")
def list_notifications(status: str | None = None, type: str | None = None, flagged: bool | None = None,
                       db: Session = Depends(get_db)):
    stmt = select(Notification)
    if status == "open":
        stmt = stmt.where(Notification.status != "gearchiveerd")
    elif status:
        stmt = stmt.where(Notification.status == status)
    if type:
        stmt = stmt.where(Notification.type == type)
    if flagged is not None:
        stmt = stmt.where(Notification.flagged.is_(flagged))
    return [to_dict(n) for n in db.scalars(stmt.order_by(Notification.created_at.desc()).limit(500))]


@router.patch("/notifications/{nid}")
def update_notification(nid: int, data: dict, db: Session = Depends(get_db)):
    n = get_or_404(db, Notification, nid, "Melding")
    if data.get("status") in ("nieuw", "gelezen", "gearchiveerd"):
        n.status = data["status"]
    if "flagged" in data:
        n.flagged = bool(data["flagged"])
    db.commit()
    return to_dict(n)


@router.post("/notifications/mark-all-read")
def mark_all(db: Session = Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.status == "nieuw")):
        n.status = "gelezen"
    db.commit()
    return {"ok": True}
