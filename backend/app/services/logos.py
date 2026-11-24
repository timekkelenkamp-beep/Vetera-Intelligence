"""Logobeheer: officiële logo's van de website van de aanbieder ophalen, de beste kandidaat kiezen,
de achtergrond transparant maken (zonder het logo te vervormen) en automatisch gebruiken.

- Logo's worden nooit opnieuw ontworpen of gegenereerd: alleen bestanden van de officiële website
  of handmatige uploads.
- Een automatisch gekozen logo krijgt de vlag ``logo_auto``; een logo dat de gebruiker zelf kiest of
  uploadt wordt nooit automatisch vervangen.
"""
from __future__ import annotations

import io
import json
import logging
import re
import shutil
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image, ImageDraw, ImageFilter

from ..config import get_settings
from .monitor import FetchError, _Robots, fetch, make_client, validate_external_url

log = logging.getLogger("vetera.logos")
MAX_LOGO_BYTES = 5 * 1024 * 1024
KIND_SCORE = {"img-logo-svg": 100, "inline-svg": 95, "img-logo": 80, "mask-icon": 20, "apple-touch": 35,
              "upload": 120, "og-image": 12, "icon": 10, "bewerkt": 0}


def candidate_dir(provider_id: int) -> Path:
    d = get_settings().logos_dir / "candidates" / str(provider_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def sniff_ext(data: bytes) -> str | None:
    head = data[:512].lstrip()
    if head.startswith(b"\x89PNG"):
        return ".png"
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if head[:4] == b"\x00\x00\x01\x00":
        return ".ico"
    if b"<svg" in data[:4096].lower():
        return ".svg"
    return None


def sanitize_svg(data: bytes) -> bytes:
    s = data.decode("utf-8", errors="replace")
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S | re.I)
    s = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", s, flags=re.I)
    s = re.sub(r"(href\s*=\s*[\"'])\s*javascript:[^\"']*", r"\1#", s, flags=re.I)
    s = re.sub(r"<foreignObject.*?</foreignObject>", "", s, flags=re.S | re.I)
    if "xmlns=" not in s[:500]:
        s = s.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"', 1)
    # Een witte vlak-achtergrond over het hele canvas weghalen (transparant maken)
    s = re.sub(r"<rect\b[^>]*\bwidth=[\"']100%[\"'][^>]*\bfill=[\"'](#fff|#ffffff|white)[\"'][^>]*/>", "", s, count=1, flags=re.I)
    return s.encode("utf-8")


def _meta_path(path: Path) -> Path:
    return path.with_name(path.name + ".meta.json")


def store_candidate(provider_id: int, data: bytes, origin: str, kind: str = "upload") -> dict:
    if len(data) > MAX_LOGO_BYTES:
        raise FetchError("Afbeelding is groter dan 5 MB.")
    ext = sniff_ext(data)
    if not ext:
        raise FetchError("Geen ondersteund afbeeldingsformaat (SVG, PNG, JPG, WEBP, ICO).")
    if ext == ".svg":
        data = sanitize_svg(data)
    else:
        try:
            Image.open(io.BytesIO(data)).verify()
        except Exception as exc:
            raise FetchError("Afbeelding is beschadigd of ongeldig.") from exc
    d = candidate_dir(provider_id)
    for existing in d.iterdir():  # hetzelfde bestand niet twee keer
        if existing.suffix == ext and existing.read_bytes() == data:
            return describe(existing)
    n = len([p for p in d.iterdir() if not p.name.endswith((".json", ".txt"))]) + 1
    path = d / f"kandidaat_{n}{ext}"
    path.write_bytes(data)
    _meta_path(path).write_text(json.dumps({"origin": origin, "kind": kind}), encoding="utf-8")
    return describe(path)


def _is_photo(im: Image.Image) -> bool:
    small = im.convert("RGB").resize((48, 48))
    return len(set(small.getdata())) > 900


