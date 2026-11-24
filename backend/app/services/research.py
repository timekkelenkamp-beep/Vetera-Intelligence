"""Automatisch onderzoek per aanbieder: producten, polisvoorwaarden en openbare premie-indicaties
van de officiële website ophalen.

Werkwijze (niets wordt verzonnen of ongemerkt opgeslagen):
1. AI-webonderzoek, beperkt tot het domein van de officiële website, zoekt productpagina's,
   polisdocumenten, gepubliceerde premies en premiecalculators.
2. De server bezoekt zelf de gevonden pagina's (robots.txt, vertraging) en verzamelt PDF-links.
   Premie-indicaties worden alleen overgenomen als het bedrag letterlijk op de pagina staat.
3. De gebruiker kiest wat er wordt geïmporteerd. PDF's worden opgehaald en verwerkt; producten,
   bronnen, premies en calculators worden aangemaakt met status 'te beoordelen'.
Premiecalculators worden nooit automatisch ingevuld; ze komen in het toestemmingsregister.
"""
from __future__ import annotations

import gc
import re
import time
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (AIAnalysis, CalculatorConnector, CalculatorLog, Document, Notification, PremiumObservation,
                      Product, Provider, Source)
from .ai_client import INT, STR, arr, build_preview, obj, run_structured
from .common import audit, normalize_text, sha256_bytes
from .documents import DocumentError, create_document_with_version
from .excel_import import parse_amount
from . import crawl
from .common import COVERAGE_LEVELS
from .monitor import FetchError, _Robots, fetch, make_client, pdf_links, validate_external_url, visible_text
from .premiums import annualize
from .settings_store import get_setting

DOC_HINTS = [
    ("verzekeringskaart", r"verzekeringskaart|ipid|productinformatie"),
    ("clausule", r"clausule"),
    ("aanvullende_voorwaarden", r"aanvullend|bijzondere voorwaarden"),
    ("polisvoorwaarden", r"voorwaarden"),
    ("premietabel", r"premie|tarie"),
]
RELEVANT = re.compile(r"oldtimer|klassie|classic|youngtimer|veteraan|motor|brom|snor|scooter|collectie|voorwaarden|"
                      r"verzekeringskaart|ipid|clausule|premie|tarie", re.I)

RESEARCH_SCHEMA = obj({
    "products": arr(obj({
        "name": STR,
        "vehicle_category": {"type": "string", "enum": ["auto", "motor", "bromfiets", "meerdere"]},
        "page_url": STR,
        "documents": arr(obj({"url": STR, "title": STR, "document_type": {"type": "string", "enum": [
            "polisvoorwaarden", "verzekeringskaart", "productinformatie", "clausule", "aanvullende_voorwaarden",
            "premietabel", "overig"]}})),
        "premium_indications": arr(obj({"page_url": STR, "quote": STR, "amount": STR,
                                        "period": {"type": "string", "enum": ["jaar", "half_jaar", "kwartaal", "maand"]},
                                        "coverage": STR, "conditions": STR})),
        "calculator_url": STR,
        "risk_carrier": STR,
    })),
    "notes": STR,
    "pages_checked": INT,
})


def domain_of(url: str | None) -> str | None:
    if not url:
        return None
    if "://" not in url:
        url = "https://" + url
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host or None


