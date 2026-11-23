"""Documentverwerking: opslag, tekstextractie per pagina, herkenning, clausules,
bronverificatie van citaten en vergelijking van documentversies."""
from __future__ import annotations

import difflib
import io
import logging
import re
import shutil
from datetime import date
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (Clause, Document, DocumentDiff, DocumentPage, DocumentVersion, Feature,
                      Finding, Product, Provider)
from .common import normalize_text, safe_filename, sha256_bytes

log = logging.getLogger("vetera.documents")

MONTHS = {"januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6, "juli": 7,
          "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12}

DOC_TYPE_PATTERNS = [
    ("verzekeringskaart", r"verzekeringskaart|insurance product information|\bipid\b"),
    ("aanvullende_voorwaarden", r"aanvullende (polis)?voorwaarden|bijzondere voorwaarden"),
    ("clausule", r"\bclausule(blad|s)?\b"),
    ("premietabel", r"premietabel|tarief(kaart|lijst)|premieoverzicht"),
    ("productinformatie", r"productinformatie|productblad|productwijzer"),
    ("polisvoorwaarden", r"polisvoorwaarden|verzekeringsvoorwaarden|algemene voorwaarden|voorwaarden"),
]

HEADING_RE = re.compile(
    r"^\s*(?:(?:artikel|art\.)\s*(?P<art>\d+(?:\.\d+)*[a-z]?)\b[\s.:–-]*(?P<t1>.{0,120})"
    r"|(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(?P<t2>[A-ZÀ-Ý][^\n]{2,100}))\s*$",
    re.IGNORECASE,
)

MIN_CHARS_GOOD = 200
MIN_CHARS_POOR = 40


class DocumentError(Exception):
    pass


# ---------------------------------------------------------------- opslag & validatie
def validate_pdf_bytes(data: bytes, filename: str) -> None:
    max_mb = get_settings().max_upload_mb
    if len(data) > max_mb * 1024 * 1024:
        raise DocumentError(f"{filename}: bestand is groter dan {max_mb} MB.")
    if not data.startswith(b"%PDF"):
        raise DocumentError(f"{filename}: dit is geen geldig PDF-bestand.")


def store_pdf(data: bytes, filename: str) -> tuple[Path, str]:
    digest = sha256_bytes(data)
    path = get_settings().documents_dir / f"{digest[:16]}_{safe_filename(filename)}"
    if not path.suffix.lower() == ".pdf":
        path = path.with_suffix(".pdf")
    path.write_bytes(data)
    return path, digest


# ---------------------------------------------------------------- extractie
def _ocr_available() -> bool:
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
    except ImportError:
        return False
    return shutil.which("tesseract") is not None


def _ocr_page(path: Path, page_number: int) -> str | None:
    try:
        import pytesseract
        from pdf2image import convert_from_path
        images = convert_from_path(str(path), first_page=page_number, last_page=page_number, dpi=250)
        if images:
            return pytesseract.image_to_string(images[0], lang="nld")
    except Exception as exc:  # pragma: no cover - afhankelijk van lokale installatie
        log.warning("OCR mislukt voor pagina %s: %s", page_number, type(exc).__name__)
    return None


def extract_pages(path: Path, use_ocr: bool = True) -> tuple[list[dict], bool]:
    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise DocumentError("PDF is versleuteld en kan niet worden gelezen.") from exc
        pages = []
        ocr_used = False
        ocr_ok = use_ocr and _ocr_available()
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                text = ""
            text = text.replace("\x00", "")
            quality = "goed"
            if len(text.strip()) < MIN_CHARS_POOR:
                if ocr_ok:
                    ocr = _ocr_page(path, i)
                    if ocr and len(ocr.strip()) >= MIN_CHARS_POOR:
                        text, ocr_used, quality = ocr, True, "ocr"
                    else:
                        quality = "onbetrouwbaar"
                else:
                    quality = "onbetrouwbaar"
            elif len(text.strip()) < MIN_CHARS_GOOD:
                quality = "matig"
            # Veel vreemde tekens wijst op slechte extractie (bv. ontbrekende fonts)
            if text and sum(1 for c in text if c == "�" or (ord(c) < 32 and c not in "\n\t\r")) > len(text) * 0.05:
                quality = "onbetrouwbaar"
            pages.append({"page_number": i, "text": text, "char_count": len(text.strip()), "quality": quality})
        return pages, ocr_used
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(f"PDF kon niet worden gelezen ({type(exc).__name__}).") from exc


def overall_quality(pages: list[dict]) -> str:
    if not pages:
        return "onbetrouwbaar"
    bad = sum(1 for p in pages if p["quality"] == "onbetrouwbaar")
    if bad / len(pages) > 0.3:
        return "onbetrouwbaar"
    if bad or any(p["quality"] in ("matig", "ocr") for p in pages):
        return "matig"
    return "goed"


# ---------------------------------------------------------------- herkenning
def detect_date(text: str) -> date | None:
    t = text.lower()
    m = re.search(r"\b(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)\s+(20\d{2}|19\d{2})\b", t)
    if m:
        return date(int(m.group(2)), MONTHS[m.group(1)], 1)
    m = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    m = re.search(r"\b(0[1-9]|1[0-2])[-/.](20\d{2})\b", t)
    if m:
        return date(int(m.group(2)), int(m.group(1)), 1)
    return None


def detect_version_label(text: str) -> str | None:
    m = re.search(r"\b(?:versie|editie|model|code)\s*[:.]?\s*([A-Z0-9][A-Z0-9.\-/]{1,25}\d)\b", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\b([A-Z]{2,6}[ -]?\d{2,4}[-/.]?\d{0,4})\b", text)
    return m.group(1) if m else None


def detect_document_type(text: str, filename: str) -> str:
    hay = (filename + " " + text[:4000]).lower()
    for dtype, pat in DOC_TYPE_PATTERNS:
        if re.search(pat, hay):
            return dtype
    return "overig"


def identify(db: Session, pages: list[dict], filename: str) -> dict:
    head = "\n".join(p["text"] for p in pages[:3])
    norm = normalize_text(head + " " + filename)
    providers = db.scalars(select(Provider).where(Provider.status != "samengevoegd")).all()
    provider_hits = []
    for pr in providers:
        n = normalize_text(pr.name)
        if n and re.search(rf"\b{re.escape(n)}\b", norm):
            provider_hits.append({"id": pr.id, "name": pr.name, "count": norm.count(n)})
    provider_hits.sort(key=lambda h: -h["count"])
    product_hits = []
    if provider_hits:
        for prod in db.scalars(select(Product).where(Product.provider_id == provider_hits[0]["id"])):
            if normalize_text(prod.name) and normalize_text(prod.name) in norm:
                product_hits.append({"id": prod.id, "name": prod.name})
    vehicle = None
    for cat, pat in (("motor", r"motor(fiets|rijwiel)"), ("bromfiets", r"bromfiets|snorfiets|brommer"),
                     ("auto", r"personenauto|oldtimer|klassieke auto|klassieker")):
        if re.search(pat, norm):
            vehicle = cat
            break
    return {
        "provider_candidates": provider_hits[:5],
        "product_candidates": product_hits[:5],
        "document_type": detect_document_type(head, filename),
        "doc_date": (d.isoformat() if (d := detect_date(head)) else None),
        "version_label": detect_version_label(head[:1500]),
        "vehicle_category": vehicle,
        "note": "Automatische herkenning; controleer en bevestig.",
    }


# ---------------------------------------------------------------- clausules
def extract_clauses(pages: list[dict]) -> list[dict]:
    clauses: list[dict] = []
    current: dict | None = None
    for p in pages:
        for raw in p["text"].splitlines():
            line = raw.strip()
            if not line:
                continue
            m = HEADING_RE.match(line) if len(line) < 140 else None
            if m:
                if current and current["text"].strip():
                    clauses.append(current)
                art = m.group("art") or m.group("num")
                title = (m.group("t1") or m.group("t2") or "").strip(" .:-–")
                current = {"page_number": p["page_number"], "article": art, "heading": title or None,
                           "text": ""}
                continue
            if current is None:
                current = {"page_number": p["page_number"], "article": None, "heading": "Inleiding", "text": ""}
            current["text"] += line + "\n"
    if current and current["text"].strip():
        clauses.append(current)
    for i, c in enumerate(clauses):
        c["order"] = i
        c["text"] = c["text"].strip()[:20000]
    return clauses


# ---------------------------------------------------------------- verwerking
def process_version(db: Session, version: DocumentVersion, use_ocr: bool = True) -> DocumentVersion:
    path = Path(version.file_path)
    try:
        pages, ocr_used = extract_pages(path, use_ocr=use_ocr)
    except DocumentError as exc:
        version.status = "fout"
        version.error = str(exc)
        db.commit()
        return version
    version.pages.clear()
    version.clauses.clear()
    db.flush()
    for p in pages:
        version.pages.append(DocumentPage(**p))
    for c in extract_clauses(pages):
        version.clauses.append(Clause(**c))
    version.page_count = len(pages)
    version.ocr_used = ocr_used
    version.extraction_quality = overall_quality(pages)
    version.status = "gereed"
    version.error = None
    db.commit()
    return version


def find_duplicate_version(db: Session, digest: str) -> DocumentVersion | None:
    return db.scalars(select(DocumentVersion).where(DocumentVersion.sha256 == digest)).first()


# ---------------------------------------------------------------- citaatverificatie
def _shingles(tokens: list[str], n: int = 4) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)}


