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
        assert s["shares_dir"] == str(env["music"])
        assert "tracktitle" in s["placeholders"]["track"]


def test_reject_when_not_configured(env):
    with TestClient(app) as client:
        assert client.post("/api/downloads", json={"url": URL}).status_code == 409


def test_reject_bad_url(configured):
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": "https://example.com/x"})
        assert res.status_code == 422


def test_settings_roundtrip(env):
    (env["music"] / "music" / "Hi-Res").mkdir(parents=True)
    with TestClient(app) as client:
        assert client.get("/api/settings").json()["format"] == "flac"
        assert client.put("/api/settings", json={"target_dir": "Video"}).status_code == 422
        new = {"format": "flac", "quality": 27, "target_dir": "music/Hi-Res",
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
    (env["music"] / "music").mkdir()
    with TestClient(app) as client:
        root = client.get("/api/folders").json()
        assert root["is_root"] and root["dirs"] == ["music"]
        # Freigaben entstehen nur über docker-compose, nicht im Webinterface
        assert client.post("/api/folders", json={"parent": "", "name": "Klassik"}).status_code == 422
        res = client.post("/api/folders", json={"parent": "music", "name": "Klassik"})
        assert res.status_code == 201 and res.json() == {"path": "music/Klassik"}
        assert client.get("/api/folders", params={"path": "music"}).json()["dirs"] == ["Klassik"]
        assert client.get("/api/folders", params={"path": ".."}).status_code == 404
        assert client.post("/api/folders", json={"parent": "music", "name": "../x"}).status_code == 422


def test_download_uses_saved_defaults_and_overrides(configured, monkeypatch):
    monkeypatch.setenv("QOBUZ_DL_BIN", write_fake_bin(configured["home"].parent))
    (configured["music"] / "music").mkdir()
    (configured["music"] / "Downloads").mkdir()
    with TestClient(app) as client:
        assert client.put("/api/settings", json={"format": "mp3", "target_dir": "music/MP3"}).status_code == 200
        job = client.post("/api/downloads", json={"url": URL}).json()
        assert (job["format"], job["target_dir"]) == ("mp3", "music/MP3")
        job2 = client.post("/api/downloads", json={"url": URL, "format": "flac", "quality": 7,
                                                   "target_dir": "Downloads/Hi-Res"}).json()
        assert (job2["format"], job2["quality"], job2["target_dir"]) == ("flac", 7, "Downloads/Hi-Res")
        # direkt in /shares oder in eine nicht eingebundene Freigabe: abgelehnt
        assert client.post("/api/downloads", json={"url": URL, "target_dir": "Video"}).status_code == 422
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


def test_account_flow(env, monkeypatch):
    monkeypatch.setattr("app.qobuz_config._fetch_tokens", lambda: ("123456789", ["s"]))

    def verify(email, pwd_md5, app_id, secrets):
        from qobuz_dl.exceptions import AuthenticationError
        if pwd_md5 != __import__("hashlib").md5(b"richtig").hexdigest():
            raise AuthenticationError()
        return "Studio"

    monkeypatch.setattr("app.qobuz_config._verify", verify)
    with TestClient(app) as client:
        assert client.get("/api/account").json() == {"configured": False, "email": None}
        res = client.put("/api/account", json={"email": "a@b.c", "password": "falsch"})
        assert res.status_code == 422 and "falsch" in res.json()["detail"]
        res = client.put("/api/account", json={"email": "a@b.c", "password": "richtig"})
        assert res.json() == {"configured": True, "email": "a@b.c", "membership": "Studio"}
        status = client.get("/api/status").json()
        assert (status["configured"], status["email"]) == (True, "a@b.c")
        # Passwort/Hash wird nirgends ausgeliefert
        for path in ("/api/account", "/api/status"):
            body = client.get(path).text
            assert "richtig" not in body and "password" not in body
        assert client.delete("/api/account").status_code == 204
        assert client.get("/api/account").json()["configured"] is False
        assert client.post("/api/downloads", json={"url": URL}).status_code == 409


def test_download_without_target_uses_single_share(configured, monkeypatch):
    monkeypatch.setenv("QOBUZ_DL_BIN", write_fake_bin(configured["home"].parent))
    with TestClient(app) as client:
        res = client.post("/api/downloads", json={"url": URL})
        assert res.status_code == 422 and "Freigabe wählen" in res.json()["detail"]
        (configured["music"] / "music").mkdir()
        assert client.post("/api/downloads", json={"url": URL}).json()["target_dir"] == "music"


def test_redownload_only_for_this_job(configured, monkeypatch):
    monkeypatch.setenv("QOBUZ_DL_BIN", write_fake_bin(configured["home"].parent))
    (configured["music"] / "music").mkdir()
    with TestClient(app) as client:
        job = client.post("/api/downloads", json={"url": URL, "redownload": True}).json()
        assert job["redownload"] is True and job["status"] in ("queued", "running")
        assert "redownload" not in client.get("/api/settings").json()
        assert client.post("/api/downloads", json={"url": URL}).json()["redownload"] is False
