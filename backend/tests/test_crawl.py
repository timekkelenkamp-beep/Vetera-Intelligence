"""Websiteverkenning zonder AI: sitemap → productpagina → voorwaarden per dekking (gesimuleerde website)."""
import httpx

from app.services import crawl
from tests.conftest import make_pdf
from tests.test_research import wait_job

SITE = "https://www.voorbeeld-verzekeraar.nl"
PAGE = f"""<html><head><title>Oldtimer | Voorbeeld</title></head><body>
<nav>Menu Autoverzekering Woonverzekering Inloggen</nav>
<main><h1>De oldtimerverzekering</h1>
<p>Je oldtimer moet 30 jaar of ouder zijn. Pechhulp in Nederland is standaard meeverzekerd.</p>
<p>Je rijdt maximaal 7.500 kilometer per jaar. Taxatiewaarde wordt vergoed bij totaal verlies.</p>
<p>Al vanaf € 6,25 per maand.</p>
<p>{'Uitleg over de dekking. ' * 20}</p>
<a href="/asr/api/getpdf?uri=/POD/65010.pdf">Oldtimerauto WA VP OTA-WA 2018-02</a>
<a href="/asr/api/getpdf?uri=/POD/65011.pdf">Oldtimerauto WA Casco Beperkt VP OTA-WACB 2018-02</a>
<a href="/asr/api/getpdf?uri=/POD/65024.pdf">Oldtimermotor WA Casco Allrisk VP OTM-WACA 2018-02</a>
<a href="/docs/jaarverslag.pdf">Jaarverslag</a>
<a href="https://verzekeringskaarten.nl/voorbeeld/Oldtimerverzekering-Auto-WA">Auto WA</a>
</main><footer>Cookies Privacy</footer></body></html>"""


def handler(pdf):
    def h(req: httpx.Request):
        host, path = req.url.host, req.url.path
        if path == "/robots.txt":
            return httpx.Response(200, text=f"User-agent: *\nDisallow: /api/\nSitemap: {SITE}/sitemap.xml\n")
        if path == "/sitemap.xml":
            return httpx.Response(200, text=f"<urlset><url><loc>{SITE}/oldtimerverzekering</loc></url>"
                                            f"<url><loc>{SITE}/zakelijke-oldtimerverzekering</loc></url>"
                                            f"<url><loc>{SITE}/woonverzekering</loc></url></urlset>")
        if path == "/oldtimerverzekering":
            return httpx.Response(200, text=PAGE, headers={"content-type": "text/html"})
        if host == "verzekeringskaarten.nl" and not path.endswith(".pdf"):
            return httpx.Response(200, headers={"content-type": "text/html"},
                                  text='<h1>Oldtimerverzekering Auto WA</h1><a href="/voorbeeld/oldtimer-auto-wa.pdf">PDF</a>')
        if path.endswith(".pdf") or "getpdf" in path:
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(404)
    return h


def test_classify():
    assert crawl.classify("Oldtimerauto WA Casco Beperkt VP OTA-WACB")["coverage_level"] == "wa_beperkt_casco"
    assert crawl.classify("Oldtimermotor WA Casco Allrisk")["vehicle_category"] == "motor"
    assert crawl.classify("Oldtimerauto WA VP OTA-WA") == {"vehicle_category": "auto", "coverage_level": "wa",
                                                           "document_type": "polisvoorwaarden"}
    assert crawl.classify("Algemene voorwaarden VP 2022-01")["document_type"] == "aanvullende_voorwaarden"


def test_main_text_skips_menu():
    t = crawl.main_text(PAGE)
    assert "30 jaar of ouder" in t and "Woonverzekering" not in t and "Cookies" not in t


def test_crawl_and_import(client, monkeypatch):
    from app.services import monitor, research
    from app.routers import ai as ai_router
    pdf = make_pdf()
    for mod in (research, monitor, crawl):
        monkeypatch.setattr(mod, "validate_external_url", lambda u: u)
    monkeypatch.setattr(research, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler(pdf))))
    monkeypatch.setattr(ai_router, "_check_ai", lambda db, web=False: None)

    def no_ai(*a, **k):
        raise AssertionError("AI mag niet nodig zijn als de website genoeg oplevert")
    monkeypatch.setattr(research, "run_structured", no_ai)
    client.patch("/api/settings", json={"monitor_request_delay_s": 0})
    prov = client.post("/api/providers", json={"name": "Voorbeeld", "website": SITE}).json()
    job = wait_job(client, client.post("/api/ai/research", json={"provider_id": prov["id"]}).json()["job_id"])
    assert job["status"] == "klaar", job
    r = job["result"]
    assert r["cost_eur"] == 0
    assert {p["vehicle_category"] for p in r["products"]} == {"auto", "motor"}
    auto = next(p for p in r["products"] if p["vehicle_category"] == "auto")
    assert auto["levels"] == ["wa", "wa_beperkt_casco"]
    titles = {d["title"]: d for d in r["documents"]}
    assert "Jaarverslag" not in titles
    assert titles["Oldtimermotor WA Casco Allrisk VP OTM-WACA 2018-02"]["product"] != auto["id"]
    kaart = next(d for d in r["documents"] if d["document_type"] == "verzekeringskaart")
    assert kaart["official"] and kaart["coverage_level"] == "wa"
    page_doc = next(d for d in r["documents"] if d["kind"] == "pagina")
    assert "zakelijk" not in page_doc["url"]
    assert r["premiums"] and r["premiums"][0]["amount"] == 6.25

    # importeren: de PDF's zijn in deze test identiek, dus alleen de eerste + de paginatekst komen erin
    sel = [x["id"] for k in ("products", "documents", "premiums") for x in r[k] if x["selected"]]
    ij = client.post("/api/ai/research/import", json={"provider_id": prov["id"], "analysis_id": r["analysis_id"],
                                                       "selection": sel}).json()
    imp = wait_job(client, ij["job_id"])["result"]
    assert imp["created"]["products"] == 2
    kinds = {v["document_type"] for v in imp["new_versions"]}
    assert "productinformatie" in kinds
    prods = client.get("/api/products", params={"provider_id": prov["id"]}).json()
    pa = next(p for p in prods if p["vehicle_category"] == "auto")
    covs = {c["level"]: c for c in client.get(f"/api/products/{pa['id']}/coverages").json()}
    assert covs["wa"]["offered"] is True   # voorwaarden voor WA gevonden → WA wordt aangeboden
    found = client.get("/api/search", params={"q": "taxatiewaarde"}).json()
    assert any("Productpagina" in h["document_title"] for h in found)


def test_split_for_analysis():
    from app.services.research import split_for_analysis
    quick, later = split_for_analysis([
        {"document_type": "polisvoorwaarden", "pages": 86}, {"document_type": "verzekeringskaart", "pages": 4},
        {"document_type": "productinformatie", "pages": 3}, {"document_type": "clausule", "pages": 2}])
    assert [q["document_type"] for q in quick] == ["verzekeringskaart", "productinformatie", "clausule"]
    assert later[0]["pages"] == 86