def verify_quote(db: Session, version_id: int | None, page_number: int | None, quote: str | None) -> dict:
    """Controleer of een citaat werkelijk in de geëxtraheerde brontekst staat.

    Geeft {'verified': bool|None, 'page_number': int|None, 'score': float} terug.
    """
    if not version_id or not quote or len(quote.strip()) < 8:
        return {"verified": None, "page_number": page_number, "score": 0.0}
    pages = db.scalars(select(DocumentPage).where(DocumentPage.version_id == version_id)
                       .order_by(DocumentPage.page_number)).all()
    if not pages:
        return {"verified": False, "page_number": page_number, "score": 0.0}
    q = normalize_text(quote)
    q_sh = _shingles(q.split())
    order = sorted(pages, key=lambda p: (0 if p.page_number == page_number else 1, p.page_number))
    best = (0.0, None)
    for i, p in enumerate(order):
        # pagina's samenvoegen met de volgende om citaten over paginagrenzen te vangen
        nxt = next((x for x in pages if x.page_number == p.page_number + 1), None)
        hay = normalize_text(p.text + " " + (nxt.text if nxt else ""))
        if q and q in hay:
            return {"verified": True, "page_number": p.page_number, "score": 1.0}
        if q_sh:
            score = len(q_sh & _shingles(hay.split())) / len(q_sh)
            if score > best[0]:
                best = (score, p.page_number)
    verified = best[0] >= 0.8
    return {"verified": verified, "page_number": best[1] if verified else page_number, "score": round(best[0], 2)}