def on_domain(url: str, domain: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == domain or host.endswith("." + domain)


def guess_doc_type(text: str) -> str:
    t = text.lower()
    for dtype, pat in DOC_HINTS:
        if re.search(pat, t):
            return dtype
    return "overig"


SYSTEM = """Je onderzoekt de officiële website van één Nederlandse verzekeraar of tussenpersoon voor Vetera.
Zoek uitsluitend op het opgegeven domein naar verzekeringen voor klassieke auto's (oldtimers, youngtimers),
klassieke motorfietsen en klassieke bromfietsen. Geef per product: naam, voertuigcategorie, productpagina,
directe links naar polisvoorwaarden, verzekeringskaarten (IPID), clausules en productinformatie (bij voorkeur PDF),
eventuele gepubliceerde premies of 'vanaf'-prijzen en een eventuele premiecalculator.
Harde regels:
- Verzin geen URL's, producten of bedragen. Neem alleen op wat je in de zoekresultaten hebt gezien.
- Een premie-indicatie alleen als het bedrag letterlijk op de pagina staat; 'quote' is de letterlijke tekst met
  het bedrag en 'conditions' beschrijft waarvoor de prijs geldt (bijv. 'vanaf, WA, bouwjaar 1970'), of 'onbekend'.
- Vul een premiecalculator alleen als link in; voer nooit zelf berekeningen of aanvragen uit.
- Laat velden leeg ('') of lijsten leeg als je iets niet hebt gevonden."""


VEHICLE_NAMES = {"auto": "auto", "motor": "motor", "bromfiets": "bromfiets"}


def start(db: Session, provider_id: int, dry_run: bool, progress=None) -> dict:
    """Eerst de website zelf verkennen (sitemap, productpagina's, voorwaarden en verzekeringskaarten per
    dekking). Alleen als daar te weinig uit komt, zoekt de AI aanvullend op het domein van de aanbieder."""
    progress = progress or (lambda *a, **k: None)
    prov = db.get(Provider, provider_id)
    if not prov:
        raise ValueError("Aanbieder niet gevonden.")
    domain = domain_of(prov.website)
    if not domain:
        raise ValueError("Vul eerst de officiële website van deze aanbieder in.")
    known = [p.name for p in db.scalars(select(Product).where(Product.provider_id == prov.id))]
    user = (f"Aanbieder: {prov.name}\nOfficiële website: {prov.website}\nDomein: {domain}\n"
            f"Reeds bekende producten: {', '.join(known) or 'geen'}")
    summary = {"items": {"aanbieder": 1}, "domein": domain}
    if dry_run:
        prev = build_preview(db, "productonderzoek", SYSTEM, user, summary, 4000, True)
        prev["note"] = ("Eerst wordt de website zelf doorzocht (gratis). De AI-zoekopdracht hieronder wordt alleen "
                        "gebruikt als daar te weinig uit komt; de kosten zijn dus maximaal dit bedrag.")
        return {"preview": prev}
    delay = float(get_setting(db, "monitor_request_delay_s", 3) or 0)
    with make_client() as client:
        robots = _Robots(client, get_settings().user_agent)
        found = crawl.crawl_provider(client, robots, prov.website, delay=min(delay, 3), progress=progress)
    candidates = crawl_candidates(db, prov, found)
    analysis, notes = None, None
    if len([d for d in candidates["documents"] if d["kind"] == "document"]) < 2:
        progress("Te weinig gevonden op de website; aanvullend zoeken met AI…")
        try:
            data, analysis = run_structured(db, kind="productonderzoek", system=SYSTEM, user_text=user,
                                            schema=RESEARCH_SCHEMA, sent_summary=summary,
                                            question=f"Productonderzoek {prov.name}", web_search=True,
                                            web_domains=[domain])
            notes = data.get("notes")
            merge_candidates(candidates, enrich(db, prov, domain, data))
        except Exception as exc:  # noqa: BLE001 - AI is een aanvulling; de websiteverkenning blijft bruikbaar
            db.rollback()
            candidates["skipped"].append(f"Aanvullend AI-onderzoek mislukt: {str(exc)[:200]}")
    if analysis is None:
        analysis = AIAnalysis(kind="productonderzoek", model=None, question=f"Websiteverkenning {prov.name}",
                              sent_summary={"items": {}, "domein": domain, "zonder_ai": True}, status="voltooid")
        db.add(analysis)
        db.flush()
    candidates["missing"] = missing_report(candidates)
    analysis.validation = {"candidates": candidates, "provider_id": prov.id}
    db.commit()
    return {"analysis_id": analysis.id, "cost_eur": analysis.cost_estimate or 0, "notes": notes, **candidates}


def crawl_candidates(db: Session, prov: Provider, found: dict) -> dict:
    """Zet de websiteverkenning om in kandidaten: één product per voertuigsoort, documenten per dekking."""
    known_urls = {s.url for s in db.scalars(select(Source).where(Source.url.is_not(None)))}
    existing = {normalize_text(p.name): p.id for p in db.scalars(select(Product).where(Product.provider_id == prov.id))}
    existing_by_vehicle = {}
    for p in db.scalars(select(Product).where(Product.provider_id == prov.id)):
        existing_by_vehicle.setdefault(p.vehicle_category, p.id)
    vehicles = [v for v in ("auto", "motor", "bromfiets")
                if any(x.get("vehicle_category") == v for x in found["documents"] + found["pages"])]
    if not vehicles and (found["documents"] or found["pages"]):
        vehicles = ["auto"]
    products, documents, premiums = [], [], []
    keys = {}
    for v in vehicles:
        key = f"p{len(products) + 1}"
        keys[v] = key
        page = next((x for x in found["pages"] if x.get("vehicle_category") == v), None) or \
            (found["pages"][0] if found["pages"] else None)
        name = f"Oldtimerverzekering {VEHICLE_NAMES[v]}"
        products.append({"id": key, "name": name, "vehicle_category": v, "page_url": page["url"] if page else None,
                         "risk_carrier": None, "selected": True,
                         "existing_product_id": existing.get(normalize_text(name)) or existing_by_vehicle.get(v),
                         "levels": sorted({d["coverage_level"] for d in found["documents"]
                                           if d.get("vehicle_category") == v and d.get("coverage_level")},
                                          key=lambda lv: list(COVERAGE_LEVELS).index(lv))})
    first = products[0]["id"] if products else None
    for d in sorted(found["documents"], key=lambda d: (d["document_type"] != "verzekeringskaart", d["title"])):
        documents.append({"id": f"d{len(documents) + 1}", "kind": "document", "url": d["url"], "title": d["title"][:300],
                          "document_type": d["document_type"], "coverage_level": d.get("coverage_level"),
                          "vehicle_category": d.get("vehicle_category"),
                          "product": keys.get(d.get("vehicle_category")) or first, "official": d["official"],
                          "known": d["url"] in known_urls, "origin": "website",
                          "selected": d["url"] not in known_urls})
    for pg in found["pages"]:
        if len(pg["text"]) < 400:
            continue
        documents.append({"id": f"d{len(documents) + 1}", "kind": "pagina", "url": pg["url"],
                          "title": f"Productpagina: {pg['title']}"[:300], "document_type": "productinformatie",
                          "coverage_level": None, "vehicle_category": pg.get("vehicle_category"),
                          "product": keys.get(pg.get("vehicle_category")) or first, "official": True,
                          "known": pg["url"] in known_urls, "origin": "website", "text": pg["text"],
                          "selected": pg["url"] not in known_urls})
        for pm in crawl.price_mentions(pg["text"]):
            try:
                amount = parse_amount(pm["amount"])
            except ValueError:
                continue
            premiums.append({"id": f"r{len(premiums) + 1}", "product": keys.get(pg.get("vehicle_category")) or first,
                             "amount": amount, "period": pm["period"], "coverage": None, "conditions": "vanaf-prijs, "
                             "voorwaarden onbekend", "quote": pm["quote"], "page_url": pg["url"], "verified": True,
                             "selected": amount is not None})
    return {"products": products, "documents": documents, "premiums": premiums, "calculators": [],
            "skipped": found["skipped"]}


def merge_candidates(base: dict, extra: dict) -> None:
    """Voeg AI-resultaten toe aan de websiteverkenning zonder dubbelingen."""
    by_name = {normalize_text(p["name"]): p["id"] for p in base["products"]}
    by_vehicle = {p["vehicle_category"]: p["id"] for p in base["products"]}
    remap = {}
    for p in extra["products"]:
        hit = by_name.get(normalize_text(p["name"])) or by_vehicle.get(p["vehicle_category"])
        if hit:
            remap[p["id"]] = hit
            continue
        new = f"p{len(base['products']) + 1}"
        remap[p["id"]] = new
        base["products"].append({**p, "id": new, "levels": []})
        by_vehicle.setdefault(p["vehicle_category"], new)
    urls = {d["url"] for d in base["documents"]}
    for d in extra["documents"]:
        if d["url"] in urls:
            continue
        c = crawl.classify(f"{d['title']} {d['url']}")
        base["documents"].append({**d, "id": f"d{len(base['documents']) + 1}", "kind": "document",
                                  "product": remap.get(d.get("product")), "coverage_level": c["coverage_level"],
                                  "vehicle_category": c["vehicle_category"]})
    for r in extra["premiums"]:
        base["premiums"].append({**r, "id": f"r{len(base['premiums']) + 1}", "product": remap.get(r.get("product"))})
    for cal in extra["calculators"]:
        base["calculators"].append({**cal, "id": f"c{len(base['calculators']) + 1}", "product": remap.get(cal.get("product"))})
    base["skipped"] += extra["skipped"]


def missing_report(c: dict) -> list[str]:
    """Wat ontbreekt er nog voor een eerlijke vergelijking?"""
    out = []
    if not c["products"]:
        return ["Geen product voor klassieke voertuigen gevonden op de website. Voeg het product en de "
                "voorwaarden handmatig toe of controleer het websiteadres."]
    for p in c["products"]:
        docs = [d for d in c["documents"] if d["product"] == p["id"]]
        if not any(d["document_type"] == "polisvoorwaarden" for d in docs):
            out.append(f"{p['name']}: geen polisvoorwaarden (PDF) gevonden.")
        if not any(d["document_type"] == "verzekeringskaart" for d in docs):
            out.append(f"{p['name']}: geen verzekeringskaart (IPID) gevonden.")
        if not p.get("levels"):
            out.append(f"{p['name']}: niet vast te stellen welke dekkingen (WA, beperkt/volledig casco) er zijn.")
    if not c["premiums"]:
        out.append("Geen gepubliceerde prijzen gevonden; premies alleen via eigen berekening of Excel-import.")
    return out


def enrich(db: Session, prov: Provider, domain: str, data: dict) -> dict:
    """Controleer en vul de AI-resultaten aan door de pagina's zelf te bezoeken."""
    known_urls = {s.url for s in db.scalars(select(Source).where(Source.url.is_not(None)))}
    existing_products = {normalize_text(p.name): p.id for p in db.scalars(select(Product).where(Product.provider_id == prov.id))}
    products, documents, premiums, calculators, skipped = [], [], [], [], []
    seen_docs: set[str] = set()
    delay = float(get_setting(db, "monitor_request_delay_s", 3) or 0)

    def add_doc(url, title, dtype, pkey, origin):
        if url in seen_docs:
            return
        seen_docs.add(url)
        documents.append({"id": f"d{len(documents) + 1}", "url": url, "title": title or url.rsplit("/", 1)[-1],
                          "document_type": dtype or guess_doc_type(f"{title} {url}"), "product": pkey,
                          "official": on_domain(url, domain), "known": url in known_urls, "origin": origin,
                          "selected": on_domain(url, domain) and url not in known_urls})

    with make_client() as client:
        robots = _Robots(client, get_settings().user_agent)
        last = 0.0
        for i, p in enumerate(data.get("products", [])):
            name = (p.get("name") or "").strip()
            if not name:
                continue
            pkey = f"p{i + 1}"
            products.append({"id": pkey, "name": name[:300], "vehicle_category": p.get("vehicle_category") or "auto",
                             "page_url": p.get("page_url") or None, "risk_carrier": p.get("risk_carrier") or None,
                             "existing_product_id": existing_products.get(normalize_text(name)),
                             "selected": True})
            for d in p.get("documents", []):
                u = (d.get("url") or "").strip()
                if u.startswith("http"):
                    add_doc(u, d.get("title"), d.get("document_type"), pkey, "ai")
            page_text = None
            page = p.get("page_url") or ""
            if page.startswith("http") and on_domain(page, domain):
                try:
                    validate_external_url(page)
                    if robots.allowed(page):
                        wait = delay - (time.monotonic() - last)
                        if wait > 0:
                            time.sleep(wait)
                        r = fetch(client, page)
                        last = time.monotonic()
                        if r.status_code < 400 and "html" in r.headers.get("content-type", "html"):
                            page_text = visible_text(r.text)
                            for link in pdf_links(r.text, str(r.url)):
                                if RELEVANT.search(link["url"] + " " + link["text"]):
                                    add_doc(link["url"], link["text"], None, pkey, "pagina")
                    else:
                        skipped.append(f"{page}: robots.txt staat ophalen niet toe")
                except (FetchError, Exception) as exc:  # noqa: BLE001 - één pagina mag het onderzoek niet stoppen
                    skipped.append(f"{page}: {str(exc)[:120] or type(exc).__name__}")
            for pi in p.get("premium_indications", []):
                quote = (pi.get("quote") or "").strip()
                try:
                    amount = parse_amount(pi.get("amount"))
                except ValueError:
                    amount = None
                url = pi.get("page_url") or page
                verified = bool(page_text and quote and url == page and normalize_text(quote) in normalize_text(page_text))
                if verified and amount is not None:
                    amounts = [a for a in re.findall(r"\d+[.,]?\d*", quote)]
                    verified = any(abs((parse_amount(a) or 0) - amount) < 0.01 for a in amounts if a)
                premiums.append({"id": f"r{len(premiums) + 1}", "product": pkey, "amount": amount,
                                 "period": pi.get("period") or "jaar", "coverage": pi.get("coverage") or None,
                                 "conditions": pi.get("conditions") or "onbekend", "quote": quote, "page_url": url,
                                 "verified": verified, "selected": verified and amount is not None})
            cu = (p.get("calculator_url") or "").strip()
            if cu.startswith("http") and cu not in {c["url"] for c in calculators}:
                calculators.append({"id": f"c{len(calculators) + 1}", "url": cu, "product": pkey, "selected": True})
    return {"products": products, "documents": documents, "premiums": premiums, "calculators": calculators,
            "skipped": skipped}


def import_selected(db: Session, provider_id: int, analysis_id: int, selection: list[str], progress=None) -> dict:
    progress = progress or (lambda *a, **k: None)
    """Importeer de gekozen kandidaten. Alleen kandidaten uit de opgeslagen onderzoeksrun worden gebruikt."""
    prov = db.get(Provider, provider_id)
    a = db.get(AIAnalysis, analysis_id)
    if not prov or not a or a.kind != "productonderzoek" or (a.validation or {}).get("provider_id") != prov.id:
        raise ValueError("Onderzoeksrun niet gevonden.")
    c = a.validation["candidates"]
    sel = set(selection)
    domain = domain_of(prov.website) or ""
    product_ids: dict[str, int] = {}
    created = {"products": 0, "documents": 0, "premiums": 0, "calculators": 0}
    errors, new_versions = [], []

    for p in c["products"]:
        if p["id"] not in sel:
            continue
        if p.get("existing_product_id") and db.get(Product, p["existing_product_id"]):
            product_ids[p["id"]] = p["existing_product_id"]
            continue
        prod = Product(provider_id=prov.id, name=p["name"], vehicle_category=p["vehicle_category"], url=p.get("page_url"),
                       status="te_beoordelen",
                       notes=f"Automatisch gevonden op {domain}" + (f"; risicodrager volgens website: {p['risk_carrier']}"
                                                                     if p.get("risk_carrier") else "") + ". Controleer.")
        db.add(prod)
        db.flush()
        product_ids[p["id"]] = prod.id
        created["products"] += 1
        audit(db, "product", prod.id, "aangemaakt", {"name": prod.name, "bron": "automatisch onderzoek"}, "ai")
        if p.get("page_url") and not db.scalars(select(Source).where(Source.url == p["page_url"])).first():
            db.add(Source(url=p["page_url"], title=f"Productpagina {p['name']}", provider_id=prov.id, product_id=prod.id,
                          source_type="officieel_primair" if on_domain(p["page_url"], domain) else "openbaar_overig",
                          kind="pagina", access_status="onbekend", monitor_enabled=True, processing_status="ontdekt"))
    db.commit()

    delay = float(get_setting(db, "monitor_request_delay_s", 3) or 0)
    docs = [d for d in c["documents"] if d["id"] in sel]
    with make_client() as client:
        robots = _Robots(client, get_settings().user_agent)
        for n, d in enumerate(docs, 1):
            progress(f"Document {n} van {len(docs)} ophalen: {d['title'][:80]}", n - 1, len(docs))
            pid = product_ids.get(d.get("product"))
            try:
                if d.get("kind") == "pagina":
                    # tekst van de productpagina zelf, als doorzoekbaar document zodat citaten controleerbaar zijn
                    content = text_pdf(d.get("text") or "", d["title"], d["url"])
                    filename = "productpagina.pdf"
                else:
                    validate_external_url(d["url"])
                    if not robots.allowed(d["url"]):
                        raise FetchError("robots.txt staat ophalen niet toe")
                    time.sleep(delay)
                    r = fetch(client, d["url"])
                    if r.status_code >= 400:
                        raise FetchError(f"HTTP {r.status_code}")
                    if not r.content.startswith(b"%PDF"):
                        raise FetchError("geen PDF-document")
                    content, filename = r.content, crawl.pdf_filename(d["url"])
                src = db.scalars(select(Source).where(Source.url == d["url"])).first()
                if not src:
                    src = Source(url=d["url"], title=d["title"], provider_id=prov.id, product_id=pid,
                                 source_type="officieel_primair" if d["official"] else "openbaar_overig",
                                 document_type=d["document_type"], kind="document", access_status="onbekend",
                                 visibility="publiek", monitor_enabled=True)
                    db.add(src)
                    db.flush()
                src.content_hash = sha256_bytes(content)
                existing = db.scalars(select(Document).where(Document.source_id == src.id)).first()
                doc, v, _ = create_document_with_version(
                    db, content, filename, provider_id=prov.id,
                    product_id=pid, document_type=d["document_type"], title=d["title"][:300], visibility="publiek",
                    document_id=existing.id if existing else None, source_url=d["url"], source_id=src.id)
                src.processing_status = "verwerkt"
                if d.get("coverage_level") or d.get("vehicle_category"):
                    doc.identification = {**(doc.identification or {}), "scope_level": d.get("coverage_level"),
                                          "scope_vehicle": d.get("vehicle_category")}
                if pid and d.get("coverage_level"):
                    mark_level(db, pid, d["coverage_level"], d["title"], v.id if v.status == "gereed" else None)
                created["documents"] += 1
                if v.status == "gereed" and pid:
                    new_versions.append({"version_id": v.id, "product_id": pid, "title": doc.title, "pages": v.page_count,
                                         "document_type": doc.document_type})
                db.commit()
            except (FetchError, DocumentError) as exc:
                db.rollback()
                errors.append(f"{d['title']}: {exc}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{d['title']}: ophalen mislukt ({type(exc).__name__})")
            finally:
                gc.collect()
        progress("Documenten verwerkt", len(docs), len(docs))

    for p in c["premiums"]:
        if p["id"] not in sel or not p.get("verified") or p.get("amount") is None:
            continue
        pid = product_ids.get(p.get("product"))
        db.add(PremiumObservation(
            provider_id=prov.id, product_id=pid, amount=p["amount"], period=p["period"],
            annual_premium=annualize(p["amount"], p["period"]), coverage_variant=p.get("coverage"),
            observation_type="openbare_indicatie", reliability="laag", visibility="publiek",
            reference_date=a.created_at.date(), calculated_at=a.created_at.date(),
            source_description=f"Gepubliceerd op {p['page_url']}: “{p['quote'][:300]}”",
            notes=f"Geldt voor: {p['conditions']}. Automatisch overgenomen; niet gekoppeld aan een rekenprofiel en daardoor "
                  "niet zonder controle vergelijkbaar."))
        created["premiums"] += 1
    for cal in c["calculators"]:
        if cal["id"] not in sel:
            continue
        if db.scalars(select(CalculatorConnector).where(CalculatorConnector.url == cal["url"])).first():
            continue
        cc = CalculatorConnector(provider_id=prov.id, name=f"Premiecalculator {prov.name}", url=cal["url"],
                                 permission_status="onbekend",
                                 notes="Automatisch gevonden. Controleer de gebruiksvoorwaarden voordat je hem gebruikt.")
        db.add(cc)
        db.flush()
        db.add(CalculatorLog(connector_id=cc.id, action="gevonden", message="Gevonden bij automatisch onderzoek"))
        created["calculators"] += 1
    prov.last_checked_at = a.created_at
    db.add(Notification(type="beoordeling_nodig", title=f"Automatisch onderzoek {prov.name} afgerond",
                        body=f"{created['products']} producten, {created['documents']} documenten, {created['premiums']} "
                             f"premie-indicaties en {created['calculators']} calculators toegevoegd. Controleer ze.",
                        link=f"/concurrenten/{prov.id}"))
    audit(db, "provider", prov.id, "automatisch_onderzoek", created, "ai")
    db.commit()
    return {"created": created, "errors": errors, "new_versions": new_versions}


def text_pdf(text: str, title: str, url: str) -> bytes:
    """Maak een eenvoudige, doorzoekbare PDF van paginatekst (met regelafbreking)."""
    import io
    import textwrap
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title[:200])
    lines = [title, f"Bron: {url}", ""]
    for para in text.splitlines():
        lines += textwrap.wrap(para, 95) or [""]
    y = 800
    for ln in lines:
        c.setFont("Helvetica", 9.5)
        c.drawString(45, y, ln.encode("cp1252", "replace").decode("cp1252"))
        y -= 13
        if y < 45:
            c.showPage()
            y = 800
    c.save()
    return buf.getvalue()


