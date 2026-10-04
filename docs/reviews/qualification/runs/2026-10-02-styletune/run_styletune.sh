#!/bin/zsh
# StyleTune V2 through Val Core's typed path, in isolation — 2 October 2026 (owner order).
#   run_styletune.sh writing|sustained|long|cold LABEL
# The scratch service (port 8766, scratch store val_test) with the candidate as the typed
# route in that process only; its llama.cpp server is started by the service's own
# supervisor on 8099. One cognition model at a time: the run REFUSES to start if LM Studio
# holds a model or anything listens on 8099 (production Voice, or another run) — it never
# stops a process it did not start — and at the end it stops only the server its own
# service started. `caffeinate -i` holds off idle sleep.
set -u
STAGE=$1; LABEL=$2
ROOT=/Users/josepharmand/Projects/val-dev
W=$ROOT/docs/reviews/qualification/runs/2026-10-02-writing-comparison
O=$ROOT/docs/reviews/qualification/runs/2026-10-02-styletune
LMS=$HOME/.lmstudio/bin/lms
cd $ROOT
# PRIME=on|transition: whether the persona prime is refreshed after every answer (on) or
# made only at start and after Voice (transition). Default on, as the first runs used.
export VAL_COMPARE=styletune VAL_TYPED_PRIME=${PRIME:-on}
export VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
export VAL_ADAPTIVE_ENDPOINT=on VAL_VOICE_TURN_PREFILL=on VAL_OWNER_PRECEDENCE=on VAL_COMBINE_CONTINUATIONS=on
export VAL_CONVERSATION_GUIDANCE=on VAL_SPOKEN_NUMERALS=on VAL_SPOKEN_FORMATTING=on
unset VAL_VOICE_MODEL VAL_VOICE_RELEASES_PARTNER VAL_VOICE_EARLY_AUDIO VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_REQUEST_CONSTRUCTION
echo "=== $LABEL stage=$STAGE prime=$VAL_TYPED_PRIME $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps | wc -l | tr -d ' ')"
RESIDENT=$($LMS ps 2>/dev/null | grep -cE "gpt-oss|gemma|LOADED|IDLE")
[[ $RESIDENT == 0 ]] || { echo "a model is resident in LM Studio (production in use?): not starting"; exit 2; }
[[ -z $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null) ]] || { echo "port 8099 has a listener this run did not start (production Voice?): not starting"; exit 2; }
[[ -z $(lsof -nP -t -iTCP:8766 -sTCP:LISTEN 2>/dev/null) ]] || { echo "port 8766 is in use (another run): not starting"; exit 2; }
( while true; do printf "%s\t%s\t%s\n" "$(date +%s)" "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"; sleep 5; done ) > $O/memory-$LABEL.tsv &
MEMORY=$!
T_START=$(date +%s.%N)
caffeinate -i uv run --project $ROOT python $W/serve_comparison.py > $O/service-$LABEL.log 2>&1 &
SERVICE=$!
owned_by_service() {  # is PID $1 a descendant of the service this run started?
  local p=$1 n=0
  while [[ -n $p && $p != 1 && $n -lt 8 ]]; do
    [[ $p == $SERVICE ]] && return 0
    p=$(ps -o ppid= -p $p 2>/dev/null | tr -d ' '); n=$((n+1))
  done
  return 1
}
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.25; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
echo "service up after $(python3 -c "import time; print(round(time.time()-$T_START,1))") s"
case $STAGE in
  writing)   caffeinate -i uv run --project $ROOT python $W/compare_bench.py styletune $LABEL forward $O/answers-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out ;;
  sustained) caffeinate -i uv run --project $ROOT python $O/typed_timing.py sustained styletune $LABEL $O/timing-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out ;;
  long)      caffeinate -i uv run --project $ROOT python $O/typed_timing.py long styletune $LABEL $O/timing-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out ;;
  cold)      caffeinate -i uv run --project $ROOT python $O/typed_timing.py cold styletune $LABEL $O/timing-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out ;;
  *) echo "unknown stage $STAGE" ;;
esac
OURS=""
for pid in $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null); do owned_by_service $pid && OURS="$OURS $pid"; done
kill $SERVICE 2>/dev/null; sleep 3
for pid in ${=OURS}; do kill $pid 2>/dev/null; done   # only the server this run's service started
kill $MEMORY 2>/dev/null
grep -E "typed prime|local runtime ready|unmetered local route" $O/service-$LABEL.log | cut -c1-260 > $O/routes-$LABEL.log
echo "DONE $LABEL $(date +%H:%M:%S)"
