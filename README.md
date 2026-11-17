# qobuz-dl-docker

Docker-App mit Webinterface für das Terminalprogramm
[qobuz-dl](https://github.com/vitiko98/qobuz-dl). Im Browser gibst du eine Qobuz-URL
ein, der Container lädt sie mit `qobuz-dl dl` herunter und zeigt die Ausgabe live an.

> Status: Grundgerüst. Es gibt eine Download-Warteschlange und eine einfache
> Oberfläche. Suche, Einstellungen und persistente Job-Historie fehlen noch.

## Schnellstart

```bash
cp .env.example .env   # QOBUZ_EMAIL und QOBUZ_PASSWORD eintragen
docker compose up -d --build
```

Danach ist das Webinterface unter <http://localhost:8080> erreichbar.

Beim ersten Start erzeugt der Container aus `QOBUZ_EMAIL`/`QOBUZ_PASSWORD` die
Datei `config/config.ini` (gespeichert wird nur der MD5-Hash des Passworts, wie bei
qobuz-dl selbst). Danach kannst du die beiden Variablen aus `.env` wieder löschen.
Eine vorhandene `config.ini` von qobuz-dl kannst du auch direkt nach `config/` kopieren.

| Pfad im Host | Pfad im Container | Inhalt |
|---|---|---|
| `./config` | `/home/app/.config/qobuz-dl` | `config.ini`, Download-Datenbank |
| `./downloads` | `/downloads` | heruntergeladene Musik |

### Umgebungsvariablen

| Variable | Standard | Zweck |
|---|---|---|
| `QOBUZ_EMAIL`, `QOBUZ_PASSWORD` | – | nur für die Ersteinrichtung |
| `QOBUZ_DEFAULT_QUALITY` | `6` | `5` MP3 320, `6` FLAC 16/44.1, `7` FLAC 24 ≤ 96 kHz, `27` FLAC 24 > 96 kHz |
| `WEB_PORT` | `8080` | Port auf dem Host |

## Aufbau

```
app/
  main.py          FastAPI: Webinterface + REST-API
  jobs.py          Warteschlange, startet qobuz-dl als Subprozess (ein Job nach dem anderen)
  qobuz_config.py  erzeugt config.ini ohne interaktive Eingabe
  settings.py      Einstellungen aus Umgebungsvariablen
  static/          HTML, CSS, JS (ohne Build-Schritt)
docker/entrypoint.sh
tests/
```

### API

| Methode | Pfad | |
|---|---|---|
| `GET` | `/api/health` | Healthcheck |
| `GET` | `/api/status` | ist qobuz-dl konfiguriert? Download-Ordner, Standardqualität |
| `GET` | `/api/downloads` | alle Jobs mit den letzten 200 Log-Zeilen |
| `GET` | `/api/downloads/{id}` | ein Job |
| `POST` | `/api/downloads` | `{"url": "...", "quality": 27}` legt einen Job an |

Interaktive Doku: <http://localhost:8080/docs>

Es werden nur `https://`-URLs von `open.`, `play.` und `www.qobuz.com` sowie von
last.fm angenommen. qobuz-dl wird ohne Shell aufgerufen.

> Das Webinterface hat **keine Anmeldung**. Betreibe es nur im eigenen Netz oder
> hinter einem Reverse-Proxy mit Authentifizierung.

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
