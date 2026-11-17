import configparser
import hashlib
import stat

import pytest
import requests
from qobuz_dl.exceptions import AuthenticationError, IneligibleError, InvalidAppSecretError

from app import qobuz_config
from app.qobuz_config import LoginError
from app.settings import get_settings


@pytest.fixture
def fake_qobuz(monkeypatch):
    """Ersetzt die Netzwerkaufrufe: Passwort 'richtig' ist korrekt."""
    calls = []
    monkeypatch.setattr(qobuz_config, "_fetch_tokens", lambda: ("123456789", ["s1", "s2"]))

    def verify(email, pwd_md5, app_id, secrets):
        calls.append((email, pwd_md5, app_id, secrets))
        if email == "frei@b.c":
            raise IneligibleError()
        if pwd_md5 != hashlib.md5(b"richtig").hexdigest():
            raise AuthenticationError()
        return "Studio"

    monkeypatch.setattr(qobuz_config, "_verify", verify)
    return calls


def test_build_config_matches_qobuz_dl_keys():
    cfg = qobuz_config.build_config(
        "a@b.c", "geheim", "123456789", ["s1", "s2"],
        shares_dir="/downloads", quality=27, folder_format="F", track_format="T",
    )
    d = cfg["DEFAULT"]
    assert d["password"] == hashlib.md5(b"geheim").hexdigest()
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


def test_login_writes_config_only_hash(env, fake_qobuz):
    s = get_settings()
    res = qobuz_config.login(s, "  a@b.c ", "richtig")
    assert res == {"configured": True, "email": "a@b.c", "membership": "Studio"}
    text = s.config_file.read_text()
    assert "richtig" not in text
    cfg = configparser.ConfigParser()
    cfg.read(s.config_file)
    assert cfg["DEFAULT"]["password"] == hashlib.md5(b"richtig").hexdigest()
    assert cfg["DEFAULT"]["app_id"] == "123456789"
    assert stat.S_IMODE(s.config_file.stat().st_mode) == 0o600
    assert fake_qobuz[0][0] == "a@b.c"


@pytest.mark.parametrize(
    "email,password,msg",
    [
        ("a@b.c", "falsch", "falsch"),
        ("frei@b.c", "richtig", "kostenloses Konto"),
        ("", "richtig", "angeben"),
        ("a@b.c", "", "angeben"),
    ],
)
def test_login_errors_keep_existing_config(env, fake_qobuz, email, password, msg):
    s = get_settings()
    qobuz_config.login(s, "alt@b.c", "richtig")
    with pytest.raises(LoginError, match=msg):
        qobuz_config.login(s, email, password)
    assert qobuz_config.account(s)["email"] == "alt@b.c"


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
        qobuz_config.login(get_settings(), "a@b.c", "x")
    assert not get_settings().config_file.exists()


def test_logout(env, fake_qobuz):
    s = get_settings()
    qobuz_config.login(s, "a@b.c", "richtig")
    qobuz_config.logout(s)
    assert qobuz_config.account(s) == {"configured": False, "email": None}
    qobuz_config.logout(s)  # zweimal ist kein Fehler


def test_ensure_config_without_credentials(env, monkeypatch):
    monkeypatch.delenv("QOBUZ_EMAIL", raising=False)
    monkeypatch.delenv("QOBUZ_PASSWORD", raising=False)
    assert qobuz_config.ensure_config() is False
    assert not get_settings().config_file.exists()


def test_ensure_config_from_env(env, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_EMAIL", "a@b.c")
    monkeypatch.setenv("QOBUZ_PASSWORD", "richtig")
    assert qobuz_config.ensure_config() is True
    assert qobuz_config.account(get_settings())["email"] == "a@b.c"


def test_ensure_config_wrong_env_password(env, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_EMAIL", "a@b.c")
    monkeypatch.setenv("QOBUZ_PASSWORD", "falsch")
    assert qobuz_config.ensure_config() is False


def test_ensure_config_keeps_existing(configured, fake_qobuz, monkeypatch):
    monkeypatch.setenv("QOBUZ_EMAIL", "neu@b.c")
    monkeypatch.setenv("QOBUZ_PASSWORD", "richtig")
    assert qobuz_config.ensure_config() is True
    assert fake_qobuz == []
