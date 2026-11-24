from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
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
def discover(data: dict, background: BackgroundTasks, db: Session = Depends(get_db)):
    res = _run(ai_tasks.discover, db, bool(data.get("dry_run")))
    if res.get("added"):
        from ..services.logos import auto_logo_background
        background.add_task(auto_logo_background, res["added"])
    return res


@router.get("/analyses")
def analyses(kind: str | None = None, limit: int = 100, db: Session = Depends(get_db)):
    stmt = select(AIAnalysis).order_by(AIAnalysis.created_at.desc()).limit(limit)
    if kind:
        stmt = stmt.where(AIAnalysis.kind == kind)
    return [to_dict(a, exclude=["response"]) for a in db.scalars(stmt)]


@router.get("/analyses/{aid}")
def analysis(aid: int, db: Session = Depends(get_db)):
    return to_dict(get_or_404(db, AIAnalysis, aid, "Analyse"))


@router.post("/research")
def research(data: dict, db: Session = Depends(get_db)):
    """Automatisch onderzoek van de officiële website. Preview direct; uitvoering als achtergrondtaak."""
    from ..services import research as svc
    from ..services.jobs import start_job
    pid = int(data.get("provider_id") or 0)
    if data.get("dry_run"):
        return _run(svc.start, db, pid, True)
    _check_ai(db, web=True)

    def job(db2, progress):
        return svc.start(db2, pid, False, progress)
    return {"job_id": start_job("productonderzoek", job)}


@router.post("/research/import")
def research_import(data: dict, db: Session = Depends(get_db)):
    from ..services import research as svc
    from ..services.jobs import start_job
    from ..services.logos import auto_logo
    from ..models import Provider
    pid, aid = int(data.get("provider_id") or 0), int(data.get("analysis_id") or 0)
    sel = [str(x) for x in (data.get("selection") or [])]

    def job(db2, progress):
        res = svc.import_selected(db2, pid, aid, sel, progress)
        p = db2.get(Provider, pid)
        if p:
            progress("Logo ophalen…")
            auto_logo(db2, p)
        return res
    return {"job_id": start_job("import", job)}


@router.post("/add-by-name")
def add_by_name(data: dict, db: Session = Depends(get_db)):
    """Naam invullen → opzoeken → website doorzoeken → importeren → optioneel analyseren."""
    from ..services import research as svc
    from ..services.jobs import start_job
    name = (data.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(422, "Vul een naam in")
    if data.get("dry_run"):
        return svc.find_provider_preview(db, name)
    _check_ai(db, web=True)
    analyze = bool(data.get("analyze", True))
    return {"job_id": start_job("opzoeken", lambda db2, progress: svc.add_by_name(db2, progress, name, analyze))}


def _check_ai(db: Session, web: bool = False):
    st = ai_status(db)
    if not st["configured"]:
        raise HTTPException(503, st["message"])
    if not st["enabled"]:
        raise HTTPException(503, "AI-functies zijn uitgeschakeld in Instellingen.")
    if web and not st["web_research"]:
        raise HTTPException(403, "Webonderzoek door AI is niet geactiveerd (Instellingen → AI).")


@router.get("/jobs/{job_id}")
def job_status(job_id: int, db: Session = Depends(get_db)):
    from ..models import Job
    j = get_or_404(db, Job, job_id, "Taak")
    return to_dict(j)
