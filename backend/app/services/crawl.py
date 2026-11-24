"""Gerichte, respectvolle verkenning van de website van een aanbieder, zonder AI.

1. Sitemap (via robots.txt of /sitemap.xml) → productpagina's voor klassieke voertuigen.
2. Productpagina's → links naar polisvoorwaarden (PDF) en verzekeringskaarten (IPID), ook op het
   veelgebruikte platform verzekeringskaarten.nl, plus de hoofdtekst van de pagina zelf.
3. Iedere gevonden bron krijgt voertuigsoort, dekkingsniveau en documenttype op basis van titel en URL,
   zodat later appels met appels worden vergeleken.
"""
from __future__ import annotations

import html as htmllib
import re
import time
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from .monitor import FetchError, _Robots, fetch, validate_external_url

IPID_HOSTS = {"verzekeringskaarten.nl", "www.verzekeringskaarten.nl"}
CLASSIC = re.compile(r"oldtimer|klassie|classic|youngtimer|veteraan|old-timer", re.I)
DOC_WORDS = re.compile(r"voorwaarden|ipid|verzekeringskaart|informatiedocument|clausule|productinformatie|\bvp\b", re.I)


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


def classify(text: str) -> dict:
    """Voertuig, dekkingsniveau en documenttype uit titel/URL."""
    t = text.lower().replace("_", " ").replace("-", " ")
    vehicle = ("motor" if re.search(r"motor(?!rijtuig)|motorfiets", t) else
               "bromfiets" if re.search(r"brom|snor|scooter", t) else
               "auto" if re.search(r"auto|personen", t) else None)
    if re.search(r"allrisk|all risk|volledig casco|casco volledig|uitgebreid", t):
        level = "wa_volledig_casco"
    elif re.search(r"beperkt", t):
        level = "wa_beperkt_casco"
    elif re.search(r"brand.{0,6}diefstal|diefstal.{0,6}brand", t):
        level = "wa_brand_diefstal"
    elif re.search(r"\bwa\b", t) and "casco" not in t:
        level = "wa"
    else:
        level = None
    if re.search(r"verzekeringskaart|ipid|informatiedocument", t):
        dtype = "verzekeringskaart"
    elif re.search(r"algemene voorwaarden|algemene polisvoorwaarden", t):
        dtype = "aanvullende_voorwaarden"
    elif re.search(r"clausule", t):
        dtype = "clausule"
    elif re.search(r"voorwaarden|\bvp\b", t):
        dtype = "polisvoorwaarden"
    else:
        dtype = "overig"
    return {"vehicle_category": vehicle, "coverage_level": level, "document_type": dtype}


def _links(html: str, base: str) -> list[tuple[str, str]]:
    out = []
    for m in re.finditer(r"<a\b[^>]*?href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", html, flags=re.S | re.I):
        text = re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", m.group(2)))).strip()
        out.append((urljoin(base, htmllib.unescape(m.group(1).strip())), text[:200]))
    return out


def main_text(html: str) -> str:
    """Hoofdtekst van een pagina (zonder menu, scripts en voettekst)."""
    m = re.search(r"<main\b[^>]*>(.*?)</main>", html, flags=re.S | re.I)
    body = m.group(1) if m else html
    body = re.sub(r"<(script|style|noscript|nav|header|footer|svg|form)[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)
    body = re.sub(r"<(br|p|li|h[1-6]|div|tr)\b[^>]*>", "\n", body, flags=re.I)
    text = htmllib.unescape(re.sub(r"<[^>]+>", " ", body))
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    return "\n".join(ln for ln in lines if ln)[:60000]


def page_title(html: str) -> str | None:
    m = re.search(r"<h1\b[^>]*>(.*?)</h1>", html, flags=re.S | re.I) or re.search(r"<title>(.*?)</title>", html, flags=re.S | re.I)
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip()[:200] if m else None


def pdf_filename(url: str) -> str:
    q = parse_qs(urlparse(url).query)
    for key in ("uri", "file", "document", "path"):
        if key in q and q[key][0].lower().endswith(".pdf"):
            return q[key][0].rsplit("/", 1)[-1]
    name = urlparse(url).path.rsplit("/", 1)[-1] or "document"
    return name if name.lower().endswith(".pdf") else name + ".pdf"


def is_pdf_url(url: str) -> bool:
    return bool(re.search(r"\.pdf($|[?&#])", url, re.I))


def sitemap_urls(client: httpx.Client, robots: _Robots, base: str, limit: int = 60000) -> list[str]:
    candidates = []
    try:
        r = client.get(base + "/robots.txt", timeout=15)
        if r.status_code < 400:
            candidates += [ln.split(":", 1)[1].strip() for ln in r.text.splitlines() if ln.lower().startswith("sitemap:")]
    except httpx.HTTPError:
        pass
    if not candidates:
        candidates = [base + "/sitemap.xml", base + "/sitemap_index.xml"]
    urls, seen, queue = [], set(), list(dict.fromkeys(candidates))
    while queue and len(seen) < 25 and len(urls) < limit:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            validate_external_url(sm)
            if not robots.allowed(sm):
                continue
            r = fetch(client, sm)
            if r.status_code >= 400:
                continue
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text)
            if "<sitemapindex" in r.text[:2000]:
                # alleen deel-sitemaps die waarschijnlijk producten bevatten eerst
                locs.sort(key=lambda u: 0 if re.search(r"product|verzeker|page|pagina", u, re.I) else 1)
                queue += locs[:30]
            else:
                urls += [htmllib.unescape(u) for u in locs]
        except (FetchError, httpx.HTTPError):
            continue
    return urls[:limit]


