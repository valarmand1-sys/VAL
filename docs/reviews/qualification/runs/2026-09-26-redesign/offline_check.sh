#!/bin/zsh
# The coordinated offline check — release-gaps order of 26 September 2026, §8.
#
# What it establishes: with the machine's Wi-Fi off, two spoken turns on the deployed
# release complete, and no process of the inference runtime (LM Studio and its helpers)
# holds a connection to anything but loopback while they do. What it does NOT establish:
# nothing is proved about a network the machine is not on, and the sampling of
# connections is sampling — a connection shorter than the interval could be missed. That
# boundary is the same one `TIER1_RELEASE.md` §5 states; this check narrows it from
# "observed by sampling with the network up" to "observed by sampling with the network
# down, and the turns still completed".
#
# Coordination (his): run it only when he is at the machine and has said the two
# minutes are his to give. It turns Wi-Fi off, waits for two spoken turns or two minutes,
# whichever comes first, and turns Wi-Fi back on — always, on any exit.
#
# Usage: offline_check.sh OUT.json     (Voice on in the desktop before starting; then speak twice)
set -u
OUT=${1:?OUT.json}
IFACE=$(networksetup -listallhardwareports | awk '/Wi-Fi/{getline; print $2}')
[[ -n "$IFACE" ]] || { echo "no Wi-Fi interface found"; exit 1; }
STATE_BEFORE=$(networksetup -getairportpower "$IFACE")
echo "Wi-Fi ($IFACE) before: $STATE_BEFORE"
LIVE=postgresql://josepharmand@localhost:5433/val
COUNT_BEFORE=$(psql "$LIVE" -tAc "select count(*) from voice_message_provenance")
restore() { networksetup -setairportpower "$IFACE" on; echo "Wi-Fi restored: $(networksetup -getairportpower "$IFACE")"; }
trap restore EXIT INT TERM

networksetup -setairportpower "$IFACE" off
sleep 2
echo "Wi-Fi off at $(date +%H:%M:%S); speak two turns now"
START=$(date +%s)
SAMPLES=()
while (( $(date +%s) - START < 120 )); do
  # Every connection of every LM Studio process, loopback and otherwise; the service's own
  # sockets are already known to be loopback-only from its launchd definition.
  NOW=$(date +%s.%N)
  CONNS=$(lsof -i -n -P 2>/dev/null | grep -i "lm.studio\|lmstudio\|mlx-llm\|llama" | grep -v "127.0.0.1\|\[::1\]\|localhost" | grep -c "ESTABLISHED\|SYN_SENT" || true)
  SAMPLES+=("{\"t\": $NOW, \"non_loopback_established\": ${CONNS:-0}}")
  COUNT_NOW=$(psql "$LIVE" -tAc "select count(*) from voice_message_provenance")
  if (( COUNT_NOW - COUNT_BEFORE >= 2 )); then echo "two spoken turns recorded at $(date +%H:%M:%S)"; break; fi
  sleep 1
done
END=$(date +%s)
COUNT_AFTER=$(psql "$LIVE" -tAc "select count(*) from voice_message_provenance")
trap - EXIT; restore
python3 - "$OUT" "$STATE_BEFORE" "$COUNT_BEFORE" "$COUNT_AFTER" "$START" "$END" "${SAMPLES[@]}" <<'EOF'
import json, sys
out, before, c0, c1, start, end, *samples = sys.argv[1:]
doc = {"wifi_before": before, "spoken_turns_during_check": int(c1) - int(c0), "seconds": int(end) - int(start),
       "samples": [json.loads(s) for s in samples],
       "boundary": "sampled every ~1 s; a shorter connection could be missed; nothing is proved about a network the machine is not on"}
doc["non_loopback_connections_seen"] = sum(s["non_loopback_established"] for s in doc["samples"])
json.dump(doc, open(out, "w"), indent=1); print(json.dumps({k: v for k, v in doc.items() if k != "samples"}))
EOF