def mark_level(db: Session, product_id: int, level: str, title: str, version_id: int | None) -> None:
    """Een document per dekkingsniveau op de website = dit niveau wordt aangeboden (tenzij handmatig vastgelegd)."""
    from ..models import ProductCoverage
    pc = db.scalars(select(ProductCoverage).where(ProductCoverage.product_id == product_id,
                                                  ProductCoverage.level == level)).first()
    if pc and pc.locked:
        return
    if pc is None:
        pc = ProductCoverage(product_id=product_id, level=level)
        db.add(pc)
    pc.offered = True
    pc.local_name = pc.local_name or title[:200]
    pc.document_version_id = pc.document_version_id or version_id
    pc.origin = pc.origin or "website"


# ---------------------------------------------------------------- volledige verwerking
def analyze_versions(db: Session, versions: list[dict], progress) -> list[dict]:
    from .ai_tasks import extract_document
    out = []
    for n, v in enumerate(versions, 1):
        progress(f"Polisvoorwaarden analyseren met AI ({n} van {len(versions)}): {v['title'][:70]}", n - 1, len(versions))
        try:
            r = extract_document(db, v["version_id"], v["product_id"], False)
            out.append({"title": v["title"], "ok": True, "created": r["created"], "unverified": r["unverified_quotes"],
                        "cost_eur": r["cost_eur"]})
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            out.append({"title": v["title"], "ok": False, "error": str(exc)[:300]})
        gc.collect()
    return out


