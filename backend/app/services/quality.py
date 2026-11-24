"""Datakwaliteitscontroles. Signaleert twijfelachtige gegevens voor menselijke controle."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (AIAnalysis, Document, DocumentVersion, Feature, Finding, PremiumObservation, Product,
                      Provider, QualityResolution)
from .common import KNOWN_STATUSES
from .settings_store import get_setting


def _issue(key, kind, severity, title, detail, link, entity, entity_id):
    return {"key": key, "kind": kind, "severity": severity, "title": title, "detail": detail, "link": link,
            "entity": entity, "entity_id": entity_id}


def run_checks(db: Session, include_resolved: bool = False) -> dict:
    issues = []
    resolved = {r.issue_key: r for r in db.scalars(select(QualityResolution))}
    stale_months = int(get_setting(db, "premium_stale_months", 12) or 12)

    # Dubbele documenten (zelfde aanbieder, type en titel)
    groups = defaultdict(list)
    for d in db.scalars(select(Document)):
        groups[(d.provider_id, d.document_type, (d.title or "").strip().lower())].append(d)
    for (_, _, title), docs in groups.items():
        if len(docs) > 1:
            ids = sorted(d.id for d in docs)
            issues.append(_issue(f"dup_doc:{'-'.join(map(str, ids))}", "dubbel_document", "middel",
                                 f"Mogelijk dubbel document: '{title}'",
                                 f"Documenten {', '.join('#%d' % i for i in ids)} hebben dezelfde aanbieder, type en titel. "
                                 "Voeg ze samen als versies of verwijder het duplicaat.", f"/documenten/{ids[0]}",
                                 "document", ids[0]))
    # Onjuiste productkoppelingen
    for d in db.scalars(select(Document).where(Document.product_id.is_not(None))):
        p = db.get(Product, d.product_id)
        if p and d.provider_id and p.provider_id != d.provider_id:
            issues.append(_issue(f"mismatch:{d.id}", "productkoppeling", "hoog",
                                 f"Product hoort niet bij aanbieder: '{d.title}'",
                                 "Het gekoppelde product valt onder een andere aanbieder dan het document.",
                                 f"/documenten/{d.id}", "document", d.id))
    for d in db.scalars(select(Document).where(Document.provider_id.is_(None))):
        issues.append(_issue(f"noprov:{d.id}", "productkoppeling", "middel", f"Document zonder aanbieder: '{d.title}'",
                             "Koppel het document aan een aanbieder en product.", f"/documenten/{d.id}", "document", d.id))
    # Extractiekwaliteit en ontbrekende clausules
    for d in db.scalars(select(Document)):
        if not d.current_version_id:
            continue
        v = db.get(DocumentVersion, d.current_version_id)
        if v.extraction_quality in ("onbetrouwbaar", "matig"):
            issues.append(_issue(f"extract:{v.id}", "extractie", "hoog" if v.extraction_quality == "onbetrouwbaar" else "laag",
                                 f"{'Onbetrouwbare' if v.extraction_quality == 'onbetrouwbaar' else 'Matige'} tekstextractie: '{d.title}'",
                                 "Mogelijk gescand document of afwijkende opmaak. Controleer citaten handmatig"
                                 + (" of installeer OCR." if not v.ocr_used else "."), f"/documenten/{d.id}",
                                 "document_version", v.id))
        if v.status == "gereed" and not v.clauses:
            issues.append(_issue(f"noclause:{v.id}", "clausules", "laag", f"Geen clausules herkend: '{d.title}'",
                                 "Artikelstructuur is niet herkend; zoeken werkt per pagina.", f"/documenten/{d.id}",
                                 "document_version", v.id))
    # Premies
    today = date.today()
    for o in db.scalars(select(PremiumObservation).where(PremiumObservation.is_historical.is_(False),
                                                         PremiumObservation.observation_type != "historisch_tarief")):
        name = o.provider_name_raw or f"premie #{o.id}"
        if o.reference_date and (today - o.reference_date).days > stale_months * 30.5:
            issues.append(_issue(f"stale:{o.id}", "verouderde_premie", "middel", f"Verouderde premie ({name})",
                                 f"Peildatum {o.reference_date.isoformat()} is ouder dan {stale_months} maanden. Markeer als "
                                 "historisch of leg een nieuwe waarneming vast.", "/premielab", "premium", o.id))
        missing = [lbl for lbl, v in (("dekkingsvariant", o.coverage_variant), ("eigen risico", o.deductible),
                                      ("peildatum", o.reference_date), ("profiel", o.profile_id)) if v is None]
        if o.tax_included == "onbekend":
            missing.append("assurantiebelasting")
        if missing:
            issues.append(_issue(f"incomp:{o.id}", "onvergelijkbare_premie", "laag", f"Onvolledige premie ({name})",
                                 "Ontbrekend: " + ", ".join(missing) + ". Vergelijking is beperkt mogelijk.",
                                 "/premielab", "premium", o.id))
    # Tegenstrijdige bevindingen
    cur = defaultdict(list)
    for f in db.scalars(select(Finding).where(Finding.is_current.is_(True))):
        cur[(f.product_id, f.feature_id, f.coverage_level)].append(f)
    feats = {f.id: f for f in db.scalars(select(Feature))}
    for (pid, fid, _lv), fs in cur.items():
        sts = {f.status for f in fs if f.status in KNOWN_STATUSES}
        if len(sts) > 1:
            p = db.get(Product, pid)
            issues.append(_issue(f"conflict:{pid}:{fid}:{_lv or 'alle'}", "tegenstrijdig", "hoog",
                                 f"Tegenstrijdige bevindingen: {p.name if p else pid} – {feats[fid].label}",
                                 "Meerdere actuele bevindingen met verschillende status.", f"/voorwaarden?product={pid}",
                                 "finding", fs[0].id))
    # Gedeelde (canonieke) producten met verschillende uitkomst
    for p in db.scalars(select(Product).where(Product.canonical_product_id.is_not(None))):
        for fid in feats:
            a = [f for f in cur.get((p.id, fid, None), []) if f.status in KNOWN_STATUSES]
            b = [f for f in cur.get((p.canonical_product_id, fid, None), []) if f.status in KNOWN_STATUSES]
            if a and b and a[0].status != b[0].status:
                issues.append(_issue(f"canon:{p.id}:{fid}", "tegenstrijdig", "middel",
                                     f"Tegenstrijdige bronnen voor hetzelfde product: {p.name} – {feats[fid].label}",
                                     "Het distributieproduct en het canonieke product hebben een verschillende status.",
                                     f"/voorwaarden?product={p.id}", "finding", a[0].id))
    # Niet-onderbouwde AI-conclusies
    for f in db.scalars(select(Finding).where(Finding.is_current.is_(True), Finding.origin == "ai")):
        if f.status in KNOWN_STATUSES and (not f.quote or f.quote_verified is False):
            issues.append(_issue(f"unsup:{f.id}", "ai_onderbouwing", "hoog",
                                 f"AI-conclusie zonder geverifieerde bron: {feats[f.feature_id].label}",
                                 "Het citaat ontbreekt of is niet teruggevonden in de documenttekst.",
                                 f"/voorwaarden?product={f.product_id}", "finding", f.id))
    n_unreviewed = len(db.scalars(select(Finding.id).where(Finding.is_current.is_(True), Finding.origin == "ai",
                                                           Finding.review_status == "te_beoordelen")).all())
    if n_unreviewed:
        issues.append(_issue(f"unreviewed:{n_unreviewed}", "beoordeling", "laag",
                             f"{n_unreviewed} AI-bevindingen wachten op menselijke beoordeling",
                             "Keur goed of corrigeer in de voorwaardenvergelijker.", "/kwaliteit?tab=bevindingen",
                             "finding", None))
    for a in db.scalars(select(AIAnalysis).where(AIAnalysis.kind.in_(["vraag", "verkoop", "dossier"]))):
        if a.validation and (a.validation.get("unknown_refs") or a.validation.get("unverified_quotes")):
            issues.append(_issue(f"aival:{a.id}", "ai_onderbouwing", "middel",
                                 f"AI-antwoord met niet-verifieerbare bronnen (#{a.id})",
                                 f"Onbekende verwijzingen: {', '.join(a.validation.get('unknown_refs') or []) or '-'}; "
                                 f"niet gevonden citaten: {', '.join(a.validation.get('unverified_quotes') or []) or '-'}.",
                                 "/instellingen?tab=ai", "ai_analysis", a.id))
    # Aanbieders te beoordelen
    for p in db.scalars(select(Provider).where(Provider.status == "te_beoordelen")):
        issues.append(_issue(f"prov:{p.id}", "beoordeling", "laag", f"Aanbieder te beoordelen: {p.name}",
                             p.verification_note or "", f"/concurrenten/{p.id}", "provider", p.id))

    for i in issues:
        r = resolved.get(i["key"])
        i["resolved"] = bool(r)
        i["resolution"] = r.resolution if r else None
    if not include_resolved:
        issues = [i for i in issues if not i["resolved"]]
    order = {"hoog": 0, "middel": 1, "laag": 2}
    issues.sort(key=lambda i: order[i["severity"]])
    counts = defaultdict(int)
    for i in issues:
        counts[i["kind"]] += 1
    return {"issues": issues, "counts": dict(counts), "total": len(issues)}
