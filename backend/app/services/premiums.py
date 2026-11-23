"""Premieberekeningen en vergelijkbaarheidscontroles.

Harde regels:
- Er worden nooit premies geschat of aangevuld.
- Premies met verschillende dekking, eigen risico, belastingbehandeling of peildatum
  worden alleen met expliciete waarschuwing naast elkaar getoond.
- Historische tarieven tellen nooit als actuele premie.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PremiumObservation, Product, Provider, ReferenceProfile
from .common import OBSERVATION_TYPES, to_dict

PERIOD_FACTOR = {"jaar": 1, "half_jaar": 2, "kwartaal": 4, "maand": 12}
NON_CURRENT_TYPES = {"historisch_tarief", "niet_beschikbaar"}


def annualize(amount: float | None, period: str) -> float | None:
    if amount is None:
        return None
    if period not in PERIOD_FACTOR:
        raise ValueError(f"Onbekende premieperiode: {period}")
    return round(float(amount) * PERIOD_FACTOR[period], 2)


def total_annual_cost(o: PremiumObservation) -> float | None:
    if o.annual_premium is None:
        return None
    return round(o.annual_premium + (o.membership_costs or 0) + (o.extra_costs or 0), 2)


def comparability_issues(a: PremiumObservation, b: PremiumObservation, stale_months: int = 12) -> list[str]:
    """Redenen waarom twee waarnemingen niet volledig vergelijkbaar zijn."""
    issues = []
    if a.profile_id != b.profile_id:
        issues.append("Verschillend referentieprofiel")
    if (a.coverage_variant or "?") != (b.coverage_variant or "?"):
        issues.append(f"Andere dekkingsvariant ({a.coverage_variant or 'onbekend'} vs {b.coverage_variant or 'onbekend'})")
    if a.deductible != b.deductible:
        issues.append(f"Ander eigen risico ({_eur(a.deductible)} vs {_eur(b.deductible)})")
    if a.tax_included != b.tax_included or "onbekend" in (a.tax_included, b.tax_included):
        issues.append("Assurantiebelasting niet eenduidig (in-/exclusief of onbekend)")
    if a.currency != b.currency:
        issues.append("Verschillende valuta")
    if a.observation_type in NON_CURRENT_TYPES or b.observation_type in NON_CURRENT_TYPES:
        issues.append("Historisch of niet-beschikbaar tarief")
    if a.reference_date and b.reference_date:
        if abs((a.reference_date - b.reference_date).days) > 183:
            issues.append("Peildata liggen meer dan 6 maanden uit elkaar")
    else:
        issues.append("Peildatum ontbreekt")
    for o in (a, b):
        if o.reference_date and (date.today() - o.reference_date).days > stale_months * 30.5:
            issues.append(f"Verouderde premie ({o.reference_date.isoformat()})")
            break
    if a.is_actual_quote != b.is_actual_quote:
        issues.append("Getoonde premie vergeleken met daadwerkelijk uitgebrachte offerte")
    return issues


def _eur(v):
    return "onbekend" if v is None else f"€ {v:,.0f}".replace(",", ".")


def observation_dict(db: Session, o: PremiumObservation) -> dict:
    d = to_dict(o)
    prov = db.get(Provider, o.provider_id) if o.provider_id else None
    prod = db.get(Product, o.product_id) if o.product_id else None
    d["provider_name"] = prov.name if prov else o.provider_name_raw
    d["provider_is_reference"] = bool(prov and prov.is_reference)
    d["product_name"] = prod.name if prod else o.product_name_raw
    d["total_annual_cost"] = total_annual_cost(o)
    d["observation_type_label"] = OBSERVATION_TYPES.get(o.observation_type, o.observation_type)
    return d


def compare_profile(db: Session, profile_id: int, as_of: date | None = None,
                    include_historical: bool = False, stale_months: int = 12) -> dict:
    """Vergelijk premies voor één referentieprofiel. Per aanbieder/product de meest recente
    waarneming op of vóór de peildatum."""
    profile = db.get(ReferenceProfile, profile_id)
    q = select(PremiumObservation).where(PremiumObservation.profile_id == profile_id,
                                         PremiumObservation.annual_premium.is_not(None))
    obs = db.scalars(q).all()
    if not include_historical:
        obs = [o for o in obs if o.observation_type not in NON_CURRENT_TYPES and not o.is_historical]
    if as_of:
        obs = [o for o in obs if o.reference_date is None or o.reference_date <= as_of]
    latest: dict[tuple, PremiumObservation] = {}
    for o in obs:
        key = (o.provider_id or o.provider_name_raw, o.product_id or o.product_name_raw, o.coverage_variant)
        cur = latest.get(key)
        if cur is None or (o.reference_date or date.min) > (cur.reference_date or date.min):
            latest[key] = o
    rows = sorted(latest.values(), key=lambda o: total_annual_cost(o) or 0)
    ref = next((o for o in rows if o.provider_id and (p := db.get(Provider, o.provider_id)) and p.is_reference), None)
    baseline = ref or (rows[0] if rows else None)
    out_rows = []
    for o in rows:
        d = observation_dict(db, o)
        if baseline is not None and o is not baseline:
            bc, oc = total_annual_cost(baseline), total_annual_cost(o)
            d["diff_abs"] = round(oc - bc, 2) if bc is not None and oc is not None else None
            d["diff_pct"] = round((oc - bc) / bc * 100, 1) if bc else None
            d["comparability_issues"] = comparability_issues(baseline, o, stale_months)
        else:
            d["diff_abs"] = d["diff_pct"] = None
            d["comparability_issues"] = []
        d["is_baseline"] = o is baseline
        d["fully_comparable"] = not d["comparability_issues"]
        out_rows.append(d)
    return {
        "profile": to_dict(profile) if profile else None,
        "baseline": "vetera" if ref else ("laagste" if baseline else None),
        "baseline_note": ("Verschillen ten opzichte van Vetera." if ref else
                          "Geen Vetera-premie voor dit profiel; verschillen ten opzichte van de laagste "
                          "vastgelegde premie." if baseline else "Nog geen premies voor dit profiel."),
        "as_of": as_of.isoformat() if as_of else None,
        "rows": out_rows,
    }


def history(db: Session, profile_id: int | None = None, provider_id: int | None = None,
            coverage_variant: str | None = None) -> dict:
    """Premieontwikkeling in de tijd, alleen binnen gelijke risico-/dekkingsprofielen."""
    q = select(PremiumObservation).where(PremiumObservation.annual_premium.is_not(None),
                                         PremiumObservation.reference_date.is_not(None))
    if profile_id:
        q = q.where(PremiumObservation.profile_id == profile_id)
    if provider_id:
        q = q.where(PremiumObservation.provider_id == provider_id)
    if coverage_variant:
        q = q.where(PremiumObservation.coverage_variant == coverage_variant)
    series: dict[str, list] = defaultdict(list)
    for o in db.scalars(q.order_by(PremiumObservation.reference_date)):
        prov = db.get(Provider, o.provider_id) if o.provider_id else None
        # serie = aanbieder + profiel + dekking + eigen risico: alleen gelijkwaardige punten
        label = " · ".join(str(x) for x in [
            prov.name if prov else (o.provider_name_raw or "Onbekend"),
            o.coverage_variant or "dekking onbekend",
            f"ER {_eur(o.deductible)}",
        ])
        key = f"{o.provider_id or o.provider_name_raw}|{o.profile_id}|{o.coverage_variant}|{o.deductible}"
        series[key].append({"date": o.reference_date.isoformat(), "annual_premium": o.annual_premium,
                            "total": total_annual_cost(o), "type": o.observation_type, "id": o.id,
                            "label": label, "profile_id": o.profile_id})
    return {"series": [{"key": k, "label": v[0]["label"], "points": v} for k, v in series.items()],
            "note": "Elke lijn bevat uitsluitend waarnemingen met hetzelfde profiel, dezelfde dekking en "
                    "hetzelfde eigen risico."}


def breakdown(db: Session, dimension: str) -> dict:
    """Gemiddelde jaarpremie per aanbieder, uitgesplitst naar dimensie (dekking, categorie,
    waardeklasse of kilometerbundel). Alleen actuele waarnemingen."""
    obs = [o for o in db.scalars(select(PremiumObservation).where(PremiumObservation.annual_premium.is_not(None)))
           if o.observation_type not in NON_CURRENT_TYPES and not o.is_historical]
    profiles = {p.id: p for p in db.scalars(select(ReferenceProfile))}

    def dim(o: PremiumObservation):
        p = profiles.get(o.profile_id)
        if dimension == "dekking":
            return o.coverage_variant or "onbekend"
        if dimension == "categorie":
            return o.vehicle_category or (p.vehicle_category if p else None) or "onbekend"
        if dimension == "waarde":
            v = o.insured_value or (p.insured_value if p else None)
            if v is None:
                return "onbekend"
            for lim, lbl in ((10000, "< € 10.000"), (25000, "€ 10.000–25.000"), (50000, "€ 25.000–50.000"),
                             (100000, "€ 50.000–100.000")):
                if v < lim:
                    return lbl
            return "≥ € 100.000"
        if dimension == "kilometers":
            if o.km_band:
                return o.km_band
            km = p.annual_km if p else None
            if km is None:
                return "onbekend"
            return "≤ 3.000 km" if km <= 3000 else "3.001–7.500 km" if km <= 7500 else "> 7.500 km"
        return "alle"

    groups: dict[tuple, list[float]] = defaultdict(list)
    for o in obs:
        prov = db.get(Provider, o.provider_id) if o.provider_id else None
        groups[(dim(o), prov.name if prov else (o.provider_name_raw or "Onbekend"))].append(total_annual_cost(o))
    rows = [{"group": g, "provider": p, "avg_total": round(sum(v) / len(v), 2), "n": len(v)}
            for (g, p), v in sorted(groups.items())]
    return {"dimension": dimension, "rows": rows,
            "note": "Gemiddelden over verschillende profielen zijn indicatief en niet volledig vergelijkbaar."}
