"""Gedeelde hulpfuncties: serialisatie, audittrail en veilige updates."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ..models import AuditLog

FINDING_STATUSES = {
    "gedekt": "Aantoonbaar gedekt",
    "uitgesloten": "Aantoonbaar uitgesloten",
    "voorwaardelijk": "Voorwaardelijk gedekt",
    "aanvullende_clausule": "Afhankelijk van aanvullende clausule",
    "niet_gevonden": "Niet gevonden",
    "onvoldoende_informatie": "Onvoldoende informatie",
    "menselijke_beoordeling": "Menselijke beoordeling noodzakelijk",
}
KNOWN_STATUSES = {"gedekt", "uitgesloten", "voorwaardelijk", "aanvullende_clausule"}

OBSERVATION_TYPES = {
    "geverifieerd_tarief": "Geverifieerd tarief",
    "proefberekening": "Vastgelegde proefberekening",
    "handmatige_offerte": "Handmatig ingevoerde offerte",
    "openbare_indicatie": "Openbare indicatie",
    "historisch_tarief": "Historisch tarief",
    "niet_beschikbaar": "Niet beschikbaar",
}

PROVIDER_TYPES = {"verzekeraar", "gevolmachtigde", "tussenpersoon", "distributeur", "onbekend"}
PROVIDER_STATUSES = {"actief", "te_beoordelen", "afgewezen", "samengevoegd"}
DOCUMENT_TYPES = {"polisvoorwaarden", "verzekeringskaart", "productinformatie", "clausule",
                  "aanvullende_voorwaarden", "premietabel", "overig"}
SOURCE_TYPES = {"officieel_primair", "openbaar_overig", "handmatig", "historisch", "niet_geverifieerd"}
VEHICLE_CATEGORIES = {"auto", "motor", "bromfiets", "meerdere"}
VISIBILITY = {"publiek", "niet_publiek"}


def to_dict(obj: Any, exclude: Iterable[str] = ()) -> dict:
    if obj is None:
        return None  # type: ignore[return-value]
    out = {}
    for col in inspect(obj).mapper.column_attrs:
        if col.key in exclude:
            continue
        v = getattr(obj, col.key)
        if isinstance(v, (datetime, date)):
            v = v.isoformat()
        out[col.key] = v
    return out


def _jsonable(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def audit(db: Session, entity: str, entity_id: int | None, action: str,
          changes: dict | None = None, actor: str = "gebruiker") -> None:
    db.add(AuditLog(entity=entity, entity_id=entity_id, action=action, actor=actor,
                    changes={k: _jsonable(v) for k, v in (changes or {}).items()}))


def parse_date(v: Any) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d", "%d-%m-%y"):
        try:
            return datetime.strptime(s[:10] if fmt.startswith("%Y") else s, fmt).date()
        except ValueError:
            continue
    raise HTTPException(422, f"Ongeldige datum: {s!r}. Gebruik JJJJ-MM-DD.")


def apply_updates(db: Session, obj: Any, data: dict, allowed: Iterable[str], entity: str,
                  date_fields: Iterable[str] = (), enums: dict[str, set] | None = None,
                  actor: str = "gebruiker") -> dict:
    """Werk alleen toegestane velden bij en leg wijzigingen vast in de audittrail."""
    changes = {}
    date_fields = set(date_fields)
    for key in allowed:
        if key not in data:
            continue
        val = data[key]
        if key in date_fields:
            val = parse_date(val)
        if isinstance(val, str):
            val = val.strip()
            if val == "" and key not in ("name", "title"):
                val = None
        if enums and key in enums and val is not None and val not in enums[key]:
            raise HTTPException(422, f"Ongeldige waarde voor {key}: {val!r}")
        old = getattr(obj, key)
        if old != val:
            changes[key] = {"oud": _jsonable(old), "nieuw": _jsonable(val)}
            setattr(obj, key, val)
    if changes:
        audit(db, entity, getattr(obj, "id", None), "bijgewerkt", changes, actor)
    return changes


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("­", "")
    s = re.sub(r"-\s*\n\s*", "", s)  # afbreekstreepjes aan regeleinde
    s = re.sub(r"[^\w€%]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "bestand"
    return name[:150]


def get_or_404(db: Session, model, obj_id: int, label: str = "Item"):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{label} niet gevonden")
    return obj
