"""AI-taken bovenop de lokale data. Elke taak:
1. bouwt een context uit uitsluitend toegestane (publieke) gegevens,
2. kan als preview worden opgevraagd voordat iets wordt verstuurd,
3. valideert bronverwijzingen tegen de werkelijk geëxtraheerde tekst.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import (ProductCoverage, DocumentDiff, Document, DocumentPage, DocumentVersion, Feature, Finding,
                      ImprovementSuggestion, Notification, PremiumObservation, Product, Provider,
                      ResearchDossier, SalesCard)
from .ai_client import INT, STR, AIBlocked, arr, build_preview, obj, run_structured
from .analysis import current_findings, local_sales_card, product_label
from .common import COVERAGE_LEVELS, FINDING_STATUSES, normalize_text
from .documents import verify_quote
from .premiums import observation_dict
from .settings_store import get_setting

BASE_RULES = """Je bent een zorgvuldige analist voor Vetera, een Nederlandse aanbieder van verzekeringen voor
klassieke auto's, motorfietsen en bromfietsen. Je werkt uitsluitend met de aangeleverde gegevens.
Harde regels:
- Verzin nooit informatie, premies, voorwaarden of bronnen.
- Een ontbrekende passage betekent NIET dat iets niet verzekerd is; noem het 'niet gevonden' of 'onvoldoende informatie'.
- Verwijs bij iedere conclusie naar de aangeleverde bron-id's (zoals F12, P3, D4p7).
- Citaten moeten letterlijk uit de aangeleverde tekst komen.
- Presenteer concurrenten nooit onterecht negatief; benoem ook hun aantoonbare sterke punten.
- Toon onzekerheid expliciet. Geen claims als 'beste dekking' of 'slechtste verzekeraar'.
- Schrijf in helder, zakelijk Nederlands."""


class ContextBuilder:
    """Verzamelt contextitems met stabiele id's en houdt bij wat er verstuurd wordt."""

    def __init__(self, db: Session, allow_nonpublic: bool = False):
        self.db = db
        self.allow_nonpublic = allow_nonpublic
        self.items: dict[str, dict] = {}
        self.parts: list[str] = []
        self.excluded_nonpublic = 0

    def _doc_public(self, version_id: int | None) -> bool:
        if not version_id:
            return True
        v = self.db.get(DocumentVersion, version_id)
        doc = self.db.get(Document, v.document_id) if v else None
        return bool(doc and (doc.visibility == "publiek" or self.allow_nonpublic))

    def add_finding(self, f: Finding) -> None:
        if not self._doc_public(f.document_version_id):
            self.excluded_nonpublic += 1
            return
        rid = f"F{f.id}"
        if rid in self.items:
            return
        p = self.db.get(Product, f.product_id)
        prov = self.db.get(Provider, p.provider_id) if p else None
        feat = self.db.get(Feature, f.feature_id)
        self.items[rid] = {"type": "finding", "finding_id": f.id, "document_version_id": f.document_version_id,
                           "page_number": f.page_number}
        line = (f"[{rid}] {prov.name if prov else '?'}{' (VETERA)' if prov and prov.is_reference else ''} – "
                f"{p.name if p else '?'} – {feat.category}/{feat.label}"
                f"{' [' + COVERAGE_LEVELS[f.coverage_level] + ']' if f.coverage_level in COVERAGE_LEVELS else ''}: "
                f"{FINDING_STATUSES.get(f.status, f.status)}")
        if f.value_text:
            line += f"; waarde: {f.value_text}"
        if f.page_number:
            line += f"; bron: documentversie {f.document_version_id}, p.{f.page_number}"
        if f.article:
            line += f", art. {f.article}"
        if f.quote:
            line += f'; citaat: "{f.quote[:500]}"'
        if f.review_status in ("goedgekeurd", "gecorrigeerd"):
            line += " [menselijk gecontroleerd]"
        self.parts.append(line)

    def add_premium(self, o: PremiumObservation) -> None:
        if o.visibility != "publiek" and not self.allow_nonpublic:
            self.excluded_nonpublic += 1
            return
        rid = f"P{o.id}"
        d = observation_dict(self.db, o)
        self.items[rid] = {"type": "premium", "premium_id": o.id}
        self.parts.append(
            f"[{rid}] Premie {d['provider_name']} / {d['product_name'] or '?'}: € {o.annual_premium} per jaar "
            f"(totaal incl. lidmaatschap/kosten € {d['total_annual_cost']}), dekking {o.coverage_variant or 'onbekend'}, "
            f"eigen risico {o.deductible if o.deductible is not None else 'onbekend'}, assurantiebelasting "
            f"inbegrepen: {o.tax_included}, type: {d['observation_type_label']}, peildatum {o.reference_date or 'onbekend'}, "
            f"profiel #{o.profile_id or '-'}")

    def add_page_excerpt(self, page: DocumentPage, max_chars: int = 2500) -> None:
        if not self._doc_public(page.version_id):
            self.excluded_nonpublic += 1
            return
        rid = f"D{page.version_id}p{page.page_number}"
        if rid in self.items:
            return
        v = self.db.get(DocumentVersion, page.version_id)
        doc = self.db.get(Document, v.document_id)
        prov = self.db.get(Provider, doc.provider_id) if doc.provider_id else None
        self.items[rid] = {"type": "page", "document_version_id": page.version_id, "page_number": page.page_number}
        self.parts.append(f"[{rid}] Document '{doc.title}' ({prov.name if prov else 'aanbieder onbekend'}, "
                          f"{doc.document_type}), pagina {page.page_number}:\n{page.text[:max_chars]}")

    def add_text(self, rid: str, label: str, body: str, meta: dict | None = None) -> None:
        self.items[rid] = {"type": "text", **(meta or {})}
        self.parts.append(f"[{rid}] {label}: {body}")

    def render(self) -> str:
        return "\n".join(self.parts)

    def summary(self) -> dict:
        counts: dict[str, int] = {}
        for v in self.items.values():
            counts[v["type"]] = counts.get(v["type"], 0) + 1
        return {"items": counts, "excluded_nonpublic": self.excluded_nonpublic,
                "nonpublic_included": self.allow_nonpublic, "ids": list(self.items)[:300]}


