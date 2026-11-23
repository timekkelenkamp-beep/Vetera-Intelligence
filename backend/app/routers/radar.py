from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ImprovementSuggestion, ResearchDossier
from ..services.analysis import local_radar_signals
from ..services.common import apply_updates, audit, get_or_404, to_dict

router = APIRouter(prefix="/api/radar", tags=["verbeterradar"])
STATUSES = {"nieuw", "onderzoeken", "interessant", "uitwerken", "afgerond", "afgewezen"}
CATEGORIES = {"Productverbetering", "Voorwaardenverbetering", "Commerciële kans", "Nieuwe doelgroep",
              "Innovatief concept", "Concurrentievoordeel", "Proces- of serviceverbetering"}
FIELDS = ["title", "category", "kind", "summary", "gap", "vetera_situation", "market_context", "suggestion",
          "customer_benefits", "commercial_benefits", "risks", "confidence", "priority", "follow_up", "status",
          "priority_factors"]
ENUMS = {"status": STATUSES, "category": CATEGORIES, "kind": {"datagedreven", "innovatiehypothese"},
         "priority": {"hoog", "middel", "laag"}, "confidence": {"hoog", "middel", "laag"}}


def _d(db, s):
    d = to_dict(s)
    d["dossier_count"] = len(db.scalars(select(ResearchDossier.id).where(ResearchDossier.suggestion_id == s.id)).all())
    return d


@router.get("/suggestions")
def list_suggestions(status: str | None = None, kind: str | None = None, category: str | None = None,
                     db: Session = Depends(get_db)):
    stmt = select(ImprovementSuggestion)
    if status:
        stmt = stmt.where(ImprovementSuggestion.status == status)
    if kind:
        stmt = stmt.where(ImprovementSuggestion.kind == kind)
    if category:
        stmt = stmt.where(ImprovementSuggestion.category == category)
    order = {"hoog": 0, "middel": 1, "laag": 2}
    rows = [_d(db, s) for s in db.scalars(stmt)]
    rows.sort(key=lambda r: (order.get(r["priority"], 3), r["created_at"]), reverse=False)
    return rows


@router.post("/suggestions")
def create_suggestion(data: dict, db: Session = Depends(get_db)):
    if not data.get("title"):
        raise HTTPException(422, "Titel is verplicht")
    s = ImprovementSuggestion(title=data["title"], category=data.get("category") or "Productverbetering", origin="handmatig")
    db.add(s)
    db.flush()
    apply_updates(db, s, data, FIELDS, "suggestion", enums=ENUMS)
    db.commit()
    return _d(db, s)


@router.post("/scan")
def scan(db: Session = Depends(get_db)):
    """Lokale, datagedreven signalering (zonder AI)."""
    created = local_radar_signals(db)
    return {"created": len(created)}


@router.get("/suggestions/{sid}")
def get_suggestion(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, ImprovementSuggestion, sid, "Suggestie")
    d = _d(db, s)
    d["dossiers"] = [to_dict(x) for x in db.scalars(select(ResearchDossier).where(ResearchDossier.suggestion_id == sid)
                                                     .order_by(ResearchDossier.created_at.desc()))]
    return d


@router.patch("/suggestions/{sid}")
def update_suggestion(sid: int, data: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, ImprovementSuggestion, sid, "Suggestie")
    apply_updates(db, s, data, FIELDS, "suggestion", enums=ENUMS)
    db.commit()
    return _d(db, s)


@router.delete("/suggestions/{sid}")
def delete_suggestion(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, ImprovementSuggestion, sid, "Suggestie")
    audit(db, "suggestion", s.id, "verwijderd", {"title": s.title})
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/dossiers")
def list_dossiers(db: Session = Depends(get_db)):
    return [to_dict(d) for d in db.scalars(select(ResearchDossier).order_by(ResearchDossier.created_at.desc()))]
