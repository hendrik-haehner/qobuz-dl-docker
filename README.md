# qobuz-dl-docker

Docker-App mit Webinterface für das Terminalprogramm
[qobuz-dl](https://github.com/vitiko98/qobuz-dl). Im Browser gibst du eine Qobuz-URL
ein, der Container lädt sie mit `qobuz-dl dl` auf dein NAS und zeigt die Ausgabe live an.

- **Zugangsschutz** per Passwort (`WEB_PASSWORD`)
- **Qobuz-Konto** im Webinterface hinterlegen (Token aus dem Browser, siehe
  „Qobuz-Anmeldung“), direkt bei Qobuz geprüft
- **Speicherort:** NAS-Freigabe und Unterordner wählen, neue Ordner anlegen
- **Format** FLAC oder MP3 320, **Qualität** CD 16/44,1 · Hi-Res 24/96 · Hi-Res 24/192
  (fehlt ein Album in der Qualität, nimmt qobuz-dl die nächstbeste)
- **Ordner- und Dateinamen** als Muster wie `{artist}/{album} ({year})`, mit Vorschau
- alles pro Download oder als gespeicherter Standard

## Auf einer Synology installieren

GitHub baut das Image bei jeder Änderung automatisch, für Intel/AMD- und ARM-Modelle:
`ghcr.io/hendrik-haehner/qobuz-dl-docker:latest`. Aufs NAS kommen nur zwei Dateien,
kein Programmcode. Beschrieben für DSM 7.2 mit Container Manager.

**1. Ordner und Dateien anlegen**

1. Im Paket-Zentrum **Container Manager** und **Text Editor** installieren.
2. In der File Station den Ordner `docker/qobuz-dl-web` anlegen, darin einen leeren Ordner `config`.
3. Darin zwei Dateien anlegen (Text Editor → Neu, Inhalt von GitHub hineinkopieren):
   - `docker-compose.yml`: unter `volumes:` deine Freigaben eintragen, z. B.
     `- /volume1/music:/shares/music` (links NAS-Pfad, rechts Name im Webinterface).
     Den NAS-Pfad zeigt die File Station unter „Eigenschaften“ → „Ort“.
   - `.env` (Vorlage: `.env.example`): mindestens
     ```bash
     WEB_PASSWORD=ein-langes-passwort
     PUID=1026
     PGID=100
     ```
     `PUID`/`PGID` ist der DSM-Benutzer, dem die Downloads gehören sollen
     (herausfinden: siehe „Benutzer-ID ohne Terminal“ unten). Er braucht Lese-/Schreibrechte
     auf die Freigaben und den Ordner `config`. Port ändern: `WEB_PORT=8095`.

**2. Einmalig: Zugriff auf das private Image**

Solange das Repository privat ist, ist auch das Image privat, und das NAS muss sich bei
`ghcr.io` anmelden:

1. GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)**
   → Generate new token (classic). Nur den Haken **`read:packages`** setzen.
   (Fine-grained Tokens funktionieren für ghcr.io nicht.)
2. Systemsteuerung → **Aufgabenplaner** → Erstellen → Geplante Aufgabe →
   Benutzerdefiniertes Skript. Benutzer `root`, „Aktiviert“ abwählen, Skript:
   ```bash
   echo "DEIN_TOKEN" | /usr/local/bin/docker login ghcr.io -u hendrik-haehner --password-stdin
   ```
3. Aufgabe markieren → **Ausführen**, danach die Aufgabe löschen. Die Anmeldung bleibt
   gespeichert.

Alternativ das Image öffentlich machen (GitHub → Packages → `qobuz-dl-docker` →
Package settings → Change visibility → Public). Dann entfällt dieser Schritt. Das Image
enthält keine Zugangsdaten, nur den Programmcode.

**3. Starten und aktualisieren**

Das Skript [`nas/update.sh`](nas/update.sh) lädt die neueste Version, startet den
Container und wartet, bis er gesund ist. Jeder Schritt landet mit Uhrzeit im Terminal
und in `update.log`: welche Version lief, ob es eine neue gab, und bei einem Fehler
den Grund und die letzten Zeilen aus dem Container. Überbleibsel abgebrochener Updates
(z. B. `cacc0a60dad3_qobuz-dl-web`) räumt es weg.

Einmalig `update.sh` neben `docker-compose.yml` ablegen, per SSH:

```bash
cd /volume1/docker/qobuz-dl-web
sudo curl -fsSL -H "Authorization: Bearer DEIN_TOKEN" -H "Accept: application/vnd.github.raw" \
  -o update.sh https://api.github.com/repos/hendrik-haehner/qobuz-dl-docker/contents/nas/update.sh
```