def _allow_nonpublic(db: Session, consent: bool) -> bool:
    if not consent:
        return False
    if not get_setting(db, "ai_allow_nonpublic", False):
        raise AIBlocked("Verzending van niet-publieke gegevens is uitgeschakeld in Instellingen.")
    return True


def search_pages(db: Session, query: str, limit: int = 12) -> list[DocumentPage]:
    words = [w for w in re.findall(r"\w+", normalize_text(query)) if len(w) > 2]
    if not words:
        return []
    fts = " OR ".join(f'"{w}"' for w in words[:12])
    try:
        ids = [r[0] for r in db.execute(text("SELECT rowid FROM page_fts WHERE page_fts MATCH :q ORDER BY rank LIMIT :l"),
                                        {"q": fts, "l": limit})]
    except Exception:
        ids = []
    pages = [db.get(DocumentPage, i) for i in ids]
    # alleen huidige versies
    out = []
    for p in pages:
        if not p:
            continue
        v = db.get(DocumentVersion, p.version_id)
        doc = db.get(Document, v.document_id) if v else None
        if doc and doc.current_version_id == v.id:
            out.append(p)
    return out


def validate_sources(db: Session, ctx: ContextBuilder, sources: list[dict]) -> dict:
    """Controleer of genoemde bron-id's bestaan en of citaten in de brontekst voorkomen."""
    checked, unknown, unverified = [], [], []
    for s in sources or []:
        ref = (s.get("ref") or "").strip()
        item = ctx.items.get(ref)
        res = {"ref": ref, "exists": item is not None, "quote_verified": None}
        if item is None:
            unknown.append(ref)
        elif s.get("quote") and item.get("document_version_id"):
            vq = verify_quote(db, item["document_version_id"], item.get("page_number") or s.get("page_number"), s["quote"])
            res["quote_verified"] = vq["verified"]
            res["page_number"] = vq["page_number"]
            if not vq["verified"]:
                unverified.append(ref)
        if item:
            res.update({k: v for k, v in item.items() if k in ("document_version_id", "finding_id", "premium_id")})
            res.setdefault("page_number", item.get("page_number"))
        checked.append(res)
    return {"sources": checked, "unknown_refs": unknown, "unverified_quotes": unverified,
            "ok": not unknown and not unverified}


SOURCE_SCHEMA = obj({"ref": STR, "quote": STR, "note": STR})


# ---------------------------------------------------------------- onderzoeksassistent
ASK_SCHEMA = obj({
    "short_answer": STR,
    "key_findings": arr(obj({"text": STR, "refs": arr(STR)})),
    "comparison": arr(obj({"subject": STR, "details": STR, "refs": arr(STR)})),
    "implications_for_vetera": arr(STR),
    "sources": arr(SOURCE_SCHEMA),
    "uncertainties": arr(STR),
    "missing_data": arr(STR),
    "next_steps": arr(STR),
})


