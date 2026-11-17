import configparser
import stat

import pytest
import requests
from qobuz_dl.exceptions import InvalidAppSecretError

from app import qobuz_config
from app.qobuz_config import LoginError
from app.settings import get_settings
from app.token_auth import TokenError

GOOD = "gueltiger-token"


@pytest.fixture
def fake_qobuz(monkeypatch):
    """Ersetzt die Netzwerkaufrufe: nur GOOD ist ein gültiger Token."""
    calls = []
    monkeypatch.setattr(qobuz_config, "_fetch_tokens", lambda: ("123456789", ["s1", "s2"]))

    def verify(token, app_id, secrets):
        calls.append((token, app_id, secrets))
        if token == "frei":
            return {"token": "t", "email": "frei@b.c", "label": "", "can_download": False}
        if token != GOOD:
            raise TokenError("ungültig")
        return {"token": "frisch", "email": "a@b.c", "label": "Studio", "can_download": True}

    monkeypatch.setattr(qobuz_config, "_verify", verify)
    return calls


def test_build_config_matches_qobuz_dl_keys():
    cfg = qobuz_config.build_config(
        "a@b.c", "tok", "123456789", ["s1", "s2"],
        shares_dir="/shares", quality=27, folder_format="F", track_format="T",
    )
    d = cfg["DEFAULT"]
    assert d["password"] == "tok" and d["auth_method"] == "token"
    assert d["secrets"] == "s1,s2"
    assert d["default_quality"] == "27"
    # Diese Schlüssel liest qobuz_dl.cli.main() und bricht ab, wenn einer fehlt
    for key in ("default_folder", "default_limit", "no_m3u", "albums_only", "no_fallback",
                "og_cover", "embed_art", "no_cover", "no_database", "app_id",
                "smart_discography", "folder_format", "track_format"):
        assert key in d


def test_build_config_rejects_quality():
    with pytest.raises(ValueError):
        qobuz_config.build_config("a", "b", "1", [], shares_dir="/d", quality=3,
                                  folder_format="F", track_format="T")


def test_login_stores_refreshed_token(env, fake_qobuz):
    s = get_settings()
    res = qobuz_config.login(s, f"  {GOOD} ")
    assert res == {"configured": True, "email": "a@b.c", "auth_method": "token", "membership": "Studio"}
    assert fake_qobuz[0] == (GOOD, "123456789", ["s1", "s2"])
    cfg = configparser.ConfigParser()
    cfg.read(s.config_file)
    assert cfg["DEFAULT"]["password"] == "frisch"  # der von Qobuz erneuerte Token
    assert cfg["DEFAULT"]["auth_method"] == "token"
    assert stat.S_IMODE(s.config_file.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "token,msg",
    [
        ("falsch", "abgelehnt"),
        ("frei", "kein Download-Abo"),
        ("   ", "Token aus dem Browser"),
    ],
)
def test_login_errors_keep_existing_config(env, fake_qobuz, token, msg):
    s = get_settings()
    qobuz_config.login(s, GOOD)
    with pytest.raises(LoginError, match=msg):
        qobuz_config.login(s, token)
    assert qobuz_config.account(s)["email"] == "a@b.c"


@pytest.mark.parametrize(
    "exc,msg",
    [
        (requests.ConnectionError(), "nicht erreichbar"),
        (InvalidAppSecretError(), "App-Kennung"),
    ],
)
def test_login_maps_technical_errors(env, monkeypatch, exc, msg):
    def boom():
        raise exc
    monkeypatch.setattr(qobuz_config, "_fetch_tokens", boom)
    with pytest.raises(LoginError, match=msg):
        qobuz_config.login(get_settings(), "x")
    assert not get_settings().config_file.exists()


def test_account_reports_legacy_password_login(configured):
    # kopierte config.ini von qobuz-dl ohne auth_method
    assert qobuz_config.account(get_settings())["auth_method"] == "password"


def test_logout(env, fake_qobuz):
    s = get_settings()
    qobuz_config.login(s, GOOD)
    qobuz_config.logout(s)
    assert qobuz_config.account(s) == {"configured": False, "email": None, "auth_method": None}
    qobuz_config.logout(s)  # zweimal ist kein Fehler


def test_ensure_config_without_token(env, monkeypatch):
    monkeypatch.delenv("QOBUZ_TOKEN", raising=False)
    assert qobuz_config.ensure_config() is False
    assert not get_settings().config_file.exists()


def test_ensure_config_from_env(env, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_TOKEN", GOOD)
    assert qobuz_config.ensure_config() is True
    assert qobuz_config.account(get_settings())["email"] == "a@b.c"


def test_ensure_config_invalid_env_token(env, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_TOKEN", "falsch")
    assert qobuz_config.ensure_config() is False


def test_ensure_config_keeps_existing(configured, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_TOKEN", GOOD)
    assert qobuz_config.ensure_config() is True
    assert fake_qobuz == []
