#!/bin/bash
# Starts Tailscale and the game server together in this one container.
#
#   serve (the default)  tailscaled, connect to your tailnet as "ffbe", then the game server
#   anything else        passed straight to ffbe.py (fetch-data, rotation, status, new-game ...)
#
# If either tailscaled or the server stops, the other is stopped too and the container exits, so Docker's
# restart policy brings both back up together. (With two containers, a restart of the Tailscale one left the
# server attached to a dead network until it was recreated by hand.)
set -u

if [ "${1:-serve}" != "serve" ]; then
    exec python3 /app/ffbe.py "$@"
fi
shift || true

STATE_DIR="${TS_STATE_DIR:-/var/lib/tailscale}"
SOCKET=/var/run/tailscale/tailscaled.sock
TS_HOSTNAME="${TS_HOSTNAME:-ffbe}"
mkdir -p "$STATE_DIR" /var/run/tailscale

log() { echo "[start] $*"; }

# The same state folder the separate Tailscale container used, so this is the same machine ("ffbe") with the
# same address on your tailnet.
tailscaled --statedir="$STATE_DIR" --socket="$SOCKET" ${TS_TAILSCALED_EXTRA_ARGS:-} &
TSD=$!

state() {
    tailscale --socket="$SOCKET" status --json 2>/dev/null \
        | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("BackendState", ""))
except Exception: print("")'
}

current=""
for _ in $(seq 1 150); do
    if ! kill -0 "$TSD" 2>/dev/null; then
        log "tailscaled exited during startup"
        exit 1
    fi
    current="$(state)"
    case "$current" in
        ""|NoState) sleep 0.2 ;;
        *) break ;;
    esac
done
log "Tailscale state: ${current:-unknown}"

if [ "$current" = "NeedsLogin" ] || [ "$current" = "Stopped" ]; then
    if [ -z "${TS_AUTHKEY:-}" ] && [ "$current" = "NeedsLogin" ]; then
        log "Tailscale needs an auth key: set TS_AUTHKEY in .env (see README, Setup step 2), then start again"
    fi
    tailscale --socket="$SOCKET" up --hostname="$TS_HOSTNAME" --accept-dns=false \
        ${TS_AUTHKEY:+--auth-key="$TS_AUTHKEY"} ${TS_EXTRA_ARGS:-} \
        || log "tailscale up failed; the server will keep looking for its Tailscale address"
else
    # Already signed in: tailscaled reconnects by itself. Make sure this node never takes the tailnet's DNS.
    tailscale --socket="$SOCKET" set --accept-dns=false --hostname="$TS_HOSTNAME" || true
fi

python3 /app/ffbe.py serve "$@" &
SRV=$!

stop_all() {
    log "stopping"
    kill -TERM "$SRV" 2>/dev/null
    kill -TERM "$TSD" 2>/dev/null
    wait "$SRV" 2>/dev/null
    wait "$TSD" 2>/dev/null
    exit 0
}
trap stop_all TERM INT

# Wait for whichever stops first, then take the other down with it.
wait -n "$TSD" "$SRV"
code=$?
if ! kill -0 "$TSD" 2>/dev/null; then
    log "tailscaled stopped (exit $code); stopping the server so both restart together"
else
    log "server stopped (exit $code); stopping tailscaled so both restart together"
fi
kill -TERM "$SRV" "$TSD" 2>/dev/null
wait 2>/dev/null
exit "$code"