def build_ask_context(db: Session, question: str, consent_nonpublic: bool = False) -> ContextBuilder:
    ctx = ContextBuilder(db, _allow_nonpublic(db, consent_nonpublic))
    providers = db.scalars(select(Provider).where(Provider.status.in_(["actief", "te_beoordelen"]))).all()
    ctx.add_text("A0", "Aanbieders", "; ".join(
        f"{p.name} ({p.provider_type}, status {p.status}{', referentie' if p.is_reference else ''})" for p in providers))
    products = db.scalars(select(Product)).all()
    ctx.add_text("A1", "Producten", "; ".join(
        f"#{p.id} {product_label(db, p)['provider_name']} – {p.name} ({p.vehicle_category})"
        + (" [distributie van canoniek product #%d]" % p.canonical_product_id if p.canonical_product_id else "")
        for p in products) or "geen")
    for f in db.scalars(select(Finding).where(Finding.product_id.in_([p.id for p in products] or [0]),
                                              Finding.is_current.is_(True))):
        if f.status != "niet_gevonden" or len(ctx.items) < 400:
            ctx.add_finding(f)
    for o in db.scalars(select(PremiumObservation).where(PremiumObservation.annual_premium.is_not(None))
                        .order_by(PremiumObservation.reference_date.desc()).limit(150)):
        ctx.add_premium(o)
    since = datetime.now() - timedelta(days=120)
    for d in db.scalars(select(DocumentDiff).where(DocumentDiff.created_at >= since)).all():
        doc = db.get(Document, d.document_id)
        ctx.add_text(f"W{d.id}", f"Wijziging in '{doc.title if doc else d.document_id}' op {d.created_at.date()}",
                     json.dumps(d.summary, ensure_ascii=False))
    for s in db.scalars(select(ImprovementSuggestion).where(ImprovementSuggestion.status != "afgewezen").limit(40)):
        ctx.add_text(f"R{s.id}", f"Verbetersuggestie ({s.kind}, prioriteit {s.priority}, status {s.status})",
                     f"{s.title}: {s.summary}")
    for p in search_pages(db, question):
        ctx.add_page_excerpt(p)
    return ctx


def ask(db: Session, question: str, dry_run: bool, consent_nonpublic: bool = False) -> dict:
    ctx = build_ask_context(db, question, consent_nonpublic)
    system = BASE_RULES + """
Beantwoord de onderzoeksvraag gestructureerd: kort antwoord, belangrijkste bevindingen, vergelijking,
gevolgen voor Vetera, bronnen (met ref naar de id's), onzekerheden, ontbrekende gegevens en vervolgstappen.
Als de gegevens onvoldoende zijn, zeg dat dan in het korte antwoord en benoem welke gegevens ontbreken."""
    user = f"Vandaag: {date.today().isoformat()}\nOnderzoeksvraag: {question}\n\nBeschikbare gegevens:\n{ctx.render()}"
    if dry_run:
        return {"preview": build_preview(db, "vraag", system, user, ctx.summary())}
    data, analysis = run_structured(db, kind="vraag", system=system, user_text=user, schema=ASK_SCHEMA,
                                    sent_summary=ctx.summary(), question=question)
    val = validate_sources(db, ctx, data.get("sources", []))
    all_refs = {r for k in ("key_findings", "comparison") for x in data.get(k, []) for r in x.get("refs", [])}
    val["unknown_inline_refs"] = sorted(r for r in all_refs if r not in ctx.items)
    analysis.validation = val
    db.commit()
    return {"analysis_id": analysis.id, "answer": data, "validation": val, "context_items": ctx.items,
            "cost_eur": analysis.cost_estimate}


# ---------------------------------------------------------------- kenmerkextractie uit document
LEVEL_ENUM = {"type": "string", "enum": ["alle", "wa", "wa_brand_diefstal", "wa_beperkt_casco", "wa_volledig_casco"]}
EXTRACT_SCHEMA = obj({
    "coverage_levels": arr(obj({
        "level": {"type": "string", "enum": ["wa", "wa_brand_diefstal", "wa_beperkt_casco", "wa_volledig_casco"]},
        "offered": {"type": "string", "enum": ["ja", "nee", "onbekend"]},
        "local_name": STR, "page_number": INT, "quote": STR,
    })),
    "items": arr(obj({
        "feature_key": STR,
        "coverage_level": LEVEL_ENUM,
        "status": {"type": "string", "enum": list(FINDING_STATUSES)},
        "value_text": STR, "explanation": STR, "page_number": INT, "article": STR, "quote": STR,
        "confidence": {"type": "string", "enum": ["hoog", "middel", "laag"]},
    })),
    "document_notes": STR,
})