# ---------------------------------------------------------------- lokale passagezoeker
def find_passages(db: Session, version: DocumentVersion, feature: Feature, limit: int = 3) -> list[dict]:
    """Zoek kandidaatpassages voor een kenmerk op basis van trefwoorden (geen interpretatie)."""
    results = []
    kws = [normalize_text(k) for k in (feature.keywords or []) if k]
    if not kws:
        return results
    for clause in version.clauses:
        norm = normalize_text(clause.text + " " + (clause.heading or ""))
        hits = [k for k in kws if k and k in norm]
        if hits:
            idx = norm.find(hits[0])
            # Toon het stuk originele tekst rondom het eerste trefwoord
            raw = clause.text
            pos = normalize_text(raw).find(hits[0])
            start = max(0, int(pos * len(raw) / max(len(norm), 1)) - 200) if idx >= 0 else 0
            snippet = raw[start:start + 600].strip()
            results.append({"page_number": clause.page_number, "article": clause.article,
                            "heading": clause.heading, "snippet": snippet, "hits": hits,
                            "score": len(hits)})
    results.sort(key=lambda r: -r["score"])
    return results[:limit]


def local_candidate_findings(db: Session, product_id: int, version: DocumentVersion) -> dict:
    """Maak per rubriek een concept-bevinding met status 'menselijke beoordeling' (passage gevonden)
    of 'niet gevonden'. Er wordt nooit geconcludeerd dat iets niet verzekerd is."""
    created = skipped = 0
    for feature in db.scalars(select(Feature).where(Feature.active.is_(True))):
        current = db.scalars(select(Finding).where(Finding.product_id == product_id,
                                                   Finding.feature_id == feature.id,
                                                   Finding.is_current.is_(True))).all()
        if any(f.locked or f.origin in ("handmatig", "ai") for f in current):
            skipped += 1
            continue
        for f in current:
            f.is_current = False
        passages = find_passages(db, version, feature, limit=1)
        if passages:
            p = passages[0]
            f = Finding(product_id=product_id, feature_id=feature.id, status="menselijke_beoordeling",
                        explanation="Relevante passage gevonden op basis van trefwoorden ("
                                    + ", ".join(p["hits"][:4]) + "). Inhoudelijke beoordeling nodig.",
                        document_version_id=version.id, page_number=p["page_number"], article=p["article"],
                        quote=p["snippet"][:1000], quote_verified=True, origin="lokaal", confidence="laag")
        else:
            f = Finding(product_id=product_id, feature_id=feature.id, status="niet_gevonden",
                        explanation="Geen passage gevonden met de trefwoorden van deze rubriek. "
                                    "Dit betekent niet dat het onderdeel niet verzekerd is.",
                        document_version_id=version.id, origin="lokaal", confidence="laag")
        db.add(f)
        created += 1
    db.commit()
    return {"aangemaakt": created, "overgeslagen_bestaand": skipped}


