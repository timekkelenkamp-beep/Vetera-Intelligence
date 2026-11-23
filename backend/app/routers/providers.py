from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CalculatorConnector, Document, PremiumObservation, Product, Provider, Source)
from ..services import logos
from ..services.analysis import product_summary
from ..services.common import PROVIDER_STATUSES, PROVIDER_TYPES, apply_updates, audit, get_or_404, to_dict
from ..services.monitor import FetchError
from ..services.seed import load_start_list

router = APIRouter(prefix="/api/providers", tags=["aanbieders"])
FIELDS = ["name", "website", "provider_type", "status", "description", "target_groups", "strengths",
          "weaknesses", "notes", "verification_note"]
ENUMS = {"provider_type": PROVIDER_TYPES, "status": PROVIDER_STATUSES}


def _summary(db: Session, p: Provider) -> dict:
    d = to_dict(p)
    d["product_count"] = db.scalar(select(func.count(Product.id)).where(Product.provider_id == p.id))
    d["document_count"] = db.scalar(select(func.count(Document.id)).where(Document.provider_id == p.id))
    d["premium_count"] = db.scalar(select(func.count(PremiumObservation.id)).where(PremiumObservation.provider_id == p.id))
    d["logo_url"] = f"/api/providers/{p.id}/logo" if p.logo_status == "goedgekeurd" and p.logo_path else None
    return d


@router.get("")
def list_providers(q: str | None = None, status: str | None = None, provider_type: str | None = None,
                   sort: str = "name", include_merged: bool = False, db: Session = Depends(get_db)):
    stmt = select(Provider)
    if not include_merged:
        stmt = stmt.where(Provider.status != "samengevoegd")
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Provider.name.ilike(like), Provider.website.ilike(like), Provider.description.ilike(like)))
    if status:
        stmt = stmt.where(Provider.status == status)
    if provider_type:
        stmt = stmt.where(Provider.provider_type == provider_type)
    rows = [_summary(db, p) for p in db.scalars(stmt)]
    key = {"name": lambda r: r["name"].lower(), "updated": lambda r: r["updated_at"] or "",
           "checked": lambda r: r["last_checked_at"] or "", "products": lambda r: -r["product_count"]}.get(sort)
    if key:
        rows.sort(key=key, reverse=sort in ("updated", "checked"))
    rows.sort(key=lambda r: not r["is_reference"])
    return rows


@router.post("")
def create_provider(data: dict, db: Session = Depends(get_db)):
    if not (data.get("name") or "").strip():
        raise HTTPException(422, "Naam is verplicht")
    if db.scalars(select(Provider).where(func.lower(Provider.name) == data["name"].strip().lower())).first():
        raise HTTPException(409, "Er bestaat al een aanbieder met deze naam")
    p = Provider(name=data["name"].strip(), origin="handmatig", status=data.get("status") or "actief")
    db.add(p)
    db.flush()
    apply_updates(db, p, data, FIELDS, "provider", enums=ENUMS)
    audit(db, "provider", p.id, "aangemaakt", {"name": p.name})
    db.commit()
    return _summary(db, p)


@router.post("/startlijst")
def startlist(db: Session = Depends(get_db)):
    added = load_start_list(db)
    for p in added:
        audit(db, "provider", p.id, "aangemaakt", {"name": p.name, "bron": "startlijst"}, "systeem")
    db.commit()
    return {"added": len(added)}


