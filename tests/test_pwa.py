"""Als App auf dem iPhone-Home-Bildschirm (PWA)."""

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client(env, monkeypatch):
    # Mit Zugangsschutz: iOS holt Manifest und Icon ohne Session-Cookie
    monkeypatch.setenv("WEB_PASSWORD", "geheim")
    with TestClient(app) as c:
        yield c


def test_manifest_public(client):
    res = client.get("/manifest.webmanifest")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/manifest+json")
    m = json.loads(res.text)
    assert m["display"] == "standalone" and m["start_url"] == "/"
    for icon in m["icons"]:
        r = client.get(icon["src"])
        assert r.status_code == 200 and r.content.startswith(b"\x89PNG"), icon["src"]


@pytest.mark.parametrize("path", ["/apple-touch-icon.png", "/apple-touch-icon-precomposed.png"])
def test_apple_touch_icon_public(client, path):
    res = client.get(path)
    assert res.status_code == 200 and res.headers["content-type"] == "image/png"


def test_other_static_files_still_protected(client):
    assert client.get("/static/app.js", follow_redirects=False).status_code == 303


@pytest.mark.parametrize("page", ["/login", "/"])
def test_pages_link_manifest_and_ios_tags(env, page):
    with TestClient(app) as c:  # ohne Passwort, damit "/" direkt erreichbar ist
        html = c.get(page).text
    for tag in ('rel="manifest"', 'rel="apple-touch-icon"', 'apple-mobile-web-app-capable',
                'viewport-fit=cover'):
        assert tag in html, (page, tag)
