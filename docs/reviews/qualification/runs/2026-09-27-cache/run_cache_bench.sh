#!/bin/zsh
# One live cache-experiment run — remaining latency work, 27 September 2026, §3.
#
# The frozen candidate (every candidate switch on, as named below) through the real
# desktop frontend and player, against the scratch service on port 8766, whose every
# GPT-OSS configuration addresses the EXPERIMENT instance `val-exp-gpt-oss-20b` — the
# byte-identical clone that is the only path on the cache-renewal allowlist. The one
# variable is renewal on a cache hit, set per run by the allowlist's "renewal" flag. The
# instance is reloaded before each run, so both conditions start from the same empty
# prompt cache; capacity is unchanged (the engine's own ten entries). Production's
# service, store, desktop and model instance are not touched, and the run never starts
# while production Voice is in use.
#
# Usage: run_cache_bench.sh renewal_off|renewal_on|baseline RUN_LABEL [SESSIONS]
#   baseline: the same frozen code with every candidate switch unset and the engine as
#   shipped (renewal off) — the tested undeployed configuration production's settings
#   would give, measured the same afternoon, on the same experiment instance.
set -u
CONDITION=$1; LABEL=$2; SESSIONS=${3:-"0 1 2 3 4"}
ROOT=/Users/josepharmand/Projects/val
D=$ROOT/docs/reviews/qualification/runs/2026-09-27-cache
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/b39b1991-6467-45ee-b07e-b4f8537d9790/scratchpad/cache-$LABEL
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-gpt-oss-20b
CLONE=$HOME/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal
mkdir -p $S
cd $ROOT
case $CONDITION in
  renewal_off) RENEW=false ;;
  renewal_on) RENEW=true ;;
  baseline) RENEW=false ;;
  *) echo "unknown condition $CONDITION"; exit 2 ;;
esac
printf '{\n  "model_paths": ["%s"],\n  "renewal": %s\n}\n' "$CLONE" "$RENEW" > $HOME/.lmstudio/val-cache-renewal.json
# The frozen candidate.
unset VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_EXPERIMENT_ENVELOPE_IN_SYSTEM
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP
if [[ "$CONDITION" == renewal_* ]]; then
  export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on \
    VAL_REQUEST_CONSTRUCTION=envelope_in_system VAL_OWNER_PRECEDENCE=on VAL_TTS_LENGTH_BOUND=on
else
  unset VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_ADAPTIVE_ENDPOINT VAL_REQUEST_CONSTRUCTION \
    VAL_OWNER_PRECEDENCE VAL_TTS_LENGTH_BOUND
fi
echo "=== $LABEL ($CONDITION) $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps infrastructure | wc -l | tr -d ' ')"
# The same empty cache for both conditions: reload the experiment instance.
$LMS unload $EXP > /dev/null 2>&1
$LMS load gpt-oss-20b-renewal --identifier $EXP -c 32768 --parallel 1 -y > $S/load.log 2>&1 || { echo "experiment load failed"; exit 1; }
tail -2 $HOME/.lmstudio/val-cache-renewal.log
# Memory, every 5 s, for the whole run: free percentage and swap in use.
( while true; do
    printf "%s\t%s\t%s\n" "$(date +%s)" \
      "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" \
      "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"
    sleep 5
  done ) > $D/memory-$LABEL.tsv &
MEMORY=$!
uv run --project $ROOT python $D/serve_experiment.py > $D/service-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
(cd $ROOT/apps/desktop && VITE_VAL_API_BASE=http://127.0.0.1:8766 npx vite --host 127.0.0.1 --port 5173 --strictPort > $S/vite.log 2>&1 &)
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && break; sleep 0.5; done
"$BRAVE" --headless=new --no-sandbox --no-first-run --no-default-browser-check \
  --disable-background-networking --disable-component-update --disable-sync \
  --user-data-dir=$S/profile --disable-web-security \
  --use-fake-device-for-media-stream --use-fake-ui-for-media-stream \
  --autoplay-policy=no-user-gesture-required --remote-debugging-port=9555 about:blank > $S/brave.log 2>&1 &
BRAVEPID=$!
sleep 2
OUTS=()
for i in ${=SESSIONS}; do
  node $D/voice_bench.mjs 9555 $D/voice-bench-plan.json $i $S/session-$i.json
  cp $S/session-$i.json $D/voice-bench-$LABEL-session-$i.json
  OUTS+=($D/voice-bench-$LABEL-session-$i.json)
done
kill $BRAVEPID 2>/dev/null
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null
kill $SERVICE 2>/dev/null; sleep 2
kill $MEMORY 2>/dev/null
uv run --project $ROOT python $D/voice_bench_extract.py $CONDITION $LABEL $D/service-$LABEL.log $D/memory-$LABEL.tsv ${OUTS[@]} | cut -c1-200
echo "DONE $LABEL $(date +%H:%M:%S)"
