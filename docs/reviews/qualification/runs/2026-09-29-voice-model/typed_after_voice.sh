#!/bin/zsh
# The retained draft, sent when Voice is off — VOICE_MODEL.md §10.10.3 (30 September 2026).
#
# The bench's second session opens within two seconds of the first closing, so the
# in-run re-send met Voice on again and was rightly refused. This is the same request
# with no Voice session open at all: the scratch service alone (same store, same switches
# as the bench), the words the desktop would keep as a draft, one POST, one answer from
# the Partner route, and the service stopped. Production, its store and its models are
# not touched; GPT-OSS is addressed as the experiment instance.
set -u
LABEL=$1
ROOT=/Users/josepharmand/Projects/val-dev
D=$ROOT/docs/reviews/qualification/runs/2026-09-28-checkpoint
O=$ROOT/docs/reviews/qualification/runs/2026-09-29-voice-model
PSQL=(/opt/homebrew/opt/postgresql@18/bin/psql -h localhost -p 5433 -d val_test -Atq)
BODY='{"content": "Typed while Voice is on: what is the capital of Portugal, in one sentence?", "no_project": true}'
cd $ROOT
export VAL_EXPERIMENT_MODEL_IDENTIFIER=val-exp-hub VAL_EXPERIMENT_MODEL_KEY=gpt-oss-20b-renewal
export VAL_VOICE_MODEL=gemma-4-26b-a4b VAL_LLAMACPP_BASE_URL=http://127.0.0.1:8099/v1 VAL_VOICE_RELEASES_PARTNER=on
export VAL_ADAPTIVE_ENDPOINT=on VAL_VOICE_TURN_PREFILL=on
export VAL_LLAMACPP_API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(24))")
unset VAL_VOICE_EARLY_AUDIO VAL_FAST_ROUTE_TIERS VAL_TIER1_ROUTE VAL_SPECULATION VAL_ADAPTIVE_GRACE VAL_REQUEST_CONSTRUCTION VAL_OWNER_PRECEDENCE VAL_TTS_LENGTH_BOUND VAL_COMBINE_CONTINUATIONS VAL_ORDINARY_LOW VAL_EXPERIMENT_COGNITION
uv run --project $ROOT python $D/serve_experiment.py > $O/service-$LABEL.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
BEFORE=$($PSQL[@] -c "select count(*) from messages")
T0=$(python3 -c "import time; print(time.time())")
CODE=$(curl -s -m 300 -o $O/typed-after-voice-$LABEL.json -w '%{http_code}' -X POST http://127.0.0.1:8766/turns -H 'content-type: application/json' -d "$BODY")
T1=$(python3 -c "import time; print(time.time())")
AFTER=$($PSQL[@] -c "select count(*) from messages")
echo "no Voice session: HTTP $CODE in $(python3 -c "print(round($T1-$T0,2))") s; messages $BEFORE -> $AFTER"
python3 -c "import json; d=json.load(open('$O/typed-after-voice-$LABEL.json')); print(d.get('kind'), '|', (d.get('val_message') or {}).get('content') or d.get('error'))"
kill $SERVICE; sleep 2
$HOME/.lmstudio/bin/lms unload val-exp-hub >/dev/null 2>&1
echo "DONE $LABEL"
