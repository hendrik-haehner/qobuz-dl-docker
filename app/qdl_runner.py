"""Startet qobuz-dl mit Token-Anmeldung (Aufruf: python -m app.qdl_runner dl URL ...).

Verhält sich wie das Programm `qobuz-dl`, nur die Anmeldung läuft über den
Browser-Token (siehe app/token_auth.py). Den bei jedem Lauf erneuerten Token
schreibt der Runner zurück in config.ini, damit die Anmeldung gültig bleibt.
"""

import configparser
import os
import sys

from qobuz_dl import cli

from app import token_auth


def auth_method(config_file: str) -> str:
    config = configparser.ConfigParser()
    config.read(config_file)
    return config["DEFAULT"].get("auth_method", "password")


def save_token(config_file: str, token: str) -> None:
    """Nur das Passwortfeld (= Token) ersetzen, Rechte 0600, atomar."""
    config = configparser.ConfigParser()
    config.read(config_file)
    config["DEFAULT"]["password"] = token
    tmp = config_file + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as fh:
        config.write(fh)
    os.replace(tmp, config_file)


def main() -> None:
    if os.path.isfile(cli.CONFIG_FILE) and auth_method(cli.CONFIG_FILE) == "token":
        token_auth.install()
        token_auth.on_token_refreshed = lambda t: save_token(cli.CONFIG_FILE, t)
    sys.argv[0] = "qobuz-dl"
    cli.main()


if __name__ == "__main__":
    main()
