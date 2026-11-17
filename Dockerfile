FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    SHARES_DIR=/shares \
    # Reverse-Proxy (z. B. DSM) meldet per X-Forwarded-Proto, dass HTTPS benutzt wird
    FORWARDED_ALLOW_IPS=*

# /shares bekommt bewusst KEIN VOLUME: Freigaben werden einzeln darunter
# eingebunden, und was dort nicht eingebunden ist, erkennt die App als "nur im Container".
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /shares /home/app/.config/qobuz-dl \
    && chown -R app:app /home/app \
    # Andere UIDs (PUID/PGID, z. B. NAS-Benutzer) müssen den Config-Mount erreichen
    && chmod 755 /home/app /home/app/.config

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app
VOLUME ["/home/app/.config/qobuz-dl"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
