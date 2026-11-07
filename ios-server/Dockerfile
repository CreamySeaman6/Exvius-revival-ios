# Exvius Offline game server for the iPhone app, with Tailscale in the same container. Build from the
# repository root:
#   docker compose -f ios-server/docker-compose.yml build
FROM tailscale/tailscale:stable AS tailscale

FROM python:3.12-slim

# Tailscale (tailscaled + the tailscale CLI) from the official image; iptables for its kernel networking.
RUN apt-get update && apt-get install -y --no-install-recommends iptables iproute2 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=tailscale /usr/local/bin/tailscaled /usr/local/bin/tailscale /usr/local/bin/

RUN pip install --no-cache-dir "cryptography>=42" "pyyaml>=6" tzdata "pillow>=10"

WORKDIR /app
COPY source/server /app/server
COPY data/latest.json /app/latest.json
COPY ios-server/serve.py ios-server/certs.py ios-server/fetch_data.py ios-server/ffbe.py ios-server/entrypoint.sh /app/
RUN chmod +x /app/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FFBE_ENGINE=/app/server \
    FFBE_DATA_DIR=/srv/ffbe/data \
    FFBE_SERVER_ROOT=/srv/ffbe/server-root

VOLUME ["/srv/ffbe/data", "/srv/ffbe/server-root", "/var/lib/tailscale"]
# entrypoint.sh: "serve" starts Tailscale, then the server; any other command goes straight to ffbe.py.
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["serve"]
