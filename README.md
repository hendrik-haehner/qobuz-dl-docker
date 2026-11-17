# qobuz-dl-docker

Docker-App mit Webinterface für das Terminalprogramm
[qobuz-dl](https://github.com/vitiko98/qobuz-dl). Im Browser gibst du eine Qobuz-URL
ein, der Container lädt sie mit `qobuz-dl dl` herunter und zeigt die Ausgabe live an.

Im Webinterface meldest du dich mit deinem **Qobuz-Konto** an (E-Mail oder
Benutzername + Passwort). Die Zugangsdaten werden direkt bei Qobuz geprüft.

Außerdem einstellbar, pro Download oder als gespeicherter Standard:

- **Format:** FLAC oder MP3 320
- **Qualität** (bei FLAC): CD 16/44,1 · Hi-Res 24/96 · Hi-Res 24/192.
  Gibt es ein Album nicht in der gewählten Qualität, nimmt qobuz-dl die nächstbeste.
- **Speicherort:** beliebiger Unterordner im Musikordner (z. B. der NAS-Freigabe),
  mit Ordnerbrowser und „Neuer Ordner“
- **Ordner- und Dateinamen:** Muster wie `{artist}/{album} ({year})`, ein `/` erzeugt
  Unterordner. Eine Vorschau zeigt das Ergebnis.

> Status: früh. Suche und eine dauerhafte Job-Historie fehlen noch.

## Schnellstart

```bash
cp .env.example .env   # Musikordner, PUID/PGID anpassen
docker compose up -d --build
```

Danach das Webinterface unter <http://localhost:8080> öffnen und oben unter
„Qobuz-Konto“ anmelden. Die App holt sich die nötige App-Kennung von Qobuz, prüft
die Anmeldung und schreibt erst dann `config/config.ini`. Gespeichert wird wie bei
qobuz-dl selbst nur der MD5-Hash des Passworts, ausgeliefert wird er nie.
„Abmelden“ löscht die Zugangsdaten wieder.

Alternativen: `QOBUZ_EMAIL`/`QOBUZ_PASSWORD` in `.env` (wird beim Start einmalig
verwendet, wenn noch keine Anmeldung existiert), oder eine vorhandene `config.ini`
von qobuz-dl nach `config/` kopieren.

| Pfad im Host | Pfad im Container | Inhalt |
|---|---|---|
| `./config` | `/home/app/.config/qobuz-dl` | `config.ini`, Download-Datenbank, `web-settings.json` |
| `$MUSIC_DIR` (Standard `./downloads`) | `/downloads` | Musik-Root, Speicherorte sind Unterordner davon |

## Auf dem NAS

**Docker läuft auf dem NAS** (z. B. Synology Container Manager, QNAP Container Station):
Trage in `.env` den Musikordner und den Benutzer ein, dem die Dateien gehören sollen:

```bash
MUSIC_DIR=/volume1/music
PUID=1026   # `id <benutzer>` auf dem NAS zeigt uid und gid
PGID=100
```

Lege vor dem ersten Start `config/` an und gib sie diesem Benutzer,
sonst legt Docker sie als root an und der Container kann nicht hineinschreiben:

```bash
mkdir -p config && sudo chown 1026:100 config
```

**Docker läuft auf einem anderen Rechner:** Binde die Freigabe per NFS oder SMB als
Docker-Volume ein. Ein Beispiel steht auskommentiert in `docker-compose.yml`.

Im Webinterface wählst du dann unter „Speicherort“ einen Unterordner,
etwa `/downloads/Hi-Res` → auf dem NAS `/volume1/music/Hi-Res`.

### Umgebungsvariablen

| Variable | Standard | Zweck |
|---|---|---|
| `QOBUZ_EMAIL`, `QOBUZ_PASSWORD` | – | optional, statt Anmeldung im Webinterface |
| `QOBUZ_DEFAULT_QUALITY` | `6` | Startwert, bis im Webinterface ein Standard gespeichert wird: `5` MP3 320, `6` FLAC 16/44.1, `7` FLAC 24/96, `27` FLAC 24/192 |
| `MUSIC_DIR` | `./downloads` | Musikordner auf dem Host |
| `PUID`, `PGID` | `1000` | Benutzer-/Gruppen-ID, mit der der Container schreibt |
| `WEB_PORT` | `8080` | Port auf dem Host |

## Aufbau

```
app/
  main.py          FastAPI: Webinterface + REST-API
  jobs.py          Warteschlange, startet qobuz-dl als Subprozess (ein Job nach dem anderen)
  preferences.py   Format, Qualität, Speicherort, Namensmuster (+ Prüfung der Platzhalter)
  storage.py       Ordner im Musik-Root auflisten/anlegen, ohne aus ihm auszubrechen
  qobuz_config.py  Qobuz-Anmeldung: prüft Zugangsdaten, schreibt config.ini
  settings.py      Einstellungen aus Umgebungsvariablen
  static/          HTML, CSS, JS (ohne Build-Schritt)
docker/entrypoint.sh
tests/
```

### API

| Methode | Pfad | |
|---|---|---|
| `GET` | `/api/health` | Healthcheck |
| `GET` | `/api/status` | angemeldet? Musik-Root, erlaubte Platzhalter |
| `GET` | `/api/account` | `{"configured": true, "email": "..."}` |
| `PUT` | `/api/account` | `{"email": "...", "password": "..."}` prüft bei Qobuz und speichert |
| `DELETE` | `/api/account` | Abmelden: löscht `config.ini` |
| `GET`/`PUT` | `/api/settings` | gespeicherte Standards: `format`, `quality`, `target_dir`, `folder_format`, `track_format` |
| `GET` | `/api/folders?path=Rock` | Unterordner im Musik-Root |
| `POST` | `/api/folders` | `{"parent": "Rock", "name": "Hi-Res"}` legt einen Ordner an |
| `GET` | `/api/downloads` | alle Jobs mit den letzten 200 Log-Zeilen |
| `GET` | `/api/downloads/{id}` | ein Job |
| `POST` | `/api/downloads` | `{"url": "..."}`, optional mit allen Feldern aus `/api/settings` als Abweichung vom Standard |

Platzhalter für Ordner: `{artist} {album} {year} {bit_depth} {sampling_rate}`.
Für Dateien: `{artist} {albumartist} {tracktitle} {tracknumber} {version} {bit_depth} {sampling_rate}`.
Andere lehnt die App ab, weil qobuz-dl sonst mitten im Download abbricht.

Interaktive Doku: <http://localhost:8080/docs>

Es werden nur `https://`-URLs von `open.`, `play.` und `www.qobuz.com` sowie von
last.fm angenommen. qobuz-dl wird ohne Shell aufgerufen. Speicherorte können den
Musik-Root nicht verlassen, auch nicht über `..` oder Symlinks.

> Das Webinterface selbst hat **keinen Zugangsschutz**: Jeder, der es erreicht, kann
> herunterladen, die hinterlegte E-Mail sehen und das Qobuz-Konto ändern. Außerdem
> geht das Passwort beim Anmelden per HTTP unverschlüsselt durchs Netz. Betreibe es
> nur im eigenen Netz, oder hinter einem Reverse-Proxy mit HTTPS und Anmeldung.

## Entwicklung

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q
.venv/bin/uvicorn app.main:app --reload --port 8080
```

### Image hinter einem TLS-inspizierenden Proxy bauen

Für Umgebungen wie die Claude-Code-Cloud-Sandbox kann ein CA-Zertifikat nur für den
Build übergeben werden (es landet nicht im Image):

```bash
docker build --network host \
  --build-arg HTTPS_PROXY="$HTTPS_PROXY" \
  --secret id=pip_cert,src=/root/.ccr/ca-bundle.crt \
  -t qobuz-dl-web:dev .
```

## Rechtliches

qobuz-dl benötigt ein bezahltes Qobuz-Abo. Halte dich an die Nutzungsbedingungen von
Qobuz. Dieses Projekt steht in keiner Verbindung zu Qobuz.
