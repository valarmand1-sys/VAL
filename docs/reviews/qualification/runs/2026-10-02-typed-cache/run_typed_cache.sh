#!/bin/zsh
# Typed prefix preparation, measured in isolation — 2 October 2026.
# The scratch service (port 8766, scratch store val_test) with GPT-OSS addressed as a
# SECOND instance of production's own model path, loaded here as `val-exp-prod` (not on
# the cache-renewal allowlist, so the runtime behaves exactly as production's instance).
# Gemma is started by the service's own supervisor on 8099 for the Voice transition.
# Production, its store, its models and its instance are not touched. Usage:
#   run_typed_cache.sh off|transition|on LABEL
set -u
MODE=$1; LABEL=$2
ROOT=/Users/josepharmand/Projects/val-dev
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
O=$ROOT/docs/reviews/qualification/runs/2026-10-02-typed-cache
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-prod
cd $ROOT
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP VAL_EXPERIMENT_MODEL_KEY=openai/gpt-oss-20b
export VAL_VOICE_MODEL=gemma-4-26b-a4b VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1 VAL_VOICE_RELEASES_PARTNER=on
export VAL_ADAPTIVE_ENDPOINT=on VAL_VOICE_TURN_PREFILL=on VAL_OWNER_PRECEDENCE=on VAL_COMBINE_CONTINUATIONS=on
export VAL_CONVERSATION_GUIDANCE=on VAL_SPOKEN_NUMERALS=on VAL_SPOKEN_FORMATTING=on
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
unset VAL_VOICE_EARLY_AUDIO VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_REQUEST_CONSTRUCTION VAL_TYPED_PRIME
[[ $MODE != off ]] && export VAL_TYPED_PRIME=$MODE
echo "=== $LABEL (typed prime: $MODE) $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps | wc -l | tr -d ' ')"
$LMS unload $EXP > /dev/null 2>&1
pkill -f "llama-server.*--port 8099" 2>/dev/null
# A fresh instance each run: the runtime's cache starts empty, as after a load.
$LMS load openai/gpt-oss-20b --identifier $EXP -c 32768 --parallel 1 -y > $O/lms-load-$LABEL.log 2>&1 || { echo "GPT-OSS did not load"; exit 1; }
( while true; do printf "%s\t%s\t%s\n" "$(date +%s)" "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"; sleep 5; done ) > $O/memory-$LABEL.tsv &
MEMORY=$!
T_START=$(date +%s.%N)
uv run --project $ROOT python $D/serve_experiment.py > $O/service-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
echo "service up after $(python3 -c "import time; print(round(time.time()-$T_START,1))") s"
sleep 2
uv run --project $ROOT python $O/typed_cache_bench.py $LABEL $O/bench-$LABEL.json 2>&1 | tee $O/bench-$LABEL.out
kill $SERVICE 2>/dev/null; sleep 3; pkill -f "llama-server.*--port 8099" 2>/dev/null
kill $MEMORY 2>/dev/null
$LMS unload $EXP > /dev/null 2>&1
grep -E "typed prime|voice prime|model transition|re-warm|rewarm" $O/service-$LABEL.log | cut -c1-200 > $O/primes-$LABEL.log
echo "DONE $LABEL $(date +%H:%M:%S)"