(`DEIN_TOKEN`: ein Token mit Leserecht auf das Repository; oder den Inhalt von GitHub
in eine neue Datei `update.sh` kopieren.)

Dann aktualisieren:

- **per SSH:** `sudo bash /volume1/docker/qobuz-dl-web/update.sh`
- **per Aufgabenplaner:** Aufgabe `qobuz-dl-web aktualisieren`, Benutzer `root`, Skript
  `bash /volume1/docker/qobuz-dl-web/update.sh`. Mit einem Zeitplan (z. B. wöchentlich
  nachts) aktualisiert er sich automatisch. Unter „Aufgabeneinstellungen“ →
  „Benachrichtigungsdetails per E-Mail senden“ → „Nur wenn das Skript abnormal beendet
  wird“ bekommst du bei einem Fehler eine Mail. Das Protokoll steht in
  `docker/qobuz-dl-web/update.log`.

Danach `http://<IP-des-NAS>:8080` öffnen (bzw. dein `WEB_PORT`), mit `WEB_PASSWORD`
anmelden und unter „Qobuz-Konto“ den Qobuz-Token eintragen (siehe „Qobuz-Anmeldung“).

**Umstieg von der Installation mit Quellcode:** In deiner `docker-compose.yml` die
Zeilen `build: .` und `image: qobuz-dl-web:latest` durch
`image: ghcr.io/hendrik-haehner/qobuz-dl-docker:latest` ersetzen und oben `name: qobuz-dl-web`
ergänzen (siehe aktuelle `docker-compose.yml`). Dann Schritt 2 und 3. Die
Programmdateien (`app/`, `Dockerfile` usw.) im Ordner kannst du danach löschen;
`docker-compose.yml`, `.env` und `config/` bleiben.

### Benutzer-ID ohne Terminal

Aufgabenplaner → Benutzerdefiniertes Skript, Benutzer `root`, „Aktiviert“ abwählen:

```bash
id deinbenutzername > /volume1/docker/id.txt
```

Ausführen und `docker/id.txt` öffnen: `uid=1026(…) gid=100(users)` heißt `PUID=1026`,
`PGID=100`. Im Webinterface zeigt der Dialog „Ordner wählen“ außerdem, mit welcher
ID der Container tatsächlich zugreift.

## Qobuz-Anmeldung

