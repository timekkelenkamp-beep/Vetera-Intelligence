from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Report
from ..services import reports as svc
from ..services.common import get_or_404, to_dict

router = APIRouter(prefix="/api/reports", tags=["rapportages"])


@router.get("/types")
def types():
    return [{"key": k, "label": v} for k, v in svc.REPORT_TYPES.items()]


@router.get("")
def list_reports(db: Session = Depends(get_db)):
    return [to_dict(r, exclude=["content"]) for r in db.scalars(select(Report).order_by(Report.created_at.desc()))]


@router.post("/preview")
def preview(data: dict, db: Session = Depends(get_db)):
    try:
        return svc.build_content(db, data.get("report_type"), data.get("params") or {})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("")
def create(data: dict, db: Session = Depends(get_db)):
    try:
        r = svc.generate(db, data.get("report_type"), data.get("params") or {})
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return to_dict(r)


@router.get("/{rid}")
def get(rid: int, db: Session = Depends(get_db)):
    return to_dict(get_or_404(db, Report, rid, "Rapport"))


@router.get("/{rid}/download")
def download(rid: int, fmt: str = "pdf", db: Session = Depends(get_db)):
    r = get_or_404(db, Report, rid, "Rapport")
    path = r.file_pdf if fmt == "pdf" else r.file_xlsx
    if not path or not Path(path).exists():
        raise HTTPException(404, "Bestand niet gevonden")
    return FileResponse(path, filename=Path(path).name,
                        media_type="application/pdf" if fmt == "pdf" else
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@router.delete("/{rid}")
def delete(rid: int, db: Session = Depends(get_db)):
    r = get_or_404(db, Report, rid, "Rapport")
    for p in (r.file_pdf, r.file_xlsx):
        if p:
            Path(p).unlink(missing_ok=True)
    db.delete(r)
    db.commit()
    return {"ok": True}