def describe(path: Path, provider_name: str | None = None) -> dict:
    meta = {}
    if _meta_path(path).exists():
        meta = json.loads(_meta_path(path).read_text(encoding="utf-8"))
    elif path.with_name(path.name + ".bron.txt").exists():
        meta = {"origin": path.with_name(path.name + ".bron.txt").read_text(encoding="utf-8"), "kind": "img-logo"}
    info = {"name": path.name, "ext": path.suffix, "size": path.stat().st_size, "transparent": None, "width": None,
            "height": None, "origin": meta.get("origin"), "kind": meta.get("kind", "icon")}
    score = KIND_SCORE.get(info["kind"], 10)
    if path.suffix == ".svg":
        info["transparent"] = True
        score += 10
        txt = path.read_text(encoding="utf-8", errors="ignore").lower()
        colors = set(re.findall(r"#[0-9a-f]{3,6}\b|rgb\([^)]*\)", txt)) - {"#000", "#000000", "#fff", "#ffffff"}
        if not colors and "currentcolor" not in txt and info["kind"] != "inline-svg":
            score -= 15  # waarschijnlijk een zwart-wit pictogram (zoals een Safari mask-icon)
    else:
        try:
            im = Image.open(path)
            im.load()
            info["width"], info["height"] = im.size
            info["transparent"] = _has_alpha(im)
            if info["transparent"]:
                score += 10
            w, h = im.size
            if max(w, h) < 48:
                score -= 50
            elif max(w, h) >= 160:
                score += 8
            if h and w / h >= 1.6:
                score += 15  # liggend woordmerk
            if _is_photo(im):
                score -= 60
        except Exception:
            score -= 100
    if meta.get("processed"):
        score += 5
    if provider_name and info["kind"] in ("img-logo", "img-logo-svg"):
        tokens = [t for t in re.split(r"[^a-z0-9]+", provider_name.lower()) if len(t) >= 3 and t not in ("verzekeringen", "verzekering", "and")]
        # Alleen bestandsnaam en alt-tekst tellen, niet de domeinnaam (die bevat de naam altijd)
        origin = re.sub(r"^https?://[^/]+", "", (info["origin"] or "").lower()).rsplit("/", 1)[-1]
        if tokens and any(t in origin for t in tokens):
            score += 30  # logo met de naam van de aanbieder in bestandsnaam of alt-tekst
        elif tokens:
            score -= 25  # waarschijnlijk een partner- of keurmerklogo
    info["score"] = score
    return info


def _has_alpha(im: Image.Image) -> bool:
    if im.mode == "P":
        return "transparency" in im.info
    if im.mode not in ("RGBA", "LA"):
        return False
    return im.getchannel("A").getextrema()[0] < 250


def list_candidates(provider_id: int, provider_name: str | None = None) -> list[dict]:
    d = candidate_dir(provider_id)
    items = [describe(p, provider_name) for p in sorted(d.iterdir()) if not p.name.endswith((".json", ".txt"))]
    return sorted(items, key=lambda c: -c["score"])


# ---------------------------------------------------------------- kandidaten vinden
class _LogoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[str, str, str]] = []  # (kind, url, label)

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        if tag == "link" and "icon" in rel and a.get("href"):
            kind = "mask-icon" if "mask-icon" in rel or a.get("type") == "image/svg+xml" else \
                "apple-touch" if "apple-touch" in rel else "icon"
            self.found.append((kind, a["href"], ""))
        if tag == "meta" and a.get("property") == "og:image" and a.get("content"):
            self.found.append(("og-image", a["content"], ""))
        if tag == "img":
            src = a.get("src") or a.get("data-src") or (a.get("srcset", "").split(",")[-1].strip().split(" ")[0])
            blob = " ".join([src, a.get("alt", ""), a.get("class", ""), a.get("id", "")]).lower()
            if src and "logo" in blob:
                self.found.append(("img-logo-svg" if src.lower().split("?")[0].endswith(".svg") else "img-logo", src,
                                   " ".join([a.get("alt", ""), a.get("title", "")]).strip()))


def inline_svgs(html: str) -> list[str]:
    """Inline <svg>-logo's: een svg met 'logo' in de attributen, of de eerste svg binnen een element
    waarvan class/id/aria-label 'logo' bevat."""
    out = []
    for m in re.finditer(r"<svg\b[^>]*>.*?</svg>", html, flags=re.S | re.I):
        tag = m.group(0)
        opening = tag[:tag.find(">") + 1].lower()
        before = html[max(0, m.start() - 400):m.start()].lower()
        if "logo" in opening or re.search(r"(class|id|aria-label)=[\"'][^\"']*logo[^\"']*[\"'][^<]*>\s*(<[^>]+>\s*){0,3}$", before):
            if 300 < len(tag) < 400_000:
                out.append(tag)
        if len(out) >= 3:
            break
    return out


