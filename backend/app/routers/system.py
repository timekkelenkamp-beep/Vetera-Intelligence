from __future__ import annotations

import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, reset_engine
from ..models import (AuditLog, Document, DocumentDiff, DocumentVersion, ExcelImport, ImprovementSuggestion,
                      MonitorRun, Notification, PremiumObservation, Product, Provider, QualityResolution)
from ..services.ai_client import AVAILABLE_MODELS, ai_status
from ..services.common import audit, to_dict
from ..services.monitor import schedule_status
from ..services.premiums import compare_profile
from ..services.quality import run_checks
from ..services.settings_store import all_settings, set_setting

router = APIRouter(prefix="/api", tags=["systeem"])

EDITABLE_SETTINGS = {
    "ai_enabled": bool, "ai_model": str, "ai_effort": str, "ai_monthly_budget_eur": float,
    "ai_max_request_cost_eur": float, "ai_allow_nonpublic": bool, "ai_web_research": bool,
    "monitor_interval_days": int, "monitor_mode": str, "monitor_request_delay_s": float, "premium_stale_months": int,
    "premium_difference_alert_pct": float, "onboarding_done": bool,
}


@router.get("/health")
def health():
    return {"ok": True, "time": datetime.now().isoformat()}


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    competitors = db.scalar(select(func.count(Provider.id)).where(Provider.is_reference.is_(False),
                                                                  Provider.status == "actief"))
    to_review = db.scalar(select(func.count(Provider.id)).where(Provider.status == "te_beoordelen"))
    # producten tellen zonder distributie-duplicaten
    products = db.scalar(select(func.count(Product.id)).where(Product.canonical_product_id.is_(None)))
    docs = db.scalar(select(func.count(DocumentVersion.id)).where(DocumentVersion.status == "gereed"))
    since = datetime.now() - timedelta(days=30)
    developments = db.scalar(select(func.count(DocumentDiff.id)).where(DocumentDiff.created_at >= since))
    new_notes = db.scalar(select(func.count(Notification.id)).where(Notification.status == "nieuw"))
    sugg_new = db.scalar(select(func.count(ImprovementSuggestion.id)).where(ImprovementSuggestion.status == "nieuw"))
    ongoing = db.scalar(select(func.count(ImprovementSuggestion.id)).where(
        ImprovementSuggestion.status.in_(["onderzoeken", "interessant", "uitwerken"])))
    vetera = db.scalars(select(Provider).where(Provider.is_reference.is_(True))).first()
    vetera_products = db.scalar(select(func.count(Product.id)).where(Product.provider_id == vetera.id)) if vetera else 0
    # recente premieverschillen (alleen profielen met Vetera-basis)
    recent_diffs = []
    from ..models import ReferenceProfile
    for prof in db.scalars(select(ReferenceProfile)):
        c = compare_profile(db, prof.id)
        if c["baseline"] != "vetera":
            continue
        for r in c["rows"]:
            if r["diff_pct"] is not None:
                recent_diffs.append({"profile": prof.name, "profile_id": prof.id, "provider": r["provider_name"],
                                     "diff_pct": r["diff_pct"], "diff_abs": r["diff_abs"],
                                     "comparable": r["fully_comparable"], "date": r["reference_date"]})
    recent_diffs.sort(key=lambda r: r["date"] or "", reverse=True)
    latest = []
    for n in db.scalars(select(Notification).where(Notification.status != "gearchiveerd")
                        .order_by(Notification.created_at.desc()).limit(6)):
        latest.append(to_dict(n))
    return {
        "counts": {"competitors": competitors, "providers_to_review": to_review, "products": products,
                   "documents": docs, "developments_30d": developments, "notifications_new": new_notes,
                   "suggestions_new": sugg_new, "research_ongoing": ongoing,
                   "premiums": db.scalar(select(func.count(PremiumObservation.id))),
                   "vetera_products": vetera_products},
        "premium_differences": recent_diffs[:8],
        "notifications": latest,
        "monitor": schedule_status(db),
        "ai": ai_status(db),
        "onboarding": {
            "vetera_product": vetera_products > 0,
            "competitors": competitors > 0 or to_review > 0,
            "documents": docs > 0,
            "premiums": db.scalar(select(func.count(PremiumObservation.id))) > 0,
            "ai": ai_status(db)["configured"],
        },
    }


