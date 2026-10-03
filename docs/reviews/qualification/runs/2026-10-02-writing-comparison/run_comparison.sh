#!/bin/zsh
# Blind writing comparison, one model at a time — 2 October 2026 (owner authorisation).
#   run_comparison.sh gptoss|gemma|styletune LABEL forward|reverse
# One model resident at a time: the other's instance or server is stopped first, and the
# run refuses to start if any model is resident in LM Studio (production's instance would
# mean he is using Val). GPT-OSS is loaded here as the second instance `val-exp-prod`
# (cold load timed); Gemma's llama.cpp server is started by the service's own supervisor
# (cold start timed from the service log). `caffeinate -i` holds off idle sleep for the
# run — the 20:39 "stall" of the typed-cache bench was the Mac sleeping.
set -u
MODEL=$1; LABEL=$2; ORDER=$3
ROOT=/Users/josepharmand/Projects/val-dev
O=$ROOT/docs/reviews/qualification/runs/2026-10-02-writing-comparison
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-prod
cd $ROOT
export VAL_COMPARE=$MODEL VAL_TYPED_PRIME=on
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP VAL_EXPERIMENT_MODEL_KEY=openai/gpt-oss-20b
export VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
export VAL_ADAPTIVE_ENDPOINT=on VAL_VOICE_TURN_PREFILL=on VAL_OWNER_PRECEDENCE=on VAL_COMBINE_CONTINUATIONS=on
export VAL_CONVERSATION_GUIDANCE=on VAL_SPOKEN_NUMERALS=on VAL_SPOKEN_FORMATTING=on
unset VAL_VOICE_MODEL VAL_VOICE_RELEASES_PARTNER VAL_VOICE_EARLY_AUDIO VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_REQUEST_CONSTRUCTION
echo "=== $LABEL model=$MODEL order=$ORDER $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps | wc -l | tr -d ' ')"
$LMS unload $EXP > /dev/null 2>&1
# Corrected 2 October 2026 (owner order §7): a listener on 8099 at the start belongs to
# production Voice or another run. The harness REFUSES; it never stops a process it did
# not start. (`pgrep -f` was a false guard — it matched the shell running the check.)
RESIDENT=$($LMS ps 2>/dev/null | grep -cE "gpt-oss|gemma|LOADED|IDLE")
[[ $RESIDENT == 0 ]] || { echo "a model is resident in LM Studio (production in use?): not starting"; $LMS ps; exit 2; }
[[ -z $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null) ]] || { echo "port 8099 has a listener this run did not start (production Voice?): not starting"; exit 2; }
owned_by_service() {  # is PID $1 a descendant of the service this run started?
  local p=$1 n=0
  while [[ -n $p && $p != 1 && $n -lt 8 ]]; do
    [[ $p == $SERVICE ]] && return 0
    p=$(ps -o ppid= -p $p 2>/dev/null | tr -d ' '); n=$((n+1))
  done
  return 1
}
( while true; do printf "%s\t%s\t%s\n" "$(date +%s)" "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"; sleep 5; done ) > $O/memory-$LABEL.tsv &
MEMORY=$!
COLD_LOAD=none
if [[ $MODEL == gptoss ]]; then
  T0=$(date +%s.%N)
  $LMS load openai/gpt-oss-20b --identifier $EXP -c 32768 --parallel 1 -y > $O/lms-load-$LABEL.log 2>&1 || { echo "GPT-OSS did not load"; kill $MEMORY; exit 1; }
  COLD_LOAD=$(python3 -c "import time; print(round(time.time()-$T0,1))")
  echo "GPT-OSS cold load ${COLD_LOAD} s"
fi
T_START=$(date +%s.%N)
caffeinate -i uv run --project $ROOT python $O/serve_comparison.py > $O/service-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
echo "service up after $(python3 -c "import time; print(round(time.time()-$T_START,1))") s"
caffeinate -i uv run --project $ROOT python $O/compare_bench.py $MODEL $LABEL $ORDER $O/answers-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out
OURS=""
for pid in $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null); do owned_by_service $pid && OURS="$OURS $pid"; done
kill $SERVICE 2>/dev/null; sleep 3
for pid in ${=OURS}; do kill $pid 2>/dev/null; done   # only the server this run's service started
$LMS unload $EXP > /dev/null 2>&1
kill $MEMORY 2>/dev/null
grep -E "typed prime|local runtime ready|unmetered local route" $O/service-$LABEL.log | cut -c1-240 > $O/routes-$LABEL.log
echo "cold_load_s=$COLD_LOAD" >> $O/routes-$LABEL.log
echo "DONE $LABEL $(date +%H:%M:%S)"