def extract_document(db: Session, version_id: int, product_id: int, dry_run: bool,
                     consent_nonpublic: bool = False) -> dict:
    v = db.get(DocumentVersion, version_id)
    if not v or v.status != "gereed":
        raise ValueError("Documentversie niet gevonden of nog niet verwerkt.")
    doc = db.get(Document, v.document_id)
    if doc.visibility != "publiek":
        _allow_nonpublic(db, consent_nonpublic)
        if not consent_nonpublic:
            raise AIBlocked("Dit document is gemarkeerd als niet-publiek en wordt niet zonder expliciete "
                            "toestemming naar de AI-dienst verstuurd.")
    feats = db.scalars(select(Feature).where(Feature.active.is_(True)).order_by(Feature.sort_order)).all()
    feat_txt = "\n".join(f"- {f.key}: {f.category} / {f.label} (type {f.value_type})" for f in feats)
    pages = "\n\n".join(f"=== PAGINA {p.page_number} ===\n{p.text}" for p in v.pages)
    system = BASE_RULES + """
Analyseer de polisdocumentatie en bepaal per rubriek de regeling. Gebruik deze statussen:
gedekt = aantoonbaar gedekt; uitgesloten = aantoonbaar uitgesloten (alleen met expliciete uitsluitingstekst);
voorwaardelijk = gedekt onder voorwaarden; aanvullende_clausule = afhankelijk van aanvullende clausule/dekking;
niet_gevonden = niets over gevonden; onvoldoende_informatie = wel genoemd maar niet eenduidig;
menselijke_beoordeling = interpretatie vereist menselijke beoordeling.
Dekkingsniveaus: wa = alleen wettelijke aansprakelijkheid; wa_brand_diefstal = WA plus brand en diefstal
(zonder verdere cascodekking); wa_beperkt_casco = WA plus beperkt casco (doorgaans brand, diefstal, storm,
ruit, natuur); wa_volledig_casco = WA plus volledig casco/allrisk. Geef in coverage_levels per niveau aan of het
product het aanbiedt (ja/nee/onbekend) en onder welke naam de aanbieder het noemt (bijv. 'WA Extra'), met citaat.
Geef per rubriek één item met coverage_level 'alle' als de regeling voor alle dekkingen gelijk is (bijv. acceptatie,
gebruik, stalling). Verschilt de regeling per dekkingsniveau (typisch bij brand, diefstal, storm, ruit, vandalisme,
casco, eigen risico), geef dan één item per aangeboden niveau met het juiste coverage_level. Een niveau dat het
product niet aanbiedt krijg geen items. 'quote' is een letterlijk citaat (max. 300 tekens) van de opgegeven pagina,
of een lege string als er geen passage is. page_number is 0 als er geen passage is. Bij tekst-/bedragrubrieken
vul je value_text met de concrete waarde (bijv. '€ 150 per gebeurtenis', 'minimaal 25 jaar oud')."""
    user = (f"Document: '{doc.title}' (type {doc.document_type}), versie {v.version_label or '-'}.\n"
            f"Rubrieken:\n{feat_txt}\n\nDocumenttekst:\n{pages}")
    summary = {"items": {"document_pages": len(v.pages)}, "document_version_id": v.id, "document": doc.title,
               "visibility": doc.visibility}
    if dry_run:
        return {"preview": build_preview(db, "extractie", system, user, summary, expected_output_tokens=9000)}
    data, analysis = run_structured(db, kind="extractie", system=system, user_text=user, schema=EXTRACT_SCHEMA,
                                    sent_summary=summary, max_tokens=32000)
    fkeys = {f.key: f for f in feats}
    created, skipped_locked, downgraded, unverified, levels_set = 0, 0, 0, 0, 0
    for cl in data.get("coverage_levels", []):
        lv = cl.get("level")
        if lv not in COVERAGE_LEVELS:
            continue
        pc = db.scalars(select(ProductCoverage).where(ProductCoverage.product_id == product_id,
                                                      ProductCoverage.level == lv)).first()
        if pc and pc.locked:
            continue
        offered = {"ja": True, "nee": False}.get(cl.get("offered"))
        quote = (cl.get("quote") or "").strip() or None
        if offered is False and not (quote and verify_quote(db, v.id, cl.get("page_number") or None, quote)["verified"]):
            offered = None  # 'niet aangeboden' alleen met een passage die dat aantoont
        if pc is None:
            pc = ProductCoverage(product_id=product_id, level=lv)
            db.add(pc)
        pc.offered = offered if offered is not None else pc.offered
        pc.local_name = (cl.get("local_name") or "").strip()[:200] or pc.local_name
        pc.document_version_id, pc.page_number, pc.quote, pc.origin = v.id, cl.get("page_number") or None, quote, "ai"
        levels_set += 1
    seen_keys: set[tuple] = set()
    for it in data.get("items", []):
        f = fkeys.get(it.get("feature_key"))
        if not f:
            continue
        level = it.get("coverage_level")
        level = level if level in COVERAGE_LEVELS else None
        if (f.id, level) in seen_keys:
            continue
        seen_keys.add((f.id, level))
        existing = db.scalars(select(Finding).where(Finding.product_id == product_id, Finding.feature_id == f.id,
                                                    Finding.coverage_level.is_(None) if level is None
                                                    else Finding.coverage_level == level,
                                                    Finding.is_current.is_(True))).all()
        if any(e.locked for e in existing):
            skipped_locked += 1  # menselijke correcties worden nooit overschreven
            continue
        page = it.get("page_number") or None
        quote = (it.get("quote") or "").strip() or None
        vq = verify_quote(db, v.id, page, quote) if quote else {"verified": None, "page_number": page}
        status = it.get("status") or "menselijke_beoordeling"
        expl = it.get("explanation") or ""
        if quote and vq["verified"] is False:
            unverified += 1
            expl += " [Citaat niet teruggevonden in de geëxtraheerde tekst; controle nodig.]"
            if status in KNOWN_STRICT:
                status, downgraded = "menselijke_beoordeling", downgraded + 1
        if status == "uitgesloten" and not (quote and vq["verified"]):
            status, downgraded = "menselijke_beoordeling", downgraded + 1
            expl += " [Uitsluiting zonder geverifieerde passage omgezet naar menselijke beoordeling.]"
        for e in existing:
            e.is_current = False
        nf = Finding(product_id=product_id, feature_id=f.id, coverage_level=level, status=status,
                     value_text=it.get("value_text") or None,
                     explanation=expl.strip(), document_version_id=v.id, page_number=vq.get("page_number") or page,
                     article=it.get("article") or None, quote=quote, quote_verified=vq["verified"], origin="ai",
                     confidence=it.get("confidence"), review_status="te_beoordelen", ai_analysis_id=analysis.id)
        db.add(nf)
        db.flush()
        for e in existing:
            e.superseded_by_id = nf.id
        created += 1
    analysis.validation = {"created": created, "skipped_locked": skipped_locked, "downgraded": downgraded,
                           "unverified_quotes": unverified, "coverage_levels": levels_set}
    db.commit()
    return {"analysis_id": analysis.id, **analysis.validation, "notes": data.get("document_notes"),
            "cost_eur": analysis.cost_estimate}