@router.get("/{provider_id}")
def get_provider(provider_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    d = _summary(db, p)
    vetera = db.scalars(select(Product).join(Provider, Product.provider_id == Provider.id)
                        .where(Provider.is_reference.is_(True))).first()
    prods = db.scalars(select(Product).where(Product.provider_id == p.id)).all()
    d["products"] = [{**to_dict(x), "summary": product_summary(db, x, vetera if not p.is_reference else None)} for x in prods]
    d["documents"] = []
    for doc in db.scalars(select(Document).where(Document.provider_id == p.id)):
        dd = to_dict(doc)
        dd["version_count"] = len(doc.versions)
        dd["versions"] = [{"id": v.id, "version_label": v.version_label, "doc_date": v.doc_date.isoformat() if v.doc_date else None,
                           "imported_at": v.imported_at.isoformat(), "status": v.status} for v in doc.versions]
        d["documents"].append(dd)
    d["sources"] = [to_dict(s) for s in db.scalars(select(Source).where(Source.provider_id == p.id))]
    d["calculators"] = [to_dict(c) for c in db.scalars(select(CalculatorConnector).where(CalculatorConnector.provider_id == p.id))]
    d["merged_from"] = [{"id": x.id, "name": x.name} for x in db.scalars(select(Provider).where(Provider.merged_into_id == p.id))]
    return d


@router.patch("/{provider_id}")
def update_provider(provider_id: int, data: dict, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    if p.is_reference and data.get("status") not in (None, "actief"):
        raise HTTPException(422, "De Vetera-referentie blijft actief")
    apply_updates(db, p, data, FIELDS, "provider", enums=ENUMS)
    db.commit()
    return _summary(db, p)


@router.delete("/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    if p.is_reference:
        raise HTTPException(422, "De Vetera-referentie kan niet worden verwijderd")
    audit(db, "provider", p.id, "verwijderd", {"name": p.name})
    db.delete(p)
    db.commit()
    return {"ok": True}


@router.post("/{provider_id}/merge")
def merge_provider(provider_id: int, data: dict, db: Session = Depends(get_db)):
    """Voeg aanbieder samen met een doelaanbieder: producten, documenten, bronnen en premies gaan mee."""
    src = get_or_404(db, Provider, provider_id, "Aanbieder")
    target = get_or_404(db, Provider, int(data.get("target_id") or 0), "Doelaanbieder")
    if src.id == target.id or src.is_reference:
        raise HTTPException(422, "Ongeldige samenvoeging")
    moved = {}
    for model in (Product, Document, Source, PremiumObservation, CalculatorConnector):
        rows = db.scalars(select(model).where(model.provider_id == src.id)).all()
        for r in rows:
            r.provider_id = target.id
        moved[model.__tablename__] = len(rows)
    src.status = "samengevoegd"
    src.merged_into_id = target.id
    audit(db, "provider", src.id, "samengevoegd", {"doel": target.id, **moved})
    db.commit()
    return {"ok": True, "moved": moved}


# ---------------------------------------------------------------- logo's
@router.get("/{provider_id}/logo")
def get_logo(provider_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    if not p.logo_path or not Path(p.logo_path).exists():
        raise HTTPException(404, "Geen goedgekeurd logo")
    return FileResponse(p.logo_path, media_type=_mt(p.logo_path), headers={"Cache-Control": "no-cache"})


def _mt(path: str) -> str:
    return {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp",
            ".ico": "image/x-icon"}.get(Path(path).suffix.lower(), "application/octet-stream")


@router.get("/{provider_id}/logo/candidates")
def logo_candidates(provider_id: int, db: Session = Depends(get_db)):
    get_or_404(db, Provider, provider_id, "Aanbieder")
    return logos.list_candidates(provider_id)


@router.get("/{provider_id}/logo/candidates/{name}")
def logo_candidate_file(provider_id: int, name: str):
    path = logos.candidate_dir(provider_id) / Path(name).name
    if not path.exists() or path.name.endswith(".txt"):
        raise HTTPException(404, "Niet gevonden")
    return FileResponse(path, media_type=_mt(str(path)))


@router.post("/{provider_id}/logo/discover")
def logo_discover(provider_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    if not p.website:
        raise HTTPException(422, "Vul eerst de officiële website in")
    try:
        res = logos.discover_candidates(p.id, p.website)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    if res["candidates"] and p.logo_status == "geen":
        p.logo_status = "kandidaat"
        db.commit()
    return res


@router.post("/{provider_id}/logo/upload")
async def logo_upload(provider_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    data = await file.read()
    try:
        c = logos.store_candidate(p.id, data, f"Handmatig geüpload: {file.filename}")
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    if p.logo_status == "geen":
        p.logo_status = "kandidaat"
        db.commit()
    return c


@router.post("/{provider_id}/logo/candidates/{name}/transparent")
def logo_transparent(provider_id: int, name: str, tolerance: int = 18):
    try:
        return logos.remove_background(provider_id, name, max(0, min(tolerance, 80)))
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/{provider_id}/logo/candidates/{name}/approve")
def logo_approve(provider_id: int, name: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    try:
        p.logo_path = logos.approve(provider_id, name)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    origin = (logos.candidate_dir(provider_id) / (Path(name).name + ".bron.txt"))
    p.logo_source_url = origin.read_text(encoding="utf-8")[:1000] if origin.exists() else None
    p.logo_status = "goedgekeurd"
    audit(db, "provider", p.id, "logo_goedgekeurd", {"bestand": name})
    db.commit()
    return _summary(db, p)


@router.delete("/{provider_id}/logo")
def logo_remove(provider_id: int, db: Session = Depends(get_db)):
    p = get_or_404(db, Provider, provider_id, "Aanbieder")
    if p.logo_path and Path(p.logo_path).exists():
        Path(p.logo_path).unlink()
    p.logo_path, p.logo_status = None, "geen"
    db.commit()
    return {"ok": True}
