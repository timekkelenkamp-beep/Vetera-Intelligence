from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (CalculatorConnector, CalculatorLog, ExcelImport, ImportMappingTemplate, Notification,
                      PremiumObservation, Product, Provider, ReferenceProfile)
from ..services import excel_import as xi
from ..services.common import OBSERVATION_TYPES, VISIBILITY, apply_updates, audit, get_or_404, parse_date, to_dict
from ..services.premiums import PERIOD_FACTOR, annualize, breakdown, compare_profile, history, observation_dict
from ..services.settings_store import get_setting

router = APIRouter(prefix="/api", tags=["premielab"])

PROFILE_FIELDS = ["name", "vehicle_category", "make", "model", "build_year", "vehicle_type", "engine_cc",
                  "insured_value", "valuation_value", "postcode_area", "driver_age_band", "claim_free_years",
                  "annual_km", "storage", "usage", "coverage", "deductible", "extras", "vehicle_count", "notes"]
OBS_FIELDS = ["provider_id", "product_id", "profile_id", "amount", "period", "currency", "tax_included",
              "extra_costs", "membership_costs", "coverage_variant", "deductible", "vehicle_category",
              "vehicle_description", "build_year", "insured_value", "km_band", "source_id", "source_description",
              "reference_date", "calculated_at", "observation_type", "reliability", "is_historical",
              "is_actual_quote", "visibility", "notes", "provider_name_raw", "product_name_raw"]
OBS_ENUMS = {"observation_type": set(OBSERVATION_TYPES), "period": set(PERIOD_FACTOR),
             "tax_included": {"ja", "nee", "onbekend"}, "reliability": {"hoog", "middel", "laag"},
             "visibility": VISIBILITY}


# ---------------------------------------------------------------- profielen
@router.get("/profiles")
def list_profiles(db: Session = Depends(get_db)):
    out = []
    for p in db.scalars(select(ReferenceProfile).order_by(ReferenceProfile.id)):
        d = to_dict(p)
        d["premium_count"] = len(db.scalars(select(PremiumObservation.id).where(PremiumObservation.profile_id == p.id)).all())
        out.append(d)
    return out


@router.post("/profiles")
def create_profile(data: dict, db: Session = Depends(get_db)):
    p = ReferenceProfile(name=(data.get("name") or "Nieuw rekenprofiel").strip())
    db.add(p)
    db.flush()
    apply_updates(db, p, data, PROFILE_FIELDS, "profile")
    db.commit()
    return to_dict(p)


@router.patch("/profiles/{pid}")
def update_profile(pid: int, data: dict, db: Session = Depends(get_db)):
    p = get_or_404(db, ReferenceProfile, pid, "Profiel")
    n = len(db.scalars(select(PremiumObservation.id).where(PremiumObservation.profile_id == p.id)).all())
    risk = {"vehicle_category", "build_year", "insured_value", "valuation_value", "annual_km", "coverage",
            "deductible", "storage", "usage", "driver_age_band", "engine_cc"}
    if n and any(k in data and data[k] != getattr(p, k) for k in risk) and not data.get("force"):
        raise HTTPException(409, f"Aan dit profiel hangen {n} premies. Wijzigen van risicokenmerken maakt die "
                                 "onvergelijkbaar. Dupliceer het profiel of bevestig de wijziging.")
    apply_updates(db, p, data, PROFILE_FIELDS, "profile")
    db.commit()
    return to_dict(p)


@router.post("/profiles/{pid}/duplicate")
def duplicate_profile(pid: int, db: Session = Depends(get_db)):
    p = get_or_404(db, ReferenceProfile, pid, "Profiel")
    d = {k: getattr(p, k) for k in PROFILE_FIELDS}
    d["name"] = f"{p.name} (kopie)"
    n = ReferenceProfile(**d)
    db.add(n)
    db.commit()
    return to_dict(n)


@router.delete("/profiles/{pid}")
def delete_profile(pid: int, db: Session = Depends(get_db)):
    p = get_or_404(db, ReferenceProfile, pid, "Profiel")
    db.delete(p)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- premiewaarnemingen
@router.get("/premiums")
def list_premiums(profile_id: int | None = None, provider_id: int | None = None, observation_type: str | None = None,
                  import_id: int | None = None, include_historical: bool = True, db: Session = Depends(get_db)):
    stmt = select(PremiumObservation)
    if profile_id:
        stmt = stmt.where(PremiumObservation.profile_id == profile_id)
    if provider_id:
        stmt = stmt.where(PremiumObservation.provider_id == provider_id)
    if observation_type:
        stmt = stmt.where(PremiumObservation.observation_type == observation_type)
    if import_id:
        stmt = stmt.where(PremiumObservation.import_id == import_id)
    if not include_historical:
        stmt = stmt.where(PremiumObservation.is_historical.is_(False))
    return [observation_dict(db, o) for o in db.scalars(stmt.order_by(PremiumObservation.reference_date.desc()).limit(5000))]


