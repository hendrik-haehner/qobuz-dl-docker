# qobuz-dl-docker

Docker-App mit Webinterface für das Terminalprogramm
[qobuz-dl](https://github.com/vitiko98/qobuz-dl). Im Browser gibst du eine Qobuz-URL
ein, der Container lädt sie mit `qobuz-dl dl` auf dein NAS und zeigt die Ausgabe live an.

- **Zugangsschutz** per Passwort (`WEB_PASSWORD`)
- **Qobuz-Konto** im Webinterface hinterlegen (E-Mail oder Benutzername + Passwort),
  direkt bei Qobuz geprüft
- **Speicherort:** NAS-Freigabe und Unterordner wählen, neue Ordner anlegen
- **Format** FLAC oder MP3 320, **Qualität** CD 16/44,1 · Hi-Res 24/96 · Hi-Res 24/192
  (fehlt ein Album in der Qualität, nimmt qobuz-dl die nächstbeste)
- **Ordner- und Dateinamen** als Muster wie `{artist}/{album} ({year})`, mit Vorschau
- alles pro Download oder als gespeicherter Standard

## Auf einer Synology installieren (Container Manager)

Beschrieben für DSM 7.2. Container Manager gibt es nur auf bestimmten Modellen
(meist „+“-Serie). Andere NAS mit Docker-Compose (QNAP, Unraid, TrueNAS) gehen
genauso; nur die Menüs heißen anders.

**1. Dateien aufs NAS bringen**

1. Im Paket-Zentrum **Container Manager** installieren. Dabei entsteht die Freigabe `docker`.
2. Auf GitHub den Code als ZIP herunterladen („Code → Download ZIP“) und am PC entpacken.
3. In der File Station den Ordner `docker/qobuz-dl-web` anlegen und den **Inhalt** des
   entpackten Ordners hineinladen (`Dockerfile`, `docker-compose.yml`, `app/`, …).
4. Dort außerdem einen leeren Ordner `config` anlegen.

**2. Freigaben festlegen**: In `docker-compose.yml` unter `volumes:` die Freigaben
eintragen (am PC vor dem Hochladen, oder später im Projekt-Editor des Container Managers):

```yaml
    volumes:
      - ./config:/home/app/.config/qobuz-dl
      - /volume1/music:/shares/music          # links NAS-Pfad, rechts Name im Webinterface
      - /volume1/Downloads:/shares/Downloads  # beliebig viele Freigaben
```

Den NAS-Pfad einer Freigabe zeigt die File Station unter „Eigenschaften“ → „Ort“.

**3. `.env` anlegen**: Am PC `.env.example` kopieren, als `.env` speichern, ausfüllen und
mit in den Ordner `docker/qobuz-dl-web` laden:

```bash
WEB_PASSWORD=ein-langes-passwort
PUID=1026
PGID=100
```

`PUID`/`PGID` ist der DSM-Benutzer, dem die heruntergeladenen Dateien gehören sollen.
Der erste selbst angelegte Benutzer hat meist `1026`, die Gruppe `users` hat `100`.
Genau zeigt es `id <benutzername>` per SSH. Dieser Benutzer braucht Lese-/Schreibrechte
auf die Freigaben (Systemsteuerung → Freigegebener Ordner → Bearbeiten → Berechtigungen)
und auf den Ordner `config`.

**4. Starten**: Container Manager → **Projekt** → **Erstellen**

- Projektname: `qobuz-dl-web`
- Pfad: `docker/qobuz-dl-web`
- Quelle: „Vorhandene docker-compose.yml verwenden“
- Weiter → Fertig. Das Image wird auf dem NAS gebaut (dauert beim ersten Mal ein paar Minuten).

Danach `http://<IP-des-NAS>:8080` öffnen, mit `WEB_PASSWORD` anmelden und unter
„Qobuz-Konto“ die Qobuz-Zugangsdaten eingeben.

**Aktualisieren:** neue Dateien in den Ordner laden (`config/` und `.env` behalten),
dann im Container Manager das Projekt stoppen und mit „Erstellen“ neu bauen.

**Per SSH** statt Oberfläche, im Ordner `/volume1/docker/qobuz-dl-web`:

```bash
sudo docker compose up -d --build
```

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
| `QOBUZ_EMAIL`, `QOBUZ_PASSWORD` | – | optional, statt Anmeldung im Webinterface |

Im Ordner `config/` liegen `config.ini` (Qobuz-Anmeldung, nur Passwort-Hash),
`web-settings.json` (Standards aus dem Webinterface), `session.key` (signiert die
Sitzungen) und die Download-Datenbank von qobuz-dl.

## Aufbau

```
app/
  main.py          FastAPI: Webinterface + REST-API, Zugangsschutz (Middleware)
  auth.py          Passwort, signierte Sitzungen, Schutz gegen Durchprobieren
  qobuz_config.py  Qobuz-Anmeldung: prüft Zugangsdaten, schreibt config.ini
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
| `GET` | `/api/account` | `{"configured": true, "email": "..."}` |
| `PUT` | `/api/account` | `{"email": "...", "password": "..."}` prüft bei Qobuz und speichert |
| `DELETE` | `/api/account` | löscht die Qobuz-Zugangsdaten |
| `GET`/`PUT` | `/api/settings` | Standards: `format`, `quality`, `target_dir`, `folder_format`, `track_format` |
| `GET` | `/api/folders?path=music/Rock` | Freigaben (ohne `path`) bzw. Unterordner |
| `POST` | `/api/folders` | `{"parent": "music", "name": "Hi-Res"}` legt einen Ordner an |
| `GET` | `/api/downloads`, `/api/downloads/{id}` | Jobs mit den letzten 200 Log-Zeilen |
| `POST` | `/api/downloads` | `{"url": "..."}`, optional mit Feldern aus `/api/settings` |

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

## Rechtliches

qobuz-dl benötigt ein bezahltes Qobuz-Abo. Halte dich an die Nutzungsbedingungen von
Qobuz. Dieses Projekt steht in keiner Verbindung zu Qobuz.
