"""Online modus (bijv. Render): alles achter een wachtwoord, en dicht als dat niet is ingesteld."""
import pytest
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch, **env):
    monkeypatch.setenv("VETERA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("VETERA_ALLOW_REMOTE_ACCESS", "true")
    for k in ("VETERA_APP_PASSWORD", "VETERA_SESSION_SECRET"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from app import auth, config, db
    config.get_settings.cache_clear()
    db.reset_engine()
    auth._attempts.clear()
    from app.main import app
    # base_url met https zodat de Secure-cookie wordt meegestuurd
    return TestClient(app, base_url="https://vetera.example.com")


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from app import config, db
    db.reset_engine()
    config.get_settings.cache_clear()


def test_cloud_without_password_is_closed(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch) as c:
        assert c.get("/api/health").status_code == 200
        assert c.get("/api/dashboard").status_code == 503
        assert c.get("/api/auth/status").json()["configured"] is False


def test_cloud_login_flow(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, VETERA_APP_PASSWORD="geheim-wachtwoord", VETERA_SESSION_SECRET="x" * 32) as c:
        assert c.get("/api/dashboard").status_code == 401
        assert c.get("/api/document-versions/1/file").status_code == 401
        assert c.get("/api/auth/status").json() == {"cloud": True, "required": True, "configured": True, "authenticated": False}
        assert c.post("/api/auth/login", json={"password": "fout"}).status_code == 401
        r = c.post("/api/auth/login", json={"password": "geheim-wachtwoord"})
        assert r.status_code == 200 and "vi_session" in r.cookies
        assert "httponly" in r.headers["set-cookie"].lower() and "secure" in r.headers["set-cookie"].lower()
        assert c.get("/api/dashboard").status_code == 200
        assert c.get("/api/auth/status").json()["authenticated"] is True
        assert "Strict-Transport-Security" in c.get("/api/health").headers
        c.post("/api/auth/logout")
        c.cookies.clear()
        assert c.get("/api/dashboard").status_code == 401


def test_forged_cookie_and_rate_limit(tmp_path, monkeypatch):
    with _client(tmp_path, monkeypatch, VETERA_APP_PASSWORD="geheim-wachtwoord", VETERA_SESSION_SECRET="y" * 32) as c:
        c.cookies.set("vi_session", "9999999999.vervalst", domain="vetera.example.com")
        assert c.get("/api/dashboard").status_code == 401
        c.cookies.clear()
        codes = [c.post("/api/auth/login", json={"password": f"fout{i}"}).status_code for i in range(9)]
        assert codes[-1] == 429
        assert c.post("/api/auth/login", json={"password": "geheim-wachtwoord"}).status_code == 429
