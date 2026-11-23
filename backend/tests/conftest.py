"""Testopzet. Alle tests gebruiken een tijdelijke, synthetische datamap die strikt
gescheiden is van productiegegevens. Synthetische data in tests is fictief."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("VETERA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("VETERA_ANTHROPIC_API_KEY", "")
    from app import config, db
    config.get_settings.cache_clear()
    db.reset_engine()
    from app.main import app
    with TestClient(app) as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


SAMPLE_POLICY = """TESTVERZEKERAAR BV - Polisvoorwaarden Klassieke Auto
Versie TST-2024-01  januari 2024
Artikel 1 Begripsomschrijvingen
In deze voorwaarden verstaan wij onder voertuig: een personenauto van minimaal 25 jaar oud.
Artikel 2 Dekking
2.1 Brand
Schade door brand, ontploffing en kortsluiting is verzekerd.
2.2 Diefstal
Diefstal van het voertuig is verzekerd mits het voertuig in een afgesloten garage is gestald.
Artikel 3 Uitsluitingen
Schade tijdens deelname aan wedstrijden op een circuit is uitgesloten.
Artikel 4 Eigen risico
Het eigen risico bedraagt EUR 150 per gebeurtenis.
\fArtikel 5 Buitenland
De verzekering geldt in alle landen van Europa.
"""


def make_pdf(text: str = SAMPLE_POLICY) -> bytes:
    from app.services.documents import pdf_bytes_from_text
    return pdf_bytes_from_text(text)


def setup_providers(client):
    vet = [p for p in client.get("/api/providers").json() if p["is_reference"]][0]
    comp = client.post("/api/providers", json={"name": "Testverzekeraar", "provider_type": "verzekeraar"}).json()
    vp = client.post("/api/products", json={"provider_id": vet["id"], "name": "Vetera Klassiek", "vehicle_category": "auto"}).json()
    cp = client.post("/api/products", json={"provider_id": comp["id"], "name": "Test Oldtimer", "vehicle_category": "auto"}).json()
    return vet, comp, vp, cp
