"""Marktmonitor: respectvolle broncontroles (robots.txt, conditionele verzoeken,
vertraging per host), wijzigingsdetectie en meldingen."""
from __future__ import annotations

import ipaddress
import logging
import re
import socket
import time
import urllib.robotparser
from datetime import datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Document, MonitorRun, Notification, Source, SourceCheck
from .common import sha256_bytes
from .documents import DocumentError, create_document_with_version
from .settings_store import get_setting, set_setting

log = logging.getLogger("vetera.monitor")
MAX_BYTES = 50 * 1024 * 1024


class FetchError(Exception):
    pass


def validate_external_url(url: str) -> str:
    """Alleen http(s) naar publieke hosts; voorkomt verzoeken naar het lokale netwerk."""
    url = (url or "").strip()
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise FetchError("Alleen http- of https-adressen zijn toegestaan.")
    if p.username or p.password:
        raise FetchError("URL's met inloggegevens zijn niet toegestaan.")
    try:
        infos = socket.getaddrinfo(p.hostname, None)
    except socket.gaierror as exc:
        raise FetchError(f"Host '{p.hostname}' is niet gevonden.") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise FetchError("Adressen in het lokale of privé-netwerk zijn niet toegestaan.")
    return url


class _Robots:
    def __init__(self, client: httpx.Client, ua: str):
        self.client, self.ua, self.cache = client, ua, {}

    def allowed(self, url: str) -> bool:
        p = urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self.cache:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.client.get(base + "/robots.txt", timeout=15)
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.allow_all = True
            self.cache[base] = rp
        return self.cache[base].can_fetch(self.ua, url)


def make_client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": get_settings().user_agent}, follow_redirects=True, timeout=30)


def fetch(client: httpx.Client, url: str, etag: str | None = None, last_modified: str | None = None) -> httpx.Response:
    validate_external_url(url)
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    with client.stream("GET", url, headers=headers) as r:
        chunks, size = [], 0
        for c in r.iter_bytes():
            size += len(c)
            if size > MAX_BYTES:
                raise FetchError("Bestand is groter dan 50 MB.")
            chunks.append(c)
        r._content = b"".join(chunks)  # noqa: SLF001
    return r


class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href = None
        self._text = ""
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = ""

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, self._text.strip()))
            self._href = None

    def handle_data(self, data):
        if self._href is not None:
            self._text += data
        self.text_parts.append(data)


def pdf_links(html: str, base: str) -> list[dict]:
    p = _LinkParser()
    try:
        p.feed(html)
    except Exception:
        return []
    out, seen = [], set()
    for href, txt in p.links:
        full = urljoin(base, href)
        if re.search(r"\.pdf($|\?)", full, re.I) and full not in seen:
            seen.add(full)
            out.append({"url": full, "text": txt[:200]})
    return out


