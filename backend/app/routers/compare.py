from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feature, Finding, Product, Provider, ScoreProfile
from ..services.analysis import compute_scores, finding_dict, matrix, product_summary
from ..services.common import FINDING_STATUSES, apply_updates, audit, get_or_404, to_dict
from ..services.documents import verify_quote
from ..services.reports import _matrix_section, render_pdf, render_xlsx, STANDARD_LIMITATIONS

router = APIRouter(prefix="/api", tags=["vergelijking"])


def _ids(s: str | None) -> list[int]:
    return [int(x) for x in (s or "").split(",") if x.strip().isdigit()]


# ---------------------------------------------------------------- rubrieken
@router.get("/features")
def list_features(include_inactive: bool = False, db: Session = Depends(get_db)):
    stmt = select(Feature).order_by(Feature.sort_order)
    if not include_inactive:
        stmt = stmt.where(Feature.active.is_(True))
    return [to_dict(f) for f in db.scalars(stmt)]


@router.post("/features")
def create_feature(data: dict, db: Session = Depends(get_db)):
    if not data.get("label") or not data.get("category"):
        raise HTTPException(422, "Rubriek en kenmerk zijn verplicht")
    import re
    key = data.get("key") or re.sub(r"[^a-z0-9]+", "_", f"eigen_{data['label'].lower()}").strip("_")
    if db.scalars(select(Feature).where(Feature.key == key)).first():
        raise HTTPException(409, "Kenmerk bestaat al")
    mx = max([f.sort_order for f in db.scalars(select(Feature))] or [0])
    f = Feature(key=key, category=data["category"], label=data["label"], description=data.get("description"),
                value_type=data.get("value_type") or "status", scoring_aspect=data.get("scoring_aspect"),
                keywords=[k.strip() for k in (data.get("keywords") or []) if k.strip()], sort_order=mx + 1)
    db.add(f)
    db.commit()
    return to_dict(f)


@router.patch("/features/{fid}")
def update_feature(fid: int, data: dict, db: Session = Depends(get_db)):
    f = get_or_404(db, Feature, fid, "Kenmerk")
    apply_updates(db, f, data, ["label", "category", "description", "value_type", "scoring_aspect", "keywords",
                                "active", "sort_order"], "feature")
    db.commit()
    return to_dict(f)


# ---------------------------------------------------------------- bevindingen
@router.get("/findings")
def list_findings(product_id: int | None = None, feature_id: int | None = None, history: bool = False,
                  review_status: str | None = None, origin: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Finding)
    if product_id:
        stmt = stmt.where(Finding.product_id == product_id)
    if feature_id:
        stmt = stmt.where(Finding.feature_id == feature_id)
    if not history:
        stmt = stmt.where(Finding.is_current.is_(True))
    if review_status:
        stmt = stmt.where(Finding.review_status == review_status)
    if origin:
        stmt = stmt.where(Finding.origin == origin)
    out = []
    for f in db.scalars(stmt.order_by(Finding.created_at.desc()).limit(1000)):
        d = finding_dict(db, f)
        d["feature_label"] = f.feature.label
        d["feature_category"] = f.feature.category
        p = db.get(Product, f.product_id)
        d["product_name"] = p.name if p else None
        d["provider_name"] = db.get(Provider, p.provider_id).name if p else None
        out.append(d)
    return out


def _validate_finding(data: dict):
    if data.get("status") and data["status"] not in FINDING_STATUSES:
        raise HTTPException(422, "Ongeldige status")


