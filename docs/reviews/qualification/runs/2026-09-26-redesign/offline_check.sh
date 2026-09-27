#!/bin/zsh
# The coordinated offline check — release-gaps corrections of 27 September 2026, §7.
#
# WHAT IT ESTABLISHES, exactly: with every enabled network service of this Mac turned
# off (not Wi-Fi alone — this machine also carries an iPhone USB service and a VPN
# service), two spoken turns on the deployed release completed and their answers were
# played to the end, and no process of the inference runtime (LM Studio and its helper
# processes, identified by executable path) held a non-loopback connection at any of the
# one-second samples taken meanwhile. WHAT IT DOES NOT ESTABLISH: anything about a
# connection shorter than the sampling interval, anything about a network the machine is
# not on, or anything about processes other than the runtime's (the service, driver and
# voice worker were constrained by the loopback sandbox separately, `TIER1_RELEASE.md`
# §5). It is a narrowing of the stated boundary, not whole-stack network denial.
#
# COORDINATION: run only when he is at the machine and has said the minutes are his to
# give. The script records the enabled/disabled state of every network service and
# restores exactly that state on any exit, including an interrupted one.
#
# Usage: offline_check.sh OUT.json   (Voice on in the desktop first; then speak twice and
#        let both answers play to the end; the check ends when the live store shows two
#        completed deliveries, or after three minutes)
set -u
OUT=${1:?OUT.json}
LIVE=postgresql://josepharmand@localhost:5433/val
NOW_ISO() { date -u +%Y-%m-%dT%H:%M:%SZ; }
NOW_S() { python3 -c 'import time; print(f"{time.time():.3f}")'; }

# 1. Record the state of every network service before touching anything.
SERVICES=()
STATE=()
while IFS= read -r line; do
  [[ "$line" == "An asterisk"* ]] && continue
  [[ -z "$line" ]] && continue
  if [[ "$line" == \** ]]; then SERVICES+=("${line#\*}"); STATE+=("disabled"); else SERVICES+=("$line"); STATE+=("enabled"); fi
done < <(networksetup -listallnetworkservices)
DEFAULT_ROUTE_BEFORE=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
echo "before: default route via ${DEFAULT_ROUTE_BEFORE:-none}; services: ${#SERVICES[@]}"

restore() {
  for i in {1..${#SERVICES[@]}}; do
    if [[ "${STATE[$i]}" == "enabled" ]]; then networksetup -setnetworkserviceenabled "${SERVICES[$i]}" on; fi
  done
  echo "restored: $(networksetup -listallnetworkservices | tr '\n' ';')"
  echo "default route now via $(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"
}
trap restore EXIT INT TERM

# 2. Runtime processes, by executable path — never by a name that another app could share.
runtime_pids() {
  ps -axo pid=,comm= | awk '$2 ~ /\/LM Studio\.app\// || $2 ~ /\.lmstudio\// {print $1}'
}
COUNT_BEFORE=$(psql "$LIVE" -tAc "select count(*) from speech_deliveries where state = 'completed'")
START_S=$(NOW_S); START_ISO=$(NOW_ISO)

# 3. Every enabled service off.
for i in {1..${#SERVICES[@]}}; do
  if [[ "${STATE[$i]}" == "enabled" ]]; then networksetup -setnetworkserviceenabled "${SERVICES[$i]}" off; fi
done
sleep 2
DEFAULT_ROUTE_DURING=$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')
echo "network off at $START_ISO (default route now: ${DEFAULT_ROUTE_DURING:-none}); speak two turns and let both answers play"

SAMPLES=()
while (( $(python3 -c "import time; print(int(time.time() - $START_S))") < 180 )); do
  PIDS=$(runtime_pids | tr '\n' ',' | sed 's/,$//')
  NONLOOP=0
  if [[ -n "$PIDS" ]]; then
    NONLOOP=$(lsof -a -i -n -P -p "$PIDS" 2>/dev/null | grep -E "ESTABLISHED|SYN_SENT" | grep -vE "127\.0\.0\.1|\[::1\]|localhost" | wc -l | tr -d ' ')
  fi
  SAMPLES+=("{\"t\": $(NOW_S), \"runtime_pids\": \"$PIDS\", \"non_loopback_established\": $NONLOOP, \"default_route\": \"${DEFAULT_ROUTE_DURING:-none}\"}")
  COUNT_NOW=$(psql "$LIVE" -tAc "select count(*) from speech_deliveries where state = 'completed'")
  if (( COUNT_NOW - COUNT_BEFORE >= 2 )); then echo "two completed deliveries at $(NOW_ISO)"; break; fi
  sleep 1
done
END_S=$(NOW_S); END_ISO=$(NOW_ISO)
COUNT_AFTER=$(psql "$LIVE" -tAc "select count(*) from speech_deliveries where state = 'completed'")
trap - EXIT INT TERM; restore
python3 - "$OUT" "$START_ISO" "$END_ISO" "$COUNT_BEFORE" "$COUNT_AFTER" "${DEFAULT_ROUTE_BEFORE:-none}" "${DEFAULT_ROUTE_DURING:-none}" "${SAMPLES[@]}" <<'EOF'
import json, sys
out, start, end, c0, c1, route_before, route_during, *samples = sys.argv[1:]
doc = {
    "started": start, "ended": end,
    "completed_deliveries_during_check": int(c1) - int(c0),
    "default_route_before": route_before, "default_route_during": route_during,
    "samples": [json.loads(s) for s in samples],
    "establishes": "with every enabled network service off, the counted deliveries completed and the runtime's processes held no non-loopback connection at any sample",
    "does_not_establish": "connections shorter than the ~1 s sampling interval; anything about a network the machine is not on; processes other than the runtime's",
}
doc["non_loopback_connections_seen"] = sum(s["non_loopback_established"] for s in doc["samples"])
doc["two_answers_completed"] = doc["completed_deliveries_during_check"] >= 2
doc["route_was_down"] = route_during == "none"
json.dump(doc, open(out, "w"), indent=1)
print(json.dumps({k: v for k, v in doc.items() if k != "samples"}))
EOF