KNOWN_STRICT = {"gedekt", "uitgesloten", "voorwaardelijk", "aanvullende_clausule"}


# ---------------------------------------------------------------- verkoopargumenten
SALES_SCHEMA = obj({
    "title": STR,
    "arguments": arr(obj({"fact": STR, "customer_benefit": STR, "sales_argument": STR, "refs": arr(STR)})),
    "competitor_strengths": arr(obj({"text": STR, "refs": arr(STR)})),
    "vetera_limitations": arr(STR),
    "advisor_questions": arr(STR),
    "relevant_for": arr(STR),
    "uncertainties": arr(STR),
})


def sales_card(db: Session, vetera_id: int, competitor_id: int, dry_run: bool, use_ai: bool) -> dict:
    vp, cp = db.get(Product, vetera_id), db.get(Product, competitor_id)
    if not vp or not cp:
        raise ValueError("Product niet gevonden.")
    if not use_ai:
        content = local_sales_card(db, vp, cp)
        card = SalesCard(competitor_product_id=cp.id, vetera_product_id=vp.id, content=content, origin="lokaal")
        db.add(card); db.commit()
        return {"card_id": card.id, "content": content}
    ctx = ContextBuilder(db)
    for f in db.scalars(select(Finding).where(Finding.product_id.in_([vp.id, cp.id]), Finding.is_current.is_(True))):
        ctx.add_finding(f)
    for o in db.scalars(select(PremiumObservation).where(PremiumObservation.product_id.in_([vp.id, cp.id]))):
        ctx.add_premium(o)
    vl, cl = product_label(db, vp), product_label(db, cp)
    system = BASE_RULES + """
Stel een compacte advieskaart op voor verzekeringsadviseurs: 'Waarom Vetera overwegen ten opzichte van
<concurrent>?'. Maximaal vijf argumenten. Maak per argument onderscheid tussen het feitelijke productverschil
(fact), het praktische klantvoordeel (customer_benefit) en het mogelijke verkoopargument (sales_argument).
Elk argument moet refs bevatten naar aangeleverde bevindingen. Benoem ook eerlijk waar de concurrent
aantoonbaar gunstiger is en welke beperkingen Vetera heeft. Voeg vragen toe die een adviseur kan stellen."""
    user = f"Vetera-product: {vl['name']}. Concurrent: {cl['provider_name']} – {cl['name']}.\n\nGegevens:\n{ctx.render()}"
    if dry_run:
        return {"preview": build_preview(db, "verkoop", system, user, ctx.summary())}
    data, analysis = run_structured(db, kind="verkoop", system=system, user_text=user, schema=SALES_SCHEMA,
                                    sent_summary=ctx.summary())
    refs = [{"ref": r} for a in data.get("arguments", []) for r in a.get("refs", [])]
    val = validate_sources(db, ctx, refs)
    data["arguments"] = data.get("arguments", [])[:5]
    for a in data["arguments"]:
        a["evidence"] = [ctx.items[r] for r in a.get("refs", []) if r in ctx.items]
        a["unsupported"] = not a["evidence"]
    data.update({"vetera": vl, "competitor": cl, "origin": "ai"})
    analysis.validation = val
    card = SalesCard(competitor_product_id=cp.id, vetera_product_id=vp.id, content=data, origin="ai",
                     ai_analysis_id=analysis.id)
    db.add(card); db.commit()
    return {"card_id": card.id, "content": data, "validation": val, "cost_eur": analysis.cost_estimate}


