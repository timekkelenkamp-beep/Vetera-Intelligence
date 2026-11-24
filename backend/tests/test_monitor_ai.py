from datetime import datetime, timedelta

from tests.conftest import make_pdf, setup_providers


def test_schedule_missed_check_detection(client):
    st = client.get("/api/monitor/status").json()
    assert st["overdue"] is False and st["mode"] == "handmatig"
    client.post("/api/sources", json={"url": "https://example.org/voorwaarden.pdf", "monitor_enabled": True})
    assert client.get("/api/monitor/status").json()["overdue"] is False   # handmatig: nooit 'gemist'
    client.patch("/api/settings", json={"monitor_mode": "automatisch", "monitor_interval_days": 7})
    st = client.get("/api/monitor/status").json()
    assert st["overdue"] is True
    client.patch("/api/settings", json={})
    from app.db import SessionLocal
    from app.services.settings_store import set_setting
    db = SessionLocal()
    set_setting(db, "monitor_last_run_at", (datetime.now() - timedelta(days=1)).isoformat())
    db.commit()
    assert client.get("/api/monitor/status").json()["overdue"] is False
    set_setting(db, "monitor_last_run_at", (datetime.now() - timedelta(days=9)).isoformat())
    db.commit()
    db.close()
    st = client.get("/api/monitor/status").json()
    assert st["overdue"] is True and "gemist" in st["message"]


def test_url_validation_blocks_local_network(client):
    for url in ("http://127.0.0.1/x.pdf", "file:///etc/passwd", "http://localhost:3000/api"):
        assert client.post("/api/documents/fetch-url", json={"url": url}).status_code == 422
    assert client.post("/api/sources", json={"url": "http://192.168.1.10/a"}).status_code == 422