@router.post("/findings")
def create_finding(data: dict, db: Session = Depends(get_db)):
    """Handmatige bevinding (menselijke invoer): wordt vastgezet en niet door AI overschreven."""
    _validate_finding(data)
    get_or_404(db, Product, int(data.get("product_id") or 0), "Product")
    get_or_404(db, Feature, int(data.get("feature_id") or 0), "Kenmerk")
    old = db.scalars(select(Finding).where(Finding.product_id == data["product_id"], Finding.feature_id == data["feature_id"],
                                           Finding.is_current.is_(True))).all()
    f = Finding(product_id=int(data["product_id"]), feature_id=int(data["feature_id"]), origin="handmatig",
                review_status="goedgekeurd", locked=True)
    for k in ("status", "value_text", "value_number", "explanation", "document_version_id", "page_number", "article", "quote"):
        if k in data:
            setattr(f, k, data[k] if data[k] != "" else None)
    f.status = f.status or "menselijke_beoordeling"
    if f.quote and f.document_version_id:
        f.quote_verified = verify_quote(db, f.document_version_id, f.page_number, f.quote)["verified"]
    db.add(f)
    db.flush()
    for o in old:
        o.is_current = False
        o.superseded_by_id = f.id
    audit(db, "finding", f.id, "handmatig_vastgelegd", {"status": f.status, "vervangt": [o.id for o in old]})
    db.commit()
    return finding_dict(db, f)


@router.post("/findings/{fid}/review")
def review_finding(fid: int, data: dict, db: Session = Depends(get_db)):
    """action = goedkeuren | corrigeren | afwijzen | ontgrendelen"""
    f = get_or_404(db, Finding, fid, "Bevinding")
    action = data.get("action")
    if action == "goedkeuren":
        f.review_status, f.locked = "goedgekeurd", True
        audit(db, "finding", f.id, "goedgekeurd")
    elif action == "afwijzen":
        f.review_status, f.is_current = "afgewezen", False
        audit(db, "finding", f.id, "afgewezen", {"reden": data.get("note")})
    elif action == "ontgrendelen":
        f.locked = False
        audit(db, "finding", f.id, "ontgrendeld")
    elif action == "corrigeren":
        _validate_finding(data)
        nf = Finding(product_id=f.product_id, feature_id=f.feature_id, origin="handmatig", review_status="gecorrigeerd",
                     locked=True, status=f.status, value_text=f.value_text, value_number=f.value_number,
                     explanation=f.explanation, document_version_id=f.document_version_id, page_number=f.page_number,
                     article=f.article, quote=f.quote, quote_verified=f.quote_verified, confidence="hoog")
        changes = {}
        for k in ("status", "value_text", "value_number", "explanation", "page_number", "article", "quote",
                  "document_version_id"):
            if k in data and data[k] != getattr(f, k):
                changes[k] = {"oud": getattr(f, k), "nieuw": data[k]}
                setattr(nf, k, data[k] if data[k] != "" else None)
        if nf.quote and nf.document_version_id:
            nf.quote_verified = verify_quote(db, nf.document_version_id, nf.page_number, nf.quote)["verified"]
        db.add(nf)
        db.flush()
        f.is_current, f.superseded_by_id = False, nf.id
        audit(db, "finding", nf.id, "gecorrigeerd", {"vorige": f.id, **changes})
        db.commit()
        return finding_dict(db, nf)
    else:
        raise HTTPException(422, "Onbekende actie")
    db.commit()
    return finding_dict(db, f)


@router.post("/findings/{fid}/verify")
def verify_finding(fid: int, db: Session = Depends(get_db)):
    f = get_or_404(db, Finding, fid, "Bevinding")
    res = verify_quote(db, f.document_version_id, f.page_number, f.quote)
    f.quote_verified = res["verified"]
    if res["verified"] and res["page_number"]:
        f.page_number = res["page_number"]
    db.commit()
    return res


@router.get("/findings/{fid}/history")
def finding_history(fid: int, db: Session = Depends(get_db)):
    f = get_or_404(db, Finding, fid, "Bevinding")
    rows = db.scalars(select(Finding).where(Finding.product_id == f.product_id, Finding.feature_id == f.feature_id)
                      .order_by(Finding.created_at.desc())).all()
    return [finding_dict(db, x) for x in rows]


# ---------------------------------------------------------------- vergelijker
@router.get("/compare/matrix")
def compare_matrix(product_ids: str, reference: int | None = None, category: str | None = None,
                   only_differences: bool = False, only_unknown: bool = False, q: str | None = None,
                   db: Session = Depends(get_db)):
    return matrix(db, _ids(product_ids), reference, category, only_differences, only_unknown, q)