# ---------------------------------------------------------------- verbeterradar
SUGGESTION_ITEM = obj({
    "kind": {"type": "string", "enum": ["datagedreven", "innovatiehypothese"]},
    "title": STR,
    "category": {"type": "string", "enum": ["Productverbetering", "Voorwaardenverbetering", "Commerciële kans",
                                            "Nieuwe doelgroep", "Innovatief concept", "Concurrentievoordeel",
                                            "Proces- of serviceverbetering"]},
    "summary": STR, "gap": STR, "vetera_situation": STR, "market_context": STR, "suggestion": STR,
    "customer_benefits": STR, "commercial_benefits": STR, "risks": STR, "refs": arr(STR),
    "confidence": {"type": "string", "enum": ["hoog", "middel", "laag"]},
    "priority": {"type": "string", "enum": ["hoog", "middel", "laag"]},
    "priority_rationale": STR, "follow_up": STR,
})
RADAR_SCHEMA = obj({"suggestions": arr(SUGGESTION_ITEM), "data_gaps": arr(STR)})


def radar(db: Session, dry_run: bool, focus: str | None = None, web: bool = False) -> dict:
    ctx = build_ask_context(db, focus or "dekking voorwaarden eigen risico collectie acceptatie")
    existing = db.scalars(select(ImprovementSuggestion)).all()
    if existing:
        ctx.add_text("X0", "Reeds vastgelegde suggesties (niet herhalen)", "; ".join(s.title for s in existing[:80]))
    system = BASE_RULES + """
Je bent de Vetera Verbeterradar. Doe twee soorten voorstellen:
A) datagedreven: verbeteringen die direct volgen uit aantoonbare verschillen met concurrenten (met refs);
B) innovatiehypothese: nieuwe ideeën, ook als concurrenten ze nog niet bieden. Label deze als 'innovatiehypothese'
en presenteer ze nooit als bewezen marktkans.
Maak GEEN nieuw Vetera-product of 'Vetera 2.0'; alles zijn voorstellen voor doorontwikkeling van het huidige product.
Prioriteit is kwalitatief (hoog/middel/laag) en onderbouwd in priority_rationale op basis van aantoonbaarheid,
klantwaarde, commerciële aantrekkelijkheid, onderscheidend vermogen, uitvoerbaarheid, risico's en
beschikbaarheid van informatie. Noem geen omzet-, conversie- of marktgroottecijfers tenzij ze in de bronnen staan;
vermeld anders dat deze niet betrouwbaar te bepalen zijn. Geef 4 tot 8 voorstellen."""
    if web:
        system += "\nJe mag webonderzoek gebruiken voor bredere marktontwikkelingen; vermeld de gebruikte URL's in market_context."
    user = f"Focus: {focus or 'algemeen'}\n\nGegevens:\n{ctx.render()}"
    if dry_run:
        return {"preview": build_preview(db, "radar", system, user, ctx.summary(), 8000, web)}
    data, analysis = run_structured(db, kind="radar", system=system, user_text=user, schema=RADAR_SCHEMA,
                                    sent_summary=ctx.summary(), question=focus, web_search=web)
    created = []
    for s in data.get("suggestions", []):
        ev = [{**ctx.items[r], "ref": r} for r in s.get("refs", []) if r in ctx.items]
        conf = s.get("confidence", "laag")
        if s.get("kind") == "datagedreven" and not ev:
            conf = "laag"
        sug = ImprovementSuggestion(
            kind=s.get("kind", "innovatiehypothese"), title=s["title"][:300], category=s.get("category", "Productverbetering"),
            summary=s.get("summary"), gap=s.get("gap"), vetera_situation=s.get("vetera_situation"),
            market_context=s.get("market_context"), suggestion=s.get("suggestion"),
            customer_benefits=s.get("customer_benefits"), commercial_benefits=s.get("commercial_benefits"),
            risks=s.get("risks"), evidence=ev + [{"type": "web", **w} for w in data.get("_web_results", [])[:5]],
            confidence=conf, priority=s.get("priority", "middel"),
            priority_factors={"toelichting": s.get("priority_rationale"),
                              "bronverwijzingen": len(ev)},
            follow_up=s.get("follow_up"), origin="ai", ai_analysis_id=analysis.id)
        db.add(sug)
        created.append(sug)
    db.commit()
    return {"analysis_id": analysis.id, "created": [s.id for s in created], "data_gaps": data.get("data_gaps", []),
            "cost_eur": analysis.cost_estimate}