# ---------------------------------------------------------------- versievergelijking
CHANGE_LABELS = {
    "redactioneel": "Redactionele wijziging",
    "verduidelijking": "Verduidelijking",
    "dekkingsuitbreiding": "Mogelijke dekkingsuitbreiding",
    "dekkingsbeperking": "Mogelijke dekkingsbeperking",
    "acceptatie": "Gewijzigde acceptatiecriteria",
    "nieuwe_uitsluiting": "Mogelijke nieuwe uitsluiting",
    "overig": "Overige relevante wijziging",
}
_EXCL = re.compile(r"niet verzekerd|uitgesloten|geen dekking|vergoeden wij niet|is niet gedekt|uitsluiting")
_COVER = re.compile(r"verzekerd|vergoeden wij|gedekt|dekking")
_ACC = re.compile(r"acceptatie|accepteren|minimale leeftijd|bouwjaar|stalling|tweede auto")
_AMOUNT = re.compile(r"€\s?\d|\d+\s?%|\d+\s?(km|kilometer|jaar|dagen)")


def _units(version: DocumentVersion) -> list[tuple[str, int]]:
    units = []
    for p in version.pages:
        for s in re.split(r"(?<=[.;:])\s+|\n{2,}", p.text):
            s = re.sub(r"\s+", " ", s).strip()
            if len(s) > 3:
                units.append((s, p.page_number))
    return units


def classify_change(old: str, new: str) -> str:
    on, nn = normalize_text(old), normalize_text(new)
    if on == nn or difflib.SequenceMatcher(None, on, nn).ratio() > 0.97:
        return "redactioneel"
    if _EXCL.search(nn) and not _EXCL.search(on):
        return "nieuwe_uitsluiting"
    if _EXCL.search(on) and not _EXCL.search(nn):
        return "dekkingsuitbreiding"
    if _ACC.search(on + " " + nn):
        return "acceptatie"
    if not old and _COVER.search(nn):
        return "dekkingsuitbreiding"
    if not new and _COVER.search(on):
        return "dekkingsbeperking"
    if _AMOUNT.search(on + " " + nn):
        return "overig"
    if difflib.SequenceMatcher(None, on, nn).ratio() > 0.85:
        return "verduidelijking"
    return "overig"