def discover_candidates(provider_id: int, website: str) -> dict:
    validate_external_url(website)
    added, errors = [], []
    with make_client() as client:
        robots = _Robots(client, get_settings().user_agent)
        if not robots.allowed(website):
            raise FetchError("robots.txt van deze website staat geautomatiseerd ophalen niet toe. Upload het logo handmatig.")
        r = fetch(client, website)
        if r.status_code >= 400:
            raise FetchError(f"Website gaf HTTP {r.status_code}.")
        html = r.text
        for svg in inline_svgs(html):
            try:
                added.append(store_candidate(provider_id, svg.encode(), f"Inline SVG op {r.url}", "inline-svg"))
            except FetchError as exc:
                errors.append(str(exc))
        p = _LogoParser()
        p.feed(html)
        order = sorted(p.found, key=lambda x: -KIND_SCORE.get(x[0], 0))
        seen = set()
        for kind, href, label in order:
            full = urljoin(str(r.url), href.strip())
            if full in seen or full.startswith("data:"):
                continue
            seen.add(full)
            if len(seen) > 8:
                break
            try:
                if not robots.allowed(full):
                    continue
                ir = fetch(client, full)
                if ir.status_code < 400:
                    added.append(store_candidate(provider_id, ir.content, full + (f" (alt: {label})" if label else ""), kind))
            except FetchError as exc:
                errors.append(f"{full}: {exc}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{full}: {type(exc).__name__}")
    return {"candidates": added, "errors": errors,
            "note": "Kandidaten van de officiële website. Controleer of dit het officiële logo is en of gebruik "
                    "is toegestaan (merkrichtlijnen van de aanbieder)."}


