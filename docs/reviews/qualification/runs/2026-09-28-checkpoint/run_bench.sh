#!/bin/zsh
# One Voice bench run — remaining latency work, 28 September 2026 (§5, §6, §8).
#
# The code under test is this worktree (`val-dev`, branch latency-2026-09-28), served by
# the scratch service on port 8766 against the scratch store, every GPT-OSS
# configuration addressing the EXPERIMENT instance `val-exp-gpt-oss-20b` (the clone on
# the hook's allowlist). The desktop frontend is served from the main checkout: this
# candidate changes nothing under apps/desktop (diff against master empty, checked at
# each run), and the worktree has no node_modules. The instance is reloaded before each
# run, so every condition starts from an empty prompt cache. Production's service,
# store, desktop and model instance are not touched, and the run refuses to start if
# production Voice has been used since the last check.
#
# Usage: run_bench.sh candidate|prior|baseline RUN_LABEL "SESSION INDEXES"
#   candidate: renewal + divergence checkpoint + split record state + combined
#              continuations, with the 27 September switches;
#   prior:     the 27 September candidate's switches and renewal, nothing new switched on;
#   baseline:  every switch unset, the engine as shipped (renewal and divergence off).
set -u
CONDITION=$1; LABEL=$2; SESSIONS=${3:-"0 1 2 3 4"}
ROOT=/Users/josepharmand/Projects/val-dev
DESKTOP=/Users/josepharmand/Projects/val/apps/desktop
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/b39b1991-6467-45ee-b07e-b4f8537d9790/scratchpad/bench-$LABEL
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-gpt-oss-20b
CLONE=$HOME/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal
PRODUCTION_VOICE_SESSIONS=16
mkdir -p $S
cd $ROOT
[[ $(grep -c "POST /voice/sessions HTTP" /opt/homebrew/var/log/val/api.log) == $PRODUCTION_VOICE_SESSIONS ]] || { echo "production Voice has been used: not starting"; exit 3; }
[[ $(git diff master -- apps/desktop | wc -l | tr -d ' ') == 0 ]] || { echo "apps/desktop differs from master: not starting"; exit 2; }
case $CONDITION in
  candidate) RENEW=true; DIVERGE=true ;;
  prior) RENEW=true; DIVERGE=false ;;
  baseline) RENEW=false; DIVERGE=false ;;
  *) echo "unknown condition $CONDITION"; exit 2 ;;
esac
printf '{\n  "model_paths": ["%s"],\n  "renewal": %s,\n  "divergence_checkpoint": %s\n}\n' "$CLONE" "$RENEW" "$DIVERGE" > $HOME/.lmstudio/val-cache-renewal.json
unset VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_EXPERIMENT_ENVELOPE_IN_SYSTEM VAL_COMBINE_CONTINUATIONS
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP
case $CONDITION in
  candidate) export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on \
      VAL_REQUEST_CONSTRUCTION=split_state VAL_OWNER_PRECEDENCE=on VAL_TTS_LENGTH_BOUND=on \
      VAL_COMBINE_CONTINUATIONS=on ;;
  prior) export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_ADAPTIVE_ENDPOINT=on \
      VAL_REQUEST_CONSTRUCTION=envelope_in_system VAL_OWNER_PRECEDENCE=on VAL_TTS_LENGTH_BOUND=on ;;
  baseline) unset VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_ADAPTIVE_ENDPOINT VAL_REQUEST_CONSTRUCTION \
      VAL_OWNER_PRECEDENCE VAL_TTS_LENGTH_BOUND ;;
esac
echo "=== $LABEL ($CONDITION) $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps infrastructure | wc -l | tr -d ' ') hook=$(shasum -a 256 $HOME/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@34/lib/python3.11/site-packages/val_cache_renewal.py | cut -c1-12)"
$LMS unload $EXP > /dev/null 2>&1
$LMS load gpt-oss-20b-renewal --identifier $EXP -c 32768 --parallel 1 -y > $S/load.log 2>&1 || { echo "experiment load failed"; exit 1; }
tail -1 $HOME/.lmstudio/val-cache-renewal.log | cut -c1-160
( while true; do
    printf "%s\t%s\t%s\n" "$(date +%s)" \
      "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" \
      "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')"
    sleep 5
  done ) > $D/memory-$LABEL.tsv &
MEMORY=$!
HOOKLOG_FROM=$(wc -l < $HOME/.lmstudio/val-cache-renewal.log)
uv run --project $ROOT python $D/serve_experiment.py > $D/service-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE $MEMORY; exit 1; }
(cd $DESKTOP && VITE_VAL_API_BASE=http://127.0.0.1:8766 npx vite --host 127.0.0.1 --port 5173 --strictPort > $S/vite.log 2>&1 &)
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
  # The driver's own output is kept per session (28 September: C2a's S5 driver exited
  # without writing its file, and the reason was lost to the runner's tail).
  node $D/voice_bench.mjs 9555 $D/voice-bench-plan.json $i $S/session-$i.json > $D/driver-$LABEL-session-$i.log 2>&1
  echo "driver session $i exit $?"
  if [[ -f $S/session-$i.json ]]; then
    cp $S/session-$i.json $D/voice-bench-$LABEL-session-$i.json
    OUTS+=($D/voice-bench-$LABEL-session-$i.json)
  else
    echo "session $i: the driver wrote no file (see driver-$LABEL-session-$i.log); extracted without it"
  fi
done
kill $BRAVEPID 2>/dev/null
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null
kill $SERVICE 2>/dev/null; sleep 2
kill $MEMORY 2>/dev/null
tail -n +$((HOOKLOG_FROM + 1)) $HOME/.lmstudio/val-cache-renewal.log > $D/hook-$LABEL.log
# The run's store, preserved before any later run rebuilds it (28 September: C2a's
# attribution was lost that way). Local only: the repository ignores *.dump.
/opt/homebrew/opt/postgresql@18/bin/pg_dump -h localhost -p 5433 -d val_test -Fc -f $D/store-$LABEL.dump \
  && echo "store preserved: store-$LABEL.dump" || echo "STORE NOT PRESERVED for $LABEL"
uv run --project $ROOT python $D/voice_bench_extract.py $CONDITION $LABEL $D/service-$LABEL.log $D/memory-$LABEL.tsv ${OUTS[@]} | cut -c1-200
echo "DONE $LABEL $(date +%H:%M:%S)"
