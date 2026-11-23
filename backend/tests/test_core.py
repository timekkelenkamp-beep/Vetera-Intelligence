from tests.conftest import make_pdf, setup_providers


def test_fresh_install_is_empty_but_configured(client):
    d = client.get("/api/dashboard").json()
    assert d["counts"]["competitors"] == 0
    assert d["counts"]["premiums"] == 0          # geen fictieve premies
    assert d["counts"]["documents"] == 0
    assert d["ai"]["configured"] is False         # werkt zonder AI-sleutel
    profiles = client.get("/api/profiles").json()
    assert len(profiles) == 5 and all(p["is_example"] for p in profiles)
    assert len(client.get("/api/features").json()) >= 40
    vet = [p for p in client.get("/api/providers").json() if p["is_reference"]]
    assert len(vet) == 1 and vet[0]["name"] == "Vetera"


def test_provider_crud_merge_and_startlist(client):
    r = client.post("/api/providers/startlijst").json()
    assert r["added"] == 9
    provs = client.get("/api/providers", params={"status": "te_beoordelen"}).json()
    assert len(provs) == 9 and all(p["origin"] == "startlijst" for p in provs)
    a = client.post("/api/providers", json={"name": "Alpha"}).json()
    b = client.post("/api/providers", json={"name": "Alpha BV"}).json()
    assert client.post("/api/providers", json={"name": "alpha"}).status_code == 409
    client.post("/api/products", json={"provider_id": b["id"], "name": "Product B"})
    m = client.post(f"/api/providers/{b['id']}/merge", json={"target_id": a["id"]}).json()
    assert m["moved"]["products"] == 1
    assert client.get(f"/api/providers/{a['id']}").json()["product_count"] == 1
    assert all(p["id"] != b["id"] for p in client.get("/api/providers").json())
    vet = [p for p in client.get("/api/providers").json() if p["is_reference"]][0]
    assert client.delete(f"/api/providers/{vet['id']}").status_code == 422
    assert client.get("/api/audit", params={"entity": "provider"}).json()


def test_distribution_products_not_double_counted(client):
    vet, comp, vp, cp = setup_providers(client)
    dist = client.post("/api/providers", json={"name": "Tussenpersoon X", "provider_type": "tussenpersoon"}).json()
    client.post("/api/products", json={"provider_id": dist["id"], "name": "Test Oldtimer (via X)",
                                       "canonical_product_id": cp["id"]})
    assert client.get("/api/dashboard").json()["counts"]["products"] == 2


def test_pdf_upload_extraction_clauses_and_duplicate(client):
    vet, comp, vp, cp = setup_providers(client)
    pdf = make_pdf()
    r = client.post("/api/documents/upload", files=[("files", ("voorwaarden.pdf", pdf, "application/pdf"))],
                    data={"provider_id": comp["id"], "product_id": cp["id"]}).json()
    assert r[0]["ok"], r
    v = r[0]["version"]
    assert v["page_count"] == 2 and v["clause_count"] >= 5
    assert r[0]["document"]["document_type"] == "polisvoorwaarden"
    pages = client.get(f"/api/document-versions/{v['id']}/pages").json()
    assert "kortsluiting" in pages[0]["text"]
    clauses = client.get(f"/api/document-versions/{v['id']}/clauses").json()
    assert any(c["article"] == "4" for c in clauses)
    # identiek document opnieuw → geweigerd
    dup = client.post("/api/documents/upload", files=[("files", ("kopie.pdf", pdf, "application/pdf"))]).json()
    assert dup[0]["ok"] is False and "identiek" in dup[0]["error"]
    # geen PDF
    bad = client.post("/api/documents/upload", files=[("files", ("x.pdf", b"hallo", "application/pdf"))]).json()
    assert bad[0]["ok"] is False
    # full-text zoeken
    hits = client.get("/api/search", params={"q": "kortsluiting"}).json()
    assert hits and hits[0]["page_number"] == 1
    # PDF-viewer bestand
    f = client.get(f"/api/document-versions/{v['id']}/file")
    assert f.status_code == 200 and f.content.startswith(b"%PDF")