def _normalize_obs(db: Session, o: PremiumObservation):
    if o.observation_type == "niet_beschikbaar":
        o.amount = o.annual_premium = None
    else:
        if o.amount is None:
            raise HTTPException(422, "Vul een premiebedrag in, of kies type 'Niet beschikbaar'. Premies worden nooit geschat.")
        if o.amount <= 0:
            raise HTTPException(422, "Premie moet groter dan 0 zijn")
        o.annual_premium = annualize(o.amount, o.period or "jaar")
    if o.observation_type == "historisch_tarief":
        o.is_historical = True
    if o.product_id:
        p = db.get(Product, o.product_id)
        if p and o.provider_id and p.provider_id != o.provider_id:
            raise HTTPException(422, "Product hoort niet bij deze aanbieder")
        if p and not o.provider_id:
            o.provider_id = p.provider_id
    if not o.provider_id and not o.provider_name_raw:
        raise HTTPException(422, "Aanbieder is verplicht")


def _check_alert(db: Session, o: PremiumObservation):
    """Meld een relevant premieverschil t.o.v. Vetera voor hetzelfde profiel."""
    if not o.profile_id or o.annual_premium is None:
        return
    pct_limit = float(get_setting(db, "premium_difference_alert_pct", 15) or 15)
    comp = compare_profile(db, o.profile_id)
    if comp["baseline"] != "vetera":
        return
    for r in comp["rows"]:
        if r["id"] == o.id and r["diff_pct"] is not None and abs(r["diff_pct"]) >= pct_limit:
            db.add(Notification(type="premieverschil", title=f"Premieverschil {r['diff_pct']:+.0f}% bij {r['provider_name']}",
                                body=f"Profiel '{comp['profile']['name']}'. " + ("Let op: " + "; ".join(r["comparability_issues"])
                                                                               if r["comparability_issues"] else "Volledig vergelijkbaar."),
                                link="/premielab"))


@router.post("/premiums")
def create_premium(data: dict, db: Session = Depends(get_db)):
    o = PremiumObservation()
    db.add(o)
    apply_updates(db, o, {"observation_type": "handmatige_offerte", "period": "jaar", **data}, OBS_FIELDS, "premium",
                  date_fields=["reference_date", "calculated_at"], enums=OBS_ENUMS)
    o.reference_date = o.reference_date or date.today()
    _normalize_obs(db, o)
    db.flush()
    audit(db, "premium", o.id, "aangemaakt", {"bedrag": o.amount, "type": o.observation_type})
    _check_alert(db, o)
    db.commit()
    return observation_dict(db, o)


@router.patch("/premiums/{oid}")
def update_premium(oid: int, data: dict, db: Session = Depends(get_db)):
    o = get_or_404(db, PremiumObservation, oid, "Premie")
    apply_updates(db, o, data, OBS_FIELDS, "premium", date_fields=["reference_date", "calculated_at"], enums=OBS_ENUMS)
    _normalize_obs(db, o)
    db.commit()
    return observation_dict(db, o)


@router.delete("/premiums/{oid}")
def delete_premium(oid: int, db: Session = Depends(get_db)):
    o = get_or_404(db, PremiumObservation, oid, "Premie")
    audit(db, "premium", o.id, "verwijderd", {"bedrag": o.amount})
    db.delete(o)
    db.commit()
    return {"ok": True}


@router.get("/premiums/compare")
def premiums_compare(profile_id: int, as_of: str | None = None, include_historical: bool = False,
                     db: Session = Depends(get_db)):
    get_or_404(db, ReferenceProfile, profile_id, "Profiel")
    return compare_profile(db, profile_id, parse_date(as_of), include_historical,
                           int(get_setting(db, "premium_stale_months", 12) or 12))


@router.get("/premiums/history")
def premiums_history(profile_id: int | None = None, provider_id: int | None = None, coverage_variant: str | None = None,
                     db: Session = Depends(get_db)):
    return history(db, profile_id, provider_id, coverage_variant)


@router.get("/premiums/breakdown")
def premiums_breakdown(dimension: str = "dekking", db: Session = Depends(get_db)):
    if dimension not in ("dekking", "categorie", "waarde", "kilometers"):
        raise HTTPException(422, "Onbekende dimensie")
    return breakdown(db, dimension)


# ---------------------------------------------------------------- Excel Import Studio
@router.get("/imports/fields")
def import_fields():
    return [{"field": k, "label": v[0], "type": v[1], "required": k in xi.REQUIRED} for k, v in xi.TARGET_FIELDS.items()]


