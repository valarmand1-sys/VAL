#!/bin/zsh
# The repair check — 1 October 2026 — run_voice_resident.sh with the repair plan, this
# directory for output, and the corrected release's proposed switches. Original header:
# The resident-together check — 29 September 2026 (CHALLENGER.md §4 / VOICE_MODEL.md §10).
# Identical to run_voice.sh except that GPT-OSS is LOADED on the experiment instance before
# the run and kept resident throughout, as production would have it when Voice is turned on
# within an hour of typed work. Nothing else differs.
#
# The code under test is this worktree, served by the scratch service on port 8766 against
# the scratch store, through the real desktop frontend and player in headless Brave (only
# getUserMedia replaced). Spoken turns are pinned to the Voice model, which the service's
# own supervisor starts as a llama.cpp server on the loopback interface (port 8099, a
# throwaway key generated here and never printed). GPT-OSS is NOT loaded at the start: it
# is the fallback, addressed as the experiment instance, and is loaded only if a fallback
# happens. Recognition and speech synthesis run as in production. Production's service,
# store, desktop and models are not touched, and the run refuses to start if production
# Voice has been used since the last check.
#
# Usage: run_voice.sh voice|voice_prefill RUN_LABEL "SESSION INDEXES"
#   voice:          production's switches unset, the Voice model pinned for spoken turns;
#   voice_adaptive: the same, with the existing adaptive endpoint (VAL_ADAPTIVE_ENDPOINT);
#   voice_prefill:  voice_adaptive, with the turn's request prepared ahead of his words;
#   voice_early:    voice_prefill, with audio released early for complete utterances.
set -u
CONDITION=$1; LABEL=$2; SESSIONS=${3:-"0 1 2 3 4"}
ROOT=/Users/josepharmand/Projects/val-dev
# 30 September 2026 (§10.10): the desktop under test is this worktree's — it is part of the
# release now — not master's. The equality check with master is therefore gone.
DESKTOP=$ROOT/apps/desktop
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
O=$ROOT/docs/reviews/qualification/runs/2026-10-01-voice-repair
S=/private/tmp/claude-501/-Users-josepharmand-Projects-val/9b173baf-5584-48a8-a1fc-27ef2794b6ab/scratchpad/bench-$LABEL
BRAVE="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
LMS=$HOME/.lmstudio/bin/lms
EXP=val-exp-hub
CLONE=$HOME/.lmstudio/models/val-experiment/gpt-oss-20b-MXFP4-Q8-renewal
PRODUCTION_VOICE_SESSIONS=18
mkdir -p $S
cd $ROOT
[[ $(grep -c "POST /voice/sessions HTTP" /opt/homebrew/var/log/val/api.log) == $PRODUCTION_VOICE_SESSIONS ]] || { echo "production Voice has been used: not starting"; exit 3; }
case $CONDITION in
  voice|voice_adaptive|voice_prefill|voice_early|voice_release) ;;
  *) echo "unknown condition $CONDITION"; exit 2 ;;
esac
unset VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_EXPERIMENT_ENVELOPE_IN_SYSTEM VAL_COMBINE_CONTINUATIONS
export VAL_EXPERIMENT_MODEL_IDENTIFIER=$EXP
export VAL_EXPERIMENT_MODEL_KEY=gpt-oss-20b-renewal  # so the service can reload the instance (serve_experiment.py)
unset VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_ADAPTIVE_ENDPOINT VAL_REQUEST_CONSTRUCTION \
  VAL_OWNER_PRECEDENCE VAL_TTS_LENGTH_BOUND VAL_COMBINE_CONTINUATIONS VAL_ORDINARY_LOW VAL_EXPERIMENT_COGNITION
