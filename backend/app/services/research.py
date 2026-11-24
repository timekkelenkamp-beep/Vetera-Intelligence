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


def start(db: Session, provider_id: int, dry_run: bool) -> dict:
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
        return {"preview": build_preview(db, "productonderzoek", SYSTEM, user, summary, 4000, True)}
    data, analysis = run_structured(db, kind="productonderzoek", system=SYSTEM, user_text=user, schema=RESEARCH_SCHEMA,
                                    sent_summary=summary, question=f"Productonderzoek {prov.name}", web_search=True,
                                    web_domains=[domain])
    candidates = enrich(db, prov, domain, data)
    analysis.validation = {"candidates": candidates, "provider_id": prov.id}
    db.commit()
    return {"analysis_id": analysis.id, "cost_eur": analysis.cost_estimate, "notes": data.get("notes"), **candidates}


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


def import_selected(db: Session, provider_id: int, analysis_id: int, selection: list[str]) -> dict:
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
    with make_client() as client:
        robots = _Robots(client, get_settings().user_agent)
        for d in c["documents"]:
            if d["id"] not in sel:
                continue
            pid = product_ids.get(d.get("product"))
            try:
                validate_external_url(d["url"])
                if not robots.allowed(d["url"]):
                    raise FetchError("robots.txt staat ophalen niet toe")
                time.sleep(delay)
                r = fetch(client, d["url"])
                if r.status_code >= 400:
                    raise FetchError(f"HTTP {r.status_code}")
                if not r.content.startswith(b"%PDF"):
                    raise FetchError("geen PDF-document")
                src = db.scalars(select(Source).where(Source.url == d["url"])).first()
                if not src:
                    src = Source(url=d["url"], title=d["title"], provider_id=prov.id, product_id=pid,
                                 source_type="officieel_primair" if d["official"] else "openbaar_overig",
                                 document_type=d["document_type"], kind="document", access_status="onbekend",
                                 visibility="publiek", monitor_enabled=True)
                    db.add(src)
                    db.flush()
                src.content_hash = sha256_bytes(r.content)
                existing = db.scalars(select(Document).where(Document.source_id == src.id)).first()
                doc, v, _ = create_document_with_version(
                    db, r.content, urlparse(d["url"]).path.rsplit("/", 1)[-1] or "document.pdf", provider_id=prov.id,
                    product_id=pid, document_type=d["document_type"], title=d["title"][:300], visibility="publiek",
                    document_id=existing.id if existing else None, source_url=d["url"], source_id=src.id)
                src.processing_status = "verwerkt"
                created["documents"] += 1
                if v.status == "gereed" and pid:
                    new_versions.append({"version_id": v.id, "product_id": pid, "title": doc.title, "pages": v.page_count})
                db.commit()
            except (FetchError, DocumentError) as exc:
                db.rollback()
                errors.append(f"{d['title']}: {exc}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors.append(f"{d['title']}: ophalen mislukt ({type(exc).__name__})")

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
