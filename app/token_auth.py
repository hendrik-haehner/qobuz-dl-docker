"""Qobuz-Anmeldung mit Browser-Token statt E-Mail/Passwort.

Seit April 2026 nimmt Qobuz an seiner API keine Anmeldung mit E-Mail und
Passwort mehr an (der Web-Player nutzt jetzt OAuth mit reCAPTCHA), siehe
https://github.com/vitiko98/qobuz-dl/issues/329. qobuz-dl wird nicht mehr
gepflegt. Stattdessen nehmen wir den `user_auth_token` aus einer angemeldeten
Browser-Sitzung: `POST user/login` mit `extra=partner` und dem Token im Header
`X-User-Auth-Token` liefert die Kontodaten und einen frischen Token.

`install()` ersetzt die Login-Methode von qobuz-dl (`qopy.Client.auth`), der
Rest von qobuz-dl bleibt unverändert. In `config.ini` steht dann statt des
Passwort-Hashes der Token und `auth_method = token`.
"""

import logging
from collections.abc import Callable

from qobuz_dl import qopy
from qobuz_dl.exceptions import AuthenticationError, InvalidAppIdError

log = logging.getLogger(__name__)

BASE = "https://www.qobuz.com/api.json/0.2/"
TIMEOUT = 30
TOKEN_INVALID = "Qobuz-Token ungültig oder abgelaufen"

# Wird mit dem frischen Token aufgerufen (der Runner speichert ihn in config.ini)
on_token_refreshed: Callable[[str], None] | None = None


class TokenError(Exception):
    pass


def refresh(session, token: str) -> dict:
    """Meldet sich mit dem Token an. Gibt frischen Token und Kontodaten zurück."""
    token = token.strip()
    if not token:
        raise TokenError("Kein Token angegeben.")
    session.headers["X-User-Auth-Token"] = token
    r = session.post(BASE + "user/login", data={"extra": "partner"}, timeout=TIMEOUT)
    if r.status_code == 401:
        raise TokenError(TOKEN_INVALID)
    if r.status_code == 400:
        raise InvalidAppIdError("Qobuz hat die App-Kennung abgelehnt.")
    r.raise_for_status()
    data = r.json()
    user = data.get("user") or {}
    credential = user.get("credential") or {}
    params = credential.get("parameters") or {}
    return {
        "token": data.get("user_auth_token") or token,
        "email": user.get("email") or user.get("login") or "",
        "label": params.get("short_label") or credential.get("label")
        or credential.get("description") or "",
        "can_download": bool(params),
    }


def _auth(self, email, pwd):
    """Ersatz für qopy.Client.auth: `pwd` enthält den Token aus config.ini."""
    try:
        info = refresh(self.session, pwd)
    except TokenError as exc:
        # qobuz-dl erwartet diese Exception; der Text landet im Job-Log
        raise AuthenticationError(
            f"{exc}. Im Webinterface unter „Qobuz-Konto“ einen neuen Token eintragen."
        ) from exc
    self.uat = info["token"]
    self.session.headers["X-User-Auth-Token"] = self.uat
    self.label = info["label"] or "unbekannt"
    self.account = info
    if not info["can_download"]:
        log.warning("Qobuz meldet kein Download-Abo (%s).", self.label)
    log.info("Angemeldet (%s)", self.label)
    if on_token_refreshed and info["token"] != pwd:
        on_token_refreshed(info["token"])


def install() -> None:
    qopy.Client.auth = _auth


def login(token: str, app_id: str, secrets: list[str]) -> dict:
    """Anmeldung prüfen wie bei einem Download, inklusive Test der App-Secrets."""
    install()
    client = qopy.Client("", token, app_id, secrets)  # ruft auth() und cfg_setup()
    return client.account