def test_document_versioning_and_diff(client):
    vet, comp, vp, cp = setup_providers(client)
    from tests.conftest import SAMPLE_POLICY
    r1 = client.post("/api/documents/upload", files=[("files", ("v1.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"]}).json()[0]
    doc_id = r1["document"]["id"]
    new_text = SAMPLE_POLICY.replace("Het eigen risico bedraagt EUR 150 per gebeurtenis.",
                                     "Het eigen risico bedraagt EUR 250 per gebeurtenis.") + \
        "Artikel 6 Uitsluiting\nSchade door slijtage is niet verzekerd.\n"
    r2 = client.post("/api/documents/upload", files=[("files", ("v2.pdf", make_pdf(new_text), "application/pdf"))],
                     data={"document_id": doc_id}).json()[0]
    assert r2["ok"] and r2["info"]["diff_id"]
    doc = client.get(f"/api/documents/{doc_id}").json()
    assert doc["version_count"] == 2                       # oude versie blijft bewaard
    assert doc["current_version"]["id"] == r2["version"]["id"]
    diff = client.get(f"/api/diffs/{r2['info']['diff_id']}").json()
    cats = {c["category"] for c in diff["changes"]}
    assert "nieuwe_uitsluiting" in cats
    assert any("250" in (c["new"] or "") for c in diff["changes"])
    notes = client.get("/api/notifications").json()
    assert any(n["type"] == "voorwaarden_gewijzigd" for n in notes)


def test_findings_matrix_and_human_lock(client):
    vet, comp, vp, cp = setup_providers(client)
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    up = client.post("/api/documents/upload", files=[("files", ("v.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"]}).json()[0]
    vid = up["version"]["id"]
    # lokale passagezoeker: nooit 'uitgesloten', wel 'niet gevonden' of 'menselijke beoordeling'
    res = client.post(f"/api/document-versions/{vid}/local-findings", json={}).json()
    assert res["aangemaakt"] == len(feats)
    fl = client.get("/api/findings", params={"product_id": cp["id"]}).json()
    assert {f["status"] for f in fl} <= {"niet_gevonden", "menselijke_beoordeling"}
    brand = next(f for f in fl if f["feature_id"] == feats["dek_brand"]["id"])
    assert brand["status"] == "menselijke_beoordeling" and brand["page_number"] == 1
    # handmatige vastlegging met geverifieerd citaat
    f1 = client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_brand"]["id"],
                                            "status": "gedekt", "document_version_id": vid, "page_number": 1,
                                            "article": "2.1", "quote": "Schade door brand, ontploffing en kortsluiting is verzekerd"}).json()
    assert f1["quote_verified"] is True and f1["locked"]
    fake = client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_storm"]["id"],
                                              "status": "gedekt", "document_version_id": vid, "page_number": 1,
                                              "quote": "Stormschade is altijd volledig verzekerd zonder eigen risico"}).json()
    assert fake["quote_verified"] is False
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["dek_brand"]["id"], "status": "voorwaardelijk"})
    m = client.get("/api/compare/matrix", params={"product_ids": f"{vp['id']},{cp['id']}", "reference": vp["id"],
                                                  "only_differences": True}).json()
    row = next(r for r in m["rows"] if r["feature"]["key"] == "dek_brand")
    d = row["differences"][str(cp["id"])]
    assert d["kind"] == "concurrent_ruimer" and "ruimere regeling" in d["text"]
    # onbekend vs bekend → onzeker, geen claim
    assert all(r["differences"].get(str(cp["id"]), {}).get("kind") != "referentie_ruimer"
               for r in m["rows"] if r["feature"]["key"] == "dek_diefstal")
    # lokale passagezoeker overschrijft menselijke bevinding niet
    client.post(f"/api/document-versions/{vid}/local-findings", json={})
    cur = [f for f in client.get("/api/findings", params={"product_id": cp["id"]}).json()
           if f["feature_id"] == feats["dek_brand"]["id"]]
    assert len(cur) == 1 and cur[0]["status"] == "gedekt" and cur[0]["origin"] == "handmatig"
    # correctie houdt historie
    corr = client.post(f"/api/findings/{cur[0]['id']}/review", json={"action": "corrigeren", "value_text": "incl. kortsluiting"}).json()
    hist = client.get(f"/api/findings/{corr['id']}/history").json()
    assert len(hist) >= 3
    # filters
    m2 = client.get("/api/compare/matrix", params={"product_ids": f"{vp['id']},{cp['id']}", "q": "kortsluiting"}).json()
    assert [r["feature"]["key"] for r in m2["rows"]] == ["dek_brand"]
    m3 = client.get("/api/compare/matrix", params={"product_ids": f"{vp['id']},{cp['id']}", "category": "Eigen risico"}).json()
    assert {r["feature"]["category"] for r in m3["rows"]} == {"Eigen risico"}
    # export
    x = client.get("/api/compare/export", params={"product_ids": f"{vp['id']},{cp['id']}", "reference": vp["id"], "fmt": "xlsx"})
    assert x.status_code == 200 and x.content[:2] == b"PK"
    p = client.get("/api/compare/export", params={"product_ids": f"{vp['id']},{cp['id']}", "fmt": "pdf"})
    assert p.content.startswith(b"%PDF")


