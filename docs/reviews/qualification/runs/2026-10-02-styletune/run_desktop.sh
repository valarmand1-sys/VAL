#!/bin/zsh
# Typed work through the real desktop frontend, in isolation — 3 October 2026 (owner order §7).
#   run_desktop.sh LABEL
# The integrated service (StyleTune V2 typed, GPT-OSS deep as `val-exp-prod`, regular Gemma
# Voice) on the scratch store and port 8766; the unmodified desktop source on its dev server
# pointed at it; headless Brave with a fake (silent) microphone, driven over CDP. Same guards
# as run_integrated.sh: refuses if production holds a model or a port; stops only its own.
set -u
LABEL=$1
ROOT=/Users/josepharmand/Projects/val-dev
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
O=$ROOT/docs/reviews/qualification/runs/2026-10-02-styletune
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/6ffd6307-c028-44d4-b53e-bcac2ca0d01b/scratchpad/desktop-$LABEL
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-prod
mkdir -p $S
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
for port in 8099 8766 5173 9445; do
  [[ -z $(lsof -nP -t -iTCP:$port -sTCP:LISTEN 2>/dev/null) ]] || { echo "port $port has a listener this run did not start: not starting"; exit 2; }
done
( while true; do printf "%s\t%s\t%s\n" "$(date +%s)" "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"; sleep 1; done ) > $O/memory-$LABEL.tsv &
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
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
(cd $ROOT/apps/desktop && VITE_VAL_API_BASE=http://127.0.0.1:8766 npx vite --host 127.0.0.1 --port 5173 --strictPort > $S/vite.log 2>&1 &)
for i in $(seq 1 80); do curl -fsS http://127.0.0.1:5173/ >/dev/null 2>&1 && break; sleep 0.5; done
"$BRAVE" --headless=new --no-sandbox --no-first-run --no-default-browser-check \
  --disable-background-networking --disable-component-update --disable-sync \
  --user-data-dir=$S/profile --disable-web-security \
  --use-fake-device-for-media-stream --use-fake-ui-for-media-stream \
  --autoplay-policy=no-user-gesture-required --remote-debugging-port=9445 about:blank > $S/brave.log 2>&1 &
BRAVEPID=$!
sleep 2
caffeinate -i node $O/desktop_typed.mjs 9445 $O/desktop-$LABEL.json 2>&1 | tee $O/bench-$LABEL.out
kill $BRAVEPID 2>/dev/null
for pid in $(lsof -nP -t -iTCP:5173 -sTCP:LISTEN 2>/dev/null); do kill $pid 2>/dev/null; done
OURS=""
for pid in $(lsof -nP -t -iTCP:8099 -sTCP:LISTEN 2>/dev/null); do owned_by_service $pid && OURS="$OURS $pid"; done
kill $SERVICE 2>/dev/null; sleep 3
for pid in ${=OURS}; do kill $pid 2>/dev/null; done
$LMS unload $EXP > /dev/null 2>&1
kill $MEMORY 2>/dev/null
echo "DONE $LABEL $(date +%H:%M:%S)"