def product_pages(urls: list[str], domain: str) -> list[str]:
    scored = []
    for u in urls:
        if not on_domain(u, domain) or is_pdf_url(u):
            continue
        path = urlparse(u).path.lower()
        if not CLASSIC.search(path):
            continue
        if re.search(r"zakelijk|bedrijf|ondernem|blog|nieuws|artikel|vacature", path):
            continue  # zakelijke producten en artikelen zijn niet vergelijkbaar met Vetera's particuliere polis
        score = 10 - path.count("/")
        if re.search(r"vraag|faq|schade-melden|klantenservice", path):
            score -= 8
        if re.search(r"verzekering", path):
            score += 3
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    return [u for _, u in scored[:6]]


def crawl_provider(client: httpx.Client, robots: _Robots, website: str, delay: float = 2.0, progress=None) -> dict:
    progress = progress or (lambda *a, **k: None)
    domain = domain_of(website)
    base = f"https://{urlparse(website if '://' in website else 'https://' + website).hostname}"
    progress("Sitemap van de website lezen…")
    pages = product_pages(sitemap_urls(client, robots, base), domain)
    if not pages:
        # geen sitemap: probeer de homepage op links naar oldtimerpagina's
        try:
            r = fetch(client, base + "/")
            pages = product_pages([u for u, t in _links(r.text, str(r.url)) if CLASSIC.search(u + " " + t)], domain)
        except (FetchError, httpx.HTTPError):
            pages = []
    found_pages, docs, ipid_pages, skipped = [], {}, [], []
    last = 0.0

    def polite_fetch(url):
        nonlocal last
        wait = delay - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
        last = time.monotonic()
        return fetch(client, url)

    for n, url in enumerate(pages, 1):
        progress(f"Productpagina {n} van {len(pages)} lezen: {urlparse(url).path}")
        try:
            if not robots.allowed(url):
                skipped.append(f"{url}: robots.txt staat ophalen niet toe")
                continue
            r = polite_fetch(url)
            if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
                continue
            html = r.text
            title = page_title(html) or url
            text = main_text(html)
            info = classify(f"{title} {url}")
            found_pages.append({"url": str(r.url), "title": title, "text": text, **info})
            for link, ltext in _links(html, str(r.url)):
                host = (urlparse(link).hostname or "").lower()
                label = f"{ltext} {urlparse(link).path} {parse_qs(urlparse(link).query).get('uri', [''])[0]}"
                if re.search(r"zakelijk|bedrijven", label, re.I):
                    continue
                if is_pdf_url(link) and (DOC_WORDS.search(label) or CLASSIC.search(label)):
                    c = classify(label)
                    docs.setdefault(link, {"url": link, "title": ltext or pdf_filename(link), "page": str(r.url),
                                           "official": on_domain(link, domain), **c})
                elif host in IPID_HOSTS and urlparse(link).path.count("/") >= 2:
                    ipid_pages.append((link, ltext, str(r.url)))
        except (FetchError, httpx.HTTPError) as exc:
            skipped.append(f"{url}: {str(exc)[:100] or type(exc).__name__}")
    # Verzekeringskaarten-platform: pagina → PDF-download
    for link, ltext, origin in list(dict.fromkeys(ipid_pages))[:12]:
        try:
            if not robots.allowed(link):
                continue
            r = polite_fetch(link)
            if r.status_code >= 400:
                continue
            title = page_title(r.text) or ltext or link
            label = f"{title} {ltext} {link}"
            pdfs = [u for u, _ in _links(r.text, str(r.url)) if is_pdf_url(u) and (urlparse(u).hostname or "").lower() in IPID_HOSTS]
            target = pdfs[0] if pdfs else None
            if target:
                c = classify(label)
                c["document_type"] = "verzekeringskaart"
                docs.setdefault(target, {"url": target, "title": f"Verzekeringskaart {ltext or title}".strip(), "page": origin,
                                         "official": True, **c})
        except (FetchError, httpx.HTTPError) as exc:
            skipped.append(f"{link}: {str(exc)[:100] or type(exc).__name__}")
    return {"pages": found_pages, "documents": list(docs.values()), "skipped": skipped, "domain": domain}


PRICE = re.compile(r"(?:vanaf|al vanaf|vanaf slechts)\s*€\s?(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:per|p\.?)\s*(maand|jaar|kwartaal)", re.I)


def price_mentions(text: str) -> list[dict]:
    out = []
    for m in PRICE.finditer(text):
        start = max(0, text.rfind("\n", 0, m.start()) + 1)
        end = text.find("\n", m.end())
        quote = text[start:end if end > 0 else None].strip()[:300]
        out.append({"amount": m.group(1), "period": m.group(2).lower(), "quote": quote})
    return out[:5]
