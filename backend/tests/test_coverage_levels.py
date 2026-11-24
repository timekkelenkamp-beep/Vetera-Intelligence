"""Vergelijken per dekkingsniveau (WA, WA + brand/diefstal, beperkt casco, volledig casco)."""
from tests.conftest import setup_providers


def test_findings_per_level_and_matrix(client):
    vet, comp, vp, cp = setup_providers(client)
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    dief = feats["dek_diefstal"]["id"]
    acc = feats["acc_stalling"]["id"]
    # Vetera: diefstal bij beperkt casco voorwaardelijk, bij volledig casco gedekt
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": dief, "status": "voorwaardelijk", "coverage_level": "wa_beperkt_casco"})
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": dief, "status": "gedekt", "coverage_level": "wa_volledig_casco"})
    # Concurrent: diefstal bij beperkt casco gedekt; stalling geldt voor alle dekkingen
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": dief, "status": "gedekt", "coverage_level": "wa_beperkt_casco"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": acc, "status": "voorwaardelijk"})
    # beide niveau-bevindingen van Vetera blijven naast elkaar actueel
    cur = [f for f in client.get("/api/findings", params={"product_id": vp["id"]}).json() if f["feature_id"] == dief]
    assert {f["coverage_level"] for f in cur} == {"wa_beperkt_casco", "wa_volledig_casco"}

    def row(level, key):
        m = client.get("/api/compare/matrix", params={"product_ids": f"{vp['id']},{cp['id']}", "reference": vp["id"], "level": level}).json()
        return next(r for r in m["rows"] if r["feature"]["key"] == key)

    bc = row("wa_beperkt_casco", "dek_diefstal")
    assert bc["cells"][str(vp["id"])]["status"] == "voorwaardelijk" and bc["differences"][str(cp["id"])]["kind"] == "concurrent_ruimer"
    vc = row("wa_volledig_casco", "dek_diefstal")
    assert vc["cells"][str(vp["id"])]["status"] == "gedekt" and vc["cells"][str(cp["id"])] is None
    wa = row("wa", "dek_diefstal")
    assert wa["cells"][str(vp["id"])] is None                       # andere niveaus tellen niet mee
    # 'alle dekkingen'-bevinding geldt op elk niveau
    assert row("wa", "acc_stalling")["cells"][str(cp["id"])]["status"] == "voorwaardelijk"
    assert row("wa_volledig_casco", "acc_stalling")["cells"][str(cp["id"])]["coverage_level"] is None


def test_product_coverages_not_offered(client):
    vet, comp, vp, cp = setup_providers(client)
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["acc_stalling"]["id"], "status": "gedekt"})
    cov = client.put(f"/api/products/{cp['id']}/coverages/wa_volledig_casco", json={"offered": False}).json()
    assert next(c for c in cov if c["level"] == "wa_volledig_casco")["offered"] is False
    client.put(f"/api/products/{cp['id']}/coverages/wa_beperkt_casco", json={"offered": True, "local_name": "WA Extra"})
    m = client.get("/api/compare/matrix", params={"product_ids": f"{vp['id']},{cp['id']}", "level": "wa_volledig_casco"}).json()
    lab = next(p for p in m["products"] if p["id"] == cp["id"])
    assert lab["level_info"]["offered"] is False
    assert all(r["cells"][str(cp["id"])] is None for r in m["rows"])     # niet aangeboden → geen gegevens
    m2 = client.get("/api/compare/matrix", params={"product_ids": str(cp["id"]), "level": "wa_beperkt_casco"}).json()
    assert m2["products"][0]["level_info"]["local_name"] == "WA Extra"
    assert client.put(f"/api/products/{cp['id']}/coverages/onzin", json={}).status_code == 422


def test_ai_extraction_per_level(client, monkeypatch):
    from app.services import ai_tasks
    from tests.conftest import make_pdf
    vet, comp, vp, cp = setup_providers(client)
    up = client.post("/api/documents/upload", files=[("files", ("v.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"]}).json()[0]
    vid = up["version"]["id"]

    def fake_run(db, **kw):
        from app.models import AIAnalysis
        a = AIAnalysis(kind=kw["kind"], model="test", status="voltooid"); db.add(a); db.commit()
        return {"document_notes": "", "coverage_levels": [
            {"level": "wa_beperkt_casco", "offered": "ja", "local_name": "WA Extra", "page_number": 1, "quote": ""},
            {"level": "wa_volledig_casco", "offered": "nee", "local_name": "", "page_number": 0, "quote": ""}],
            "items": [
                {"feature_key": "dek_brand", "coverage_level": "wa_beperkt_casco", "status": "gedekt", "value_text": "",
                 "explanation": "", "page_number": 1, "article": "2.1", "quote": "Schade door brand, ontploffing en kortsluiting is verzekerd.", "confidence": "hoog"},
                {"feature_key": "acc_stalling", "coverage_level": "alle", "status": "voorwaardelijk", "value_text": "afgesloten garage",
                 "explanation": "", "page_number": 1, "article": "2.2", "quote": "", "confidence": "middel"}]}, a

    monkeypatch.setattr(ai_tasks, "run_structured", fake_run)
    r = client.post("/api/ai/extract", json={"version_id": vid, "product_id": cp["id"]}).json()
    assert r["created"] == 2 and r["coverage_levels"] == 2
    fs = {f["feature_label"]: f for f in client.get("/api/findings", params={"product_id": cp["id"]}).json()}
    assert fs["Brand"]["coverage_level"] == "wa_beperkt_casco" and fs["Stallingsvereisten"]["coverage_level"] is None
    cov = {c["level"]: c for c in client.get(f"/api/products/{cp['id']}/coverages").json()}
    assert cov["wa_beperkt_casco"]["offered"] is True and cov["wa_beperkt_casco"]["local_name"] == "WA Extra"
    assert cov["wa_volledig_casco"]["offered"] is None   # 'nee' zonder citaat → onbekend, niet 'niet aangeboden'
