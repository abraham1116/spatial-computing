#!/bin/sh
# Per-strategy energy on macOS with powermetrics (needs administrator rights).
#   sudo benchmarks/hardware/energy.sh
# Samples CPU/GPU/package power every second for 10 s idle, then while each strategy runs, and
# writes benchmarks/results/energy.json. Run on AC power with the screen at a fixed brightness
# and no other heavy process; note the machine state in the output.
set -eu
[ "$(id -u)" = 0 ] || { echo '{"ok": false, "error": "needs sudo (powermetrics)"}'; exit 2; }
command -v powermetrics >/dev/null || { echo '{"ok": false, "error": "powermetrics not found (macOS only)"}'; exit 2; }
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
PY=${PYTHON:-$ROOT/.venv/bin/python}
OUT=$ROOT/benchmarks/results/energy.json
sample() {  # $1 = label, $2.. = command; prints "label mean_watts duration_s"
  label=$1; shift
  powermetrics -i 1000 --samplers cpu_power,gpu_power -f plist > /tmp/spatial_pm.plist 2>/dev/null &
  PM=$!
  t0=$(date +%s)
  "$@" >/dev/null 2>&1 || true
  t1=$(date +%s)
  kill $PM 2>/dev/null || true; wait $PM 2>/dev/null || true
  "$PY" - "$label" $((t1 - t0)) <<'PYEOF'
import plistlib, re, sys
label, dur = sys.argv[1], sys.argv[2]
raw = open("/tmp/spatial_pm.plist", "rb").read()
vals = [float(m) for m in re.findall(rb"<key>(?:combined_power|package_watts|cpu_power)</key>\s*<real>([0-9.]+)</real>", raw)]
mean = sum(vals) / len(vals) if vals else None
print(f"{label} {mean} {dur}")
PYEOF
}
{
  sample idle sleep 10
  sample numba_1thread "$PY" -c "from spatial.compute import workloads as w; w.mandel_numba(8,8); w.mandel_numba(3000,300)"
  sample numba_2threads "$PY" -c "from spatial.compute import workloads as w; w.mandel_numba_parallel(8,8); w.mandel_numba_parallel(3000,300)"
  sample python_pure "$PY" -c "from spatial.compute import workloads as w; w.mandel_python(500,300)"
} | "$PY" -c "
import json, sys
rows = [l.split() for l in sys.stdin if l.strip()]
idle = float(rows[0][1]) if rows and rows[0][1] != 'None' else None
out = {'unit': 'watts (powermetrics combined power, mean)', 'idle': idle, 'runs': [
  {'label': r[0], 'mean_watts': None if r[1] == 'None' else float(r[1]), 'duration_s': float(r[2]),
   'marginal_joules': None if (r[1] == 'None' or idle is None) else (float(r[1]) - idle) * float(r[2])} for r in rows[1:]]}
open('$OUT', 'w').write(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))"