MAX_AUTO_PAGES = 30


def split_for_analysis(versions: list[dict]) -> tuple[list[dict], list[dict]]:
    """Korte, gestructureerde bronnen (verzekeringskaarten, productpagina, korte voorwaarden) eerst door AI;
    lange polisvoorwaarden alleen op verzoek, zodat de kosten beperkt blijven."""
    order = {"verzekeringskaart": 0, "productinformatie": 1}
    quick = [v for v in versions if v.get("document_type") in order or (v.get("pages") or 0) <= MAX_AUTO_PAGES]
    later = [v for v in versions if v not in quick]
    quick.sort(key=lambda v: order.get(v.get("document_type"), 2))
    return quick, later


def full_research(db: Session, progress, provider_id: int, analyze: bool) -> dict:
    """Zoeken → standaard geselecteerde kandidaten importeren → logo → optioneel AI-analyse."""
    res = start(db, provider_id, False, progress)
    selection = [x["id"] for k in ("products", "documents", "premiums", "calculators") for x in res[k] if x.get("selected")]
    imp = import_selected(db, provider_id, res["analysis_id"], selection, progress)
    progress("Logo ophalen…")
    from .logos import auto_logo
    prov = db.get(Provider, provider_id)
    logo = auto_logo(db, prov)
    quick, later = split_for_analysis(imp["new_versions"])
    analysis = analyze_versions(db, quick, progress) if analyze and quick else []
    if analyze and later:
        analysis.append({"title": f"{len(later)} uitgebreide polisvoorwaarden", "ok": True, "skipped": True,
                         "note": "Opgeslagen en doorzoekbaar; analyseer ze per document als je meer detail wilt "
                                 "(kost meer omdat ze lang zijn)."})
    return {"provider_id": provider_id, "found": {k: len(res[k]) for k in ("products", "documents", "premiums", "calculators")},
            "created": imp["created"], "errors": imp["errors"] + res.get("skipped", [])[:5],
            "logo": logo.get("status"), "analysis": analysis}


