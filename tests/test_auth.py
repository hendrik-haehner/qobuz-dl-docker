import pytest
from fastapi.testclient import TestClient

from app import auth
from app.main import app


@pytest.fixture
def pw(env, monkeypatch):
    monkeypatch.setenv("WEB_PASSWORD", "geheim")
    monkeypatch.setattr("app.main.asyncio.sleep", _no_sleep)
    return env


async def _no_sleep(_):
    return None


def test_token_roundtrip_and_tampering(pw):
    cfg = pw["config"]
    token = auth.create_token(cfg)
    assert auth.valid_token(cfg, token)
    exp, nonce, sig = token.split(".")
    assert not auth.valid_token(cfg, f"{int(exp) + 999}.{nonce}.{sig}")
    assert not auth.valid_token(cfg, f"{exp}.{nonce}.{'0' * len(sig)}")
    assert not auth.valid_token(cfg, "kaputt")
    assert not auth.valid_token(cfg, None)
    # Schlüssel liegt mit 0600 im Config-Ordner und überlebt einen Neustart
    assert (cfg / "session.key").stat().st_mode & 0o777 == 0o600


def test_token_expires(pw):
    token = auth.create_token(pw["config"], now=1000)
    assert auth.valid_token(pw["config"], token, now=1000 + auth.SESSION_SECONDS - 1)
    assert not auth.valid_token(pw["config"], token, now=1000 + auth.SESSION_SECONDS + 1)


def test_password_change_invalidates_sessions(pw, monkeypatch):
    token = auth.create_token(pw["config"])
    monkeypatch.setenv("WEB_PASSWORD", "neu")
    assert not auth.valid_token(pw["config"], token)


def test_throttle(pw):
    for _ in range(auth.MAX_FAILURES):
        assert auth.check_password("falsch", now=100) is False
    with pytest.raises(auth.TooManyAttempts):
        auth.check_password("geheim", now=101)
    # nach Ablauf des Zeitfensters geht es wieder
    assert auth.check_password("geheim", now=100 + auth.FAILURE_WINDOW + 1) is True


def test_without_password_everything_open(env):
    with TestClient(app) as client:
        assert client.get("/api/status").json()["auth_enabled"] is False
        assert client.get("/login", follow_redirects=False).headers["location"] == "/"


def test_protected_without_login(pw):
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/static/style.css").status_code == 200
        for path in ("/api/status", "/api/account", "/api/settings", "/api/folders", "/api/downloads"):
            assert client.get(path).status_code == 401, path
        assert client.put("/api/account", json={"email": "a", "password": "b"}).status_code == 401
        assert client.delete("/api/account").status_code == 401
        for path in ("/", "/docs", "/openapi.json", "/static/app.js"):
            res = client.get(path, follow_redirects=False)
            assert (res.status_code, res.headers["location"]) == (303, "/login"), path
        assert "Passwort" in client.get("/login").text


def test_login_logout_flow(pw):
    with TestClient(app) as client:
        res = client.post("/api/login", json={"password": "falsch"})
        assert res.status_code == 401
        res = client.post("/api/login", json={"password": "geheim"})
        assert res.status_code == 204
        cookie = res.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert "secure" not in cookie  # TestClient spricht HTTP
        assert client.get("/api/status").json()["auth_enabled"] is True
        assert client.get("/login", follow_redirects=False).headers["location"] == "/"
        assert client.post("/api/logout").status_code == 204
        assert client.get("/api/status").status_code == 401


def test_secure_cookie_over_https(pw):
    with TestClient(app, base_url="https://nas.local") as client:
        res = client.post("/api/login", json={"password": "geheim"})
        assert "secure" in res.headers["set-cookie"].lower()


def test_login_rate_limited(pw):
    with TestClient(app) as client:
        for _ in range(auth.MAX_FAILURES):
            client.post("/api/login", json={"password": "falsch"})
        assert client.post("/api/login", json={"password": "geheim"}).status_code == 429
