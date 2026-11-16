#!/bin/sh
# Consistent backup of the account database and hub state from the running stack.
set -e
OUT="${1:-./backup-$(date +%Y%m%d-%H%M%S)}"
mkdir -p "$OUT"
docker compose exec -T platform python - <<'PY' > "$OUT/platform.db"
import sqlite3, sys, tempfile, os
src = sqlite3.connect("/data/platform.db")
tmp = tempfile.mktemp()
dst = sqlite3.connect(tmp); src.backup(dst); dst.close()
sys.stdout.buffer.write(open(tmp, "rb").read()); os.remove(tmp)
PY
docker compose cp hub:/data/hub-state.json "$OUT/hub-state.json" 2>/dev/null || true
docker compose cp hub:/data/usage.jsonl "$OUT/usage.jsonl" 2>/dev/null || true
echo "backup in $OUT (the hub master key is NOT included: store it separately and safely)"
