#!/bin/sh
# Start the whole platform on this machine, for development: hub (127.0.0.1:7700) and console (http://127.0.0.1:8090).
# Data lives in ~/.spatial/local (master key, database, usage). Stop with: deploy/run-local.sh stop
set -e
D="${SPATIAL_LOCAL_DIR:-$HOME/.spatial/local}"
PY="${PYTHON:-python3}"
cd "$(dirname "$0")/.."
if [ "$1" = "stop" ]; then
  [ -f "$D/hub.pid" ] && kill "$(cat "$D/hub.pid")" 2>/dev/null || true
  [ -f "$D/platform.pid" ] && kill "$(cat "$D/platform.pid")" 2>/dev/null || true
  rm -f "$D/hub.pid" "$D/platform.pid"; echo stopped; exit 0
fi
mkdir -p "$D"; touch "$D/usage.jsonl" "$D/revoked.txt"
[ -f "$D/hub.key" ] || $PY -m spatial.cli token init --master-key-file "$D/hub.key"
nohup $PY -m spatial.cli serve hub --master-key-file "$D/hub.key" --host 127.0.0.1 --port 7700 --state-file "$D/hub-state.json" \
  --usage-file "$D/usage.jsonl" --revoked-file "$D/revoked.txt" --audit-log "$D/audit.jsonl" --decision-log "$D/decisions.jsonl" > "$D/hub.log" 2>&1 &
echo $! > "$D/hub.pid"
sleep 2
nohup $PY -m spatial.cli platform serve --db "$D/platform.db" --master-key-file "$D/hub.key" --hub 127.0.0.1:7700 --hub-public 127.0.0.1:7700 \
  --usage-file "$D/usage.jsonl" --revoked-file "$D/revoked.txt" --docs-url "${DOCS_URL:-http://127.0.0.1:8080/docs/index.html}" --port 8090 --dev-outbox > "$D/platform.log" 2>&1 &
echo $! > "$D/platform.pid"
sleep 2
echo "console: http://127.0.0.1:8090/   hub: 127.0.0.1:7700   data: $D"
