# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/home/app \
    DOWNLOAD_DIR=/downloads

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /downloads /home/app/.config/qobuz-dl \
    && chown -R app:app /downloads /home/app \
    # Andere UIDs (PUID/PGID, z. B. NAS-Benutzer) müssen den Config-Mount erreichen
    && chmod 755 /home/app /home/app/.config

WORKDIR /srv
COPY requirements.txt .
# Optional: eigenes CA-Zertifikat für Proxys mit TLS-Inspektion (z. B. Cloud-Sandbox),
# nur zur Build-Zeit, landet nicht im Image:
#   docker build --secret id=pip_cert,src=/pfad/ca.crt ...
RUN --mount=type=secret,id=pip_cert,required=false \
    if [ -f /run/secrets/pip_cert ]; then export PIP_CERT=/run/secrets/pip_cert; fi; \
    pip install -r requirements.txt

COPY app ./app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER app
VOLUME ["/downloads", "/home/app/.config/qobuz-dl"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
