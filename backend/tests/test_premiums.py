import csv
import io
from datetime import date, timedelta

import openpyxl

from tests.conftest import setup_providers


def test_premium_annualize_and_no_invented_premiums(client):
    vet, comp, vp, cp = setup_providers(client)
    prof = client.get("/api/profiles").json()[0]
    r = client.post("/api/premiums", json={"provider_id": comp["id"], "product_id": cp["id"], "profile_id": prof["id"],
                                           "amount": 10, "period": "maand", "coverage_variant": "wa_beperkt_casco",
                                           "deductible": 150, "tax_included": "ja"}).json()
    assert r["annual_premium"] == 120
    assert client.post("/api/premiums", json={"provider_id": comp["id"]}).status_code == 422   # geen bedrag → geen premie
    na = client.post("/api/premiums", json={"provider_id": comp["id"], "observation_type": "niet_beschikbaar"}).json()
    assert na["annual_premium"] is None
    assert client.post("/api/premiums", json={"provider_id": vet["id"], "product_id": cp["id"], "amount": 5}).status_code == 422


def test_comparability_warnings_and_differences(client):
    vet, comp, vp, cp = setup_providers(client)
    prof = client.get("/api/profiles").json()[0]
    today = date.today().isoformat()
    client.post("/api/premiums", json={"provider_id": vet["id"], "product_id": vp["id"], "profile_id": prof["id"], "amount": 200,
                                       "coverage_variant": "wa_beperkt_casco", "deductible": 150, "tax_included": "ja",
                                       "reference_date": today})
    client.post("/api/premiums", json={"provider_id": comp["id"], "product_id": cp["id"], "profile_id": prof["id"], "amount": 180,
                                       "membership_costs": 40, "coverage_variant": "wa_beperkt_casco", "deductible": 250,
                                       "tax_included": "ja", "reference_date": today})
    c = client.get("/api/premiums/compare", params={"profile_id": prof["id"]}).json()
    assert c["baseline"] == "vetera"
    other = next(r for r in c["rows"] if not r["is_baseline"])
    assert other["total_annual_cost"] == 220 and other["diff_abs"] == 20 and other["diff_pct"] == 10.0
    assert any("eigen risico" in i.lower() for i in other["comparability_issues"])
    assert other["fully_comparable"] is False
    # premieverschil-melding (≥ 15%) alleen bij voldoende verschil
    client.post("/api/premiums", json={"provider_id": comp["id"], "product_id": cp["id"], "profile_id": prof["id"], "amount": 400,
                                       "coverage_variant": "wa_volledig_casco", "deductible": 150, "tax_included": "ja",
                                       "reference_date": today})
    assert any(n["type"] == "premieverschil" for n in client.get("/api/notifications").json())


def test_historical_never_current(client):
    vet, comp, vp, cp = setup_providers(client)
    prof = client.get("/api/profiles").json()[0]
    old = (date.today() - timedelta(days=800)).isoformat()
    client.post("/api/premiums", json={"provider_id": comp["id"], "profile_id": prof["id"], "amount": 100,
                                       "observation_type": "historisch_tarief", "reference_date": old})
    assert client.get("/api/premiums/compare", params={"profile_id": prof["id"]}).json()["rows"] == []
    c = client.get("/api/premiums/compare", params={"profile_id": prof["id"], "include_historical": True}).json()
    assert len(c["rows"]) == 1
    h = client.get("/api/premiums/history", params={"profile_id": prof["id"]}).json()
    assert h["series"][0]["points"][0]["annual_premium"] == 100