def diff_versions(db: Session, old: DocumentVersion, new: DocumentVersion) -> DocumentDiff:
    a, b = _units(old), _units(new)
    sm = difflib.SequenceMatcher(None, [x[0] for x in a], [x[0] for x in b], autojunk=False)
    changes = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        old_txt = " ".join(x[0] for x in a[i1:i2])
        new_txt = " ".join(x[0] for x in b[j1:j2])
        cat = classify_change(old_txt, new_txt)
        changes.append({
            "type": {"replace": "gewijzigd", "delete": "verwijderd", "insert": "toegevoegd"}[tag],
            "category": cat, "category_label": CHANGE_LABELS[cat],
            "old": old_txt[:3000], "new": new_txt[:3000],
            "old_page": a[i1][1] if i1 < len(a) else None,
            "new_page": b[j1][1] if j1 < len(b) else None,
        })
    counts: dict[str, int] = {}
    for c in changes:
        counts[c["category"]] = counts.get(c["category"], 0) + 1
    summary = {"aantal_wijzigingen": len(changes), "per_categorie": counts,
               "gelijkheid": round(sm.ratio(), 3),
               "toelichting": "Automatische, indicatieve classificatie op basis van tekstpatronen. "
                              "Inhoudelijke impact vereist menselijke of AI-beoordeling."}
    d = DocumentDiff(document_id=new.document_id, old_version_id=old.id, new_version_id=new.id,
                     summary=summary, changes=changes[:500])
    db.add(d)
    db.commit()
    return d


def pdf_bytes_from_text(text: str) -> bytes:
    """Hulpfunctie voor tests: maak een eenvoudige PDF met reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for page in text.split("\f"):
        y = 800
        for line in page.splitlines():
            c.drawString(50, y, line)
            y -= 14
            if y < 50:
                c.showPage()
                y = 800
        c.showPage()
    c.save()
    return buf.getvalue()


def create_document_with_version(db: Session, data: bytes, filename: str, *, provider_id: int | None,
                                 product_id: int | None, document_type: str | None, title: str | None,
                                 visibility: str = "publiek", document_id: int | None = None,
                                 source_url: str | None = None, source_id: int | None = None,
                                 use_ocr: bool = True) -> tuple[Document, DocumentVersion, dict]:
    """Opslaan + verwerken. Bestaat ``document_id`` dan wordt een nieuwe versie toegevoegd
    (de oude versie blijft bewaard) en worden de versies vergeleken."""
    validate_pdf_bytes(data, filename)
    dup = find_duplicate_version(db, sha256_bytes(data))
    if dup is not None:
        raise DocumentError(f"{filename}: identiek document bestaat al (document #{dup.document_id}, "
                            f"versie #{dup.id}).")
    path, digest = store_pdf(data, filename)
    if document_id:
        doc = db.get(Document, document_id)
        if doc is None:
            raise DocumentError("Document niet gevonden.")
    else:
        doc = Document(title=title or Path(filename).stem, provider_id=provider_id, product_id=product_id,
                       document_type=document_type or "overig", visibility=visibility, source_id=source_id)
        db.add(doc)
        db.flush()
    prev_id = doc.current_version_id
    version = DocumentVersion(document_id=doc.id, file_path=str(path), original_filename=filename,
                              sha256=digest, size_bytes=len(data), source_url=source_url,
                              supersedes_id=prev_id)
    db.add(version)
    db.flush()
    process_version(db, version, use_ocr=use_ocr)
    info: dict = {}
    if version.status == "gereed":
        ident = identify(db, [{"text": p.text} for p in version.pages], filename)
        info["identificatie"] = ident
        if not document_id:
            doc.identification = ident
            if not document_type and ident["document_type"]:
                doc.document_type = ident["document_type"]
            if not provider_id and len(ident["provider_candidates"]) == 1:
                doc.provider_id = ident["provider_candidates"][0]["id"]
            if not product_id and len(ident["product_candidates"]) == 1:
                doc.product_id = ident["product_candidates"][0]["id"]
        if ident.get("doc_date"):
            version.doc_date = date.fromisoformat(ident["doc_date"])
        version.version_label = ident.get("version_label")
        doc.current_version_id = version.id
        db.commit()
        if prev_id:
            old = db.get(DocumentVersion, prev_id)
            if old and old.status == "gereed":
                d = diff_versions(db, old, version)
                info["diff_id"] = d.id
                info["diff_summary"] = d.summary
    else:
        db.commit()
    return doc, version, info
