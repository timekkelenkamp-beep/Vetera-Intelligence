from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (Document, DocumentDiff, DocumentPage, DocumentVersion, Feature, Notification, Product,
                      Provider, Source)
from ..services.common import DOCUMENT_TYPES, VISIBILITY, apply_updates, audit, get_or_404, to_dict
from ..services.documents import (DocumentError, create_document_with_version, diff_versions, find_passages,
                                  local_candidate_findings, process_version)
from ..services.monitor import FetchError, _Robots, fetch, make_client, validate_external_url
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["documenten"])


def _doc_dict(db: Session, d: Document) -> dict:
    out = to_dict(d)
    prov = db.get(Provider, d.provider_id) if d.provider_id else None
    prod = db.get(Product, d.product_id) if d.product_id else None
    out["provider_name"] = prov.name if prov else None
    out["product_name"] = prod.name if prod else None
    cv = db.get(DocumentVersion, d.current_version_id) if d.current_version_id else None
    out["current_version"] = _version_dict(cv) if cv else None
    out["version_count"] = len(d.versions)
    return out


def _version_dict(v: DocumentVersion) -> dict:
    d = to_dict(v, exclude=["file_path"])
    d["clause_count"] = len(v.clauses)
    d["unreliable_pages"] = [p.page_number for p in v.pages if p.quality == "onbetrouwbaar"]
    return d


@router.get("/documents")
def list_documents(provider_id: int | None = None, product_id: int | None = None, document_type: str | None = None,
                   q: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Document)
    if provider_id:
        stmt = stmt.where(Document.provider_id == provider_id)
    if product_id:
        stmt = stmt.where(Document.product_id == product_id)
    if document_type:
        stmt = stmt.where(Document.document_type == document_type)
    if q:
        stmt = stmt.where(Document.title.ilike(f"%{q}%"))
    return [_doc_dict(db, d) for d in db.scalars(stmt.order_by(Document.updated_at.desc()))]


@router.post("/documents/upload")
async def upload_documents(files: list[UploadFile] = File(...), provider_id: int | None = Form(None),
                           product_id: int | None = Form(None), document_type: str | None = Form(None),
                           visibility: str = Form("publiek"), document_id: int | None = Form(None),
                           use_ocr: bool = Form(True), db: Session = Depends(get_db)):
    if visibility not in VISIBILITY:
        raise HTTPException(422, "Ongeldige zichtbaarheid")
    if document_type and document_type not in DOCUMENT_TYPES:
        raise HTTPException(422, "Ongeldig documenttype")
    if document_id and len(files) > 1:
        raise HTTPException(422, "Upload één bestand per nieuwe versie")
    results = []
    for f in files:
        data = await f.read()
        try:
            doc, v, info = create_document_with_version(
                db, data, f.filename or "document.pdf", provider_id=provider_id, product_id=product_id,
                document_type=document_type, title=None, visibility=visibility, document_id=document_id,
                use_ocr=use_ocr)
            audit(db, "document", doc.id, "nieuwe_versie" if document_id else "geimporteerd",
                  {"bestand": f.filename, "versie": v.id})
            if info.get("diff_id"):
                db.add(Notification(type="voorwaarden_gewijzigd", title=f"Nieuwe versie: {doc.title}",
                                    body=f"{info['diff_summary']['aantal_wijzigingen']} wijzigingen gevonden.",
                                    link=f"/documenten/{doc.id}", severity="belangrijk"))
            db.commit()
            results.append({"filename": f.filename, "ok": v.status == "gereed", "document": _doc_dict(db, doc),
                            "version": _version_dict(v), "info": info, "error": v.error})
        except DocumentError as exc:
            db.rollback()
            results.append({"filename": f.filename, "ok": False, "error": str(exc)})
    return results


