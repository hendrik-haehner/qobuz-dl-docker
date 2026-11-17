import pytest
from pathvalidate import sanitize_filename, sanitize_filepath
from qobuz_dl.downloader import Download

from app import qdl_patches

META = {
    "artist": {"name": "AC/DC"},
    "release_date_original": "1980-07-25",
    "album": {"title": "Live/Dead", "artist": {"name": "AC/DC"}, "release_date_original": "1980-07-25"},
}
TRACK = {
    "maximum_bit_depth": 24, "maximum_sampling_rate": 96, "version": None, "track_number": 1,
    "album": {"artist": {"name": "AC/DC"}},
}


@pytest.fixture
def patched():
    originals = {n: Download.__dict__[n] for n in qdl_patches.NAME_HELPERS}
    qdl_patches.install_name_fix()
    yield
    for name, value in originals.items():
        setattr(Download, name, value)


def folder(attrs, pattern="{artist}/{album}"):
    # So setzt qobuz-dl den Ordner zusammen (downloader.py)
    return sanitize_filepath(pattern.format(**attrs))


def test_without_fix_slash_creates_extra_folders():
    attrs = Download._get_album_attr(META, "Back/In Black", "FLAC", 24, 96)
    assert folder(attrs) == "AC/DC/Back/In Black"


def test_album_folder(patched):
    attrs = Download._get_album_attr(META, "Back/In Black", "FLAC", 24, 96)
    assert folder(attrs) == "AC-DC/Back-In Black"
    assert (attrs["bit_depth"], attrs["year"]) == (24, "1980")  # Nicht-Text bleibt


def test_single_track_folder(patched):
    attrs = Download._get_track_attr(META, "T.N.T./Live", 24, 96)
    assert folder(attrs, "{artist}/{album} ({year})") == "AC-DC/Live-Dead (1980)"
    assert attrs["tracktitle"] == "T.N.T.-Live"


def test_filename(patched):
    attrs = Download._get_filename_attr("AC/DC", TRACK, "Highway to Hell / Live")
    name = sanitize_filename("{tracknumber}. {artist} - {tracktitle}".format(**attrs))
    assert name == "01. AC-DC - Highway to Hell - Live"
    assert attrs["version"] is None


def test_install_twice_wraps_once(patched):
    qdl_patches.install_name_fix()
    attrs = Download._get_album_attr(META, "A/B", "FLAC", 16, 44.1)
    assert attrs["album"] == "A-B"
    assert not hasattr(Download.__dict__["_get_album_attr"].__func__.__wrapped__, "__wrapped__")
