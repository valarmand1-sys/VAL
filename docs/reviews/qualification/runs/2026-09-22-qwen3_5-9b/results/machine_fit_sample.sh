#!/bin/zsh
# Sample the machine's memory state every 5 seconds for the duration of the
# qualification runs. One line of JSON per sample, so the worst moment can be
# found afterwards rather than inferred from a before/after pair.
OUT="$1"
while true; do
  ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  vm=$(vm_stat)
  page=$(sysctl -n vm.pagesize)
  swap=$(sysctl -n vm.swapusage)
  press=$(memory_pressure 2>/dev/null | tail -3 | tr '\n' ' ')
  python3 - "$ts" "$page" <<PY >> "$OUT"
import sys, re, json, subprocess
ts, page = sys.argv[1], int(sys.argv[2])
vm = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
def g(k):
    m = re.search(re.escape(k) + r":\s+(\d+)", vm)
    return int(m.group(1)) * page / 1e9 if m else None
swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout.strip()
pressure = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
free_pct = re.search(r"System-wide memory free percentage:\s*(\d+)", pressure)
print(json.dumps({
    "t": ts,
    "free_gb": round(g("Pages free") or 0, 2),
    "inactive_gb": round(g("Pages inactive") or 0, 2),
    "purgeable_gb": round(g("Pages purgeable") or 0, 2),
    "wired_gb": round(g("Pages wired down") or 0, 2),
    "active_gb": round(g("Pages active") or 0, 2),
    "compressed_gb": round(g("Pages occupied by compressor") or 0, 2),
    "swap": swap,
    "free_pct": int(free_pct.group(1)) if free_pct else None,
}))
PY
  sleep 5
done