def test_monitor_detects_pdf_change(client, monkeypatch):
    """Broncontrole met gesimuleerde webserver (geen echt netwerkverkeer)."""
    import httpx
    from app.services import monitor
    vet, comp, vp, cp = setup_providers(client)
    from tests.conftest import SAMPLE_POLICY
    state = {"pdf": make_pdf()}

    def handler(request: httpx.Request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /geheim/\n")
        if request.url.path.startswith("/geheim/"):
            return httpx.Response(200, content=b"%PDF")
        if request.url.path == "/weg.pdf":
            return httpx.Response(404)
        return httpx.Response(200, content=state["pdf"], headers={"content-type": "application/pdf"})

    monkeypatch.setattr(monitor, "make_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(monitor, "validate_external_url", lambda u: u)
    from app.routers import sources as sources_router
    monkeypatch.setattr(sources_router, "validate_external_url", lambda u: u)
    client.patch("/api/settings", json={"monitor_request_delay_s": 0})
    s1 = client.post("/api/sources", json={"url": "https://verzekeraar.test/voorwaarden.pdf", "provider_id": comp["id"],
                                           "product_id": cp["id"], "monitor_enabled": True}).json()
    s2 = client.post("/api/sources", json={"url": "https://verzekeraar.test/geheim/x.pdf", "monitor_enabled": True}).json()
    s3 = client.post("/api/sources", json={"url": "https://verzekeraar.test/weg.pdf", "monitor_enabled": True}).json()
    r = client.post("/api/monitor/run", json={"sync": True}).json()
    assert r["status"] == "voltooid"
    srcs = {s["id"]: s for s in client.get("/api/sources").json()}
    assert srcs[s1["id"]]["last_check_result"] == "nieuw"
    assert srcs[s2["id"]]["last_check_result"] == "geblokkeerd"       # robots.txt gerespecteerd
    assert srcs[s3["id"]]["last_check_result"] == "niet_beschikbaar"
    r = client.post("/api/monitor/run", json={"sync": True}).json()
    assert client.get("/api/sources").json() and \
        {s["id"]: s for s in client.get("/api/sources").json()}[s1["id"]]["last_check_result"] == "ongewijzigd"
    state["pdf"] = make_pdf(SAMPLE_POLICY + "Artikel 9 Nieuw\nSchade door hagel is niet verzekerd.\n")
    client.post("/api/monitor/run", json={"sync": True})
    assert {s["id"]: s for s in client.get("/api/sources").json()}[s1["id"]]["last_check_result"] == "gewijzigd"
    docs = client.get("/api/documents").json()
    assert docs[0]["version_count"] == 2
    types = {n["type"] for n in client.get("/api/notifications").json()}
    assert {"voorwaarden_gewijzigd", "bron_onbeschikbaar"} <= types
    assert client.get("/api/monitor/status").json()["last_run_at"]


def test_ai_response_validation_with_fake_model(client, monkeypatch):
    """AI-responsvalidatie: verzonnen bron-id's en citaten worden gedetecteerd; uitsluitingen zonder
    geverifieerde passage worden omgezet naar menselijke beoordeling; vergrendelde bevindingen blijven."""
    from app.services import ai_tasks
    vet, comp, vp, cp = setup_providers(client)
    up = client.post("/api/documents/upload", files=[("files", ("v.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"]}).json()[0]
    vid = up["version"]["id"]
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    locked = client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_diefstal"]["id"],
                                                "status": "voorwaardelijk"}).json()

    class FakeAnalysis:
        id = 1
        cost_estimate = 0.0
        validation = None

    def fake_run(db, **kw):
        from app.models import AIAnalysis
        a = AIAnalysis(kind=kw["kind"], model="test", status="voltooid")
        db.add(a)
        db.commit()
        if kw["kind"] == "extractie":
            return {"document_notes": "", "items": [
                {"feature_key": "dek_brand", "status": "gedekt", "value_text": "", "explanation": "art 2.1",
                 "page_number": 1, "article": "2.1", "quote": "Schade door brand, ontploffing en kortsluiting is verzekerd.", "confidence": "hoog"},
                {"feature_key": "dek_storm", "status": "uitgesloten", "value_text": "", "explanation": "verzonnen",
                 "page_number": 0, "article": "", "quote": "", "confidence": "laag"},
                {"feature_key": "dek_vandalisme", "status": "gedekt", "value_text": "", "explanation": "",
                 "page_number": 1, "article": "", "quote": "Vandalisme is altijd volledig gedekt bij ons.", "confidence": "hoog"},
                {"feature_key": "dek_diefstal", "status": "uitgesloten", "value_text": "", "explanation": "",
                 "page_number": 1, "article": "", "quote": "", "confidence": "hoog"},
            ]}, a
        return {"short_answer": "x", "key_findings": [{"text": "y", "refs": ["F999"]}], "comparison": [],
                "implications_for_vetera": [], "sources": [{"ref": f"D{vid}p1", "quote": "Diefstal van het voertuig is verzekerd", "note": ""},
                                                            {"ref": "F424242", "quote": "", "note": ""}],
                "uncertainties": [], "missing_data": [], "next_steps": []}, a

    monkeypatch.setattr(ai_tasks, "run_structured", fake_run)
    r = client.post("/api/ai/extract", json={"version_id": vid, "product_id": cp["id"]}).json()
    assert r["created"] == 3 and r["skipped_locked"] == 1
    cur = {f["feature_id"]: f for f in client.get("/api/findings", params={"product_id": cp["id"]}).json()}
    assert cur[feats["dek_brand"]["id"]]["status"] == "gedekt" and cur[feats["dek_brand"]["id"]]["quote_verified"]
    assert cur[feats["dek_storm"]["id"]]["status"] == "menselijke_beoordeling"
    assert cur[feats["dek_vandalisme"]["id"]]["status"] == "menselijke_beoordeling"
    assert cur[feats["dek_diefstal"]["id"]]["id"] == locked["id"]
    a = client.post("/api/ai/ask", json={"question": "diefstal dekking"}).json()
    assert "F424242" in a["validation"]["unknown_refs"] and "F999" in a["validation"]["unknown_inline_refs"]
    src = next(s for s in a["validation"]["sources"] if s["ref"] == f"D{vid}p1")
    assert src["quote_verified"] is True
    q = client.get("/api/quality").json()
    assert any(i["kind"] == "ai_onderbouwing" for i in q["issues"])


def test_ai_budget_limit(client, monkeypatch):
    monkeypatch.setenv("VETERA_ANTHROPIC_API_KEY", "sk-test")
    from app import config
    config.get_settings.cache_clear()
    client.patch("/api/settings", json={"ai_max_request_cost_eur": 0.000001})
    r = client.post("/api/ai/ask", json={"question": "Welke kansen zijn er?"})
    assert r.status_code == 403 and "limiet" in r.json()["detail"]
