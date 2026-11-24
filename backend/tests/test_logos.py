"""Logo's: automatisch kiezen en achtergrond verwijderen (gesimuleerde website)."""
import io

import httpx
from PIL import Image, ImageDraw

from app.services import logos


def _logo_png(bg=(255, 255, 255), size=(300, 100)):
    im = Image.new("RGB", size, bg)
    d = ImageDraw.Draw(im)
    d.rectangle([40, 30, 260, 70], fill=(10, 80, 160))   # het 'logo'
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def test_make_transparent_removes_background_and_keeps_logo():
    out = Image.open(io.BytesIO(logos.make_transparent(_logo_png()))).convert("RGBA")
    w, h = out.size
    assert w < 300 and h < 100                       # marge bijgesneden
    assert out.getpixel((0, 0))[3] == 0              # achtergrond transparant
    assert out.getpixel((w // 2, h // 2)) == (10, 80, 160, 255)  # logo onveranderd
    # gekleurde achtergrond werkt ook
    out2 = Image.open(io.BytesIO(logos.make_transparent(_logo_png(bg=(240, 200, 40))))).convert("RGBA")
    assert out2.getpixel((0, 0))[3] == 0


def test_inline_svg_detection():
    svg = '<svg viewBox="0 0 10 10">' + '<path d="M0 0h10v10H0z"/>' * 20 + "</svg>"
    html = f'<header><a class="site-logo" href="/">{svg}</a></header><svg class="icon"><path d="M1 1"/></svg>'
    found = logos.inline_svgs(html)
    assert len(found) == 1 and found[0].startswith("<svg")


def test_auto_logo_end_to_end(client, monkeypatch):
    png = _logo_png()

    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if req.url.path == "/":
            return httpx.Response(200, headers={"content-type": "text/html"}, text=(
                '<html><head><link rel="icon" href="/favicon.ico"><meta property="og:image" content="/foto.jpg"></head>'
                '<body><img class="header-logo" src="/img/logo.png" alt="Logo Test"></body></html>'))
        if req.url.path == "/img/logo.png":
            return httpx.Response(200, content=png, headers={"content-type": "image/png"})
        return httpx.Response(404)

    monkeypatch.setattr(logos, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(logos, "validate_external_url", lambda u: u)
    from app.services import monitor
    monkeypatch.setattr(monitor, "validate_external_url", lambda u: u)
    p = client.post("/api/providers", json={"name": "Logotest", "website": "https://www.logotest.nl/"}).json()
    detail = client.get(f"/api/providers/{p['id']}").json()
    assert detail["logo_status"] == "goedgekeurd" and detail["logo_auto"] is True
    img = Image.open(io.BytesIO(client.get(f"/api/providers/{p['id']}/logo").content)).convert("RGBA")
    assert img.getpixel((0, 0))[3] == 0
    # handmatige keuze wordt niet automatisch vervangen
    cand = client.get(f"/api/providers/{p['id']}/logo/candidates").json()[0]
    client.post(f"/api/providers/{p['id']}/logo/candidates/{cand['name']}/approve")
    assert client.post("/api/providers/logos/auto").json()["started"] == 0