@router.post("/documents/fetch-url")
def fetch_document_url(data: dict, db: Session = Depends(get_db)):
    """Haal een openbare PDF op (met robots.txt-controle) en registreer de bron."""
    url = (data.get("url") or "").strip()
    try:
        validate_external_url(url)
        with make_client() as client:
            if not _Robots(client, get_settings().user_agent).allowed(url):
                raise FetchError("robots.txt van deze website staat geautomatiseerd ophalen niet toe. "
                                 "Download het document handmatig en upload het.")
            r = fetch(client, url)
    except FetchError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Ophalen mislukt ({type(exc).__name__}).") from exc
    if r.status_code >= 400:
        raise HTTPException(422, f"De server gaf HTTP {r.status_code}.")
    if not r.content.startswith(b"%PDF"):
        raise HTTPException(422, "Het adres verwijst niet naar een PDF-document.")
    src = db.scalars(select(Source).where(Source.url == url)).first()
    if not src:
        src = Source(url=url, title=data.get("title"), provider_id=data.get("provider_id"),
                     product_id=data.get("product_id"), source_type=data.get("source_type") or "officieel_primair",
                     document_type=data.get("document_type"), kind="document", access_status="onbekend",
                     visibility="publiek", monitor_enabled=bool(data.get("monitor", True)))
        db.add(src)
        db.flush()
    from datetime import datetime
    from ..services.common import sha256_bytes
    src.retrieved_at = datetime.now()
    src.content_hash = sha256_bytes(r.content)
    existing = db.scalars(select(Document).where(Document.source_id == src.id)).first()
    try:
        doc, v, info = create_document_with_version(
            db, r.content, urlparse(url).path.rsplit("/", 1)[-1] or "document.pdf",
            provider_id=data.get("provider_id"), product_id=data.get("product_id"),
            document_type=data.get("document_type"), title=data.get("title"), visibility="publiek",
            document_id=existing.id if existing else None, source_url=url, source_id=src.id)
    except DocumentError as exc:
        db.commit()
        raise HTTPException(409, str(exc)) from exc
    src.processing_status = "verwerkt" if v.status == "gereed" else "fout"
    audit(db, "document", doc.id, "opgehaald", {"url": url})
    db.commit()
    return {"document": _doc_dict(db, doc), "version": _version_dict(v), "info": info}


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, db: Session = Depends(get_db)):
    d = get_or_404(db, Document, doc_id, "Document")
    out = _doc_dict(db, d)
    out["versions"] = [_version_dict(v) for v in sorted(d.versions, key=lambda v: v.imported_at, reverse=True)]
    out["diffs"] = [{**to_dict(x), "changes": None} for x in
                    db.scalars(select(DocumentDiff).where(DocumentDiff.document_id == d.id)
                               .order_by(DocumentDiff.created_at.desc()))]
    out["source"] = to_dict(db.get(Source, d.source_id)) if d.source_id else None
    return out


@router.patch("/documents/{doc_id}")
def update_document(doc_id: int, data: dict, db: Session = Depends(get_db)):
    d = get_or_404(db, Document, doc_id, "Document")
    if data.get("product_id"):
        p = get_or_404(db, Product, int(data["product_id"]), "Product")
        if data.get("provider_id") and int(data["provider_id"]) != p.provider_id:
            raise HTTPException(422, "Dit product hoort bij een andere aanbieder")
        data.setdefault("provider_id", p.provider_id)
    apply_updates(db, d, data, ["title", "provider_id", "product_id", "document_type", "visibility"], "document",
                  enums={"document_type": DOCUMENT_TYPES, "visibility": VISIBILITY})
    db.commit()
    return _doc_dict(db, d)


@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, delete_files: bool = True, db: Session = Depends(get_db)):
    d = get_or_404(db, Document, doc_id, "Document")
    paths = [v.file_path for v in d.versions]
    d.current_version_id = None
    db.flush()
    audit(db, "document", d.id, "verwijderd", {"title": d.title})
    db.delete(d)
    db.commit()
    if delete_files:
        for p in paths:
            try:
                Path(p).unlink(missing_ok=True)
            except OSError:
                pass
    return {"ok": True}


