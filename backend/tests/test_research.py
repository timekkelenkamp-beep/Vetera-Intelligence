"""Automatisch onderzoek met gesimuleerde AI en gesimuleerde website (geen echt netwerkverkeer)."""
import time

import httpx

from tests.conftest import make_pdf


def wait_job(client, job_id, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/ai/jobs/{job_id}").json()
        if j["status"] in ("klaar", "fout"):
            return j
        time.sleep(0.1)
    raise AssertionError("taak niet klaar")


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
    from app.routers import ai as ai_router
    monkeypatch.setattr(ai_router, "_check_ai", lambda db, web=False: None)
    pv = client.post("/api/ai/research", json={"provider_id": prov["id"], "dry_run": True}).json()
    assert pv["preview"]["web_search"] is True
    # webonderzoek staat standaard uit → zonder sleutel/instelling gaat de echte run niet via run_structured;
    # hier is run_structured gesimuleerd
    job = wait_job(client, client.post("/api/ai/research", json={"provider_id": prov["id"]}).json()["job_id"])
    assert job["status"] == "klaar", job
    r = job["result"]
    docs = {d["title"]: d for d in r["documents"]}
    assert "Polisvoorwaarden oldtimer" in docs and "Jaarverslag" not in docs   # alleen relevante PDF's
    prem = sorted(r["premiums"], key=lambda p: p["amount"])
    assert prem[0]["verified"] is False and prem[1]["verified"] is True      # verzonnen bedrag niet overgenomen
    sel = [x["id"] for k in ("products", "documents", "premiums", "calculators") for x in r[k] if x["selected"]]
    ij = client.post("/api/ai/research/import", json={"provider_id": prov["id"], "analysis_id": r["analysis_id"],
                                                       "selection": sel + [prem[0]["id"]]}).json()
    imp = wait_job(client, ij["job_id"])["result"]
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


def test_add_by_name_pipeline(client, monkeypatch):
    from app.services import research
    from app.routers import ai as ai_router
    monkeypatch.setattr(ai_router, "_check_ai", lambda db, web=False: None)
    calls = []

    def fake_run(db, **kw):
        from app.models import AIAnalysis
        a = AIAnalysis(kind=kw["kind"], model="test", status="voltooid")
        db.add(a); db.commit()
        calls.append(kw["kind"])
        if kw["kind"] == "opzoeken":
            return {"found": True, "name": "Nieuwe Oldtimerverzekeraar", "website": "www.nieuwe-oldtimer.test",
                    "provider_type": "gevolmachtigde", "description": "Specialist", "offers_classic_vehicle_insurance": True,
                    "risk_carrier": "", "evidence_url": "https://www.nieuwe-oldtimer.test", "notes": ""}, a
        return {"notes": "", "pages_checked": 0, "products": [{"name": "Klassiekerpolis", "vehicle_category": "auto",
                "page_url": "", "documents": [], "premium_indications": [], "calculator_url": "", "risk_carrier": ""}]}, a

    monkeypatch.setattr(research, "run_structured", fake_run)
    monkeypatch.setattr(research, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
    from app.services import logos
    monkeypatch.setattr(logos, "auto_logo", lambda db, p, force=False: {"status": "overgeslagen"})
    pv = client.post("/api/ai/add-by-name", json={"name": "Nieuwe Oldtimer", "dry_run": True}).json()
    assert pv["preview"]["web_search"] is True
    j = wait_job(client, client.post("/api/ai/add-by-name", json={"name": "Nieuwe Oldtimer", "analyze": False}).json()["job_id"])
    assert j["status"] == "klaar", j
    assert calls == ["opzoeken", "productonderzoek"]
    prov = client.get(f"/api/providers/{j['result']['provider_id']}").json()
    assert prov["website"] == "https://www.nieuwe-oldtimer.test" and prov["provider_type"] == "gevolmachtigde"
    assert prov["products"][0]["name"] == "Klassiekerpolis"


def test_add_by_name_not_found(client, monkeypatch):
    from app.services import research
    from app.routers import ai as ai_router
    monkeypatch.setattr(ai_router, "_check_ai", lambda db, web=False: None)

    def fake_run(db, **kw):
        from app.models import AIAnalysis
        a = AIAnalysis(kind=kw["kind"], model="test"); db.add(a); db.commit()
        return {"found": False, "name": "", "website": "", "provider_type": "onbekend", "description": "",
                "offers_classic_vehicle_insurance": False, "risk_carrier": "", "evidence_url": "", "notes": "Geen bron"}, a
    monkeypatch.setattr(research, "run_structured", fake_run)
    j = wait_job(client, client.post("/api/ai/add-by-name", json={"name": "Bestaatniet BV"}).json()["job_id"])
    assert j["status"] == "fout" and "niet met zekerheid gevonden" in j["error"]
    assert all(p["name"] != "Bestaatniet BV" for p in client.get("/api/providers").json())
