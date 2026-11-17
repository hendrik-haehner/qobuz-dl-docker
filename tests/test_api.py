from fastapi.testclient import TestClient

from app.main import app


def test_health_and_index():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert "qobuz-dl web" in client.get("/").text


def test_status_without_config(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/status").json()["configured"] is False


def _configure(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".config" / "qobuz-dl" / "config.ini"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("[DEFAULT]\n")


def test_reject_when_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": "https://open.qobuz.com/album/a"})
        assert res.status_code == 409


def test_reject_bad_url(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": "https://example.com/x"})
        assert res.status_code == 422


def test_create_and_list(tmp_path, monkeypatch):
    _configure(tmp_path, monkeypatch)
    monkeypatch.setenv("QOBUZ_DL_BIN", "true")
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": "https://open.qobuz.com/album/a"})
        assert res.status_code == 202
        job = res.json()
        assert job["quality"] == 6
        assert client.get(f"/api/downloads/{job['id']}").status_code == 200
        assert [j["id"] for j in client.get("/api/downloads").json()] == [job["id"]]
        assert client.get("/api/downloads/nope").status_code == 404