FIND_SCHEMA = obj({
    "found": {"type": "boolean"},
    "name": STR, "website": STR,
    "provider_type": {"type": "string", "enum": ["verzekeraar", "gevolmachtigde", "tussenpersoon", "distributeur", "onbekend"]},
    "description": STR,
    "offers_classic_vehicle_insurance": {"type": "boolean"},
    "risk_carrier": STR, "evidence_url": STR, "notes": STR,
})
FIND_SYSTEM = """Zoek op internet naar de Nederlandse aanbieder met de opgegeven naam (verzekeraar, gevolmachtigde,
tussenpersoon of distributeur). Bepaal de officiële website (alleen het eigen domein, geen vergelijkingssite),
het type aanbieder, een korte zakelijke omschrijving en of de partij verzekeringen voor klassieke auto's,
klassieke motorfietsen of klassieke bromfietsen aanbiedt. Verzin niets: als je de partij of de officiële website
niet met zekerheid vindt, zet found op false en leg uit waarom in notes."""


def find_provider_preview(db: Session, name: str) -> dict:
    return {"preview": build_preview(db, "opzoeken", FIND_SYSTEM, f"Naam: {name}",
                                     {"items": {"aanbieder": 1}, "naam": name}, 2000, True),
            "note": "Daarna wordt de officiële website doorzocht (ongeveer dezelfde kosten) en worden PDF's opgehaald. "
                    "AI-analyse van polisvoorwaarden kost per document ongeveer € 0,05 – € 0,50."}