export VAL_VOICE_MODEL=gemma-4-26b-a4b
export VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
unset VAL_VOICE_TURN_PREFILL VAL_VOICE_EARLY_AUDIO VAL_VOICE_RELEASES_PARTNER
[[ $CONDITION == voice_prefill || $CONDITION == voice_early || $CONDITION == voice_release ]] && export VAL_VOICE_TURN_PREFILL=on
#   voice_release:  voice_prefill, and Voice On releases the Partner model (VAL_VOICE_RELEASES_PARTNER).
[[ $CONDITION == voice_release ]] && export VAL_VOICE_RELEASES_PARTNER=on
[[ $CONDITION == voice_early ]] && export VAL_VOICE_EARLY_AUDIO=on
[[ $CONDITION != voice ]] && export VAL_ADAPTIVE_ENDPOINT=on
# The corrected release's proposed settings (1 October 2026), unless REPAIR_SWITCHES=off.
if [[ ${REPAIR_SWITCHES:-on} == on ]]; then export VAL_OWNER_PRECEDENCE=on VAL_COMBINE_CONTINUATIONS=on VAL_CONVERSATION_GUIDANCE=on VAL_SPOKEN_NUMERALS=on; fi
echo "=== $LABEL ($CONDITION) $(date +%H:%M:%S) commit $(git rev-parse --short HEAD) dirty=$(git status --porcelain -- packages apps infrastructure | wc -l | tr -d ' ') hook=$(shasum -a 256 $HOME/.lmstudio/extensions/backends/vendor/_amphibian/app-mlx-generate-mac14-arm64@34/lib/python3.11/site-packages/val_cache_renewal.py | cut -c1-12)"
$LMS unload $EXP > /dev/null 2>&1
$LMS load gpt-oss-20b-renewal --identifier $EXP -c 32768 --parallel 1 -y > $O/lms-load-$LABEL.log 2>&1 || { echo "GPT-OSS did not load"; exit 1; }
pkill -f "llama-server.*--port 8099" 2>/dev/null
echo "resident before the run: LM Studio [$($LMS ps 2>/dev/null | awk 'NR>1 && NF {printf "%s ", $1}')] llama-server [$(pgrep -f 'llama-server' | wc -l | tr -d ' ')]"
( while true; do
    printf "%s\t%s\t%s\t%s\t%s\n" "$(date +%s)" \
      "$(memory_pressure | awk '/free percentage/ {gsub("%",""); print $NF}')" \
      "$(sysctl -n vm.swapusage | awk '{gsub("M","",$6); print $6}')" \
      "$(footprint -p $(pgrep -f 'llama-server.*--port 8099' | head -1) 2>/dev/null | awk '/Footprint:/ {print $(NF-5) $(NF-4); exit}')" \
      "$($LMS ps 2>/dev/null | awk 'NR>1 && NF {printf "%s,", $1}')"
    sleep 5
  done ) > $O/memory-$LABEL.tsv &
MEMORY=$!
HOOKLOG_FROM=$(wc -l < $HOME/.lmstudio/val-cache-renewal.log)
uv run --project $ROOT python $D/serve_experiment.py > $O/service-$LABEL.log 2>&1 &
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
PASS=0
for i in ${=SESSIONS}; do
  # The driver's own output is kept per session (28 September: C2a's S5 driver exited
  # without writing its file, and the reason was lost to the runner's tail). A session
  # run more than once keeps every pass (L2's first pass was overwritten by its second).
  PASS=$((PASS + 1)); N=$i; [[ $(echo ${=SESSIONS} | tr ' ' '\n' | grep -cx $i) -gt 1 ]] && N=$i-p$PASS
  node $D/voice_bench.mjs 9555 $O/repair-plan.json $i $S/session-$N.json > $O/driver-$LABEL-session-$N.log 2>&1
  echo "driver session $N exit $?"
  if [[ -f $S/session-$N.json ]]; then
    cp $S/session-$N.json $O/voice-bench-$LABEL-session-$N.json
    OUTS+=($O/voice-bench-$LABEL-session-$N.json)
  else
    echo "session $N: the driver wrote no file (see driver-$LABEL-session-$N.log); extracted without it"
  fi
done
kill $BRAVEPID 2>/dev/null
pkill -f "vite --host 127.0.0.1 --port 5173" 2>/dev/null
kill $SERVICE 2>/dev/null; sleep 3; pkill -f "llama-server.*--port 8099" 2>/dev/null
kill $MEMORY 2>/dev/null
tail -n +$((HOOKLOG_FROM + 1)) $HOME/.lmstudio/val-cache-renewal.log > $O/hook-$LABEL.log
# The run's store, preserved before any later run rebuilds it (28 September: C2a's
# attribution was lost that way). Local only: the repository ignores *.dump.
/opt/homebrew/opt/postgresql@18/bin/pg_dump -h localhost -p 5433 -d val_test -Fc -f $O/store-$LABEL.dump \
  && echo "store preserved: store-$LABEL.dump" || echo "STORE NOT PRESERVED for $LABEL"
uv run --project $ROOT python $D/voice_bench_extract.py $CONDITION $LABEL $O/service-$LABEL.log $O/memory-$LABEL.tsv ${OUTS[@]} | cut -c1-200
echo "DONE $LABEL $(date +%H:%M:%S)"
