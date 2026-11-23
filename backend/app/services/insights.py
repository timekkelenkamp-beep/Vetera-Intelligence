"""Inzichten bovenop de vastgelegde gegevens: positioneringskaart, adviestool, wat-als-simulator,
concurrentiekaart, tijdlijn, marktbericht en snelzoeken.

Alles is afgeleid van bestaande bevindingen, premies en documenten. Er wordt niets verzonnen:
ontbrekende gegevens worden als zodanig getoond, en hypothetische scenario's worden nooit opgeslagen.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from ..models import (AuditLog, Clause, Document, DocumentDiff, DocumentPage, DocumentVersion, Feature, Finding,
                      ImprovementSuggestion, MonitorRun, Notification, PremiumObservation, Product, Provider,
                      ReferenceProfile, ScoreProfile)
from .analysis import compute_scores, current_findings, finding_dict, local_sales_card, product_label
from .common import FINDING_STATUSES, KNOWN_STATUSES, OBSERVATION_TYPES, to_dict
from .premiums import compare_profile


def _vetera_product(db: Session, category: str | None = None) -> Product | None:
    q = select(Product).join(Provider, Product.provider_id == Provider.id).where(Provider.is_reference.is_(True))
    prods = db.scalars(q).all()
    if category:
        for p in prods:
            if p.vehicle_category in (category, "meerdere"):
                return p
    return prods[0] if prods else None


def _active_products(db: Session, category: str | None = None) -> list[Product]:
    q = (select(Product).join(Provider, Product.provider_id == Provider.id)
         .where(Provider.status == "actief", Product.canonical_product_id.is_(None)))
    if category:
        q = q.where(Product.vehicle_category.in_([category, "meerdere"]))
    return list(db.scalars(q))


# ---------------------------------------------------------------- 1. positioneringskaart
def positioning(db: Session, profile_id: int, min_coverage: float = 0.5) -> dict:
    """Plaats producten op premie (x) tegenover breedte van de voorwaarden (y)."""
    profile = db.get(ReferenceProfile, profile_id)
    if not profile:
        raise ValueError("Rekenprofiel niet gevonden.")
    products = _active_products(db, profile.vehicle_category if profile.vehicle_category != "meerdere" else None)
    sp = ScoreProfile(name="positionering", weights={"voorwaarden": 1}, min_coverage=min_coverage)
    scores = {r["product"]["id"]: r for r in compute_scores(db, sp, [p.id for p in products])["results"]}
    comp = compare_profile(db, profile_id)
    prem: dict[int, dict] = {}
    for r in comp["rows"]:
        pid = r.get("product_id")
        if pid and r["total_annual_cost"] and (pid not in prem or r["total_annual_cost"] < prem[pid]["total"]):
            prem[pid] = {"total": r["total_annual_cost"], "comparable": r["fully_comparable"] or r["is_baseline"],
                         "issues": r["comparability_issues"], "date": r["reference_date"]}
    points, missing = [], []
    for p in products:
        lbl = product_label(db, p)
        sc = scores.get(p.id, {}).get("aspects", {}).get("voorwaarden", {})
        pr = prem.get(p.id)
        reasons = []
        if sc.get("score") is None:
            reasons.append(sc.get("note") or "Onvoldoende bekende voorwaarden")
        if not pr:
            reasons.append("Geen premie voor dit rekenprofiel")
        if reasons:
            missing.append({**lbl, "reasons": reasons})
            continue
        points.append({**lbl, "premium": pr["total"], "conditions": sc["score"], "known": sc.get("known"),
                       "total_features": sc.get("total"), "comparable": pr["comparable"], "issues": pr["issues"],
                       "premium_date": pr["date"]})
    mx = median([p["premium"] for p in points]) if points else None
    my = median([p["conditions"] for p in points]) if points else None
    for pt in points:
        if mx is None:
            continue
        cheap, broad = pt["premium"] <= mx, pt["conditions"] >= my
        pt["quadrant"] = ("Ruim en voordelig" if cheap and broad else "Ruim en duurder" if broad else
                          "Beperkt en voordelig" if cheap else "Beperkt en duurder")
    return {"profile": to_dict(profile), "points": points, "missing": missing, "median_premium": mx,
            "median_conditions": my,
            "method": "X-as: laagste actuele totale jaarlast voor dit rekenprofiel. Y-as: voorwaardenscore (gedekt = 100, "
                      "voorwaardelijk/aanvullend = 50, uitgesloten = 0; onbekend telt niet mee). Kwadranten t.o.v. de mediaan. "
                      "Producten zonder voldoende gegevens worden niet geplaatst."}


# ---------------------------------------------------------------- 2. adviestool
ADVICE_QUESTIONS = [
    {"key": "vehicle_category", "label": "Om welk voertuig gaat het?", "type": "choice",
     "options": [["auto", "Klassieke auto"], ["motor", "Klassieke motorfiets"], ["bromfiets", "Klassieke bromfiets"]]},
    {"key": "value", "label": "Wat is de geschatte waarde?", "type": "choice",
     "options": [["laag", "Tot € 15.000"], ["midden", "€ 15.000 – 50.000"], ["hoog", "Meer dan € 50.000"]]},
    {"key": "usage", "label": "Hoe wordt het voertuig gebruikt?", "type": "multi",
     "options": [["hobby", "Hobbymatig / toertochten"], ["woonwerk", "Soms woon-werkverkeer"], ["dagelijks", "Dagelijks"],
                 ["zakelijk", "Zakelijk"]]},
    {"key": "activities", "label": "Welke activiteiten zijn belangrijk?", "type": "multi",
     "options": [["rally", "Rally's en evenementen"], ["circuit", "Circuit / trackdays"], ["buitenland", "Reizen in het buitenland"],
                 ["trailer", "Vervoer op een aanhanger of trailer"]]},
    {"key": "collection", "label": "Heeft de klant meerdere klassiekers?", "type": "choice",
     "options": [["nee", "Nee, één voertuig"], ["ja", "Ja, meerdere voertuigen"], ["gemengd", "Ja, verschillende soorten"]]},
    {"key": "second_vehicle", "label": "Heeft de klant een ander voertuig voor dagelijks gebruik?", "type": "choice",
     "options": [["ja", "Ja"], ["nee", "Nee"]]},
]

# antwoord → [(kenmerk, gewicht, reden)]
ADVICE_RULES: dict[tuple[str, str], list[tuple[str, int, str]]] = {
    ("value", "midden"): [("waa_taxatie", 2, "Waarde vastleggen op basis van taxatie")],
    ("value", "hoog"): [("waa_taxatie", 3, "Waarde vastleggen op basis van taxatie"),
                        ("dek_volledig_casco", 3, "Volledige cascodekking bij hoge waarde"),
                        ("dek_diefstal", 2, "Dekking tegen diefstal")],
    ("usage", "woonwerk"): [("geb_woon_werk", 3, "Woon-werkverkeer toegestaan")],
    ("usage", "dagelijks"): [("acc_dagelijks_gebruik", 3, "Dagelijks gebruik toegestaan")],
    ("usage", "zakelijk"): [("geb_zakelijk", 3, "Zakelijk gebruik toegestaan")],
    ("activities", "rally"): [("geb_evenementen", 3, "Dekking tijdens rally's en evenementen")],
    ("activities", "circuit"): [("geb_circuit", 3, "Dekking op het circuit")],
    ("activities", "buitenland"): [("geb_buitenland", 2, "Dekking in het buitenland"),
                                   ("dek_pechhulp", 1, "Pechhulp onderweg")],
    ("activities", "trailer"): [("dek_transport", 3, "Schade tijdens transport")],
    ("collection", "ja"): [("col_meerdere_voertuigen", 3, "Meerdere voertuigen op één polis")],
    ("collection", "gemengd"): [("col_meerdere_voertuigen", 3, "Meerdere voertuigen op één polis"),
                                ("col_verschillende_soorten", 3, "Verschillende voertuigsoorten op één polis")],
    ("second_vehicle", "nee"): [("acc_tweede_voertuig", 3, "Geen tweede voertuig vereist")],
}
BASE_NEEDS = [("dek_wa", 1, "Wettelijke aansprakelijkheid"), ("dek_brand", 1, "Brand"), ("dek_storm", 1, "Storm")]
FIT = {"gedekt": "ja", "voorwaardelijk": "mogelijk", "aanvullende_clausule": "mogelijk", "uitgesloten": "nee"}


def advice(db: Session, answers: dict) -> dict:
    needs: dict[str, tuple[int, str]] = {k: (w, r) for k, w, r in BASE_NEEDS}
    for key, val in answers.items():
        vals = val if isinstance(val, list) else [val]
        for v in vals:
            for fk, w, reason in ADVICE_RULES.get((key, v), []):
                if fk not in needs or needs[fk][0] < w:
                    needs[fk] = (w, reason)
    # Bij 'nee' op tweede voertuig is 'tweede voertuig verplicht' juist een knelpunt (omgekeerde logica)
    inverse = {"acc_tweede_voertuig"}
    feats = {f.key: f for f in db.scalars(select(Feature))}
    cat = answers.get("vehicle_category")
    products = _active_products(db, cat)
    fmap = current_findings(db, [p.id for p in products])
    results = []
    for p in products:
        lbl = product_label(db, p)
        rows, score, max_score, unknown_w, blockers = [], 0, 0, 0, 0
        for fk, (w, reason) in sorted(needs.items(), key=lambda x: -x[1][0]):
            f = feats.get(fk)
            if not f:
                continue
            fd = fmap.get((p.id, f.id))
            st = fd.status if fd else None
            fit = FIT.get(st, "onbekend")
            if fk in inverse and fit in ("ja", "nee"):
                fit = "nee" if fit == "ja" else "ja"  # 'tweede voertuig verplicht: gedekt' = eis aanwezig
            max_score += w * 2
            if fit == "ja":
                score += w * 2
            elif fit == "mogelijk":
                score += w
            elif fit == "nee" and w >= 3:
                blockers += 1
            if fit == "onbekend":
                unknown_w += w
            rows.append({"feature": f.label, "feature_key": fk, "need": reason, "weight": w, "fit": fit,
                         "status": st, "status_label": FINDING_STATUSES.get(st, "Geen gegevens"),
                         "value_text": fd.value_text if fd else None, "finding": finding_dict(db, fd) if fd else None})
        total_w = sum(w for w, _ in needs.values())
        known_share = 1 - unknown_w / total_w if total_w else 0
        if known_share < 0.5:
            verdict = "onvoldoende_gegevens"
        elif blockers:
            verdict = "past_niet"
        elif score >= max_score * 0.75 and known_share >= 0.75:
            verdict = "past"
        else:
            verdict = "past_mogelijk"
        results.append({**lbl, "verdict": verdict, "match": round(score / max_score * 100) if max_score else 0,
                        "known_share": round(known_share * 100), "blockers": blockers, "rows": rows})
    order = {"past": 0, "past_mogelijk": 1, "onvoldoende_gegevens": 2, "past_niet": 3}
    results.sort(key=lambda r: (order[r["verdict"]], -r["match"], not r["is_reference"]))
    questions = ["Is er een recent taxatierapport en hoe oud is dat?", "Hoe en waar is het voertuig gestald?",
                 "Welk eigen risico vindt de klant acceptabel?"]
    if "rally" in (answers.get("activities") or []):
        questions.append("Gaat het om toertochten/regelmatigheidsritten of om wedstrijden op snelheid?")
    if answers.get("collection") in ("ja", "gemengd"):
        questions.append("Worden alle voertuigen door dezelfde bestuurder(s) gebruikt?")
    return {"needs": [{"feature_key": k, "weight": w, "reason": r} for k, (w, r) in needs.items()],
            "results": results, "advisor_questions": questions,
            "note": "Uitkomst op basis van vastgelegde bevindingen. ‘Onbekend’ betekent dat de voorwaarden hierover niet zijn "
                    "vastgesteld, niet dat het niet verzekerd is. Controleer altijd de polisvoorwaarden en acceptatie."}


# ---------------------------------------------------------------- 3. wat-als
def whatif(db: Session, score_profile_id: int, product_id: int, changes: dict[str, str],
           premium: float | None = None) -> dict:
    sp = db.get(ScoreProfile, score_profile_id)
    p = db.get(Product, product_id)
    if not sp or not p:
        raise ValueError("Scoreprofiel of product niet gevonden.")
    feats = {str(f.id): f for f in db.scalars(select(Feature))}
    overrides = {}
    for fid, st in changes.items():
        if fid in feats and st in FINDING_STATUSES:
            overrides[(p.id, int(fid))] = st
    dropped = None
    if "premie" in (sp.weights or {}) and float(sp.weights["premie"]) > 0 and not sp.reference_profile_id and not premium:
        # Zonder rekenprofiel kan premie niet meewegen; laat dit aspect in het scenario weg in plaats van alles onbepaald te maken.
        sp = ScoreProfile(name=sp.name, weights={k: v for k, v in sp.weights.items() if k != "premie"},
                          min_coverage=sp.min_coverage, vehicle_category=sp.vehicle_category)
        dropped = "Premie telt niet mee: aan dit scoreprofiel is geen rekenprofiel gekoppeld."
    ids = [x.id for x in _active_products(db, sp.vehicle_category)]
    if p.id not in ids:
        ids.append(p.id)
    base = compute_scores(db, sp, ids)
    scen = compute_scores(db, sp, ids, overrides, {p.id: premium} if premium else None)

    def rank(res):
        ranked = sorted([r for r in res["results"] if r["total"] is not None], key=lambda r: -r["total"])
        return {r["product"]["id"]: i + 1 for i, r in enumerate(ranked)}

    rb, rs = rank(base), rank(scen)
    rows = []
    for b, s in zip(base["results"], scen["results"]):
        rows.append({"product": b["product"], "base_total": b["total"], "scenario_total": s["total"],
                     "base_rank": rb.get(b["product"]["id"]), "scenario_rank": rs.get(s["product"]["id"]),
                     "base_aspects": {k: v.get("score") for k, v in b["aspects"].items()},
                     "scenario_aspects": {k: v.get("score") for k, v in s["aspects"].items()},
                     "is_subject": b["product"]["id"] == p.id})
    rows.sort(key=lambda r: (r["scenario_rank"] or 999, r["product"]["provider_name"]))
    return {"rows": rows, "changes": [{"feature": feats[str(fid)].label, "status": FINDING_STATUSES[st]}
                                      for (_, fid), st in overrides.items()],
            "premium": premium, "score_profile": to_dict(sp), "dropped": dropped,
            "note": "Hypothetisch scenario. Er wordt niets opgeslagen en dit is geen bestaande productvoorwaarde."}


# ---------------------------------------------------------------- 4. concurrentiekaart
def battlecard(db: Session, provider_id: int) -> dict:
    prov = db.get(Provider, provider_id)
    if not prov:
        raise ValueError("Aanbieder niet gevonden.")
    products = db.scalars(select(Product).where(Product.provider_id == prov.id)).all()
    cards = []
    for p in products:
        vet = _vetera_product(db, p.vehicle_category)
        sales = local_sales_card(db, vet, p) if vet and not prov.is_reference else None
        # prijsniveau: gemiddeld verschil t.o.v. Vetera over profielen met Vetera-basis
        diffs, comparable = [], 0
        for prof in db.scalars(select(ReferenceProfile)):
            c = compare_profile(db, prof.id)
            if c["baseline"] != "vetera":
                continue
            for r in c["rows"]:
                if r.get("product_id") == p.id and r["diff_pct"] is not None:
                    diffs.append({"profile": prof.name, "diff_pct": r["diff_pct"], "comparable": r["fully_comparable"]})
                    comparable += 1 if r["fully_comparable"] else 0
        avg = round(sum(d["diff_pct"] for d in diffs) / len(diffs), 1) if diffs else None
        level = None if avg is None else ("duurder dan Vetera" if avg > 5 else "goedkoper dan Vetera" if avg < -5
                                          else "vergelijkbaar met Vetera")
        fmap = current_findings(db, [p.id])
        known = sum(1 for f in fmap.values() if f.status in KNOWN_STATUSES)
        cards.append({"product": product_label(db, p), "vetera_product": product_label(db, vet) if vet else None,
                      "risk_carrier": p.risk_carrier.name if p.risk_carrier else None,
                      "strengths": sales["competitor_strengths"] if sales else [],
                      "weaknesses": [{"feature": a["feature"], "text": a["fact"]} for a in sales["arguments"]] if sales else [],
                      "arguments": sales["arguments"][:5] if sales else [],
                      "advisor_questions": sales["advisor_questions"] if sales else [],
                      "unknown_count": len(sales["unknown"]) if sales else 0,
                      "price": {"avg_diff_pct": avg, "level": level, "observations": diffs, "comparable": comparable},
                      "known_features": known})
    last_diff = db.scalars(select(DocumentDiff).join(Document, DocumentDiff.document_id == Document.id)
                           .where(Document.provider_id == prov.id).order_by(DocumentDiff.created_at.desc())).first()
    return {"provider": {**to_dict(prov), "logo_url": f"/api/providers/{prov.id}/logo" if prov.logo_status == "goedgekeurd" else None},
            "products": cards, "generated_at": datetime.now().isoformat(),
            "last_change": to_dict(last_diff) if last_diff else None,
            "note": "Alleen aantoonbare verschillen op basis van vastgelegde bevindingen en vergelijkbare premies. "
                    "Onbekende onderdelen zijn niet als voor- of nadeel meegewogen."}


# ---------------------------------------------------------------- 5. tijdlijn
def timeline(db: Session, provider_id: int) -> dict:
    prov = db.get(Provider, provider_id)
    if not prov:
        raise ValueError("Aanbieder niet gevonden.")
    pids = [p.id for p in db.scalars(select(Product).where(Product.provider_id == prov.id))]
    pnames = {p.id: p.name for p in db.scalars(select(Product).where(Product.provider_id == prov.id))}
    events = []
    docs = db.scalars(select(Document).where(Document.provider_id == prov.id)).all()
    for d in docs:
        for v in d.versions:
            events.append({"type": "document", "date": v.imported_at.isoformat(), "title": f"Documentversie: {d.title}",
                           "detail": f"{v.version_label or v.original_filename} · {v.page_count} pagina's"
                                     + (f" · documentdatum {v.doc_date.isoformat()}" if v.doc_date else ""),
                           "link": f"/documenten/{d.id}", "version_id": v.id})
    for df in db.scalars(select(DocumentDiff).where(DocumentDiff.document_id.in_([d.id for d in docs] or [0]))):
        cats = {k: v for k, v in (df.summary or {}).get("per_categorie", {}).items() if k != "redactioneel"}
        events.append({"type": "wijziging", "date": df.created_at.isoformat(),
                       "title": f"Voorwaarden gewijzigd ({(df.summary or {}).get('aantal_wijzigingen', 0)} wijzigingen)",
                       "detail": ", ".join(f"{v}× {k.replace('_', ' ')}" for k, v in cats.items()) or "alleen redactioneel",
                       "link": f"/documenten/{df.document_id}", "diff_id": df.id})
    for o in db.scalars(select(PremiumObservation).where(PremiumObservation.provider_id == prov.id)):
        d = o.reference_date or o.created_at.date()
        events.append({"type": "premie", "date": datetime.combine(d, datetime.min.time()).isoformat(),
                       "title": f"Premie € {o.annual_premium:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                       if o.annual_premium else "Premie niet beschikbaar",
                       "detail": f"{OBSERVATION_TYPES.get(o.observation_type)} · {pnames.get(o.product_id) or o.product_name_raw or ''}"
                                 + (f" · {o.coverage_variant}" if o.coverage_variant else ""),
                       "link": "/premielab?tab=premies", "historical": o.is_historical})
    if pids:
        byday: dict[tuple, list] = {}
        for f in db.scalars(select(Finding).where(Finding.product_id.in_(pids))):
            byday.setdefault((f.created_at.date(), f.product_id, f.origin), []).append(f)
        for (day, pid, origin), fs in byday.items():
            events.append({"type": "bevinding", "date": datetime.combine(day, datetime.min.time()).isoformat(),
                           "title": f"{len(fs)} bevinding(en) vastgelegd – {pnames.get(pid)}",
                           "detail": {"handmatig": "handmatig", "ai": "door AI (te beoordelen)", "lokaal": "passagezoeker"}
                           .get(origin, origin), "link": f"/producten/{pid}"})
    for a in db.scalars(select(AuditLog).where(AuditLog.entity == "provider", AuditLog.entity_id == prov.id)):
        if a.action == "bijgewerkt" and a.changes and "status" in a.changes:
            events.append({"type": "status", "date": a.at.isoformat(),
                           "title": f"Status: {a.changes['status'].get('oud')} → {a.changes['status'].get('nieuw')}",
                           "detail": None, "link": None})
        elif a.action in ("aangemaakt", "samengevoegd"):
            events.append({"type": "status", "date": a.at.isoformat(), "title": f"Aanbieder {a.action}",
                           "detail": None, "link": None})
    events.sort(key=lambda e: e["date"], reverse=True)
    return {"provider": {"id": prov.id, "name": prov.name}, "events": events}


# ---------------------------------------------------------------- 6. marktbericht
def market_brief(db: Session, since: datetime | None = None, until: datetime | None = None) -> dict:
    until = until or datetime.now()
    if since is None:
        prev = db.scalars(select(MonitorRun).where(MonitorRun.status == "voltooid", MonitorRun.finished_at < until)
                          .order_by(MonitorRun.finished_at.desc()).offset(1)).first()
        since = prev.finished_at if prev else until - timedelta(days=7)
    diffs = db.scalars(select(DocumentDiff).where(DocumentDiff.created_at >= since, DocumentDiff.created_at <= until)).all()
    changes = []
    for d in diffs:
        doc = db.get(Document, d.document_id)
        prov = db.get(Provider, doc.provider_id) if doc and doc.provider_id else None
        relevant = [c for c in (d.changes or []) if c["category"] != "redactioneel"]
        if relevant:
            changes.append({"provider": prov.name if prov else "Onbekend", "document": doc.title if doc else "?",
                            "document_id": d.document_id, "diff_id": d.id, "count": len(relevant),
                            "categories": sorted({c["category_label"] for c in relevant}),
                            "examples": [{"category": c["category_label"], "new": (c["new"] or c["old"] or "")[:220]}
                                         for c in relevant[:3]]})
    new_docs = db.scalars(select(DocumentVersion).where(DocumentVersion.imported_at >= since,
                                                        DocumentVersion.imported_at <= until,
                                                        DocumentVersion.supersedes_id.is_(None))).all()
    new_prov = db.scalars(select(Provider).where(Provider.created_at >= since, Provider.created_at <= until,
                                                 Provider.is_reference.is_(False))).all()
    notes = db.scalars(select(Notification).where(Notification.created_at >= since, Notification.created_at <= until)).all()
    unavailable = [n.title for n in notes if n.type == "bron_onbeschikbaar"]
    price = [n.title for n in notes if n.type == "premieverschil"]
    sugg = db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.created_at >= since,
                                                          ImprovementSuggestion.created_at <= until)).all()
    runs = db.scalars(select(MonitorRun).where(MonitorRun.started_at >= since, MonitorRun.started_at <= until)).all()
    headline = []
    if changes:
        headline.append(f"Bij {len({c['provider'] for c in changes})} aanbieder(s) zijn polisvoorwaarden inhoudelijk gewijzigd "
                        f"({sum(c['count'] for c in changes)} wijzigingen).")
    if new_prov:
        headline.append(f"{len(new_prov)} nieuwe aanbieder(s) toegevoegd of gevonden: {', '.join(p.name for p in new_prov[:5])}.")
    if new_docs:
        headline.append(f"{len(new_docs)} nieuw(e) document(en) geïmporteerd.")
    if price:
        headline.append(f"{len(price)} relevant(e) premieverschil(len) gesignaleerd.")
    if unavailable:
        headline.append(f"{len(unavailable)} bron(nen) niet meer bereikbaar.")
    if not headline:
        headline.append("Geen inhoudelijke wijzigingen gevonden in deze periode.")
    return {"period": {"from": since.isoformat(), "to": until.isoformat()}, "headline": headline, "changes": changes,
            "new_providers": [{"id": p.id, "name": p.name, "status": p.status} for p in new_prov],
            "new_documents": [{"id": v.document_id, "file": v.original_filename} for v in new_docs],
            "price_signals": price, "unavailable_sources": unavailable,
            "suggestions": [{"id": s.id, "title": s.title, "kind": s.kind} for s in sugg],
            "checks": len(runs)}


# ---------------------------------------------------------------- 7. snelzoeken
def quicksearch(db: Session, q: str, limit: int = 6) -> list[dict]:
    q = (q or "").strip()
    if len(q) < 2:
        return []
    like = f"%{q}%"
    out = []
    for p in db.scalars(select(Provider).where(Provider.name.ilike(like), Provider.status != "samengevoegd").limit(limit)):
        out.append({"type": "aanbieder", "title": p.name, "subtitle": p.provider_type, "link": f"/concurrenten/{p.id}"})
    for p in db.scalars(select(Product).where(Product.name.ilike(like)).limit(limit)):
        out.append({"type": "product", "title": p.name, "subtitle": db.get(Provider, p.provider_id).name,
                    "link": f"/producten/{p.id}"})
    for d in db.scalars(select(Document).where(Document.title.ilike(like)).limit(limit)):
        out.append({"type": "document", "title": d.title, "subtitle": d.document_type, "link": f"/documenten/{d.id}"})
    for f in db.scalars(select(Feature).where(Feature.label.ilike(like)).limit(limit)):
        out.append({"type": "kenmerk", "title": f.label, "subtitle": f.category, "link": f"/voorwaarden?view=tabel&q={f.label}"})
    cl = (select(Clause, Document).join(DocumentVersion, Clause.version_id == DocumentVersion.id)
          .join(Document, Document.current_version_id == DocumentVersion.id)
          .where(or_(Clause.heading.ilike(like), Clause.article == q)).limit(limit))
    for c, d in db.execute(cl):
        out.append({"type": "clausule", "title": f"{'Art. ' + c.article + ' ' if c.article else ''}{c.heading or ''}".strip(),
                    "subtitle": d.title, "version_id": c.version_id, "page": c.page_number, "link": f"/documenten/{d.id}"})
    for s in db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.title.ilike(like)).limit(limit)):
        out.append({"type": "verbetervoorstel", "title": s.title, "subtitle": s.category, "link": f"/verbeterradar/{s.id}"})
    for r in db.scalars(select(ReferenceProfile).where(ReferenceProfile.name.ilike(like)).limit(limit)):
        out.append({"type": "rekenprofiel", "title": r.name, "subtitle": r.vehicle_category, "link": "/premielab?tab=profielen"})
    words = [w for w in q.replace('"', " ").split() if len(w) > 2]
    if words:
        try:
            rows = db.execute(text("SELECT rowid, snippet(page_fts, 0, '', '', '…', 10) FROM page_fts WHERE page_fts MATCH :m "
                                   "ORDER BY rank LIMIT :l"),
                              {"m": " ".join(f'"{w}"' for w in words[:-1]) + f' "{words[-1]}"*', "l": limit}).all()
        except Exception:
            rows = []
        for rid, snip in rows:
            pg = db.get(DocumentPage, rid)
            if not pg:
                continue
            v = db.get(DocumentVersion, pg.version_id)
            d = db.get(Document, v.document_id)
            if d.current_version_id != v.id:
                continue
            out.append({"type": "tekst", "title": snip, "subtitle": f"{d.title} · p. {pg.page_number}",
                        "version_id": v.id, "page": pg.page_number, "link": f"/documenten/{d.id}"})
    return out