@router.get("/compare/cards")
def compare_cards(product_ids: str | None = None, reference: int | None = None, db: Session = Depends(get_db)):
    ids = _ids(product_ids)
    products = [db.get(Product, i) for i in ids] if ids else db.scalars(
        select(Product).join(Provider, Product.provider_id == Provider.id).where(Provider.status == "actief")).all()
    ref = db.get(Product, reference) if reference else None
    return [product_summary(db, p, ref) for p in products if p]


@router.get("/compare/export")
def compare_export(product_ids: str, reference: int | None = None, fmt: str = "xlsx", db: Session = Depends(get_db)):
    products = [p for p in (db.get(Product, i) for i in _ids(product_ids)) if p]
    if not products:
        raise HTTPException(422, "Selecteer minimaal één product")
    sources: list[str] = []
    sec, summary = _matrix_section(db, products, db.get(Product, reference) if reference else None, sources)
    content = {"title": "Voorwaardenvergelijking", "type_label": "Voorwaardenanalyse", "date": date.today().isoformat(),
               "products": [f"{db.get(Provider, p.provider_id).name} – {p.name}" for p in products],
               "management_summary": summary, "sections": [sec], "sources": sources, "limitations": STANDARD_LIMITATIONS}
    tmp = Path(tempfile.mkdtemp()) / f"voorwaardenvergelijking_{date.today().isoformat()}.{'pdf' if fmt == 'pdf' else 'xlsx'}"
    (render_pdf if fmt == "pdf" else render_xlsx)(content, tmp)
    return FileResponse(tmp, filename=tmp.name, media_type="application/pdf" if fmt == "pdf" else
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------------------------------------------------------------- scores
@router.get("/score-profiles")
def list_score_profiles(db: Session = Depends(get_db)):
    return [to_dict(s) for s in db.scalars(select(ScoreProfile))]


@router.post("/score-profiles")
def create_score_profile(data: dict, db: Session = Depends(get_db)):
    s = ScoreProfile(name=data.get("name") or "Nieuw scoreprofiel", weights=data.get("weights") or
                     {"voorwaarden": 40, "premie": 30, "acceptatie": 20, "flexibiliteit": 10})
    db.add(s)
    db.flush()
    apply_updates(db, s, data, ["description", "reference_profile_id", "vehicle_category", "min_coverage"], "score_profile")
    db.commit()
    return to_dict(s)


@router.patch("/score-profiles/{sid}")
def update_score_profile(sid: int, data: dict, db: Session = Depends(get_db)):
    s = get_or_404(db, ScoreProfile, sid, "Scoreprofiel")
    if "weights" in data:
        w = {k: float(v) for k, v in data["weights"].items() if k in ("voorwaarden", "premie", "acceptatie", "flexibiliteit")}
        if any(v < 0 for v in w.values()):
            raise HTTPException(422, "Wegingen mogen niet negatief zijn")
        data["weights"] = w
    apply_updates(db, s, data, ["name", "description", "weights", "reference_profile_id", "vehicle_category",
                                "min_coverage"], "score_profile")
    db.commit()
    return to_dict(s)


@router.delete("/score-profiles/{sid}")
def delete_score_profile(sid: int, db: Session = Depends(get_db)):
    s = get_or_404(db, ScoreProfile, sid, "Scoreprofiel")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.get("/scores")
def scores(score_profile_id: int, product_ids: str | None = None, db: Session = Depends(get_db)):
    sp = get_or_404(db, ScoreProfile, score_profile_id, "Scoreprofiel")
    ids = _ids(product_ids)
    if not ids:
        stmt = select(Product.id).join(Provider, Product.provider_id == Provider.id).where(
            Provider.status == "actief", Product.canonical_product_id.is_(None))
        if sp.vehicle_category:
            stmt = stmt.where(Product.vehicle_category.in_([sp.vehicle_category, "meerdere"]))
        ids = list(db.scalars(stmt))
    return compute_scores(db, sp, ids)