def visible_text(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    p = _LinkParser()
    try:
        p.feed(html)
    except Exception:
        pass
    return re.sub(r"\s+", " ", " ".join(p.text_parts)).strip()


def visible_text_hash(html: str) -> str:
    return sha256_bytes(visible_text(html).encode())


def notify(db: Session, type_: str, title: str, body: str | None = None, link: str | None = None,
           severity: str = "info") -> None:
    db.add(Notification(type=type_, title=title, body=body, link=link, severity=severity))


def check_source(db: Session, client: httpx.Client, robots: _Robots, src: Source, run: MonitorRun | None) -> SourceCheck:
    chk = SourceCheck(source_id=src.id, run_id=run.id if run else None, result="fout")
    src.last_check_at = datetime.now()
    try:
        if not src.url:
            raise FetchError("Bron heeft geen URL.")
        if src.access_status == "niet_toegestaan":
            chk.result, chk.message = "geblokkeerd", "Toegang voor deze bron is als 'niet toegestaan' gemarkeerd."
            return chk
        if not robots.allowed(src.url):
            src.access_status = "robots_blokkeert"
            chk.result, chk.message = "geblokkeerd", "robots.txt staat geautomatiseerd ophalen niet toe."
            notify(db, "beoordeling_nodig", f"Bron geblokkeerd door robots.txt: {src.title or src.url}",
                   "Controle overgeslagen. Haal het document handmatig op indien nodig.", "/bronnen")
            return chk
        r = fetch(client, src.url, src.etag, src.last_modified)
        chk.http_status = r.status_code
        if r.status_code == 304:
            chk.result = "ongewijzigd"
            src.last_success_check_at = datetime.now()
            return chk
        if r.status_code in (404, 410):
            chk.result, chk.message = "niet_beschikbaar", f"HTTP {r.status_code}"
            notify(db, "bron_onbeschikbaar", f"Bron niet meer beschikbaar: {src.title or src.url}",
                   f"De server gaf HTTP {r.status_code}.", "/bronnen", "belangrijk")
            return chk
        if r.status_code >= 400:
            chk.result, chk.message = "fout", f"HTTP {r.status_code}"
            return chk
        src.etag = r.headers.get("etag")
        src.last_modified = r.headers.get("last-modified")
        src.last_success_check_at = datetime.now()
        ctype = r.headers.get("content-type", "")
        body = r.content
        is_pdf = body.startswith(b"%PDF") or "pdf" in ctype
        new_hash = sha256_bytes(body) if is_pdf else visible_text_hash(r.text)
        chk.content_hash = new_hash
        if src.content_hash == new_hash:
            chk.result = "ongewijzigd"
            return chk
        first = src.content_hash is None
        src.content_hash = new_hash
        src.retrieved_at = datetime.now()
        if is_pdf:
            doc = db.scalars(select(Document).where(Document.source_id == src.id)).first()
            try:
                d, v, info = create_document_with_version(
                    db, body, urlparse(src.url).path.rsplit("/", 1)[-1] or "document.pdf",
                    provider_id=src.provider_id, product_id=src.product_id, document_type=src.document_type,
                    title=src.title, visibility=src.visibility, document_id=doc.id if doc else None,
                    source_url=src.url, source_id=src.id)
                src.processing_status = "verwerkt"
                if doc:
                    chk.result = "gewijzigd"
                    notify(db, "voorwaarden_gewijzigd", f"Nieuwe documentversie: {d.title}",
                           f"{(info.get('diff_summary') or {}).get('aantal_wijzigingen', '?')} wijzigingen gevonden.",
                           f"/documenten/{d.id}", "belangrijk")
                else:
                    chk.result = "nieuw"
                    notify(db, "beoordeling_nodig", f"Document opgehaald: {d.title}",
                           "Controleer aanbieder, product en documenttype.", f"/documenten/{d.id}")
            except DocumentError as exc:
                chk.result, chk.message = "fout", str(exc)
        else:
            chk.result = "nieuw" if first else "gewijzigd"
            if not first:
                notify(db, "beoordeling_nodig", f"Productpagina gewijzigd: {src.title or src.url}",
                       "De zichtbare tekst van de pagina is veranderd. Beoordeel of dit relevant is.", "/bronnen")
            known = {s.url for s in db.scalars(select(Source).where(Source.url.is_not(None)))}
            for link in pdf_links(r.text, src.url)[:50]:
                if link["url"] not in known:
                    db.add(Source(url=link["url"], title=link["text"] or link["url"].rsplit("/", 1)[-1],
                                  provider_id=src.provider_id, source_type="niet_geverifieerd", kind="document",
                                  access_status=src.access_status, processing_status="ontdekt"))
                    if not first:
                        notify(db, "beoordeling_nodig", f"Nieuw document gevonden op {urlparse(src.url).netloc}",
                               f"{link['text'] or link['url']}", "/bronnen")
        return chk
    except (FetchError, httpx.HTTPError) as exc:
        chk.result, chk.message = "fout", str(exc)[:500] or type(exc).__name__
        return chk
    finally:
        src.last_check_result = chk.result
        db.add(chk)
        db.commit()


def run_monitor(db: Session, trigger: str = "handmatig", source_ids: list[int] | None = None) -> MonitorRun:
    run = MonitorRun(trigger=trigger)
    db.add(run)
    db.commit()
    q = select(Source).where(Source.url.is_not(None))
    q = q.where(Source.id.in_(source_ids)) if source_ids else q.where(Source.monitor_enabled.is_(True))
    sources = db.scalars(q).all()
    delay = float(get_setting(db, "monitor_request_delay_s", 3) or 0)
    counts: dict[str, int] = {}
    last_host_at: dict[str, float] = {}
    try:
        with make_client() as client:
            robots = _Robots(client, get_settings().user_agent)
            for src in sources:
                host = urlparse(src.url).netloc
                wait = delay - (time.monotonic() - last_host_at.get(host, -1e9))
                if wait > 0:
                    time.sleep(wait)
                chk = check_source(db, client, robots, src, run)
                last_host_at[host] = time.monotonic()
                counts[chk.result] = counts.get(chk.result, 0) + 1
        run.status = "voltooid"
    except Exception as exc:  # pragma: no cover
        log.exception("Monitorrun mislukt")
        run.status = "fout"
        counts["fout_run"] = 1
        counts["melding"] = type(exc).__name__
    run.finished_at = datetime.now()
    run.summary = {"bronnen": len(sources), **counts}
    if not source_ids:
        set_setting(db, "monitor_last_run_at", run.finished_at.isoformat())
    db.commit()
    if not source_ids and run.status == "voltooid":
        try:
            from .reports import generate
            rep = generate(db, "marktbericht", {})
            notify(db, "systeem", rep.title, "Het marktbericht van deze broncontrole staat klaar.",
                   f"/rapportages/{rep.id}")
            db.commit()
        except Exception:  # pragma: no cover - een rapport mag de controle niet laten mislukken
            log.exception("Marktbericht opstellen mislukt")
            db.rollback()
    return run


def schedule_status(db: Session) -> dict:
    """Bij 'handmatig' (standaard) wordt er nooit vanzelf gecontroleerd en verschijnt er geen
    'gemist'-melding; de gebruiker start een controle zelf wanneer dat zinvol is."""
    mode = get_setting(db, "monitor_mode", "handmatig") or "handmatig"
    last = get_setting(db, "monitor_last_run_at")
    interval = int(get_setting(db, "monitor_interval_days", 91) or 91)
    last_dt = datetime.fromisoformat(last) if last else None
    enabled_sources = db.query(Source).filter(Source.monitor_enabled.is_(True)).count()
    auto = mode == "automatisch"
    due = (last_dt + timedelta(days=interval)) if (last_dt and auto) else None
    overdue = auto and bool(enabled_sources) and (due is None or datetime.now() > due + timedelta(hours=12))
    return {"mode": mode, "last_run_at": last, "interval_days": interval, "next_due_at": due.isoformat() if due else None,
            "overdue": overdue, "monitored_sources": enabled_sources,
            "message": ("Er is een geplande controle gemist (bijvoorbeeld omdat de computer uit stond). "
                        "Start een inhaalcontrole." if overdue and last_dt else
                        "Er is nog geen broncontrole uitgevoerd." if overdue else None)}
