from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import write_fake_bin

URL = "https://open.qobuz.com/album/a"


def test_health_and_index(env):
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert "qobuz-dl web" in client.get("/").text


def test_status(env):
    with TestClient(app) as client:
        s = client.get("/api/status").json()
        assert s["configured"] is False
        assert s["download_dir"] == str(env["music"])
        assert "tracktitle" in s["placeholders"]["track"]


def test_reject_when_not_configured(env):
    with TestClient(app) as client:
        assert client.post("/api/downloads", json={"url": URL}).status_code == 409


def test_reject_bad_url(configured):
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": "https://example.com/x"})
        assert res.status_code == 422


def test_settings_roundtrip(env):
    (env["music"] / "Hi-Res").mkdir()
    with TestClient(app) as client:
        assert client.get("/api/settings").json()["format"] == "flac"
        new = {"format": "flac", "quality": 27, "target_dir": "Hi-Res",
               "folder_format": "{artist}/{album} ({year})", "track_format": "{tracknumber}. {tracktitle}"}
        assert client.put("/api/settings", json=new).json() == new
        assert client.get("/api/settings").json() == new
    assert (env["config"] / "web-settings.json").is_file()


def test_settings_rejects_invalid(env):
    with TestClient(app) as client:
        res = client.put("/api/settings", json={"folder_format": "{tracktitle}"})
        assert res.status_code == 422
        assert "tracktitle" in res.json()["detail"]
        res = client.put("/api/settings", json={"target_dir": "../x"})
        assert res.status_code == 422


def test_folders_browse_and_create(env):
    with TestClient(app) as client:
        assert client.get("/api/folders").json()["dirs"] == []
        res = client.post("/api/folders", json={"parent": "", "name": "Klassik"})
        assert res.status_code == 201 and res.json() == {"path": "Klassik"}
        assert client.get("/api/folders").json()["dirs"] == ["Klassik"]
        assert client.get("/api/folders", params={"path": ".."}).status_code == 404
        assert client.post("/api/folders", json={"name": "../x"}).status_code == 422


def test_download_uses_saved_defaults_and_overrides(configured, monkeypatch):
    monkeypatch.setenv("QOBUZ_DL_BIN", write_fake_bin(configured["home"].parent))
    with TestClient(app) as client:
        client.put("/api/settings", json={"format": "mp3", "target_dir": "MP3"})
        job = client.post("/api/downloads", json={"url": URL}).json()
        assert (job["format"], job["target_dir"]) == ("mp3", "MP3")
        job2 = client.post("/api/downloads", json={"url": URL, "format": "flac", "quality": 7,
                                                   "target_dir": "Hi-Res"}).json()
        assert (job2["format"], job2["quality"], job2["target_dir"]) == ("flac", 7, "Hi-Res")
        assert client.post("/api/downloads", json={"url": URL, "quality": 9}).status_code == 422
        assert client.get(f"/api/downloads/{job['id']}").status_code == 200
        assert client.get("/api/downloads/nope").status_code == 404


def test_settings_save_error_is_reported(env, monkeypatch):
    def boom(*a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr("app.preferences.save", boom)
    with TestClient(app) as client:
        res = client.put("/api/settings", json={"format": "mp3"})
        assert res.status_code == 500
        assert "Schreibrechte" in res.json()["detail"]
