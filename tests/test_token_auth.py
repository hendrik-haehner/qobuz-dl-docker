"""Token-Anmeldung gegen eine nachgebaute Qobuz-API (ohne Netzwerk)."""

import configparser
import stat

import pytest
from qobuz_dl import qopy
from qobuz_dl.exceptions import AuthenticationError, InvalidAppIdError, InvalidAppSecretError

from app import qdl_runner, token_auth

GOOD, FRESH = "alter-token", "frischer-token"


class Resp:
    def __init__(self, status, data=None):
        self.status_code, self._data = status, data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class FakeQobuz:
    """Verhält sich wie www.qobuz.com/api.json für die Aufrufe von qobuz-dl."""

    def __init__(self, login_status=200, params=True, secret_ok=True):
        self.headers = {}
        self.login_status, self.params, self.secret_ok = login_status, params, secret_ok
        self.posts = []

    def post(self, url, data=None, timeout=None):
        self.posts.append((url, dict(data or {}), dict(self.headers)))
        if self.login_status != 200:
            return Resp(self.login_status)
        if self.headers.get("X-User-Auth-Token") != GOOD:
            return Resp(401)
        params = {"short_label": "Studio", "lossless_streaming": True} if self.params else None
        return Resp(200, {
            "user_auth_token": FRESH,
            "user": {"email": "ich@example.com", "credential": {"parameters": params}},
        })

    def get(self, url, params=None):
        # cfg_setup() testet die App-Secrets mit track/getFileUrl
        assert url.endswith("track/getFileUrl")
        assert self.headers.get("X-User-Auth-Token") == FRESH
        return Resp(200 if self.secret_ok else 400, {"url": "x"})


@pytest.fixture
def api(monkeypatch):
    holder = {}

    def factory(**kw):
        fake = FakeQobuz(**kw)
        holder["fake"] = fake
        monkeypatch.setattr(qopy.requests, "Session", lambda: fake)
        return fake

    monkeypatch.setattr(token_auth, "on_token_refreshed", None)
    original = qopy.Client.auth
    yield factory
    qopy.Client.auth = original


def test_refresh_sends_token_and_returns_account(api):
    fake = api()
    info = token_auth.refresh(fake, f"  {GOOD} ")
    url, data, headers = fake.posts[0]
    assert url == token_auth.BASE + "user/login"
    assert data == {"extra": "partner"}
    assert headers["X-User-Auth-Token"] == GOOD
    assert info == {"token": FRESH, "email": "ich@example.com", "label": "Studio", "can_download": True}


@pytest.mark.parametrize("status,exc", [(401, token_auth.TokenError), (400, InvalidAppIdError)])
def test_refresh_errors(api, status, exc):
    with pytest.raises(exc):
        token_auth.refresh(api(login_status=status), GOOD)


def test_refresh_rejects_empty_token(api):
    with pytest.raises(token_auth.TokenError):
        token_auth.refresh(api(), "   ")


def test_login_runs_qobuz_dl_client_with_token(api):
    api()
    info = token_auth.login(GOOD, "123456789", ["secret"])
    assert info["token"] == FRESH and info["can_download"]


def test_login_wrong_token_raises_qobuz_dl_error(api):
    api()
    with pytest.raises(AuthenticationError, match="Token ungültig oder abgelaufen"):
        token_auth.login("falsch", "123456789", ["secret"])


def test_login_bad_secret(api):
    api(secret_ok=False)
    with pytest.raises(InvalidAppSecretError):
        token_auth.login(GOOD, "123456789", ["secret"])


def test_refreshed_token_is_reported(api, monkeypatch):
    api()
    seen = []
    monkeypatch.setattr(token_auth, "on_token_refreshed", seen.append)
    token_auth.login(GOOD, "123456789", ["secret"])
    assert seen == [FRESH]


def test_runner_saves_token_only(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[DEFAULT]\nemail = ich@example.com\npassword = alt\nauth_method = token\napp_id = 1\n")
    assert qdl_runner.auth_method(str(cfg)) == "token"
    qdl_runner.save_token(str(cfg), FRESH)
    c = configparser.ConfigParser()
    c.read(cfg)
    assert c["DEFAULT"]["password"] == FRESH
    assert c["DEFAULT"]["email"] == "ich@example.com" and c["DEFAULT"]["app_id"] == "1"
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600


def test_runner_legacy_config_keeps_password_login(tmp_path):
    cfg = tmp_path / "config.ini"
    cfg.write_text("[DEFAULT]\nemail = a\npassword = 0123abcd\n")
    assert qdl_runner.auth_method(str(cfg)) == "password"


def test_runner_runs_real_qobuz_dl_cli_with_token(api, tmp_path, monkeypatch):
    """Ganzer Ablauf von qobuz-dl: config.ini lesen, mit Token anmelden,
    frischen Token speichern, URL an den Downloader übergeben."""
    from qobuz_dl import cli, core

    from app.qobuz_config import build_config

    api()
    cfg_dir = tmp_path / "qobuz-dl"
    cfg_dir.mkdir()
    cfg_file = cfg_dir / "config.ini"
    with open(cfg_file, "w") as fh:
        build_config("ich@example.com", GOOD, "123456789", ["secret"], shares_dir=str(tmp_path),
                     quality=6, folder_format="{artist}", track_format="{tracktitle}").write(fh)
    monkeypatch.setattr(cli, "CONFIG_PATH", str(cfg_dir))
    monkeypatch.setattr(cli, "CONFIG_FILE", str(cfg_file))
    monkeypatch.setattr(cli, "QOBUZ_DB", str(cfg_dir / "qobuz_dl.db"))
    seen = {}

    def fake_download(self, urls):
        seen.update(urls=urls, uat=self.client.uat, quality=self.quality, directory=self.directory)

    monkeypatch.setattr(core.QobuzDL, "download_list_of_urls", fake_download)
    url = "https://open.qobuz.com/album/abc"
    monkeypatch.setattr("sys.argv", ["python", "dl", url, "-q", "27", "-d", str(tmp_path / "out")])
    qdl_runner.main()

    assert seen == {"urls": [url], "uat": FRESH, "quality": "27", "directory": str(tmp_path / "out")}
    c = configparser.ConfigParser()
    c.read(cfg_file)
    assert c["DEFAULT"]["password"] == FRESH  # erneuerter Token gespeichert