DOSSIER_SCHEMA = obj({
    "background": STR, "competitive_analysis": STR, "market_figures": arr(obj({"figure": STR, "source": STR})),
    "target_group": STR, "product_adjustments": arr(STR), "commercial_opportunities": arr(STR),
    "risks": arr(STR), "open_questions": arr(STR), "next_steps": arr(STR), "sources": arr(SOURCE_SCHEMA),
    "uncertainties": arr(STR),
})


def dossier(db: Session, suggestion_id: int, dry_run: bool, web: bool = False) -> dict:
    s = db.get(ImprovementSuggestion, suggestion_id)
    if not s:
        raise ValueError("Suggestie niet gevonden.")
    ctx = build_ask_context(db, f"{s.title} {s.summary or ''}")
    system = BASE_RULES + """
Stel een verdiepend onderzoeksdossier op voor de onderstaande verbetersuggestie: achtergrond,
concurrentieanalyse, beschikbare marktcijfers (alleen met bron; anders leeg laten en bij onzekerheden vermelden),
potentiële doelgroep, mogelijke productaanpassingen, commerciële kansen, risico's, openstaande vragen,
concrete vervolgstappen en bronnen."""
    if s.kind == "innovatiehypothese":
        system += "\nDit is een innovatiehypothese, geen bewezen marktkans. Formuleer toetsbare aannames."
    user = (f"Suggestie ({s.kind}, {s.category}): {s.title}\nSamenvatting: {s.summary}\nVoorstel: {s.suggestion}\n"
            f"Huidige situatie: {s.vetera_situation}\n\nGegevens:\n{ctx.render()}")
    if dry_run:
        return {"preview": build_preview(db, "dossier", system, user, ctx.summary(), 8000, web)}
    data, analysis = run_structured(db, kind="dossier", system=system, user_text=user, schema=DOSSIER_SCHEMA,
                                    sent_summary=ctx.summary(), question=s.title, web_search=web)
    val = validate_sources(db, ctx, data.get("sources", []))
    analysis.validation = val
    d = ResearchDossier(suggestion_id=s.id, title=f"Dossier: {s.title}", content=data, ai_analysis_id=analysis.id)
    db.add(d)
    if s.status == "nieuw":
        s.status = "onderzoeken"
    db.commit()
    return {"dossier_id": d.id, "content": data, "validation": val, "cost_eur": analysis.cost_estimate}


