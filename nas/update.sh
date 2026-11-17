#!/bin/bash
# Aktualisiert qobuz-dl-web auf dem NAS und protokolliert jeden Schritt.
#
# Liegt neben docker-compose.yml, z. B. /volume1/docker/qobuz-dl-web/update.sh
#   per SSH:          sudo bash /volume1/docker/qobuz-dl-web/update.sh
#   Aufgabenplaner:   Benutzer root, Skript: bash /volume1/docker/qobuz-dl-web/update.sh
#
# Ausgabe im Terminal und in update.log (letzte 500 Zeilen). Bei einem Fehler
# endet das Skript mit Code 1, damit der Aufgabenplaner den Lauf als fehlgeschlagen
# markiert (und auf Wunsch per E-Mail benachrichtigt).

set -u
export PATH=/usr/local/bin:/usr/bin:/bin:$PATH

DIR="$(cd "$(dirname "$0")" && pwd)"
LOG="$DIR/update.log"
NAME=qobuz-dl-web
WAIT_SECONDS=120

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }
fail() {
  log "FEHLER: $*"
  log "=== abgebrochen"
  exit 1
}
# Commit, aus dem das Image gebaut wurde (Label von GitHub Actions)
revision() {
  docker inspect -f '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1" 2>/dev/null | cut -c1-7
}
health() { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$NAME" 2>/dev/null; }

cd "$DIR" || fail "Ordner $DIR nicht gefunden"
[ -f docker-compose.yml ] || fail "docker-compose.yml fehlt in $DIR"
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  fail "Docker Compose nicht gefunden (Container Manager installiert?)"
fi

log "=== Update gestartet in $DIR ($DC)"
OLD_REV=$(revision "$NAME")
log "Laufende Version: ${OLD_REV:-kein Container}"

# Überbleibsel eines abgebrochenen Updates (z. B. cacc0a60dad3_qobuz-dl-web)
for c in $(docker ps -aq --filter "name=_${NAME}"); do
  log "Entferne Überbleibsel $(docker inspect -f '{{.Name}}' "$c")"
  docker rm -f "$c" >/dev/null || fail "Überbleibsel $c ließ sich nicht entfernen"
done

log "Lade Image ..."
$DC pull 2>&1 | tee -a "$LOG"
[ "${PIPESTATUS[0]}" -eq 0 ] || fail "Image konnte nicht geladen werden. Anmeldung bei ghcr.io fehlt oder abgelaufen? (README: Zugriff auf das private Image)"

log "Starte Container ..."
$DC up -d --remove-orphans 2>&1 | tee -a "$LOG"
[ "${PIPESTATUS[0]}" -eq 0 ] || fail "Container konnte nicht gestartet werden"

log "Warte bis zu ${WAIT_SECONDS}s auf den Healthcheck ..."
STATE=""
for _ in $(seq 1 $((WAIT_SECONDS / 3))); do
  STATE=$(health)
  case "$STATE" in healthy|unhealthy|exited|dead) break ;; esac
  sleep 3
done
NEW_REV=$(revision "$NAME")
if [ "$STATE" != "healthy" ]; then
  log "Letzte Zeilen aus dem Container:"
  docker logs --tail 20 "$NAME" 2>&1 | tee -a "$LOG"
  fail "Container läuft nicht sauber (Status: ${STATE:-unbekannt}, Version: ${NEW_REV:-?})"
fi

if [ "$OLD_REV" = "$NEW_REV" ]; then
  log "Keine neue Version verfügbar, läuft weiter: $NEW_REV"
else
  log "Aktualisiert: ${OLD_REV:-kein Container} -> $NEW_REV"
fi
docker image prune -f >/dev/null 2>&1
log "=== fertig: Container gesund, Version $NEW_REV"

# Protokoll kurz halten
tail -n 500 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
exit 0