# ---------------------------------------------------------------- achtergrond verwijderen
def _bg_color(im: Image.Image) -> tuple[tuple[int, int, int], float]:
    """Meest voorkomende randkleur en het aandeel randpixels dat daarop lijkt."""
    w, h = im.size
    px = im.load()
    edge = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + \
           [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
    opaque = [c for c in edge if c[3] > 200]
    if not opaque:
        return (255, 255, 255), 0.0
    q = Counter((c[0] // 8, c[1] // 8, c[2] // 8) for c in opaque)
    (r, g, b), _ = q.most_common(1)[0]
    bg = (r * 8 + 4, g * 8 + 4, b * 8 + 4)
    near = sum(1 for c in opaque if sum(abs(c[i] - bg[i]) for i in range(3)) < 40)
    return bg, near / len(edge)


def make_transparent(data: bytes, tolerance: int = 28) -> bytes:
    """Maak een egale achtergrond die aan de rand grenst transparant, met zachte randen, en snijd
    overbodige marge weg. Het logo zelf wordt niet geschaald of vervormd."""
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGBA")
    if max(im.size) > 1200:
        im.thumbnail((1200, 1200))
    w, h = im.size
    if not _has_alpha(im):
        bg, share = _bg_color(im)
        if share >= 0.6:
            # Flood fill vanaf alle randpixels met de achtergrondkleur (Pillow, in C)
            work = im.convert("RGB")
            mark = (1, 254, 3) if bg != (1, 254, 3) else (3, 250, 1)
            wp = work.load()
            starts = [(x, y) for x in range(0, w, max(1, w // 40)) for y in (0, h - 1)] + \
                     [(x, y) for y in range(0, h, max(1, h // 40)) for x in (0, w - 1)]
            for xy in starts:
                c = wp[xy]
                if c != mark and sum(abs(c[i] - bg[i]) for i in range(3)) < tolerance * 1.5:
                    ImageDraw.floodfill(work, xy, mark, thresh=tolerance)
            mask = Image.new("L", (w, h), 0)
            mp, op = mask.load(), im.load()
            wp = work.load()
            for y in range(h):
                for x in range(w):
                    if wp[x, y] == mark and op[x, y][:3] != mark:
                        mp[x, y] = 255
            # Zachte overgang: pixels net naast de verwijderde achtergrond krijgen gedeeltelijke transparantie
            band = mask.filter(ImageFilter.MaxFilter(3))
            bp = band.load()
            for y in range(h):
                for x in range(w):
                    r, g, b, a = op[x, y]
                    if mp[x, y]:
                        op[x, y] = (r, g, b, 0)
                    elif bp[x, y]:
                        d = (abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])) / 3
                        if d < tolerance * 2.5:
                            alpha = int(255 * min(1.0, max(0.0, (d - tolerance * 0.4) / (tolerance * 2.1))))
                            op[x, y] = (r, g, b, min(a, alpha))
    bbox = im.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if bbox:
        pad = max(2, int(max(bbox[2] - bbox[0], bbox[3] - bbox[1]) * 0.02))
        im = im.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(w, bbox[2] + pad), min(h, bbox[3] + pad)))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def remove_background(provider_id: int, name: str, tolerance: int = 28) -> dict:
    src = candidate_dir(provider_id) / Path(name).name
    if not src.exists() or src.suffix == ".svg":
        raise FetchError("Achtergrondverwijdering is alleen mogelijk voor PNG/JPG/WEBP/ICO.")
    out = make_transparent(src.read_bytes(), tolerance)
    c = store_candidate(provider_id, out, f"Achtergrond transparant gemaakt van {src.name}", "bewerkt")
    path = candidate_dir(provider_id) / c["name"]
    meta = json.loads(_meta_path(path).read_text(encoding="utf-8"))
    base = describe(src)
    meta.update({"processed": True, "kind": base["kind"], "origin": (base.get("origin") or "") + " · achtergrond verwijderd"})
    _meta_path(path).write_text(json.dumps(meta), encoding="utf-8")
    return describe(path)


def approve(provider_id: int, name: str) -> str:
    src = candidate_dir(provider_id) / Path(name).name
    if not src.exists():
        raise FetchError("Kandidaat niet gevonden.")
    dest = get_settings().logos_dir / f"provider_{provider_id}{src.suffix}"
    for old in get_settings().logos_dir.glob(f"provider_{provider_id}.*"):
        old.unlink()
    shutil.copy(src, dest)
    return str(dest)


# ---------------------------------------------------------------- automatisch
def auto_logo(db, provider, force: bool = False) -> dict:
    """Zoek, kies en gebruik automatisch het beste logo. Een door de gebruiker gekozen logo blijft staan."""
    if provider.logo_status == "goedgekeurd" and not provider.logo_auto and not force:
        return {"status": "overgeslagen", "reason": "Handmatig gekozen logo blijft staan"}
    if not provider.website:
        return {"status": "overgeslagen", "reason": "Geen website"}
    try:
        discover_candidates(provider.id, provider.website)
    except (FetchError, Exception) as exc:  # noqa: BLE001
        return {"status": "mislukt", "reason": str(exc)[:200] or type(exc).__name__}
    cands = [c for c in list_candidates(provider.id, provider.name) if c["score"] > 20 and c["kind"] != "upload"]
    if not cands:
        return {"status": "geen_kandidaat", "reason": "Geen bruikbaar logo gevonden op de website"}
    best = cands[0]
    if best["ext"] != ".svg":
        try:
            best = remove_background(provider.id, best["name"])
        except Exception as exc:  # noqa: BLE001
            log.warning("Achtergrond verwijderen mislukt: %s", type(exc).__name__)
    provider.logo_path = approve(provider.id, best["name"])
    provider.logo_status = "goedgekeurd"
    provider.logo_auto = True
    provider.logo_source_url = (best.get("origin") or "")[:1000]
    db.commit()
    return {"status": "gekozen", "candidate": best}


def auto_logo_background(provider_ids: list[int], force: bool = False) -> None:
    """Voor gebruik als achtergrondtaak (eigen databasesessie)."""
    from ..db import SessionLocal
    from ..models import Provider
    db = SessionLocal()
    try:
        for pid in provider_ids:
            p = db.get(Provider, pid)
            if p:
                res = auto_logo(db, p, force)
                log.info("Logo %s: %s", p.name, res["status"])
    finally:
        db.close()