@router.get("/document-versions/{vid}")
def get_version(vid: int, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    out = _version_dict(v)
    out["document"] = _doc_dict(db, db.get(Document, v.document_id))
    return out


@router.get("/document-versions/{vid}/file")
def version_file(vid: int, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    if not Path(v.file_path).exists():
        raise HTTPException(404, "Bestand ontbreekt op schijf")
    return FileResponse(v.file_path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{Path(v.original_filename).name}"'})


@router.get("/document-versions/{vid}/pages")
def version_pages(vid: int, page: int | None = None, db: Session = Depends(get_db)):
    get_or_404(db, DocumentVersion, vid, "Documentversie")
    stmt = select(DocumentPage).where(DocumentPage.version_id == vid).order_by(DocumentPage.page_number)
    if page:
        stmt = stmt.where(DocumentPage.page_number == page)
    return [to_dict(p) for p in db.scalars(stmt)]


@router.get("/document-versions/{vid}/clauses")
def version_clauses(vid: int, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    return [to_dict(c) for c in v.clauses]


@router.post("/document-versions/{vid}/reprocess")
def reprocess(vid: int, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    process_version(db, v)
    return _version_dict(v)


@router.get("/document-versions/{vid}/passages")
def passages(vid: int, feature_id: int, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    f = get_or_404(db, Feature, feature_id, "Kenmerk")
    return find_passages(db, v, f, limit=8)


@router.post("/document-versions/{vid}/local-findings")
def local_findings(vid: int, data: dict, db: Session = Depends(get_db)):
    v = get_or_404(db, DocumentVersion, vid, "Documentversie")
    doc = db.get(Document, v.document_id)
    product_id = int(data.get("product_id") or doc.product_id or 0)
    if not product_id:
        raise HTTPException(422, "Koppel het document eerst aan een product")
    res = local_candidate_findings(db, product_id, v)
    audit(db, "document_version", v.id, "passagezoeker", res, "systeem")
    db.commit()
    return res


@router.post("/documents/{doc_id}/compare")
def compare_versions(doc_id: int, data: dict, db: Session = Depends(get_db)):
    old = get_or_404(db, DocumentVersion, int(data.get("old_version_id") or 0), "Oude versie")
    new = get_or_404(db, DocumentVersion, int(data.get("new_version_id") or 0), "Nieuwe versie")
    if old.document_id != doc_id or new.document_id != doc_id:
        raise HTTPException(422, "Versies horen niet bij dit document")
    d = diff_versions(db, old, new)
    return to_dict(d)


@router.get("/diffs")
def list_diffs(limit: int = 50, db: Session = Depends(get_db)):
    out = []
    for d in db.scalars(select(DocumentDiff).order_by(DocumentDiff.created_at.desc()).limit(limit)):
        doc = db.get(Document, d.document_id)
        x = to_dict(d)
        x["changes"] = None
        x["document_title"] = doc.title if doc else None
        x["provider_name"] = (db.get(Provider, doc.provider_id).name if doc and doc.provider_id else None)
        out.append(x)
    return out


@router.get("/diffs/{diff_id}")
def get_diff(diff_id: int, db: Session = Depends(get_db)):
    d = get_or_404(db, DocumentDiff, diff_id, "Vergelijking")
    out = to_dict(d)
    doc = db.get(Document, d.document_id)
    out["document_title"] = doc.title if doc else None
    if d.ai_analysis_id:
        from ..models import AIAnalysis
        a = db.get(AIAnalysis, d.ai_analysis_id)
        out["ai_analysis"] = a.response if a else None
    return out


@router.get("/search")
def search(q: str, limit: int = 30, db: Session = Depends(get_db)):
    """Doorzoek alle geëxtraheerde documenttekst (FTS5)."""
    import re as _re
    words = [w for w in _re.findall(r"\w+", q) if len(w) > 1]
    if not words:
        return []
    match = " ".join(f'"{w}"*' if i == len(words) - 1 else f'"{w}"' for i, w in enumerate(words))
    rows = db.execute(text(
        "SELECT rowid, snippet(page_fts, 0, '[[', ']]', ' … ', 18) FROM page_fts WHERE page_fts MATCH :q "
        "ORDER BY rank LIMIT :l"), {"q": match, "l": limit}).all()
    out = []
    for rid, snip in rows:
        p = db.get(DocumentPage, rid)
        if not p:
            continue
        v = db.get(DocumentVersion, p.version_id)
        doc = db.get(Document, v.document_id)
        prov = db.get(Provider, doc.provider_id) if doc.provider_id else None
        out.append({"page_id": p.id, "page_number": p.page_number, "version_id": v.id, "document_id": doc.id,
                    "document_title": doc.title, "provider_name": prov.name if prov else None, "snippet": snip,
                    "is_current": doc.current_version_id == v.id})
    return out
