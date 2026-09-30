#!/bin/zsh
# Voice has priority — VOICE_MODEL.md §10.10 (owner order, 30 September 2026).
#
# Runs beside run_voice_resident.sh voice_release … "0 3". During the FIRST Voice session,
# after two answers, it types one question into a separate conversation: the service must
# refuse it (409, voice_active) before writing or sending anything, the Voice model must
# stay where it is, and the spoken turns must go on unchanged. When that session ends
# (Voice off; GPT-OSS reloaded off the path), the same words are sent again — the draft,
# sent by hand — and must be answered by the Partner route, once. The driver's second
# session then turns Voice on with GPT-OSS resident and must show readiness truthfully.
set -u
LABEL=$1
O=/Users/josepharmand/Projects/val-dev/docs/reviews/qualification/runs/2026-09-29-voice-model
LOG=$O/service-$LABEL.log
PSQL=(/opt/homebrew/opt/postgresql@18/bin/psql -h localhost -p 5433 -d val_test -Atq)
OUT=$O/typed-priority-$LABEL.json
BODY='{"content": "Typed while Voice is on: what is the capital of Portugal, in one sentence?", "project": "Project Alpha"}'
now() { python3 -c "import time; print(time.time())"; }
until [[ -f $LOG && $(grep -c "POST /voice/sessions HTTP" $LOG) -ge 1 ]]; do sleep 1; done
until [[ $(grep -c "voice turn timeline" $LOG) -ge 2 ]]; do sleep 0.5; done
sleep 1
BEFORE=$($PSQL[@] -c "select count(*) from messages")
T0=$(now)
R1=$(curl -s -m 60 -o $O/typed-priority-$LABEL-during.json -w '%{http_code}' -X POST http://127.0.0.1:8766/turns -H 'content-type: application/json' -d "$BODY")
T1=$(now)
AFTER=$($PSQL[@] -c "select count(*) from messages")
echo "during Voice: HTTP $R1 in $(python3 -c "print(round($T1-$T0,3))") s; messages before/after $BEFORE/$AFTER"
until [[ $(grep -c "/close HTTP" $LOG) -ge 1 ]]; do sleep 0.5; done
sleep 2
T2=$(now)
R2=$(curl -s -m 300 -o $O/typed-priority-$LABEL-after.json -w '%{http_code}' -X POST http://127.0.0.1:8766/turns -H 'content-type: application/json' -d "$BODY")
T3=$(now)
FINAL=$($PSQL[@] -c "select count(*) from messages")
echo "after Voice ended: HTTP $R2 in $(python3 -c "print(round($T3-$T2,2))") s; messages now $FINAL"
printf '{"during_voice": {"sent_at": %s, "seconds": %s, "http": %s, "messages_before": %s, "messages_after": %s},\n "after_voice_ended": {"sent_at": %s, "seconds": %s, "http": %s, "messages_after": %s}}\n' \
  "$T0" "$(python3 -c "print(round($T1-$T0,3))")" "$R1" "$BEFORE" "$AFTER" \
  "$T2" "$(python3 -c "print(round($T3-$T2,3))")" "$R2" "$FINAL" > $OUT
echo "kept in $OUT"
