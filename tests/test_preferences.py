import pytest
from pydantic import ValidationError

from app import preferences
from app.preferences import Preferences, qobuz_quality
from app.settings import Settings


def test_quality_mapping():
    assert qobuz_quality("mp3", 27) == 5
    assert qobuz_quality("flac", 7) == 7


@pytest.mark.parametrize("folder", ["{artist}/{album} ({year})", "Musik {year}", "{artist} - {album} [{bit_depth}B]"])
def test_valid_folder_patterns(folder):
    assert Preferences(folder_format=folder).folder_format == folder


@pytest.mark.parametrize(
    "field,value",
    [
        ("folder_format", "{tracktitle}"),         # nur bei Titeln bekannt → KeyError in qobuz-dl
        ("folder_format", "{format}"),             # fehlt bei Einzeltiteln
        ("folder_format", "/abs/{artist}"),
        ("folder_format", "{artist}/../x"),
        ("folder_format", "{artist"),
        ("folder_format", "{}"),
        ("folder_format", "a:b"),
        ("folder_format", "   "),
        ("track_format", "{artist}/{tracktitle}"),
        ("track_format", "{album}"),
        ("format", "alac"),
        ("quality", 5),
        ("target_dir", "a/../../etc"),
    ],
)
def test_invalid_values(field, value):
    with pytest.raises(ValidationError):
        Preferences(**{field: value})


def test_target_dir_normalized():
    assert Preferences(target_dir="/Musik/Hi-Res/").target_dir == "Musik/Hi-Res"


def _settings(tmp_path, q=6):
    return Settings(shares_dir=tmp_path, config_dir=tmp_path / "cfg", qobuz_dl_bin="x", default_quality=q)


def test_load_defaults_from_env_quality(tmp_path):
    assert preferences.load(_settings(tmp_path, 5)).format == "mp3"
    p = preferences.load(_settings(tmp_path, 27))
    assert (p.format, p.quality) == ("flac", 27)


def test_save_and_load_roundtrip(tmp_path):
    s = _settings(tmp_path)
    prefs = Preferences(format="mp3", quality=7, target_dir="NAS/Musik", folder_format="{artist}/{album}")
    preferences.save(s, prefs)
    assert preferences.load(s) == prefs


def test_corrupt_file_falls_back(tmp_path):
    s = _settings(tmp_path)
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "web-settings.json").write_text("{kaputt")
    assert preferences.load(s) == Preferences()