Seit April 2026 nimmt Qobuz an seiner API keine Anmeldung mit E-Mail und Passwort mehr
an (der Web-Player nutzt OAuth mit reCAPTCHA). qobuz-dl selbst wird nicht mehr gepflegt
([vitiko98/qobuz-dl#329](https://github.com/vitiko98/qobuz-dl/issues/329)). Die App meldet
sich darum mit dem `user_auth_token` einer angemeldeten Browser-Sitzung an:

1. [play.qobuz.com](https://play.qobuz.com) im Browser öffnen und anmelden.
2. Entwicklerwerkzeuge öffnen (Chrome/Firefox am Mac: `Cmd`+`Option`+`I`; Safari: erst
   Einstellungen → Erweitert → „Funktionen für Webentwickler anzeigen“).
3. Reiter **Netzwerk**, nach `login` filtern, Seite neu laden.
4. Eintrag `login` → **Antwort** → Wert von `user_auth_token` kopieren.
   Kein solcher Eintrag: einen Titel abspielen, nach `api.json` filtern und bei einer
   Anfrage unter **Header** den Wert von `X-User-Auth-Token` kopieren.
5. Im Webinterface unter „Qobuz-Konto“ einfügen.

Der Token gibt vollen Zugriff auf das Qobuz-Konto. Er liegt nur in `config/config.ini`
(Rechte 0600) und wird von keiner API ausgegeben. Bei jedem Download holt die App bei
Qobuz einen frischen Token und speichert ihn; läuft er trotzdem ab, zeigt die
Download-Liste das an, und du trägst einen neuen ein.

Technisch: qobuz-dl läuft unverändert, nur seine Login-Funktion wird ersetzt
(`app/token_auth.py`): `POST user/login` mit `extra=partner` und dem Token im Header
`X-User-Auth-Token`. Eine alte `config.ini` mit Passwort-Hash zeigt das Webinterface
mit einem Hinweis an.

## Freigaben einbinden

Der Container sieht nur, was beim Start eingebunden ist. NAS-Freigaben selbst einhängen
kann er nicht (dafür bräuchte er weitreichende Rechte). Darum wird jede Freigabe in
`docker-compose.yml` als Ordner unter `/shares` eingebunden, und im Webinterface
wählst du dann Freigabe und Unterordner.

| Variante | Eintrag in `volumes:` | |
|---|---|---|
| einzelne Freigaben (empfohlen) | `- /volume1/music:/shares/music` | nur diese Ordner sind sichtbar |
| ganzes Volume | `- /volume1:/shares` | alle Freigaben, Systemordner wie `@eaDir` werden ausgeblendet |
| Docker läuft nicht auf dem NAS | NFS-/SMB-Volume, siehe Beispiel in `docker-compose.yml` | |

Die App prüft, ob ein Ordner unter `/shares` wirklich eingebunden ist. Ist er es nicht,
lägen die Dateien nur im Container und wären beim nächsten Update weg. Solche Ordner
sind im Webinterface rot markiert, und Downloads dorthin werden abgelehnt. Direkt nach
`/shares` wird nie geschrieben, und neue Freigaben lassen sich nicht im Webinterface
anlegen, nur Unterordner in einer Freigabe.

Gibt es genau eine Freigabe, ist sie automatisch der Speicherort.

## Vorhandene Ordner und Dateien

Es wird nie etwas überschrieben:

- Existiert der Album-Ordner schon, nutzt qobuz-dl ihn mit. Titel, deren Datei schon
  da ist, werden übersprungen; fehlende kommen dazu. Ein vorhandenes `cover.jpg` bleibt.
- qobuz-dl merkt sich jedes geladene Album (Datenbank in `config/`). Ein zweiter
  Download desselben Albums wird komplett übersprungen, auch in anderer Qualität.
  Mit **„Erneut herunterladen“** gilt das für diesen einen Download nicht.
- In der Download-Liste steht dann **„übersprungen“** mit dem Grund, und bei Erfolg,
  wie viele Titel neu und wie viele schon vorhanden waren.

Ein `/` in Interpret, Album oder Titel (z. B. „AC/DC“) wird in Ordner- und Dateinamen
durch `-` ersetzt, damit keine zusätzlichen Unterordner entstehen. Die Tags in den
Dateien behalten den Originalnamen.

Für eine zweite Qualität desselben Albums sollte das Ordnermuster `{bit_depth}` und
`{sampling_rate}` enthalten (wie der Standard), sonst landen beide im selben Ordner
und die Titel gelten als schon vorhanden.

## Als App auf dem iPhone

Safari → Seite öffnen → Teilen-Symbol → **„Zum Home-Bildschirm“**. Die App startet dann
im Vollbild ohne Safari-Leisten, mit eigenem Icon. Als App hat sie ihren eigenen
Cookie-Speicher, darum fragt sie einmal nach `WEB_PASSWORD`; danach bleibt die
Anmeldung 30 Tage bestehen.

Von unterwegs funktioniert sie nur, wenn das NAS von dort erreichbar ist, am besten über
ein VPN (z. B. Tailscale oder den VPN Server von DSM).

## Zugangsschutz und HTTPS

Mit `WEB_PASSWORD` fragt die Seite nach einem Passwort. Nach dem Anmelden gilt die
Sitzung 30 Tage. Wer `WEB_PASSWORD` ändert, meldet damit alle Sitzungen ab. Nach
10 Fehlversuchen in 5 Minuten sind weitere Versuche für ein paar Minuten gesperrt.
Ohne `WEB_PASSWORD` ist die Seite offen und zeigt eine Warnung.

Ohne HTTPS gehen Passwörter unverschlüsselt durchs Heimnetz. Mit dem Reverse-Proxy
von DSM bekommst du HTTPS:

1. Systemsteuerung → **Anmeldeportal** → **Erweitert** → **Reverse Proxy** → **Erstellen**
   - Quelle: Protokoll `HTTPS`, Hostname z. B. `qobuz.deinname.synology.me`, Port `443`
   - Ziel: Protokoll `HTTP`, Hostname `localhost`, Port `8080`
   - Reiter „Benutzerdefinierte Kopfzeile“ → Erstellen: Name `X-Forwarded-Proto`, Wert `$scheme`
     (damit das Session-Cookie als „nur über HTTPS“ markiert wird)
2. Systemsteuerung → **Sicherheit** → **Zertifikat**: ein Zertifikat (z. B. Let's Encrypt
   für deine DDNS-Adresse) unter „Einstellungen“ diesem Reverse-Proxy-Eintrag zuweisen.
3. In `.env` `WEB_BIND=127.0.0.1` setzen und das Projekt neu erstellen. Dann ist Port
   8080 nur noch über den Reverse-Proxy erreichbar.

Für den Zugriff von unterwegs ist ein VPN (z. B. Tailscale oder der VPN Server von DSM)
sicherer, als die Seite ins Internet freizugeben.

## Umgebungsvariablen

| Variable | Standard | Zweck |
|---|---|---|
| `WEB_PASSWORD` | – | Passwort fürs Webinterface |
| `PUID`, `PGID` | `1000` | Benutzer-/Gruppen-ID, mit der der Container schreibt |
| `WEB_PORT` | `8080` | Port auf dem NAS |
| `WEB_BIND` | `0.0.0.0` | `127.0.0.1`: nur über Reverse-Proxy erreichbar |
| `QOBUZ_DEFAULT_QUALITY` | `6` | Startwert, bis im Webinterface ein Standard gespeichert wird: `5` MP3 320, `6` FLAC 16/44,1, `7` FLAC 24/96, `27` FLAC 24/192 |
| `QOBUZ_TOKEN` | – | optional, statt den Qobuz-Token im Webinterface einzutragen |

Im Ordner `config/` liegen `config.ini` (Qobuz-Anmeldung mit Token, Rechte 0600),
`web-settings.json` (Standards aus dem Webinterface), `session.key` (signiert die
Sitzungen) und die Download-Datenbank von qobuz-dl.

## Aufbau

```
app/
  main.py          FastAPI: Webinterface + REST-API, Zugangsschutz (Middleware)
  auth.py          Passwort, signierte Sitzungen, Schutz gegen Durchprobieren
  qobuz_config.py  Qobuz-Anmeldung: prüft den Token, schreibt config.ini
  token_auth.py    Token-Anmeldung statt E-Mail/Passwort (ersetzt den Login von qobuz-dl)
  qdl_runner.py    startet qobuz-dl mit Token-Anmeldung, speichert den erneuerten Token
  jobs.py          Warteschlange, startet qobuz-dl als Subprozess (ein Job nach dem anderen)
  preferences.py   Format, Qualität, Speicherort, Namensmuster (+ Prüfung der Platzhalter)
  storage.py       Freigaben unter /shares: auflisten, Mount prüfen, Ordner anlegen
  settings.py      Einstellungen aus Umgebungsvariablen
  static/          HTML, CSS, JS (ohne Build-Schritt)
docker/entrypoint.sh
tests/
```

### API

Mit `WEB_PASSWORD` brauchen alle Endpunkte außer `/api/health` und `/api/login` eine
Sitzung (sonst `401`).

| Methode | Pfad | |
|---|---|---|
| `GET` | `/api/health` | Healthcheck |
| `POST` | `/api/login` / `/api/logout` | `{"password": "..."}` → Session-Cookie |
| `GET` | `/api/status` | Qobuz angemeldet? Zugangsschutz aktiv? Platzhalter |
| `GET` | `/api/account` | `{"configured": true, "email": "...", "auth_method": "token"}` |
| `PUT` | `/api/account` | `{"token": "..."}` prüft bei Qobuz und speichert |
| `DELETE` | `/api/account` | löscht die Qobuz-Anmeldung |
| `GET`/`PUT` | `/api/settings` | Standards: `format`, `quality`, `target_dir`, `folder_format`, `track_format` |
| `GET` | `/api/folders?path=music/Rock` | Freigaben (ohne `path`) bzw. Unterordner |
| `POST` | `/api/folders` | `{"parent": "music", "name": "Hi-Res"}` legt einen Ordner an |
| `GET` | `/api/downloads`, `/api/downloads/{id}` | Jobs mit den letzten 200 Log-Zeilen |
| `POST` | `/api/downloads` | `{"url": "..."}`, optional mit Feldern aus `/api/settings` und `"redownload": true` |

Platzhalter für Ordner: `{artist} {album} {year} {bit_depth} {sampling_rate}`.
Für Dateien: `{artist} {albumartist} {tracktitle} {tracknumber} {version} {bit_depth} {sampling_rate}`.
Andere lehnt die App ab, weil qobuz-dl sonst mitten im Download abbricht.

Es werden nur `https://`-URLs von `open.`, `play.` und `www.qobuz.com` sowie von
last.fm angenommen. qobuz-dl wird ohne Shell aufgerufen. Speicherorte können `/shares`
nicht verlassen, auch nicht über `..` oder Symlinks.

## Entwicklung

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
mkdir -p dev-shares/music
SHARES_DIR=dev-shares ALLOW_UNMOUNTED_SHARES=1 .venv/bin/uvicorn app.main:app --reload --port 8080
```

`ALLOW_UNMOUNTED_SHARES=1` schaltet die Mount-Prüfung ab, nur für die Entwicklung.

Image selbst bauen statt von ghcr.io laden:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Die CI (`.github/workflows/ci.yml`) testet jeden Pull Request und baut das Image
für amd64 und arm64. Auf `main` und bei Tags `v*` wird es nach ghcr.io veröffentlicht
(`latest`, Version, Commit-Kürzel).

## Rechtliches

qobuz-dl benötigt ein bezahltes Qobuz-Abo. Halte dich an die Nutzungsbedingungen von
Qobuz. Dieses Projekt steht in keiner Verbindung zu Qobuz.