# ---------------------------------------------------------------- wijzigingsanalyse
DIFF_SCHEMA = obj({
    "summary": STR,
    "changes": arr(obj({"index": INT, "category": {"type": "string", "enum": [
        "redactioneel", "verduidelijking", "dekkingsuitbreiding", "dekkingsbeperking", "acceptatie",
        "nieuwe_uitsluiting", "overig"]}, "impact": STR, "affected_features": arr(STR),
        "certainty": {"type": "string", "enum": ["hoog", "middel", "laag"]}})),
    "relevance_for_vetera": STR, "uncertainties": arr(STR),
})


def analyze_diff(db: Session, diff_id: int, dry_run: bool) -> dict:
    d = db.get(DocumentDiff, diff_id)
    if not d:
        raise ValueError("Vergelijking niet gevonden.")
    doc = db.get(Document, d.document_id)
    if doc.visibility != "publiek":
        raise AIBlocked("Niet-publiek document; AI-analyse is geblokkeerd.")
    changes = "\n".join(f"[{i}] ({c['type']}, indicatief: {c['category']}) OUD p.{c.get('old_page')}: "
                        f"{c['old'][:800]}\n    NIEUW p.{c.get('new_page')}: {c['new'][:800]}"
                        for i, c in enumerate((d.changes or [])[:120]))
    system = BASE_RULES + "\nBeoordeel de wijzigingen tussen twee versies van polisvoorwaarden en hun mogelijke consequenties."
    user = f"Document: {doc.title}\nWijzigingen:\n{changes}"
    if dry_run:
        return {"preview": build_preview(db, "wijziging", system, user, {"items": {"wijzigingen": len(d.changes or [])}})}
    data, analysis = run_structured(db, kind="wijziging", system=system, user_text=user, schema=DIFF_SCHEMA,
                                    sent_summary={"diff_id": d.id})
    d.ai_analysis_id = analysis.id
    db.commit()
    return {"analysis_id": analysis.id, "analysis": data, "cost_eur": analysis.cost_estimate}


# ---------------------------------------------------------------- concurrentieontdekking
DISCOVER_SCHEMA = obj({"providers": arr(obj({
    "name": STR, "website": STR, "provider_type": {"type": "string", "enum": [
        "verzekeraar", "gevolmachtigde", "tussenpersoon", "distributeur", "onbekend"]},
    "products": arr(STR), "vehicle_categories": arr(STR), "risk_carrier": STR, "evidence_url": STR, "note": STR}))})


def discover(db: Session, dry_run: bool) -> dict:
    known = ", ".join(p.name for p in db.scalars(select(Provider)))
    system = BASE_RULES + """
Zoek via webonderzoek naar Nederlandse aanbieders van verzekeringen voor klassieke auto's (oldtimers),
klassieke motorfietsen en klassieke bromfietsen: verzekeraars, gevolmachtigde agenten, tussenpersonen en
distributeurs. Geef alleen partijen waarvan je een bron-URL hebt gevonden. Noem de risicodrager als die vermeld is."""
    user = f"Reeds bekend (niet herhalen): {known}"
    if dry_run:
        return {"preview": build_preview(db, "ontdekking", system, user, {"items": {"bekende_aanbieders": known.count(",") + 1}},
                                         4000, True)}
    data, analysis = run_structured(db, kind="ontdekking", system=system, user_text=user, schema=DISCOVER_SCHEMA,
                                    sent_summary={"bekende_aanbieders": known}, web_search=True)
    names = {normalize_text(p.name) for p in db.scalars(select(Provider))}
    added = []
    for p in data.get("providers", []):
        if not p.get("name") or normalize_text(p["name"]) in names:
            continue
        prov = Provider(name=p["name"][:200], website=p.get("website") or None, provider_type=p.get("provider_type", "onbekend"),
                        status="te_beoordelen", origin="ontdekt",
                        verification_note=f"Door AI-webonderzoek gevonden ({datetime.now():%d-%m-%Y}). Bron: "
                                          f"{p.get('evidence_url') or 'onbekend'}. Producten volgens bron: "
                                          f"{', '.join(p.get('products', [])) or '-'}. Risicodrager: {p.get('risk_carrier') or '-'}. "
                                          "Verifieer voordat je deze aanbieder activeert.")
        db.add(prov)
        db.flush()
        db.add(Notification(type="nieuwe_concurrent", title=f"Nieuwe aanbieder gevonden: {prov.name}",
                            body=prov.verification_note, link=f"/concurrenten/{prov.id}", severity="belangrijk"))
        names.add(normalize_text(p["name"]))
        added.append(prov.id)
    db.commit()
    return {"analysis_id": analysis.id, "added": added, "cost_eur": analysis.cost_estimate}