@router.get("/settings")
def get_settings_(db: Session = Depends(get_db)):
    s = all_settings(db)
    s["_models"] = AVAILABLE_MODELS
    s["_ai"] = ai_status(db)
    s["_paths"] = {"data_dir": str(get_settings().data_dir)}
    s["_host"] = f"{get_settings().host}:{get_settings().port}"
    s["_cloud"] = get_settings().cloud
    s["_auto_monitor"] = get_settings().auto_monitor
    return s


@router.patch("/settings")
def update_settings(data: dict, db: Session = Depends(get_db)):
    changed = {}
    for k, v in data.items():
        if k not in EDITABLE_SETTINGS:
            continue
        typ = EDITABLE_SETTINGS[k]
        try:
            val = typ(v) if typ is not bool else bool(v)
        except (TypeError, ValueError):
            raise HTTPException(422, f"Ongeldige waarde voor {k}")
        if k == "ai_model" and val not in AVAILABLE_MODELS:
            raise HTTPException(422, "Onbekend model")
        if k == "monitor_mode" and val not in ("handmatig", "automatisch"):
            raise HTTPException(422, "Kies handmatig of automatisch")
        if k == "monitor_interval_days" and not 1 <= val <= 400:
            raise HTTPException(422, "Interval moet tussen 1 en 400 dagen liggen")
        if k == "ai_effort" and val not in ("low", "medium", "high", "xhigh", "max"):
            raise HTTPException(422, "Onbekend effort-niveau")
        set_setting(db, k, val)
        changed[k] = val
    if changed:
        audit(db, "settings", None, "bijgewerkt", changed)
    db.commit()
    return get_settings_(db)


@router.get("/audit")
def audit_log(entity: str | None = None, entity_id: int | None = None, limit: int = 200, db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.at.desc()).limit(limit)
    if entity:
        stmt = stmt.where(AuditLog.entity == entity)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    return [to_dict(a) for a in db.scalars(stmt)]


# ---------------------------------------------------------------- kwaliteit
@router.get("/quality")
def quality(include_resolved: bool = False, db: Session = Depends(get_db)):
    return run_checks(db, include_resolved)


@router.post("/quality/resolve")
def quality_resolve(data: dict, db: Session = Depends(get_db)):
    key = data.get("key")
    if not key:
        raise HTTPException(422, "Sleutel ontbreekt")
    r = db.scalars(select(QualityResolution).where(QualityResolution.issue_key == key)).first()
    if r:
        r.resolution, r.note = data.get("resolution", "geaccepteerd"), data.get("note")
    else:
        db.add(QualityResolution(issue_key=key, resolution=data.get("resolution", "geaccepteerd"), note=data.get("note")))
    audit(db, "quality", None, "beoordeeld", {"key": key, "resolutie": data.get("resolution")})
    db.commit()
    return {"ok": True}


@router.post("/premiums/{oid}/mark-historical")
def mark_hist(oid: int, db: Session = Depends(get_db)):
    o = db.get(PremiumObservation, oid)
    if not o:
        raise HTTPException(404, "Premie niet gevonden")
    o.is_historical = True
    o.observation_type = "historisch_tarief"
    audit(db, "premium", o.id, "gemarkeerd_historisch")
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- back-up & herstel
def make_backup() -> Path:
    s = get_settings()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = s.backups_dir / f"vetera_backup_{stamp}.zip"
    tmpdb = Path(tempfile.mkdtemp()) / "vetera.db"
    src = sqlite3.connect(str(s.db_path))
    dst = sqlite3.connect(str(tmpdb))
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tmpdb, "vetera.db")
        for sub in ("documents", "imports", "logos", "reports"):
            base = s.data_dir / sub
            for f in base.rglob("*"):
                if f.is_file():
                    z.write(f, f"{sub}/{f.relative_to(base).as_posix()}")
    return out


@router.post("/backup")
def backup():
    p = make_backup()
    return {"file": p.name, "size": p.stat().st_size}


