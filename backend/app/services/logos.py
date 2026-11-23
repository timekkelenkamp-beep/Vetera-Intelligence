"""Logobeheer: kandidaten van de officiële website ophalen of uploaden, achtergrond
optioneel transparant maken (zonder vervorming), en pas na goedkeuring gebruiken.
Logo's worden nooit opnieuw ontworpen of gegenereerd."""
from __future__ import annotations

import io
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from PIL import Image

from ..config import get_settings
from .monitor import FetchError, _Robots, fetch, make_client, validate_external_url

IMAGE_TYPES = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
               "image/x-icon": ".ico", "image/vnd.microsoft.icon": ".ico"}
MAX_LOGO_BYTES = 5 * 1024 * 1024


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
    if b"<svg" in data[:2048].lower():
        return ".svg"
    return None


def sanitize_svg(data: bytes) -> bytes:
    s = data.decode("utf-8", errors="replace")
    s = re.sub(r"<script.*?</script>", "", s, flags=re.S | re.I)
    s = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", s, flags=re.I)
    s = re.sub(r"(href\s*=\s*[\"'])\s*javascript:[^\"']*", r"\1#", s, flags=re.I)
    s = re.sub(r"<foreignObject.*?</foreignObject>", "", s, flags=re.S | re.I)
    return s.encode("utf-8")


def store_candidate(provider_id: int, data: bytes, origin: str) -> dict:
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
    n = len(list(d.glob("*"))) + 1
    path = d / f"kandidaat_{n}{ext}"
    path.write_bytes(data)
    (d / f"kandidaat_{n}{ext}.bron.txt").write_text(origin, encoding="utf-8")
    return describe(path)


def describe(path: Path) -> dict:
    info = {"name": path.name, "ext": path.suffix, "size": path.stat().st_size, "transparent": None,
            "width": None, "height": None}
    src = path.with_name(path.name + ".bron.txt")
    info["origin"] = src.read_text(encoding="utf-8") if src.exists() else None
    if path.suffix == ".svg":
        info["transparent"] = True
        return info
    try:
        im = Image.open(path)
        info["width"], info["height"] = im.size
        info["transparent"] = im.mode in ("RGBA", "LA", "P") and _has_alpha(im)
    except Exception:
        pass
    return info


def _has_alpha(im: Image.Image) -> bool:
    if im.mode == "P":
        return "transparency" in im.info
    alpha = im.convert("RGBA").getchannel("A")
    return alpha.getextrema()[0] < 255


def list_candidates(provider_id: int) -> list[dict]:
    d = candidate_dir(provider_id)
    return [describe(p) for p in sorted(d.iterdir()) if not p.name.endswith(".bron.txt")]


class _LogoParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "link" and "icon" in a.get("rel", "").lower():
            score = 3 if a.get("type") == "image/svg+xml" or "mask-icon" in a.get("rel", "") else \
                2 if "apple-touch" in a.get("rel", "") else 1
            if a.get("href"):
                self.found.append((score, a["href"]))
        if tag == "meta" and a.get("property") == "og:image" and a.get("content"):
            self.found.append((1, a["content"]))
        if tag == "img":
            blob = " ".join([a.get("src", ""), a.get("alt", ""), a.get("class", ""), a.get("id", "")]).lower()
            if "logo" in blob and a.get("src"):
                self.found.append((5 if a["src"].lower().endswith(".svg") else 4, a["src"]))


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
        p = _LogoParser()
        p.feed(r.text)
        urls = []
        for _, href in sorted(p.found, key=lambda x: -x[0]):
            full = urljoin(str(r.url), href)
            if full not in urls and not full.startswith("data:"):
                urls.append(full)
        for u in urls[:6]:
            try:
                if not robots.allowed(u):
                    continue
                ir = fetch(client, u)
                if ir.status_code < 400:
                    added.append(store_candidate(provider_id, ir.content, u))
            except FetchError as exc:
                errors.append(f"{u}: {exc}")
    return {"candidates": added, "errors": errors,
            "note": "Kandidaten van de officiële website. Controleer of dit het officiële logo is en of gebruik "
                    "is toegestaan (merkrichtlijnen van de aanbieder)."}


def remove_background(provider_id: int, name: str, tolerance: int = 18) -> dict:
    """Maak een egale (lichte) achtergrond die aan de rand grenst transparant.
    Alleen pixels die vanaf de rand bereikbaar zijn en op de achtergrondkleur lijken; het logo
    zelf wordt niet vervormd of geschaald. Resultaat is een nieuwe kandidaat (origineel blijft)."""
    src = candidate_dir(provider_id) / Path(name).name
    if not src.exists() or src.suffix == ".svg":
        raise FetchError("Achtergrondverwijdering is alleen mogelijk voor PNG/JPG/WEBP.")
    im = Image.open(src).convert("RGBA")
    w, h = im.size
    px = im.load()
    bg = px[0, 0]
    def close(c):
        return all(abs(c[i] - bg[i]) <= tolerance for i in range(3))
    seen = bytearray(w * h)
    stack = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    while stack:
        x, y = stack.pop()
        i = y * w + x
        if seen[i]:
            continue
        seen[i] = 1
        c = px[x, y]
        if c[3] == 0 or close(c):
            px[x, y] = (c[0], c[1], c[2], 0)
            if x > 0: stack.append((x - 1, y))
            if x < w - 1: stack.append((x + 1, y))
            if y > 0: stack.append((x, y - 1))
            if y < h - 1: stack.append((x, y + 1))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return store_candidate(provider_id, buf.getvalue(), f"Achtergrond transparant gemaakt van {src.name}")


def approve(provider_id: int, name: str) -> str:
    src = candidate_dir(provider_id) / Path(name).name
    if not src.exists():
        raise FetchError("Kandidaat niet gevonden.")
    dest = get_settings().logos_dir / f"provider_{provider_id}{src.suffix}"
    for old in get_settings().logos_dir.glob(f"provider_{provider_id}.*"):
        old.unlink()
    shutil.copy(src, dest)
    return str(dest)