@router.get("/imports")
def list_imports(db: Session = Depends(get_db)):
    return [to_dict(i, exclude=["stored_path"]) for i in db.scalars(select(ExcelImport).order_by(ExcelImport.created_at.desc()))]


@router.post("/imports/upload")
async def upload_import(file: UploadFile = File(...), visibility: str = Form("niet_publiek"), db: Session = Depends(get_db)):
    data = await file.read()
    try:
        path, digest = xi.store_import_file(data, file.filename or "bestand.xlsx")
        prev = xi.preview(path, None)
    except xi.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    dup = db.scalars(select(ExcelImport).where(ExcelImport.sha256 == digest, ExcelImport.status == "geimporteerd")).first()
    imp = ExcelImport(filename=file.filename, stored_path=str(path), sha256=digest, sheet=prev["sheet"],
                      header_row=prev["header_row"], row_count=prev["row_count"],
                      mapping={k: v["field"] for k, v in prev["mapping"].items()},
                      visibility=visibility if visibility in VISIBILITY else "niet_publiek")
    db.add(imp)
    db.commit()
    return {"import": to_dict(imp, exclude=["stored_path"]), "preview": prev,
            "warning": f"Dit bestand is al eerder geïmporteerd (import #{dup.id})." if dup else None}


@router.post("/imports/{iid}/preview")
def import_preview(iid: int, data: dict, db: Session = Depends(get_db)):
    imp = get_or_404(db, ExcelImport, iid, "Import")
    try:
        prev = xi.preview(Path(imp.stored_path), data.get("sheet") or imp.sheet, data.get("header_row"))
    except xi.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.get("sheet") and data["sheet"] != imp.sheet or data.get("header_row"):
        imp.sheet, imp.header_row, imp.row_count = prev["sheet"], prev["header_row"], prev["row_count"]
        imp.mapping = {k: v["field"] for k, v in prev["mapping"].items()}
        db.commit()
    return {"import": to_dict(imp, exclude=["stored_path"]), "preview": prev}


@router.post("/imports/{iid}/validate")
def import_validate(iid: int, data: dict, db: Session = Depends(get_db)):
    imp = get_or_404(db, ExcelImport, iid, "Import")
    if imp.status == "geimporteerd":
        raise HTTPException(409, "Deze import is al uitgevoerd")
    fields = set(xi.TARGET_FIELDS)
    mapping = {str(k): (v if v in fields else None) for k, v in (data.get("mapping") or imp.mapping or {}).items()}
    used = [v for v in mapping.values() if v]
    if len(used) != len(set(used)):
        raise HTTPException(422, "Elk doelveld mag maar aan één kolom worden gekoppeld")
    imp.mapping = mapping
    imp.defaults = data.get("defaults") or imp.defaults or {}
    if data.get("treat_as") in ("historisch", "actueel"):
        imp.treat_as = data["treat_as"]
    try:
        res = xi.build_rows(db, imp)
    except xi.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    imp.status = "gevalideerd"
    imp.validation = {k: res[k] for k in ("total", "valid", "invalid", "duplicates")}
    db.commit()
    return {**res, "rows": res["rows"][:300]}


@router.post("/imports/{iid}/commit")
def import_commit(iid: int, data: dict, db: Session = Depends(get_db)):
    imp = get_or_404(db, ExcelImport, iid, "Import")
    if imp.status == "geimporteerd":
        raise HTTPException(409, "Deze import is al uitgevoerd")
    try:
        res = xi.commit_import(db, imp, skip_duplicates=data.get("skip_duplicates", True))
    except xi.ImportError_ as exc:
        raise HTTPException(422, str(exc)) from exc
    if data.get("save_template"):
        name = data["save_template"][:200]
        t = db.scalars(select(ImportMappingTemplate).where(ImportMappingTemplate.name == name)).first()
        headers = xi.preview(Path(imp.stored_path), imp.sheet, imp.header_row)["headers"]
        tmpl = {headers[int(k)]: v for k, v in (imp.mapping or {}).items() if v and int(k) < len(headers)}
        if t:
            t.mapping = tmpl
        else:
            db.add(ImportMappingTemplate(name=name, mapping=tmpl))
    audit(db, "excel_import", imp.id, "geimporteerd", res, "import")
    db.commit()
    return res


@router.post("/imports/{iid}/rollback")
def import_rollback(iid: int, db: Session = Depends(get_db)):
    imp = get_or_404(db, ExcelImport, iid, "Import")
    rows = db.scalars(select(PremiumObservation).where(PremiumObservation.import_id == imp.id)).all()
    for r in rows:
        db.delete(r)
    imp.status = "teruggedraaid"
    audit(db, "excel_import", imp.id, "teruggedraaid", {"verwijderd": len(rows)}, "gebruiker")
    db.commit()
    return {"removed": len(rows)}