@router.get("/backups")
def list_backups():
    d = get_settings().backups_dir
    return [{"file": f.name, "size": f.stat().st_size, "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()}
            for f in sorted(d.glob("*.zip"), reverse=True)]


@router.get("/backups/{name}")
def download_backup(name: str):
    p = get_settings().backups_dir / Path(name).name
    if not p.exists():
        raise HTTPException(404, "Back-up niet gevonden")
    return FileResponse(p, filename=p.name, media_type="application/zip")


@router.post("/restore")
async def restore(file: UploadFile = File(...)):
    s = get_settings()
    tmp = Path(tempfile.mkdtemp())
    zpath = tmp / "restore.zip"
    zpath.write_bytes(await file.read())
    try:
        with zipfile.ZipFile(zpath) as z:
            names = z.namelist()
            if "vetera.db" not in names:
                raise HTTPException(422, "Geen geldige Vetera-back-up (vetera.db ontbreekt)")
            for n in names:
                if n.startswith("/") or ".." in Path(n).parts:
                    raise HTTPException(422, "Ongeldig pad in back-up")
            z.extractall(tmp / "x")
    except zipfile.BadZipFile as exc:
        raise HTTPException(422, "Bestand is geen geldig ZIP-archief") from exc
    con = sqlite3.connect(str(tmp / "x" / "vetera.db"))
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise HTTPException(422, "Database in back-up is beschadigd")
    finally:
        con.close()
    safety = make_backup()  # eerst huidige toestand veiligstellen
    reset_engine()
    for f in s.db_path.parent.glob(s.db_path.name + "*"):
        f.unlink()
    shutil.copy(tmp / "x" / "vetera.db", s.db_path)
    for sub in ("documents", "imports", "logos", "reports"):
        src = tmp / "x" / sub
        if src.exists():
            shutil.rmtree(s.data_dir / sub, ignore_errors=True)
            shutil.copytree(src, s.data_dir / sub)
    from ..services.migrate import upgrade_database
    upgrade_database()
    fixed = fix_paths()
    return {"ok": True, "safety_backup": safety.name, "paths_fixed": fixed}


def fix_paths() -> int:
    """Herstel absolute bestandspaden als de datamap is verplaatst (bijv. na herstel op een andere pc)."""
    from ..db import SessionLocal
    s = get_settings()
    db = SessionLocal()
    n = 0
    try:
        for v in db.scalars(select(DocumentVersion)):
            if not Path(v.file_path).exists():
                cand = s.documents_dir / Path(v.file_path).name
                if cand.exists():
                    v.file_path, n = str(cand), n + 1
        for imp in db.scalars(select(ExcelImport)):
            if not Path(imp.stored_path).exists():
                cand = s.imports_dir / Path(imp.stored_path).name
                if cand.exists():
                    imp.stored_path, n = str(cand), n + 1
        for p in db.scalars(select(Provider).where(Provider.logo_path.is_not(None))):
            if not Path(p.logo_path).exists():
                cand = s.logos_dir / Path(p.logo_path).name
                if cand.exists():
                    p.logo_path, n = str(cand), n + 1
        db.commit()
    finally:
        db.close()
    return n


@router.post("/data/delete")
def delete_data(data: dict, db: Session = Depends(get_db)):
    """Verwijder gegevens per categorie. Vereist bevestigingstekst 'VERWIJDEREN'."""
    if data.get("confirm") != "VERWIJDEREN":
        raise HTTPException(422, "Typ VERWIJDEREN om te bevestigen")
    what = data.get("what")
    n = 0
    if what == "premies":
        n = db.query(PremiumObservation).delete()
    elif what == "imports":
        for imp in db.scalars(select(ExcelImport)):
            Path(imp.stored_path).unlink(missing_ok=True)
            db.query(PremiumObservation).filter(PremiumObservation.import_id == imp.id).delete()
            db.delete(imp)
            n += 1
    elif what == "meldingen":
        n = db.query(Notification).delete()
    elif what == "ai":
        from ..models import AIAnalysis
        n = db.query(AIAnalysis).delete()
    elif what == "monitor":
        n = db.query(MonitorRun).delete()
    elif what == "documenten":
        for d in db.scalars(select(Document)):
            for v in d.versions:
                Path(v.file_path).unlink(missing_ok=True)
            d.current_version_id = None
            db.flush()
            db.delete(d)
            n += 1
    else:
        raise HTTPException(422, "Onbekende categorie")
    audit(db, "data", None, "verwijderd", {"categorie": what, "aantal": n})
    db.commit()
    return {"deleted": n}
