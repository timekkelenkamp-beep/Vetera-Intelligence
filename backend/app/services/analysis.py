"""Vergelijkingslogica zonder AI: voorwaardenmatrix, verschilverklaringen, scores,
lokale verkoopargumenten en datagedreven verbetersignalen.

Alle conclusies zijn herleidbaar naar concrete bevindingen (finding-id's) met bron.
Ontbrekende of onzekere informatie wordt nooit als 'niet verzekerd' geïnterpreteerd.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (Document, DocumentVersion, Feature, Finding, ImprovementSuggestion, Product,
                      Provider, ScoreProfile)
from .common import FINDING_STATUSES, KNOWN_STATUSES, to_dict
from .premiums import compare_profile

STATUS_RANK = {"gedekt": 3, "voorwaardelijk": 2, "aanvullende_clausule": 2, "uitgesloten": 0}
STATUS_SCORE = {"gedekt": 1.0, "voorwaardelijk": 0.5, "aanvullende_clausule": 0.5, "uitgesloten": 0.0}
# Welke scoringsaspecten tellen mee in welke weging
ASPECT_GROUPS = {
    "voorwaarden": {"dekking", "aanvullend", "waarde", "eigen_risico", "collectie"},
    "acceptatie": {"acceptatie"},
    "flexibiliteit": {"flexibiliteit", "gebruik"},
}


def current_findings(db: Session, product_ids: list[int]) -> dict[tuple[int, int], Finding]:
    rows = db.scalars(select(Finding).where(Finding.product_id.in_(product_ids), Finding.is_current.is_(True))).all()
    out: dict[tuple[int, int], Finding] = {}
    for f in rows:
        key = (f.product_id, f.feature_id)
        prev = out.get(key)
        # Menselijk vastgezette bevindingen hebben voorrang
        if prev is None or (f.locked and not prev.locked) or (f.locked == prev.locked and f.id > prev.id):
            out[key] = f
    return out


def finding_dict(db: Session, f: Finding | None) -> dict | None:
    if f is None:
        return None
    d = to_dict(f)
    d["status_label"] = FINDING_STATUSES.get(f.status, f.status)
    if f.document_version_id:
        v = db.get(DocumentVersion, f.document_version_id)
        if v:
            doc = db.get(Document, v.document_id)
            d["document"] = {"id": v.document_id, "version_id": v.id, "title": doc.title if doc else None,
                             "version_label": v.version_label, "doc_date": v.doc_date.isoformat() if v.doc_date else None}
    return d


def product_label(db: Session, p: Product) -> dict:
    prov = db.get(Provider, p.provider_id)
    return {"id": p.id, "name": p.name, "provider_id": p.provider_id, "provider_name": prov.name if prov else "",
            "is_reference": bool(prov and prov.is_reference), "vehicle_category": p.vehicle_category,
            "logo": f"/api/providers/{prov.id}/logo" if prov and prov.logo_status == "goedgekeurd" else None}


def explain_difference(feature: Feature, ref: Finding | None, other: Finding | None, ref_name: str,
                       other_name: str) -> dict | None:
    """Korte, onderbouwde uitleg van een verschil. Geen oordeel bij onvoldoende informatie."""
    rs, os_ = (ref.status if ref else None), (other.status if other else None)
    if rs is None and os_ is None:
        return None
    if rs not in KNOWN_STATUSES or os_ not in KNOWN_STATUSES:
        if rs == os_:
            return None
        return {"kind": "onzeker",
                "text": f"Niet vast te stellen: voor {ref_name if rs not in KNOWN_STATUSES else other_name} "
                        f"is de regeling {FINDING_STATUSES.get(rs if rs not in KNOWN_STATUSES else os_, 'onbekend').lower()}."}
    if feature.value_type == "status":
        r, o = STATUS_RANK[rs], STATUS_RANK[os_]
        if r == o:
            if (ref.value_text or "") != (other.value_text or "") and (ref.value_text or other.value_text):
                return {"kind": "afwijkend", "text": "Beide dekken dit onderdeel, met een afwijkende invulling; "
                                                     "zie de toelichting en bronpassages."}
            return None
        if o > r:
            return {"kind": "concurrent_ruimer",
                    "text": f"{other_name} biedt onder deze voorwaarden een ruimere regeling "
                            f"({FINDING_STATUSES[os_].lower()} tegenover {FINDING_STATUSES[rs].lower()} bij {ref_name})."}
        return {"kind": "referentie_ruimer",
                "text": f"{ref_name} biedt onder deze voorwaarden een ruimere regeling "
                        f"({FINDING_STATUSES[rs].lower()} tegenover {FINDING_STATUSES[os_].lower()} bij {other_name})."}
    # tekst / bedrag: alleen signaleren, niet rangschikken (tenzij beide numeriek bij eigen risico)
    if feature.value_type == "bedrag" and ref.value_number is not None and other.value_number is not None:
        if ref.value_number == other.value_number:
            return None
        lower = other_name if other.value_number < ref.value_number else ref_name
        return {"kind": "concurrent_ruimer" if lower == other_name else "referentie_ruimer",
                "text": f"{lower} hanteert een lager bedrag ({min(ref.value_number, other.value_number):,.0f} tegenover "
                        f"{max(ref.value_number, other.value_number):,.0f}). Controleer of de voorwaarden verder gelijk zijn."}
    if (ref.value_text or "").strip().lower() != (other.value_text or "").strip().lower():
        return {"kind": "afwijkend", "text": "Afwijkende regeling; vergelijk de bronpassages."}
    return None


def matrix(db: Session, product_ids: list[int], reference_product_id: int | None = None,
           category: str | None = None, only_differences: bool = False, only_unknown: bool = False,
           search: str | None = None) -> dict:
    products = [p for p in (db.get(Product, i) for i in product_ids) if p]
    ids = [p.id for p in products]
    q = select(Feature).where(Feature.active.is_(True)).order_by(Feature.sort_order)
    if category:
        q = q.where(Feature.category == category)
    features = db.scalars(q).all()
    fmap = current_findings(db, ids)
    ref = db.get(Product, reference_product_id) if reference_product_id else None
    labels = {p.id: product_label(db, p) for p in products}
    rows = []
    s = (search or "").lower().strip()
    for feat in features:
        cells = {}
        diffs = {}
        for p in products:
            f = fmap.get((p.id, feat.id))
            cells[str(p.id)] = finding_dict(db, f)
            if ref and p.id != ref.id:
                d = explain_difference(feat, fmap.get((ref.id, feat.id)), f, labels[ref.id]["provider_name"],
                                       labels[p.id]["provider_name"])
                if d:
                    diffs[str(p.id)] = d
        statuses = [c["status"] if c else None for c in cells.values()]
        has_unknown = any(st not in KNOWN_STATUSES for st in statuses)
        is_diff = bool(diffs) if ref else len({st for st in statuses}) > 1
        if only_differences and not is_diff:
            continue
        if only_unknown and not has_unknown:
            continue
        if s:
            blob = " ".join([feat.label, feat.category] + [
                " ".join(filter(None, [c.get("quote"), c.get("value_text"), c.get("article"), c.get("explanation")]))
                for c in cells.values() if c]).lower()
            if s not in blob:
                continue
        rows.append({"feature": to_dict(feat), "cells": cells, "differences": diffs,
                     "has_unknown": has_unknown, "is_difference": is_diff})
    return {"products": [labels[i] for i in ids], "reference_product_id": ref.id if ref else None,
            "rows": rows, "categories": sorted({f.category for f in db.scalars(select(Feature))},
                                               key=lambda c: ["Acceptatie", "Gebruik", "Verzekerde waarde", "Dekkingen",
                                                              "Eigen risico", "Collecties"].index(c)
                                               if c in ["Acceptatie", "Gebruik", "Verzekerde waarde", "Dekkingen",
                                                        "Eigen risico", "Collecties"] else 99)}


def product_summary(db: Session, product: Product, reference: Product | None) -> dict:
    """Kaartweergave: aantoonbare voor- en nadelen t.o.v. de referentie en datastatus."""
    ids = [product.id] + ([reference.id] if reference and reference.id != product.id else [])
    fmap = current_findings(db, ids)
    features = db.scalars(select(Feature).where(Feature.active.is_(True)).order_by(Feature.sort_order)).all()
    known = sum(1 for f in features if (fm := fmap.get((product.id, f.id))) and fm.status in KNOWN_STATUSES)
    verified = sum(1 for f in features if (fm := fmap.get((product.id, f.id))) and fm.review_status in ("goedgekeurd", "gecorrigeerd"))
    adv, disadv, highlights = [], [], []
    pl = product_label(db, product)
    for f in features:
        mine = fmap.get((product.id, f.id))
        if mine and mine.status == "gedekt" and f.value_type == "status" and len(highlights) < 6:
            highlights.append({"feature": f.label, "finding_id": mine.id})
        if reference and reference.id != product.id:
            rl = product_label(db, reference)
            d = explain_difference(f, fmap.get((reference.id, f.id)), mine, rl["provider_name"], pl["provider_name"])
            if d and d["kind"] == "concurrent_ruimer":
                adv.append({"feature": f.label, "text": d["text"], "finding_id": mine.id if mine else None})
            elif d and d["kind"] == "referentie_ruimer":
                disadv.append({"feature": f.label, "text": d["text"], "finding_id": mine.id if mine else None})
    return {**pl, "features_total": len(features), "features_known": known, "features_verified": verified,
            "data_status": "onvoldoende" if known < len(features) * 0.3 else "gedeeltelijk"
            if known < len(features) * 0.8 else "goed",
            "highlights": highlights, "advantages": adv[:6], "disadvantages": disadv[:6]}


# ---------------------------------------------------------------- scores
def compute_scores(db: Session, score_profile: ScoreProfile, product_ids: list[int]) -> dict:
    weights = {k: float(v) for k, v in (score_profile.weights or {}).items() if float(v) > 0}
    features = db.scalars(select(Feature).where(Feature.active.is_(True))).all()
    fmap = current_findings(db, product_ids)
    premium_info = {}
    if score_profile.reference_profile_id and "premie" in weights:
        comp = compare_profile(db, score_profile.reference_profile_id)
        totals = [r["total_annual_cost"] for r in comp["rows"] if r["total_annual_cost"]]
        lo = min(totals) if totals else None
        for r in comp["rows"]:
            if r["product_id"] and r["total_annual_cost"] and lo:
                prev = premium_info.get(r["product_id"])
                if prev is None or r["total_annual_cost"] < prev["total"]:
                    premium_info[r["product_id"]] = {"total": r["total_annual_cost"],
                                                     "score": round(lo / r["total_annual_cost"], 3),
                                                     "comparable": r["fully_comparable"] or r["is_baseline"],
                                                     "issues": r["comparability_issues"]}
    results = []
    for pid in product_ids:
        p = db.get(Product, pid)
        if not p:
            continue
        aspects = {}
        for group, asp in ASPECT_GROUPS.items():
            if group not in weights:
                continue
            feats = [f for f in features if f.scoring_aspect in asp and f.value_type == "status"]
            vals, unknown = [], []
            for f in feats:
                fm = fmap.get((pid, f.id))
                if fm and fm.status in STATUS_SCORE:
                    vals.append((f.label, STATUS_SCORE[fm.status], fm.id))
                else:
                    unknown.append(f.label)
            coverage = len(vals) / len(feats) if feats else 0
            enough = coverage >= score_profile.min_coverage and len(vals) > 0
            aspects[group] = {
                "score": round(sum(v for _, v, _ in vals) / len(vals) * 100, 1) if enough else None,
                "coverage": round(coverage, 2), "known": len(vals), "total": len(feats),
                "unknown_features": unknown, "basis": [{"feature": l, "value": v, "finding_id": i} for l, v, i in vals],
                "note": None if enough else f"Onvoldoende betrouwbare gegevens ({len(vals)}/{len(feats)} bekend; "
                                            f"minimaal {int(score_profile.min_coverage * 100)}% nodig).",
            }
        if "premie" in weights:
            pi = premium_info.get(pid)
            aspects["premie"] = {
                "score": round(pi["score"] * 100, 1) if pi and pi["comparable"] else None,
                "basis": pi, "note": None if pi and pi["comparable"] else
                ("Geen premie voor het gekozen rekenprofiel." if not pi else
                 "Premie niet volledig vergelijkbaar: " + "; ".join(pi["issues"])) if score_profile.reference_profile_id
                else "Kies een rekenprofiel om premies mee te wegen."}
        avail = {k: v for k, v in aspects.items() if v["score"] is not None}
        missing = [k for k in weights if k not in avail]
        total = None
        if avail and not missing:
            wsum = sum(weights[k] for k in avail)
            total = round(sum(avail[k]["score"] * weights[k] for k in avail) / wsum, 1)
        results.append({"product": product_label(db, p), "aspects": aspects, "total": total,
                        "missing_aspects": missing,
                        "total_note": None if total is not None else
                        "Geen totaalscore: niet alle gewogen aspecten zijn betrouwbaar te bepalen."})
    return {"score_profile": to_dict(score_profile), "results": results,
            "method": "Per aspect: gemiddelde van statuskenmerken (gedekt = 100, voorwaardelijk/aanvullende "
                      "clausule = 50, uitgesloten = 0). Onbekende kenmerken tellen niet mee; een aspect krijgt "
                      "alleen een score bij voldoende bekende kenmerken. Premie: laagste vergelijkbare totale "
                      "jaarlast / eigen totale jaarlast × 100. Een lage premie bepaalt nooit alleen de conclusie."}


# ---------------------------------------------------------------- lokale verkoopargumenten
def local_sales_card(db: Session, vetera: Product, competitor: Product) -> dict:
    feats = db.scalars(select(Feature).where(Feature.active.is_(True)).order_by(Feature.sort_order)).all()
    fmap = current_findings(db, [vetera.id, competitor.id])
    vl, cl = product_label(db, vetera), product_label(db, competitor)
    args, comp_strengths, unknown = [], [], []
    for f in feats:
        rv, rc = fmap.get((vetera.id, f.id)), fmap.get((competitor.id, f.id))
        d = explain_difference(f, rv, rc, vl["provider_name"], cl["provider_name"])
        if not d:
            continue
        if d["kind"] == "referentie_ruimer":
            args.append({"feature": f.label, "fact": d["text"],
                         "customer_benefit": f"Relevant voor klanten voor wie '{f.label.lower()}' belangrijk is.",
                         "sales_argument": f"Bespreek met de klant of {f.label.lower()} voor hem of haar van belang is.",
                         "evidence": [x for x in (finding_dict(db, rv), finding_dict(db, rc)) if x]})
        elif d["kind"] == "concurrent_ruimer":
            comp_strengths.append({"feature": f.label, "text": d["text"],
                                   "evidence": [x for x in (finding_dict(db, rc),) if x]})
        elif d["kind"] == "onzeker":
            unknown.append(f.label)
    return {
        "title": f"Waarom Vetera overwegen ten opzichte van {cl['provider_name']}?",
        "vetera": vl, "competitor": cl,
        "arguments": args[:5], "competitor_strengths": comp_strengths,
        "vetera_limitations": [c["text"] for c in comp_strengths],
        "unknown": unknown,
        "advisor_questions": [
            "Hoe en hoe vaak wordt het voertuig gebruikt (hobby, evenementen, buitenland)?",
            "Hoe is het voertuig gestald en is er een recent taxatierapport?",
            "Heeft de klant meerdere klassieke voertuigen die op één polis kunnen?",
            "Welk eigen risico en welke dekkingsvorm passen bij de waarde van het voertuig?",
        ],
        "disclaimer": "Automatisch afgeleid uit vastgelegde bevindingen. Uitsluitend aantoonbare verschillen; "
                      "onbekende onderdelen zijn niet als voor- of nadeel meegenomen.",
        "origin": "lokaal",
    }


# ---------------------------------------------------------------- datagedreven verbetersignalen
def local_radar_signals(db: Session) -> list[ImprovementSuggestion]:
    """Signaleert kenmerken waar concurrenten aantoonbaar ruimer zijn dan Vetera (en omgekeerd:
    onbenutte voordelen). Maakt suggesties met status 'nieuw', zonder dubbelingen."""
    vetera_products = db.scalars(select(Product).join(Provider, Product.provider_id == Provider.id)
                                 .where(Provider.is_reference.is_(True))).all()
    if not vetera_products:
        return []
    competitors = db.scalars(select(Product).join(Provider, Product.provider_id == Provider.id)
                             .where(Provider.is_reference.is_(False), Provider.status == "actief",
                                    Product.canonical_product_id.is_(None))).all()
    feats = db.scalars(select(Feature).where(Feature.active.is_(True))).all()
    fmap = current_findings(db, [p.id for p in vetera_products + competitors])
    created = []
    for vp in vetera_products:
        better_by: dict[int, list] = defaultdict(list)
        worse_by: dict[int, list] = defaultdict(list)
        for cp in competitors:
            if vp.vehicle_category != "meerdere" and cp.vehicle_category not in (vp.vehicle_category, "meerdere"):
                continue
            for f in feats:
                d = explain_difference(f, fmap.get((vp.id, f.id)), fmap.get((cp.id, f.id)), "Vetera",
                                       product_label(db, cp)["provider_name"])
                if not d:
                    continue
                if d["kind"] == "concurrent_ruimer":
                    better_by[f.id].append((cp, fmap.get((cp.id, f.id)), d["text"]))
                elif d["kind"] == "referentie_ruimer":
                    worse_by[f.id].append((cp, fmap.get((cp.id, f.id)), d["text"]))
        fdict = {f.id: f for f in feats}
        for fid, items in better_by.items():
            f = fdict[fid]
            fp = f"gap:{vp.id}:{fid}"
            if db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.fingerprint == fp)).first():
                continue
            names = sorted({product_label(db, cp)["provider_name"] for cp, _, _ in items})
            vf = fmap.get((vp.id, fid))
            ev = [{"type": "finding", "finding_id": vf.id, "label": f"Vetera – {f.label}"}] if vf else []
            ev += [{"type": "finding", "finding_id": fi.id, "label": f"{product_label(db, cp)['provider_name']} – {f.label}"}
                   for cp, fi, _ in items if fi]
            s = ImprovementSuggestion(
                kind="datagedreven", category="Voorwaardenverbetering",
                title=f"{f.label}: ruimere regeling bij {len(names)} concurrent(en)",
                summary=f"Bij {', '.join(names)} is '{f.label.lower()}' aantoonbaar ruimer geregeld dan in {vp.name}.",
                gap=items[0][2], vetera_situation=f"{vp.name}: {FINDING_STATUSES.get(vf.status, 'onbekend') if vf else 'onbekend'}"
                + (f" ({vf.value_text})" if vf and vf.value_text else ""),
                market_context=f"Concurrenten met ruimere regeling: {', '.join(names)}.",
                suggestion=f"Onderzoek of '{f.label.lower()}' binnen {vp.name} ruimer kan worden ingericht.",
                customer_benefits="Ruimere dekking of minder beperkingen op dit onderdeel.",
                commercial_benefits="Wegnemen van een aantoonbaar nadeel in vergelijkingen. Commercieel effect is "
                                    "niet betrouwbaar te kwantificeren.",
                risks="Mogelijke invloed op schadelast en premie; acceptatie- en risicobeleid moet worden beoordeeld.",
                evidence=ev, confidence="middel" if all(fi and fi.review_status in ("goedgekeurd", "gecorrigeerd")
                                                         for _, fi, _ in items) else "laag",
                priority="hoog" if len(names) >= 3 else "middel" if len(names) >= 2 else "laag",
                priority_factors={"aantoonbaarheid": "bronverwijzingen aanwezig",
                                  "concurrenten_met_ruimere_regeling": len(names),
                                  "klantwaarde": "niet gekwantificeerd", "uitvoerbaarheid": "onbekend"},
                follow_up="Controleer de bronpassages en beoordeel de impact op risico en premie.",
                origin="lokaal", fingerprint=fp)
            db.add(s)
            created.append(s)
        for fid, items in worse_by.items():
            if len(items) < 2:
                continue
            f = fdict[fid]
            fp = f"adv:{vp.id}:{fid}"
            if db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.fingerprint == fp)).first():
                continue
            names = sorted({product_label(db, cp)["provider_name"] for cp, _, _ in items})
            vf = fmap.get((vp.id, fid))
            s = ImprovementSuggestion(
                kind="datagedreven", category="Concurrentievoordeel",
                title=f"Onderscheidend voordeel: {f.label}",
                summary=f"{vp.name} is op '{f.label.lower()}' aantoonbaar ruimer dan {len(names)} concurrent(en).",
                gap="Mogelijk onvoldoende benut voordeel in commerciële communicatie.",
                vetera_situation=f"{vp.name}: {FINDING_STATUSES.get(vf.status, '') if vf else ''}",
                market_context=f"Minder ruim bij: {', '.join(names)}.",
                suggestion="Overweeg dit voordeel nadrukkelijker in advies- en verkoopmateriaal te benoemen.",
                customer_benefits="Duidelijker inzicht in de dekking.",
                commercial_benefits="Sterker onderscheidend vermogen in adviesgesprekken (niet gekwantificeerd).",
                risks="Claims moeten feitelijk en actueel blijven; concurrenten kunnen voorwaarden wijzigen.",
                evidence=[{"type": "finding", "finding_id": vf.id, "label": f"Vetera – {f.label}"}] if vf else [],
                confidence="middel", priority="middel",
                priority_factors={"aantoonbaarheid": "bronverwijzingen aanwezig", "concurrenten": len(names)},
                follow_up="Toets de formulering met compliance.", origin="lokaal", fingerprint=fp)
            db.add(s)
            created.append(s)
    db.commit()
    return created