def test_scores_require_enough_data(client):
    vet, comp, vp, cp = setup_providers(client)
    sp = client.get("/api/score-profiles").json()[0]
    s = client.get("/api/scores", params={"score_profile_id": sp["id"]}).json()
    assert all(r["total"] is None for r in s["results"])      # geen score zonder voldoende data
    feats = [f for f in client.get("/api/features").json() if f["scoring_aspect"] in ("acceptatie",) and f["value_type"] == "status"]
    for f in feats:
        client.post("/api/findings", json={"product_id": cp["id"], "feature_id": f["id"], "status": "gedekt"})
    s = client.get("/api/scores", params={"score_profile_id": sp["id"], "product_ids": str(cp["id"])}).json()
    assert s["results"][0]["aspects"]["acceptatie"]["score"] == 100.0
    assert s["results"][0]["aspects"]["voorwaarden"]["score"] is None
    assert s["results"][0]["total"] is None
    client.patch(f"/api/score-profiles/{sp['id']}", json={"weights": {"acceptatie": 100, "voorwaarden": 0, "premie": 0, "flexibiliteit": 0}})
    s = client.get("/api/scores", params={"score_profile_id": sp["id"], "product_ids": str(cp["id"])}).json()
    assert s["results"][0]["total"] == 100.0


def test_ai_without_key_is_clear_and_blocks(client):
    st = client.get("/api/ai/status").json()
    assert st["available"] is False and "sleutel" in st["message"]
    r = client.post("/api/ai/ask", json={"question": "Wie heeft de ruimste dekking?"})
    assert r.status_code == 503
    # preview werkt wel en toont wat verstuurd zou worden
    pv = client.post("/api/ai/ask", json={"question": "Wie heeft de ruimste dekking?", "dry_run": True}).json()
    assert "preview" in pv and pv["preview"]["destination"].startswith("Anthropic")


def test_nonpublic_data_not_sent_to_ai(client):
    vet, comp, vp, cp = setup_providers(client)
    up = client.post("/api/documents/upload", files=[("files", ("intern.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"], "visibility": "niet_publiek"}).json()[0]
    vid = up["version"]["id"]
    feats = client.get("/api/features").json()
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats[0]["id"], "status": "gedekt",
                                       "document_version_id": vid, "page_number": 1})
    pv = client.post("/api/ai/ask", json={"question": "brand dekking", "dry_run": True}).json()["preview"]
    assert pv["sent"]["excluded_nonpublic"] >= 1
    assert not any(i.startswith(f"D{vid}") for i in pv["sent"]["ids"])
    r = client.post("/api/ai/extract", json={"version_id": vid, "product_id": cp["id"], "dry_run": True})
    assert r.status_code == 403
    r = client.post("/api/ai/ask", json={"question": "brand", "dry_run": True, "consent_nonpublic": True})
    assert r.status_code == 403  # instelling staat standaard uit


def test_local_sales_card_and_radar(client):
    vet, comp, vp, cp = setup_providers(client)
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["dek_transport"]["id"], "status": "gedekt"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_transport"]["id"], "status": "uitgesloten"})
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["geb_circuit"]["id"], "status": "uitgesloten"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["geb_circuit"]["id"], "status": "voorwaardelijk"})
    card = client.post("/api/ai/sales-card", json={"vetera_product_id": vp["id"], "competitor_product_id": cp["id"]}).json()["content"]
    assert len(card["arguments"]) == 1 and card["arguments"][0]["feature"] == "Schade tijdens transport"
    assert card["competitor_strengths"][0]["feature"] == "Circuitgebruik"   # eerlijk ook concurrentvoordeel
    client.patch(f"/api/providers/{comp['id']}", json={"status": "actief"})
    sc = client.post("/api/radar/scan").json()
    assert sc["created"] == 1
    s = client.get("/api/radar/suggestions").json()[0]
    assert s["kind"] == "datagedreven" and s["evidence"]
    assert client.post("/api/radar/scan").json()["created"] == 0            # geen dubbelingen
    client.patch(f"/api/radar/suggestions/{s['id']}", json={"status": "interessant"})
    assert client.patch(f"/api/radar/suggestions/{s['id']}", json={"status": "onzin"}).status_code == 422


def test_reports_generate_pdf_and_excel(client):
    vet, comp, vp, cp = setup_providers(client)
    for t in client.get("/api/reports/types").json():
        params = {}
        if t["key"] == "verkoop":
            params = {"vetera_product_id": vp["id"], "competitor_product_id": cp["id"]}
        r = client.post("/api/reports", json={"report_type": t["key"], "params": params})
        assert r.status_code == 200, (t, r.text)
        rid = r.json()["id"]
        assert client.get(f"/api/reports/{rid}/download", params={"fmt": "pdf"}).content.startswith(b"%PDF")
        assert client.get(f"/api/reports/{rid}/download", params={"fmt": "xlsx"}).content[:2] == b"PK"


def test_local_only_access(client):
    r = client.get("/api/health", headers={"host": "evil.example.com"})
    assert r.status_code == 403


def test_backup_and_restore(client):
    client.post("/api/providers", json={"name": "Backuptest"})
    b = client.post("/api/backup").json()
    z = client.get(f"/api/backups/{b['file']}").content
    client.post("/api/providers", json={"name": "Na backup"})
    r = client.post("/api/restore", files={"file": ("b.zip", z, "application/zip")}).json()
    assert r["ok"]
    names = [p["name"] for p in client.get("/api/providers").json()]
    assert "Backuptest" in names and "Na backup" not in names
    assert client.post("/api/data/delete", json={"what": "premies"}).status_code == 422
