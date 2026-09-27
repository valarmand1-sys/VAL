#!/bin/zsh
# The desktop-integration run — release-gaps order of 26 September 2026, §6.
#
# The real service on the scratch store and port 8766 with the release settings, the
# real desktop frontend served by its dev server and pointed at it, headless Brave with
# a prepared WAV as its microphone, driven over the DevTools protocol. Production (port
# 8756, the live store, the installed desktop) is not touched; the model instance is
# the shared LM Studio one, so this never runs while he uses production Voice.
#
# Usage: run_desktop_integration.sh CASE LEAD_S PHRASE GAP_S PHRASE GAP_S ... PHRASE TAIL_S
set -u
CASE=$1; LEAD=$2; shift 2
ROOT=/Users/josepharmand/Projects/val
D=$ROOT/docs/reviews/qualification/runs/2026-09-26-redesign
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/b39b1991-6467-45ee-b07e-b4f8537d9790/scratchpad/desktop-$CASE
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
mkdir -p $S
cd $ROOT

echo "=== compose owner audio $(date +%H:%M:%S)"
uv run python $D/desktop_owner_audio.py $S/owner.wav $LEAD "$@" | cut -c1-400
TOTAL=$(python3 -c "import json;print(int(json.load(open('$S/owner.plan.json'))['total_s'])+4)")

echo "=== scratch service $(date +%H:%M:%S)"
export VAL_SCRATCH_MODEL_IDENTIFIER=openai/gpt-oss-20b VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low
unset VAL_SPECULATION VAL_ADAPTIVE_GRACE
if [[ "${PRECEDENCE:-off}" == "on" ]]; then export VAL_OWNER_PRECEDENCE=on; else unset VAL_OWNER_PRECEDENCE; fi
uv run --project $ROOT python $D/serve_variant.py > $D/service-desktop-$CASE.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE; exit 1; }

echo "=== desktop dev server $(date +%H:%M:%S)"
(cd $ROOT/apps/desktop && VITE_VAL_API_BASE=http://127.0.0.1:8766 npx vite --host 127.0.0.1 --port 5173 --strictPort > $S/vite.log 2>&1 &)
for i in $(seq 1 60); do curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && break; sleep 0.5; done

echo "=== brave $(date +%H:%M:%S)"
"$BRAVE" --headless=new --no-sandbox --no-first-run --no-default-browser-check \
  --disable-background-networking --disable-component-update --disable-sync \
  --user-data-dir=$S/profile --disable-web-security \
  --use-fake-device-for-media-stream --use-fake-ui-for-media-stream \
  --use-file-for-fake-audio-capture=$S/owner.wav%noloop \
  --autoplay-policy=no-user-gesture-required --remote-debugging-port=9444 about:blank > $S/brave.log 2>&1 &
BRAVEPID=$!
sleep 2
echo "=== drive for ${TOTAL}s $(date +%H:%M:%S)"
node $D/desktop_integration.mjs 9444 $TOTAL $S/dom.json
sleep 3
kill $BRAVEPID 2>/dev/null
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null
kill $SERVICE 2>/dev/null; sleep 2
echo "=== extract $(date +%H:%M:%S)"
uv run python $D/desktop_integration_extract.py $CASE $S $D/service-desktop-$CASE.log $D/desktop-integration-$CASE.json | cut -c1-2000
echo "DONE $(date +%H:%M:%S)"
