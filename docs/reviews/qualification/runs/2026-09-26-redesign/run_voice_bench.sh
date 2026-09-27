#!/bin/zsh
# One Voice bench run: the isolated scratch service in one condition, the real desktop
# frontend, the controllable microphone, the three sessions in order — owner order of
# 27 September 2026, §6. Production (port 8756, the live store, the installed desktop) is
# not touched; the model instance is the shared one, so this never runs while he uses Voice.
#
# Usage: run_voice_bench.sh CONDITION RUN_LABEL [cold]
#   CONDITION: baseline (production settings) | candidate (the integrated candidate)
set -u
CONDITION=$1; LABEL=$2; COLD=${3:-}
ROOT=/Users/josepharmand/Projects/val
D=$ROOT/docs/reviews/qualification/runs/2026-09-26-redesign
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/b39b1991-6467-45ee-b07e-b4f8537d9790/scratchpad/bench-$LABEL
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
mkdir -p $S
cd $ROOT
unset VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_OWNER_PRECEDENCE VAL_ADAPTIVE_ENDPOINT VAL_REQUEST_CONSTRUCTION VAL_EXPERIMENT_ENVELOPE_IN_SYSTEM
export VAL_SCRATCH_MODEL_IDENTIFIER=openai/gpt-oss-20b
unset VAL_TTS_LENGTH_BOUND
if [[ "$CONDITION" == candidate* ]]; then
  export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on VAL_REQUEST_CONSTRUCTION=envelope_in_system VAL_OWNER_PRECEDENCE=on
fi
if [[ "$CONDITION" == "candidate_bound" ]]; then export VAL_TTS_LENGTH_BOUND=on; fi
echo "=== $LABEL ($CONDITION) $(date +%H:%M:%S)"
if [[ "$COLD" == "cold" ]]; then
  uv run python $D/evict_checkpoints.py > /dev/null 2>&1 && echo "persona checkpoints evicted"
fi
uv run --project $ROOT python $D/serve_variant.py > $D/service-bench-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE; exit 1; }
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
for i in 0 1 2; do
  node $D/voice_bench.mjs 9555 $D/voice-bench-plan.json $i $S/session-$i.json
  OUTS+=($S/session-$i.json)
done
kill $BRAVEPID 2>/dev/null
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null
kill $SERVICE 2>/dev/null; sleep 2
for i in 0 1 2; do cp $S/session-$i.json $D/voice-bench-$LABEL-session-$i.json; done
uv run python $D/voice_bench_extract.py $CONDITION $LABEL $D/service-bench-$LABEL.log ${OUTS[@]} | cut -c1-200
echo "DONE $LABEL $(date +%H:%M:%S)"
