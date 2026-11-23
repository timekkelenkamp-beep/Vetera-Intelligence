"""Excel Import Studio: flexibele import van premie-onderzoeken (XLSX, XLS, CSV).

Proces: upload → werkblad kiezen → voorbeeld → automatische kolomherkenning →
handmatige koppeling → validatie (types, verplichte velden, duplicaten) → goedkeuren → opslaan.
Geïmporteerde tarieven worden standaard als historisch gemarkeerd.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ExcelImport, PremiumObservation, Product, Provider
from .common import normalize_text, safe_filename, sha256_bytes
from .premiums import annualize

ALLOWED_EXT = {".xlsx", ".xlsm", ".xls", ".csv"}

# doelveld → (label, type, synoniemen)
TARGET_FIELDS: dict[str, tuple[str, str, list[str]]] = {
    "provider": ("Verzekeraar", "tekst", ["verzekeraar", "maatschappij", "aanbieder", "insurer", "partij",
                                          "concurrent", "volmacht", "merk verzekeraar"]),
    "product": ("Product", "tekst", ["product", "productnaam", "polis", "verzekering", "pakket"]),
    "vehicle": ("Voertuig", "tekst", ["voertuig", "auto", "merk model", "type voertuig", "object", "merk", "model"]),
    "vehicle_category": ("Voertuigcategorie", "tekst", ["categorie", "soort", "voertuigsoort", "voertuigcategorie"]),
    "build_year": ("Bouwjaar", "jaar", ["bouwjaar", "jaar", "bj", "year"]),
    "insured_value": ("Waarde", "bedrag", ["waarde", "verzekerde waarde", "taxatiewaarde", "cataloguswaarde",
                                           "dagwaarde", "value"]),
    "km_band": ("Kilometerbundel", "tekst", ["km", "kilometer", "kilometrage", "km bundel", "kilometerbundel",
                                              "km per jaar"]),
    "coverage_variant": ("Dekkingsvorm", "tekst", ["dekking", "dekkingsvorm", "dekkingsvariant", "wa casco",
                                                   "coverage"]),
    "amount": ("Premie", "bedrag", ["premie", "jaarpremie", "prijs", "bedrag", "maandpremie", "premium",
                                    "premie per jaar", "kosten"]),
    "period": ("Premieperiode", "tekst", ["periode", "termijn", "betaaltermijn"]),
    "deductible": ("Eigen risico", "bedrag", ["eigen risico", "er", "deductible", "eigenrisico"]),
    "reference_date": ("Onderzoeksdatum", "datum", ["datum", "onderzoeksdatum", "peildatum", "berekend op",
                                                    "date"]),
    "tax_included": ("Incl. assurantiebelasting", "tekst", ["assurantiebelasting", "incl ab", "inclusief belasting",
                                                            "belasting"]),
    "notes": ("Opmerkingen", "tekst", ["opmerking", "opmerkingen", "toelichting", "notitie", "notes"]),
}
REQUIRED = {"provider", "amount"}


class ImportError_(Exception):
    pass


def store_import_file(data: bytes, filename: str) -> tuple[Path, str]:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise ImportError_(f"Bestandstype {ext or '?'} wordt niet ondersteund. Gebruik XLSX, XLS of CSV.")
    if len(data) > get_settings().max_upload_mb * 1024 * 1024:
        raise ImportError_("Bestand is te groot.")
    digest = sha256_bytes(data)
    path = get_settings().imports_dir / f"{digest[:16]}_{safe_filename(filename)}"
    path.write_bytes(data)
    return path, digest


def read_sheets(path: Path) -> dict[str, list[list[Any]]]:
    ext = path.suffix.lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            import openpyxl
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            out = {}
            for ws in wb.worksheets:
                rows = []
                for r in ws.iter_rows(values_only=True):
                    rows.append(list(r))
                    if len(rows) > 20000:
                        break
                out[ws.title] = _trim(rows)
            wb.close()
            return out
        if ext == ".xls":
            import xlrd
            book = xlrd.open_workbook(str(path))
            out = {}
            for sh in book.sheets():
                rows = []
                for i in range(min(sh.nrows, 20000)):
                    row = []
                    for c in sh.row(i):
                        if c.ctype == xlrd.XL_CELL_DATE:
                            row.append(xlrd.xldate_as_datetime(c.value, book.datemode))
                        else:
                            row.append(c.value if c.value != "" else None)
                    rows.append(row)
                out[sh.name] = _trim(rows)
            return out
        if ext == ".csv":
            raw = path.read_bytes()
            for enc in ("utf-8-sig", "cp1252", "latin-1"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            try:
                dialect = csv.Sniffer().sniff(text[:5000], delimiters=";,\t|")
            except csv.Error:
                dialect = csv.excel
            rows = [[c if c != "" else None for c in r] for r in csv.reader(io.StringIO(text), dialect)]
            return {"CSV": _trim(rows)}
    except ImportError_:
        raise
    except Exception as exc:
        raise ImportError_(f"Bestand kon niet worden gelezen ({type(exc).__name__}). Is het een geldig "
                           f"{ext.upper().strip('.')}-bestand?") from exc
    raise ImportError_("Onbekend bestandstype")


def _trim(rows: list[list[Any]]) -> list[list[Any]]:
    rows = [r for r in rows if any(c not in (None, "") for c in r)]
    width = max((max((i for i, c in enumerate(r) if c not in (None, "")), default=-1) for r in rows), default=-1) + 1
    return [list(r[:width]) + [None] * (width - len(r[:width])) for r in rows]


def detect_header_row(rows: list[list[Any]]) -> int:
    """Index (0-based) van de waarschijnlijke kopregel: de eerste rij met veel tekstcellen
    die op bekende synoniemen lijken."""
    best, best_score = 0, -1.0
    for i, r in enumerate(rows[:15]):
        texts = [c for c in r if isinstance(c, str) and c.strip()]
        if not texts:
            continue
        score = len(texts) / max(len(r), 1)
        score += sum(1 for c in texts if _match_field(c)[0]) * 0.5
        if score > best_score:
            best, best_score = i, score
    return best


def _match_field(header: str) -> tuple[str | None, float]:
    h = normalize_text(str(header))
    if not h:
        return None, 0.0
    best, best_score = None, 0.0
    for field, (label, _t, syns) in TARGET_FIELDS.items():
        for s in [normalize_text(label)] + [normalize_text(x) for x in syns]:
            if h == s:
                score = 1.0
            elif re.search(rf"\b{re.escape(s)}\b", h):
                score = 0.75 + min(len(s) / max(len(h), 1), 1) * 0.2
            else:
                continue
            if score > best_score:
                best, best_score = field, score
    return best, round(best_score, 2)


def suggest_mapping(headers: list[str]) -> dict[str, dict]:
    used: dict[str, float] = {}
    out: dict[str, dict] = {}
    cands = []
    for idx, h in enumerate(headers):
        f, s = _match_field(h) if h else (None, 0)
        cands.append((idx, h, f, s))
    for idx, h, f, s in sorted(cands, key=lambda c: -c[3]):
        if f and f not in used:
            used[f] = s
            out[str(idx)] = {"header": h, "field": f, "confidence": s}
        else:
            out[str(idx)] = {"header": h, "field": None, "confidence": 0}
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def preview(path: Path, sheet: str | None, header_row: int | None = None) -> dict:
    sheets = read_sheets(path)
    if not sheets:
        raise ImportError_("Het bestand bevat geen gegevens.")
    name = sheet if sheet in sheets else next(iter(sheets))
    rows = sheets[name]
    if not rows:
        return {"sheets": list(sheets), "sheet": name, "headers": [], "rows": [], "header_row": 1,
                "mapping": {}, "row_count": 0}
    hr = (header_row - 1) if header_row else detect_header_row(rows)
    hr = max(0, min(hr, len(rows) - 1))
    headers = [str(c).strip() if c is not None else f"Kolom {i + 1}" for i, c in enumerate(rows[hr])]
    data = rows[hr + 1:]
    return {"sheets": list(sheets), "sheet": name, "header_row": hr + 1, "headers": headers,
            "rows": [[_cell(c) for c in r] for r in data[:25]], "row_count": len(data),
            "mapping": suggest_mapping(headers)}


def _cell(c):
    if isinstance(c, (datetime, date)):
        return c.isoformat()[:10]
    return c


# ---------------------------------------------------------------- conversie
def parse_amount(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("€", "").replace("EUR", "").replace(" ", "").replace(" ", "")
    if s in ("-", "–", "n.v.t.", "nvt", "onbekend", "?"):
        return None
    if s.endswith(",-") or s.endswith(".-"):
        s = s[:-2]
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s) or re.fullmatch(r"-?\d+,\d+", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", s):
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"'{v}' is geen geldig bedrag")


def parse_year(v: Any) -> int | None:
    if v in (None, ""):
        return None
    if isinstance(v, (datetime, date)):
        return v.year
    try:
        y = int(float(str(v).strip()))
    except ValueError:
        raise ValueError(f"'{v}' is geen geldig bouwjaar")
    if not 1885 <= y <= date.today().year:
        raise ValueError(f"Bouwjaar {y} is onwaarschijnlijk")
    return y


def parse_cell_date(v: Any) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 20000 < v < 80000:  # Excel-serienummer
        from datetime import timedelta
        return date(1899, 12, 30) + timedelta(days=int(v))
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%y", "%m-%Y", "%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"'{v}' is geen herkenbare datum")


def parse_period(v: Any) -> str:
    s = normalize_text(str(v or ""))
    if not s or s.startswith("jaar") or s in ("j", "per jaar", "jaarlijks"):
        return "jaar"
    if "maand" in s:
        return "maand"
    if "kwartaal" in s:
        return "kwartaal"
    if "half" in s:
        return "half_jaar"
    raise ValueError(f"Onbekende premieperiode '{v}'")


def parse_tax(v: Any) -> str:
    s = normalize_text(str(v or ""))
    if not s:
        return "onbekend"
    if s in ("ja", "j", "incl", "inclusief", "yes", "true", "1") or s.startswith("incl"):
        return "ja"
    if s in ("nee", "n", "excl", "exclusief", "no", "false", "0") or s.startswith("excl"):
        return "nee"
    return "onbekend"


def _match_provider(db: Session, name: str) -> Provider | None:
    n = normalize_text(name)
    for p in db.scalars(select(Provider)):
        if normalize_text(p.name) == n:
            return p.merged_into_id and db.get(Provider, p.merged_into_id) or p
    return None


def _match_product(db: Session, provider: Provider | None, name: str | None) -> Product | None:
    if not provider or not name:
        return None
    n = normalize_text(name)
    for p in db.scalars(select(Product).where(Product.provider_id == provider.id)):
        if normalize_text(p.name) == n:
            return p
    return None


def build_rows(db: Session, imp: ExcelImport) -> dict:
    """Converteer de rijen volgens de koppeling en valideer ze. Er wordt niets opgeslagen."""
    sheets = read_sheets(Path(imp.stored_path))
    rows = sheets.get(imp.sheet or next(iter(sheets)), [])
    hr = (imp.header_row or 1) - 1
    data = rows[hr + 1:]
    mapping = {int(k): v for k, v in (imp.mapping or {}).items() if v}
    defaults = imp.defaults or {}
    mapped_fields = set(mapping.values())
    missing_fields = [TARGET_FIELDS[f][0] for f in REQUIRED if f not in mapped_fields]
    out, errors, warnings = [], [], []
    seen: dict[tuple, int] = {}
    existing_keys = set()
    for o in db.scalars(select(PremiumObservation).where(PremiumObservation.import_id != imp.id)):
        existing_keys.add(_dup_key_obs(o))

    for i, r in enumerate(data, start=hr + 2):
        rec: dict[str, Any] = {}
        row_err = []
        for col, field in mapping.items():
            raw = r[col] if col < len(r) else None
            try:
                ftype = TARGET_FIELDS[field][1]
                if ftype == "bedrag":
                    rec[field] = parse_amount(raw)
                elif ftype == "jaar":
                    rec[field] = parse_year(raw)
                elif ftype == "datum":
                    rec[field] = parse_cell_date(raw)
                elif field == "period":
                    rec[field] = parse_period(raw)
                elif field == "tax_included":
                    rec[field] = parse_tax(raw)
                else:
                    rec[field] = (str(raw).strip() if raw is not None else None) or None
            except ValueError as exc:
                row_err.append(f"{TARGET_FIELDS[field][0]}: {exc}")
        for k, v in defaults.items():
            if rec.get(k) in (None, "") and v not in (None, ""):
                rec[k] = parse_cell_date(v) if k == "reference_date" else v
        rec.setdefault("period", "jaar")
        if not rec.get("provider"):
            row_err.append("Verzekeraar ontbreekt")
        if rec.get("amount") is None:
            row_err.append("Premie ontbreekt of is ongeldig")
        elif rec["amount"] is not None and rec["amount"] <= 0:
            row_err.append("Premie moet groter dan 0 zijn")
        elif rec["amount"] and rec["amount"] > 100000:
            row_err.append("Premie is onwaarschijnlijk hoog")
        row_warn = []
        if not rec.get("reference_date"):
            row_warn.append("Onderzoeksdatum ontbreekt")
        if not rec.get("coverage_variant"):
            row_warn.append("Dekkingsvorm ontbreekt (beperkt vergelijkbaar)")
        if rec.get("deductible") is None and "deductible" in mapped_fields:
            row_warn.append("Eigen risico ontbreekt")
        prov = _match_provider(db, rec["provider"]) if rec.get("provider") else None
        if rec.get("provider") and not prov:
            row_warn.append(f"Verzekeraar '{rec['provider']}' is (nog) niet bekend; wordt als tekst bewaard")
        prod = _match_product(db, prov, rec.get("product"))
        key = (normalize_text(rec.get("provider") or ""), normalize_text(rec.get("product") or ""),
               normalize_text(rec.get("vehicle") or ""), rec.get("build_year"), rec.get("insured_value"),
               normalize_text(rec.get("coverage_variant") or ""), rec.get("amount"),
               rec.get("reference_date").isoformat() if rec.get("reference_date") else None)
        dup = None
        if key in seen:
            dup = f"Duplicaat van rij {seen[key]}"
        elif key in existing_keys:
            dup = "Komt al voor in de database"
        else:
            seen[key] = i
        if dup:
            row_warn.append(dup)
        item = {"row": i, "values": {k: (v.isoformat() if isinstance(v, date) else v) for k, v in rec.items()},
                "provider_id": prov.id if prov else None, "product_id": prod.id if prod else None,
                "errors": row_err, "warnings": row_warn, "duplicate": bool(dup)}
        out.append(item)
        if row_err:
            errors.append({"row": i, "messages": row_err})
        if row_warn:
            warnings.append({"row": i, "messages": row_warn})
    valid = [x for x in out if not x["errors"]]
    return {
        "rows": out, "total": len(out), "valid": len(valid),
        "invalid": len(out) - len(valid), "duplicates": sum(1 for x in out if x["duplicate"]),
        "missing_required_mappings": missing_fields, "errors": errors[:500], "warnings": warnings[:500],
    }


def _dup_key_obs(o: PremiumObservation) -> tuple:
    return (normalize_text(o.provider_name_raw or ""), normalize_text(o.product_name_raw or ""),
            normalize_text(o.vehicle_description or ""), o.build_year, o.insured_value,
            normalize_text(o.coverage_variant or ""), o.amount,
            o.reference_date.isoformat() if o.reference_date else None)


def commit_import(db: Session, imp: ExcelImport, skip_duplicates: bool = True) -> dict:
    result = build_rows(db, imp)
    if result["missing_required_mappings"]:
        raise ImportError_("Koppel eerst de verplichte velden: " + ", ".join(result["missing_required_mappings"]))
    historical = imp.treat_as != "actueel"
    n = 0
    for item in result["rows"]:
        if item["errors"] or (skip_duplicates and item["duplicate"]):
            continue
        v = item["values"]
        ref = date.fromisoformat(v["reference_date"]) if v.get("reference_date") else None
        o = PremiumObservation(
            provider_id=item["provider_id"], provider_name_raw=v.get("provider"),
            product_id=item["product_id"], product_name_raw=v.get("product"),
            amount=v["amount"], period=v.get("period") or "jaar",
            annual_premium=annualize(v["amount"], v.get("period") or "jaar"),
            tax_included=v.get("tax_included") or "onbekend",
            coverage_variant=v.get("coverage_variant"), deductible=v.get("deductible"),
            vehicle_category=v.get("vehicle_category"), vehicle_description=v.get("vehicle"),
            build_year=v.get("build_year"), insured_value=v.get("insured_value"), km_band=v.get("km_band"),
            reference_date=ref, calculated_at=ref,
            observation_type="historisch_tarief" if historical else "handmatige_offerte",
            is_historical=historical, reliability="middel" if ref else "laag",
            import_id=imp.id, visibility=imp.visibility,
            source_description=f"Excel-import '{imp.filename}', werkblad '{imp.sheet}', rij {item['row']}",
            notes=v.get("notes"),
        )
        db.add(o)
        n += 1
    imp.imported_count = n
    imp.row_count = result["total"]
    imp.status = "geimporteerd"
    imp.validation = {k: result[k] for k in ("total", "valid", "invalid", "duplicates")}
    db.commit()
    return {"imported": n, **imp.validation}