def _xlsx(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Premies 2022"
    ws.append(["Premievergelijking oldtimers"])  # titelregel boven de kop
    for r in rows:
        ws.append(r)
    ws2 = wb.create_sheet("Leeg")
    ws2.append(["x"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_excel_import_studio_full_flow(client):
    vet, comp, vp, cp = setup_providers(client)
    data = _xlsx([
        ["Maatschappij", "Product", "Auto", "Bouwjaar", "Verzekerde waarde", "Dekking", "Jaarpremie", "Eigen risico", "Datum", "Opmerking"],
        ["Testverzekeraar", "Test Oldtimer", "MG B", 1972, "€ 12.500", "WA + beperkt casco", "€ 145,50", 150, "15-03-2022", ""],
        ["Testverzekeraar", "Test Oldtimer", "MG B", 1972, "€ 12.500", "WA + beperkt casco", "€ 145,50", 150, "15-03-2022", "dubbel"],
        ["Onbekende BV", "X", "Volvo", 1880, 5000, "WA", "abc", None, "2022-03-15", ""],
        [None, "Y", "Saab", 1980, 6000, "WA", 99, 0, "2022-03-15", ""],
    ])
    up = client.post("/api/imports/upload", files={"file": ("premies.xlsx", data, "application/vnd.ms-excel")}).json()
    prev = up["preview"]
    assert prev["sheets"] == ["Premies 2022", "Leeg"]
    assert prev["header_row"] == 2                       # titelregel overgeslagen
    fields = {v["field"] for v in prev["mapping"].values()}
    assert {"provider", "product", "vehicle", "build_year", "insured_value", "coverage_variant", "amount",
            "deductible", "reference_date", "notes"} <= fields
    iid = up["import"]["id"]
    val = client.post(f"/api/imports/{iid}/validate", json={}).json()
    assert val["total"] == 4 and val["valid"] == 2 and val["duplicates"] == 1
    bad = {e["row"]: e["messages"] for e in val["errors"]}
    assert any("bouwjaar" in m.lower() for m in bad[5]) and any("bedrag" in m for m in bad[5])
    assert any("Verzekeraar ontbreekt" in m for m in bad[6])
    assert val["rows"][0]["values"]["amount"] == 145.5 and val["rows"][0]["values"]["insured_value"] == 12500
    # dubbele koppeling geweigerd
    m = {k: v["field"] for k, v in prev["mapping"].items()}
    m2 = dict(m)
    m2["1"] = "provider"
    assert client.post(f"/api/imports/{iid}/validate", json={"mapping": m2}).status_code == 422
    res = client.post(f"/api/imports/{iid}/commit", json={"save_template": "Mijn sjabloon"}).json()
    assert res["imported"] == 1
    obs = client.get("/api/premiums", params={"import_id": iid}).json()
    assert obs[0]["observation_type"] == "historisch_tarief" and obs[0]["is_historical"]
    assert obs[0]["provider_id"] == comp["id"] and obs[0]["product_id"] == cp["id"]
    assert client.post(f"/api/imports/{iid}/commit", json={}).status_code == 409
    # tweede import van hetzelfde bestand → waarschuwing en duplicaatdetectie t.o.v. database
    up2 = client.post("/api/imports/upload", files={"file": ("premies.xlsx", data, "application/vnd.ms-excel")}).json()
    assert up2["warning"]
    v2 = client.post(f"/api/imports/{up2['import']['id']}/validate", json={}).json()
    assert v2["duplicates"] == 2
    # sjabloon en terugdraaien
    assert client.get("/api/import-templates").json()[0]["name"] == "Mijn sjabloon"
    assert client.post(f"/api/imports/{iid}/rollback").json()["removed"] == 1


def test_csv_import_and_wrong_type(client):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["verzekeraar", "premie per jaar", "peildatum"])
    w.writerow(["ACME", "1.234,56", "01-02-2021"])
    up = client.post("/api/imports/upload", files={"file": ("p.csv", buf.getvalue().encode("cp1252"), "text/csv")}).json()
    val = client.post(f"/api/imports/{up['import']['id']}/validate", json={"treat_as": "actueel"}).json()
    assert val["valid"] == 1 and val["rows"][0]["values"]["amount"] == 1234.56
    assert client.post("/api/imports/upload", files={"file": ("p.docx", b"xx", "x")}).status_code == 422
    assert client.post("/api/imports/upload", files={"file": ("p.xlsx", b"geen excel", "x")}).status_code == 422


def test_calculator_permission_flow(client):
    vet, comp, vp, cp = setup_providers(client)
    c = client.post("/api/calculators", json={"name": "Calc", "provider_id": comp["id"], "url": "https://example.org"}).json()
    assert client.post(f"/api/calculators/{c['id']}/run").status_code == 409
    assert client.patch(f"/api/calculators/{c['id']}", json={"permission_status": "toegestaan"}).status_code == 422
    prof = client.get("/api/profiles").json()[0]
    m = client.post(f"/api/calculators/{c['id']}/manual", json={"profile_id": prof["id"], "amount": 321}).json()
    assert m["observation_type"] == "proefberekening" and m["is_actual_quote"] is False
    log = client.get("/api/calculators").json()[0]["log"]
    assert any(x["action"] == "handmatig_vastgelegd" for x in log)


def test_quality_checks(client):
    vet, comp, vp, cp = setup_providers(client)
    old = (date.today() - timedelta(days=500)).isoformat()
    o = client.post("/api/premiums", json={"provider_id": comp["id"], "amount": 100, "reference_date": old}).json()
    q = client.get("/api/quality").json()
    kinds = {i["kind"] for i in q["issues"]}
    assert "verouderde_premie" in kinds and "onvergelijkbare_premie" in kinds
    key = next(i["key"] for i in q["issues"] if i["kind"] == "verouderde_premie")
    client.post("/api/quality/resolve", json={"key": key})
    assert key not in {i["key"] for i in client.get("/api/quality").json()["issues"]}
    client.post(f"/api/premiums/{o['id']}/mark-historical")
    assert all(i["entity_id"] != o["id"] for i in client.get("/api/quality").json()["issues"] if i["entity"] == "premium")
