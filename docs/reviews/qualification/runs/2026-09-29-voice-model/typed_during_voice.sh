#!/bin/zsh
# A GPT-OSS request during Voice — VOICE_MODEL.md §10.7 (owner order, 29 September 2026, late).
#
# Runs beside run_voice_resident.sh voice_release … "0 3": waits for the SECOND Voice
# session (the plan's S4) to open on the scratch service, waits for its first two answers,
# then types one ordinary question into the FIRST session's conversation — sealed (it was
# spoken in), no longer live, so the turn is local-only and takes the Partner route: GPT-OSS
# loads beside the Voice model, answers, and the gateway releases it when the call settles.
# The typed request's wall times and its answer are kept; memory is sampled by the run.
set -u
LABEL=$1
O=/Users/josepharmand/Projects/val-dev/docs/reviews/qualification/runs/2026-09-29-voice-model
LOG=$O/service-$LABEL.log
PSQL=(/opt/homebrew/opt/postgresql@18/bin/psql -h localhost -p 5433 -d val_test -Atq)
until [[ -f $LOG && $(grep -c "POST /voice/sessions HTTP" $LOG) -ge 2 ]]; do sleep 1; done
echo "second Voice session open at $(date +%H:%M:%S.%N | cut -c1-12)"
FIRST=$($PSQL[@] -c "select id from conversations order by started_at asc limit 1")
echo "typing into the first (sealed, not live) conversation $FIRST"
# Two answers into the second session before typing, so the Voice turn that follows is ordinary.
until [[ $(grep -c "voice turn timeline" $LOG) -ge 8 ]]; do sleep 0.5; done
sleep 1
T0=$(python3 -c "import time; print(time.time())")
echo "typed request sent at $(date +%H:%M:%S.%N | cut -c1-12)"
RESPONSE=$(curl -s -m 300 -X POST http://127.0.0.1:8766/turns -H 'content-type: application/json' \
  -d "{\"content\": \"Typed while Voice is on: what is the capital of Portugal, in one sentence?\", \"conversation_id\": \"$FIRST\"}")
T1=$(python3 -c "import time; print(time.time())")
python3 - "$T0" "$T1" "$RESPONSE" > $O/typed-during-voice-$LABEL.json <<'EOF'
import json, sys
t0, t1, body = float(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
try:
    parsed = json.loads(body)
except Exception:
    parsed = {"raw": body[:2000]}
json.dump({"sent_at": t0, "answered_at": t1, "seconds": round(t1 - t0, 3), "response": parsed}, sys.stdout, indent=1)
EOF
echo "typed request answered in $(python3 -c "print(round($T1-$T0,2))") s; kept in typed-during-voice-$LABEL.json"