@router.get("/import-templates")
def list_templates(db: Session = Depends(get_db)):
    return [to_dict(t) for t in db.scalars(select(ImportMappingTemplate))]


@router.post("/imports/{iid}/apply-template")
def apply_template(iid: int, data: dict, db: Session = Depends(get_db)):
    imp = get_or_404(db, ExcelImport, iid, "Import")
    t = get_or_404(db, ImportMappingTemplate, int(data.get("template_id") or 0), "Sjabloon")
    headers = xi.preview(Path(imp.stored_path), imp.sheet, imp.header_row)["headers"]
    imp.mapping = {str(i): t.mapping.get(h) for i, h in enumerate(headers)}
    db.commit()
    return {"mapping": imp.mapping}


# ---------------------------------------------------------------- calculators (fase 7)
CALC_FIELDS = ["provider_id", "name", "url", "terms_url", "permission_status", "permission_evidence",
               "terms_checked_at", "robots_status", "notes"]


@router.get("/calculators")
def list_calculators(db: Session = Depends(get_db)):
    out = []
    for c in db.scalars(select(CalculatorConnector)):
        d = to_dict(c)
        d["provider_name"] = db.get(Provider, c.provider_id).name if c.provider_id else None
        d["log"] = [to_dict(x) for x in db.scalars(select(CalculatorLog).where(CalculatorLog.connector_id == c.id)
                                                    .order_by(CalculatorLog.at.desc()).limit(20))]
        out.append(d)
    return out


@router.post("/calculators")
def create_calculator(data: dict, db: Session = Depends(get_db)):
    c = CalculatorConnector(name=data.get("name") or "Premiecalculator")
    db.add(c)
    db.flush()
    apply_updates(db, c, data, CALC_FIELDS, "calculator", date_fields=["terms_checked_at"],
                  enums={"permission_status": {"onbekend", "in_onderzoek", "toegestaan", "niet_toegestaan"}})
    db.add(CalculatorLog(connector_id=c.id, action="aangemaakt", message=f"Status: {c.permission_status}"))
    db.commit()
    return to_dict(c)


@router.patch("/calculators/{cid}")
def update_calculator(cid: int, data: dict, db: Session = Depends(get_db)):
    c = get_or_404(db, CalculatorConnector, cid, "Calculator")
    if data.get("permission_status") == "toegestaan" and not (data.get("permission_evidence") or c.permission_evidence):
        raise HTTPException(422, "Leg vast waaruit de toestemming blijkt (voorwaarden, schriftelijke toestemming).")
    changes = apply_updates(db, c, data, CALC_FIELDS, "calculator", date_fields=["terms_checked_at"],
                            enums={"permission_status": {"onbekend", "in_onderzoek", "toegestaan", "niet_toegestaan"}})
    if changes:
        db.add(CalculatorLog(connector_id=c.id, action="gewijzigd", message=", ".join(
            f"{k}: {v['oud']} → {v['nieuw']}" for k, v in changes.items())[:2000]))
    db.commit()
    return to_dict(c)


@router.post("/calculators/{cid}/run")
def run_calculator(cid: int, db: Session = Depends(get_db)):
    c = get_or_404(db, CalculatorConnector, cid, "Calculator")
    if c.permission_status != "toegestaan":
        msg = "Geautomatiseerd gebruik is niet als toegestaan vastgelegd; gebruik de handmatige workflow."
    elif not c.implemented:
        msg = ("Toestemming is vastgelegd, maar er is nog geen bron-specifieke connector gebouwd. "
               "Gebruik de handmatige workflow; een connector wordt alleen per bron en na toestemming ontwikkeld.")
    else:  # pragma: no cover - geen connectors meegeleverd
        msg = "Connector uitgevoerd."
    db.add(CalculatorLog(connector_id=c.id, action="uitvoeren_geweigerd" if not c.implemented else "uitgevoerd", message=msg))
    db.commit()
    if not c.implemented:
        raise HTTPException(409, msg)
    return {"ok": True}


@router.post("/calculators/{cid}/manual")
def manual_calculation(cid: int, data: dict, db: Session = Depends(get_db)):
    """Handmatige workflow: de gebruiker voert de proefberekening zelf uit en legt het resultaat vast."""
    c = get_or_404(db, CalculatorConnector, cid, "Calculator")
    payload = {**data, "observation_type": "proefberekening", "provider_id": data.get("provider_id") or c.provider_id,
               "source_description": f"Handmatige proefberekening via {c.name} ({c.url or 'geen URL'})",
               "is_actual_quote": False}
    res = create_premium(payload, db)
    db.add(CalculatorLog(connector_id=c.id, action="handmatig_vastgelegd", message=f"Premie #{res['id']}"))
    db.commit()
    return res
