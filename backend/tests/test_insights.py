from datetime import date

from tests.conftest import make_pdf, setup_providers


def _setup(client):
    vet, comp, vp, cp = setup_providers(client)
    client.patch(f"/api/providers/{comp['id']}", json={"status": "actief"})
    feats = {f["key"]: f for f in client.get("/api/features").json()}
    return vet, comp, vp, cp, feats


def test_positioning_places_only_products_with_data(client):
    vet, comp, vp, cp, feats = _setup(client)
    prof = client.get("/api/profiles").json()[0]
    dek = [f for f in feats.values() if f["scoring_aspect"] in ("dekking", "aanvullend", "waarde", "eigen_risico", "collectie")
           and f["value_type"] == "status"]
    for f in dek:
        client.post("/api/findings", json={"product_id": vp["id"], "feature_id": f["id"], "status": "gedekt"})
        client.post("/api/findings", json={"product_id": cp["id"], "feature_id": f["id"], "status": "voorwaardelijk"})
    client.post("/api/premiums", json={"provider_id": vet["id"], "product_id": vp["id"], "profile_id": prof["id"], "amount": 200,
                                       "reference_date": date.today().isoformat()})
    r = client.get("/api/insights/positioning", params={"profile_id": prof["id"]}).json()
    assert [p["id"] for p in r["points"]] == [vp["id"]]
    assert r["points"][0]["conditions"] == 100.0
    assert r["missing"][0]["id"] == cp["id"] and "Geen premie" in r["missing"][0]["reasons"][0]


def test_advice_never_treats_unknown_as_no(client):
    vet, comp, vp, cp, feats = _setup(client)
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["geb_evenementen"]["id"], "status": "gedekt"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["geb_evenementen"]["id"], "status": "uitgesloten"})
    r = client.post("/api/insights/advice", json={"answers": {"vehicle_category": "auto", "activities": ["rally"]}}).json()
    byid = {x["id"]: x for x in r["results"]}
    assert byid[cp["id"]]["verdict"] == "past_niet"
    rally = next(x for x in byid[vp["id"]]["rows"] if x["feature_key"] == "geb_evenementen")
    assert rally["fit"] == "ja"
    wa = next(x for x in byid[vp["id"]]["rows"] if x["feature_key"] == "dek_wa")
    assert wa["fit"] == "onbekend"   # onbekend blijft onbekend
    assert byid[vp["id"]]["verdict"] in ("onvoldoende_gegevens", "past_mogelijk")


def test_whatif_does_not_persist(client):
    vet, comp, vp, cp, feats = _setup(client)
    sp = client.get("/api/score-profiles").json()[0]
    client.patch(f"/api/score-profiles/{sp['id']}", json={"weights": {"acceptatie": 100, "voorwaarden": 0, "premie": 0, "flexibiliteit": 0}})
    acc = [f for f in feats.values() if f["scoring_aspect"] == "acceptatie" and f["value_type"] == "status"]
    for f in acc:
        client.post("/api/findings", json={"product_id": vp["id"], "feature_id": f["id"], "status": "uitgesloten"})
        client.post("/api/findings", json={"product_id": cp["id"], "feature_id": f["id"], "status": "gedekt"})
    r = client.post("/api/insights/whatif", json={"score_profile_id": sp["id"], "product_id": vp["id"],
                                                  "changes": {str(f["id"]): "gedekt" for f in acc}}).json()
    row = next(x for x in r["rows"] if x["is_subject"])
    assert row["base_total"] == 0 and row["scenario_total"] == 100.0
    assert all(f["status"] == "uitgesloten" for f in client.get("/api/findings", params={"product_id": vp["id"]}).json())


def test_battlecard_timeline_brief_quicksearch(client):
    vet, comp, vp, cp, feats = _setup(client)
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["dek_transport"]["id"], "status": "gedekt"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_transport"]["id"], "status": "uitgesloten"})
    up = client.post("/api/documents/upload", files=[("files", ("v.pdf", make_pdf(), "application/pdf"))],
                     data={"provider_id": comp["id"], "product_id": cp["id"]}).json()[0]
    b = client.get(f"/api/insights/battlecard/{comp['id']}").json()
    assert b["products"][0]["weaknesses"][0]["feature"] == "Schade tijdens transport"
    t = client.get(f"/api/insights/timeline/{comp['id']}").json()
    assert {"document", "bevinding"} <= {e["type"] for e in t["events"]}
    brief = client.get("/api/insights/market-brief").json()
    assert brief["new_documents"] and brief["headline"]
    rep = client.post("/api/reports", json={"report_type": "marktbericht", "params": {}})
    assert rep.status_code == 200
    qs = client.get("/api/insights/quicksearch", params={"q": "Testverz"}).json()
    assert any(x["type"] == "aanbieder" for x in qs)
    qs = client.get("/api/insights/quicksearch", params={"q": "kortsluiting"}).json()
    assert any(x["type"] == "tekst" and x["version_id"] == up["version"]["id"] for x in qs)


def test_overview_compact(client):
    vet, comp, vp, cp, feats = _setup(client)
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["dek_transport"]["id"], "status": "gedekt"})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["dek_transport"]["id"], "status": "uitgesloten"})
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["er_standaard"]["id"], "status": "gedekt", "value_number": 150})
    client.post("/api/findings", json={"product_id": cp["id"], "feature_id": feats["geb_evenementen"]["id"], "status": "gedekt"})
    client.post("/api/findings", json={"product_id": vp["id"], "feature_id": feats["geb_evenementen"]["id"], "status": "voorwaardelijk"})
    o = client.get("/api/insights/overview", params={"product_ids": f"{cp['id']}", "reference": vp["id"]}).json()
    assert o["products"][0]["id"] == vp["id"]                      # referentie eerst
    assert len(o["rows"]) == 12 and o["core_count"] == 12
    row = {r["feature"]["key"]: r for r in o["rows"]}
    assert row["dek_transport"]["cells"][str(cp["id"])]["compare"] == "slechter"
    assert row["geb_evenementen"]["cells"][str(cp["id"])]["compare"] == "beter"
    assert row["er_standaard"]["cells"][str(vp["id"])]["value"] == "€ 150"
    s = o["summaries"][0]
    assert s["better"] == ["Evenementen en rally's"] and s["worse"] == ["Schade tijdens transport"]
    assert s["unknown"] == s["total"] - 2
    f = feats["dek_ruitbreuk"]
    client.patch(f"/api/features/{f['id']}", json={"is_core": True})
    assert client.get("/api/insights/overview", params={"product_ids": str(cp["id"])}).json()["core_count"] == 13
