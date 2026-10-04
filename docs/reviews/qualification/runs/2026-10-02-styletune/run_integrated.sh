#!/bin/zsh
# The integrated service in isolation — 3 October 2026 (owner order of 2 October, ruling of 3 October).
#   run_integrated.sh LABEL
# The real application with VAL_TYPED_MODEL set: StyleTune V2 for ordinary typing, GPT-OSS
# MEDIUM (addressed as the second instance `val-exp-prod`) for deliberate deep reasoning,
# regular Gemma for Voice. Scratch store, port 8766. One cognition model at a time. The run
# REFUSES to start if LM Studio holds a model or anything listens on 8099 or 8766, and at
# the end stops only the llama.cpp server its own service started and unloads only its
# own LM Studio instance. `caffeinate -i` holds off idle sleep.
set -u
LABEL=$1
ROOT=/Users/josepharmand/Projects/val-dev
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
O=$ROOT/docs/reviews/qualification/runs/2026-10-02-styletune
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-prod
cd $ROOT
export VAL_TYPED_MODEL=gemma-4-26b-a4b-styletune-v2
export VAL_VOICE_MODEL=gemma-4-26b-a4b VAL_VOICE_RELEASES_PARTNER=on
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP VAL_EXPERIMENT_MODEL_KEY=openai/gpt-oss-20b
export VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
export VAL_ADAPTIVE_ENDPOINT=on VAL_VOICE_TURN_PREFILL=on VAL_OWNER_PRECEDENCE=on VAL_COMBINE_CONTINUATIONS=on
export VAL_CONVERSATION_GUIDANCE=on VAL_SPOKEN_NUMERALS=on VAL_SPOKEN_FORMATTING=on
unset VAL_TYPED_PRIME VAL_VOICE_EARLY_AUDIO VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_REQUEST_CONSTRUCTION
echo "=== $LABEL $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps | wc -l | tr -d ' ')"
RESIDENT=$($LMS ps 2>/dev/null | grep -cE "gpt-oss|gemma|LOADED|IDLE")
[[ $RESIDENT == 0 ]] || { echo "a model is resident in LM Studio (production in use?): not starting"; exit 2; }
[[ -z $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null) ]] || { echo "port 8099 has a listener this run did not start (production Voice?): not starting"; exit 2; }
[[ -z $(lsof -nP -t -iTCP:8766 -sTCP:LISTEN 2>/dev/null) ]] || { echo "port 8766 is in use (another run): not starting"; exit 2; }
( while true; do printf "%s\t%s\t%s\n" "$(date +%s)" "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"; sleep 3; done ) > $O/memory-$LABEL.tsv &
MEMORY=$!
caffeinate -i uv run --project $ROOT python $D/serve_experiment.py > $O/service-$LABEL.log 2>&1 &
SERVICE=$!
owned_by_service() {
  local p=$1 n=0
  while [[ -n $p && $p != 1 && $n -lt 8 ]]; do
    [[ $p == $SERVICE ]] && return 0
    p=$(ps -o ppid= -p $p 2>/dev/null | tr -d ' '); n=$((n+1))
  done
  return 1
}
for i in $(seq 1 480); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.25; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; tail -5 $O/service-$LABEL.log; kill $SERVICE $MEMORY; exit 1; }
caffeinate -i uv run --project $ROOT python $O/integrated_bench.py $O/integrated-$LABEL.json $O/service-$LABEL.log 2>&1 | tee $O/bench-$LABEL.out
OURS=""
for pid in $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null); do owned_by_service $pid && OURS="$OURS $pid"; done
kill $SERVICE 2>/dev/null; sleep 3
for pid in ${=OURS}; do kill $pid 2>/dev/null; done
$LMS unload $EXP > /dev/null 2>&1   # this run's own instance, by its own identifier
kill $MEMORY 2>/dev/null
grep -E "typed prime|model transition|CANDIDATE typed model|deep reasoning: this turn|voice model: this turn|preparing .* did not" $O/service-$LABEL.log | cut -c1-260 > $O/routes-$LABEL.log
echo "DONE $LABEL $(date +%H:%M:%S)"
