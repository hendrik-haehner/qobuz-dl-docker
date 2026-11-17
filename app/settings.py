"""Zentrale Einstellungen, alle per Umgebungsvariable überschreibbar."""

import os
from dataclasses import dataclass, field
from pathlib import Path


def _default_config_dir() -> Path:
    # qobuz-dl liest seine Konfiguration aus $HOME/.config/qobuz-dl
    return Path(os.environ.get("HOME", "/home/app")) / ".config" / "qobuz-dl"


@dataclass(frozen=True)
class Settings:
    shares_dir: Path = field(
        default_factory=lambda: Path(os.environ.get("SHARES_DIR", "/shares"))
    )
    config_dir: Path = field(default_factory=_default_config_dir)
    qobuz_dl_bin: str = field(
        default_factory=lambda: os.environ.get("QOBUZ_DL_BIN", "qobuz-dl")
    )
    default_quality: int = field(
        default_factory=lambda: int(os.environ.get("QOBUZ_DEFAULT_QUALITY", "6"))
    )

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.ini"


def get_settings() -> Settings:
    return Settings()
