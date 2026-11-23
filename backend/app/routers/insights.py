from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..services import insights

router = APIRouter(prefix="/api/insights", tags=["inzichten"])


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/positioning")
def positioning(profile_id: int, min_coverage: float = 0.5, db: Session = Depends(get_db)):
    return _run(insights.positioning, db, profile_id, max(0.1, min(min_coverage, 1.0)))


@router.get("/advice/questions")
def advice_questions():
    return insights.ADVICE_QUESTIONS


@router.post("/advice")
def advice(data: dict, db: Session = Depends(get_db)):
    return insights.advice(db, data.get("answers") or {})


@router.post("/whatif")
def whatif(data: dict, db: Session = Depends(get_db)):
    premium = data.get("premium")
    return _run(insights.whatif, db, int(data.get("score_profile_id") or 0), int(data.get("product_id") or 0),
                {str(k): v for k, v in (data.get("changes") or {}).items()},
                float(premium) if premium not in (None, "") else None)


@router.get("/battlecard/{provider_id}")
def battlecard(provider_id: int, db: Session = Depends(get_db)):
    return _run(insights.battlecard, db, provider_id)


@router.get("/timeline/{provider_id}")
def timeline(provider_id: int, db: Session = Depends(get_db)):
    return _run(insights.timeline, db, provider_id)


@router.get("/market-brief")
def market_brief(since: str | None = None, until: str | None = None, db: Session = Depends(get_db)):
    try:
        s = datetime.fromisoformat(since) if since else None
        u = datetime.fromisoformat(until) if until else None
    except ValueError as exc:
        raise HTTPException(422, "Ongeldige datum") from exc
    return insights.market_brief(db, s, u)


@router.get("/quicksearch")
def quicksearch(q: str, db: Session = Depends(get_db)):
    return insights.quicksearch(db, q)