def add_by_name(db: Session, progress, name: str, analyze: bool) -> dict:
    name = name.strip()
    if len(name) < 2:
        raise ValueError("Vul een naam in.")
    existing = next((p for p in db.scalars(select(Provider)) if normalize_text(p.name) == normalize_text(name)), None)
    if existing and existing.website:
        prov = existing
        progress(f"{prov.name} bestaat al; website bekend.")
    else:
        progress(f"{name} opzoeken op internet…")
        data, _ = run_structured(db, kind="opzoeken", system=FIND_SYSTEM, user_text=f"Naam: {name}", schema=FIND_SCHEMA,
                                 sent_summary={"naam": name}, question=f"Opzoeken: {name}", web_search=True, max_tokens=4000)
        site = (data.get("website") or "").strip()
        if not data.get("found") or not site:
            raise ValueError(f"‘{name}’ niet met zekerheid gevonden. {data.get('notes') or ''}".strip())
        if not site.startswith("http"):
            site = "https://" + site
        note = (f"Opgezocht met AI op {time.strftime('%d-%m-%Y')}. Bron: {data.get('evidence_url') or site}. "
                f"Biedt klassieke voertuigverzekeringen: {'ja' if data.get('offers_classic_vehicle_insurance') else 'niet vastgesteld'}."
                + (f" Risicodrager: {data['risk_carrier']}." if data.get("risk_carrier") else "") + " Controleer.")
        if existing:
            prov = existing
            prov.website = site
            prov.verification_note = note
        else:
            prov = Provider(name=(data.get("name") or name)[:200], website=site, provider_type=data.get("provider_type") or "onbekend",
                            description=data.get("description") or None, status="actief", origin="ontdekt",
                            verification_note=note)
            db.add(prov)
        db.flush()
        audit(db, "provider", prov.id, "opgezocht", {"naam": name, "website": site}, "ai")
        db.commit()
        if not data.get("offers_classic_vehicle_insurance"):
            progress("Let op: niet vastgesteld dat deze partij klassieke voertuigen verzekert; website wordt toch doorzocht.")
    result = full_research(db, progress, prov.id, analyze)
    result["provider_name"] = prov.name
    return result
