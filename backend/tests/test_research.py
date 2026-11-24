"""Automatisch onderzoek met gesimuleerde AI en gesimuleerde website (geen echt netwerkverkeer)."""
import httpx

from tests.conftest import make_pdf


def test_research_flow(client, monkeypatch):
    from app.services import ai_tasks  # noqa: F401
    from app.services import research
    prov = client.post("/api/providers", json={"name": "Testverzekeraar", "website": "https://www.testverzekeraar.nl"}).json()
    client.patch("/api/settings", json={"monitor_request_delay_s": 0})
    pdf = make_pdf()
    page = ('<html><body><h1>Oldtimerverzekering</h1><p>Al vanaf € 7,50 per maand verzekerd.</p>'
            '<a href="/docs/voorwaarden-oldtimer.pdf">Polisvoorwaarden oldtimer</a>'
            '<a href="/docs/jaarverslag.pdf">Jaarverslag</a></body></html>')

    def handler(req: httpx.Request):
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        if req.url.path == "/oldtimer":
            return httpx.Response(200, text=page, headers={"content-type": "text/html"})
        if req.url.path.endswith(".pdf"):
            return httpx.Response(200, content=pdf, headers={"content-type": "application/pdf"})
        return httpx.Response(404)

    monkeypatch.setattr(research, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(research, "validate_external_url", lambda u: u)
    from app.services import monitor
    monkeypatch.setattr(monitor, "validate_external_url", lambda u: u)

    def fake_run(db, **kw):
        from app.models import AIAnalysis
        assert kw["web_domains"] == ["testverzekeraar.nl"]
        a = AIAnalysis(kind=kw["kind"], model="test", status="voltooid")
        db.add(a); db.commit()
        return {"notes": "", "pages_checked": 2, "products": [{
            "name": "Oldtimerverzekering", "vehicle_category": "auto", "page_url": "https://www.testverzekeraar.nl/oldtimer",
            "documents": [], "risk_carrier": "",
            "calculator_url": "https://www.testverzekeraar.nl/premie-berekenen",
            "premium_indications": [
                {"page_url": "https://www.testverzekeraar.nl/oldtimer", "quote": "Al vanaf € 7,50 per maand verzekerd.",
                 "amount": "7,50", "period": "maand", "coverage": "WA", "conditions": "vanaf-prijs"},
                {"page_url": "https://www.testverzekeraar.nl/oldtimer", "quote": "Vanaf € 3 per maand",
                 "amount": "3", "period": "maand", "coverage": "WA", "conditions": "verzonnen"}]}]}, a

    monkeypatch.setattr(research, "run_structured", fake_run)
    pv = client.post("/api/ai/research", json={"provider_id": prov["id"], "dry_run": True}).json()
    assert pv["preview"]["web_search"] is True
    # webonderzoek staat standaard uit → zonder sleutel/instelling gaat de echte run niet via run_structured;
    # hier is run_structured gesimuleerd
    r = client.post("/api/ai/research", json={"provider_id": prov["id"]}).json()
    docs = {d["title"]: d for d in r["documents"]}
    assert "Polisvoorwaarden oldtimer" in docs and "Jaarverslag" not in docs   # alleen relevante PDF's
    prem = sorted(r["premiums"], key=lambda p: p["amount"])
    assert prem[0]["verified"] is False and prem[1]["verified"] is True      # verzonnen bedrag niet overgenomen
    sel = [x["id"] for k in ("products", "documents", "premiums", "calculators") for x in r[k] if x["selected"]]
    imp = client.post("/api/ai/research/import", json={"provider_id": prov["id"], "analysis_id": r["analysis_id"],
                                                        "selection": sel + [prem[0]["id"]]}).json()
    assert imp["created"] == {"products": 1, "documents": 1, "premiums": 1, "calculators": 1}, imp
    assert imp["new_versions"] and imp["new_versions"][0]["pages"] == 2
    p = client.get("/api/premiums", params={"provider_id": prov["id"]}).json()
    assert len(p) == 1 and p[0]["annual_premium"] == 90 and p[0]["observation_type"] == "openbare_indicatie"
    calc = client.get("/api/calculators").json()[0]
    assert calc["permission_status"] == "onbekend"
    prods = client.get("/api/products", params={"provider_id": prov["id"]}).json()
    assert prods[0]["status"] == "te_beoordelen"
    assert any(s["monitor_enabled"] for s in client.get("/api/sources").json())


def test_research_requires_website(client):
    prov = client.post("/api/providers", json={"name": "Zonder site"}).json()
    r = client.post("/api/ai/research", json={"provider_id": prov["id"], "dry_run": True})
    assert r.status_code == 422 and "website" in r.json()["detail"]
