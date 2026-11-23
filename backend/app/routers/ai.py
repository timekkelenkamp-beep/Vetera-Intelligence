from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AIAnalysis, Product, Provider, SalesCard
from ..services import ai_tasks
from ..services.ai_client import AVAILABLE_MODELS, AIBlocked, AIFailed, AIUnavailable, ai_status
from ..services.common import get_or_404, to_dict

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _run(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AIBlocked as exc:
        raise HTTPException(403, str(exc)) from exc
    except AIFailed as exc:
        raise HTTPException(502, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/status")
def status(db: Session = Depends(get_db)):
    return {**ai_status(db), "models": AVAILABLE_MODELS}


@router.post("/ask")
def ask(data: dict, db: Session = Depends(get_db)):
    q = (data.get("question") or "").strip()
    if len(q) < 3:
        raise HTTPException(422, "Stel een vraag")
    return _run(ai_tasks.ask, db, q, bool(data.get("dry_run")), bool(data.get("consent_nonpublic")))


@router.post("/extract")
def extract(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.extract_document, db, int(data.get("version_id") or 0), int(data.get("product_id") or 0),
                bool(data.get("dry_run")), bool(data.get("consent_nonpublic")))


@router.post("/sales-card")
def sales(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.sales_card, db, int(data.get("vetera_product_id") or 0),
                int(data.get("competitor_product_id") or 0), bool(data.get("dry_run")), bool(data.get("use_ai")))


@router.get("/sales-cards")
def sales_cards(competitor_product_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(SalesCard).order_by(SalesCard.created_at.desc())
    if competitor_product_id:
        stmt = stmt.where(SalesCard.competitor_product_id == competitor_product_id)
    return [to_dict(c) for c in db.scalars(stmt.limit(50))]


@router.post("/radar")
def radar(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.radar, db, bool(data.get("dry_run")), data.get("focus"), bool(data.get("web")))


@router.post("/dossier")
def dossier(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.dossier, db, int(data.get("suggestion_id") or 0), bool(data.get("dry_run")),
                bool(data.get("web")))


@router.post("/diff-analysis")
def diff_analysis(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.analyze_diff, db, int(data.get("diff_id") or 0), bool(data.get("dry_run")))


@router.post("/discover")
def discover(data: dict, db: Session = Depends(get_db)):
    return _run(ai_tasks.discover, db, bool(data.get("dry_run")))


@router.get("/analyses")
def analyses(kind: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(AIAnalysis).order_by(AIAnalysis.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(AIAnalysis.kind == kind)
    return [to_dict(a, exclude=["response"]) for a in db.scalars(stmt)]


@router.get("/analyses/{aid}")
def analysis(aid: int, db: Session = Depends(get_db)):
    return to_dict(get_or_404(db, AIAnalysis, aid, "Analyse"))
