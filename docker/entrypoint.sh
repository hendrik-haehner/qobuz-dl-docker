#!/bin/sh
set -e
# Legt die qobuz-dl-Konfiguration aus QOBUZ_EMAIL/QOBUZ_PASSWORD an, falls sie fehlt.
python -m app.qobuz_config
exec "$@"
