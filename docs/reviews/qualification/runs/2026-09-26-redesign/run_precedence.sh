#!/bin/zsh
# Owner precedence on the real service, software player — release-gaps order §3.
# Usage: run_precedence.sh CASE on|off FIRST SECOND TRIGGER [TAIL_S] [evict]
set -u
CASE=$1; SWITCH=$2; FIRST=$3; SECOND=$4; TRIGGER=$5; TAIL=${6:-45}; EVICT=${7:-}
ROOT=/Users/josepharmand/Projects/val
D=$ROOT/docs/reviews/qualification/runs/2026-09-26-redesign
cd $ROOT
export VAL_SCRATCH_MODEL_IDENTIFIER=openai/gpt-oss-20b VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low
unset VAL_SPECULATION VAL_ADAPTIVE_GRACE
if [[ "$SWITCH" == "on" ]]; then export VAL_OWNER_PRECEDENCE=on; else unset VAL_OWNER_PRECEDENCE; fi
echo "=== $CASE precedence=$SWITCH trigger=$TRIGGER $(date +%H:%M:%S)"
uv run --project $ROOT python $D/serve_variant.py > $D/service-precedence-$CASE.log 2>&1 &
SERVICE=$!
for i in $(seq 1 360); do curl -fsS http://127.0.0.1:8766/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -fsS http://127.0.0.1:8766/health >/dev/null || { echo "service did not start"; kill $SERVICE; exit 1; }
if [[ "$EVICT" == "evict" ]]; then export EVICT_BEFORE_SPEECH=1; else unset EVICT_BEFORE_SPEECH; fi
uv run python $D/precedence_drive.py "$CASE" $D/precedence-$CASE.json "$FIRST" "$SECOND" "$TRIGGER" $TAIL | cut -c1-600
kill $SERVICE 2>/dev/null; sleep 2
uv run python $D/precedence_extract.py $CASE $D/precedence-$CASE.json $D/service-precedence-$CASE.log | cut -c1-1500
echo "DONE $(date +%H:%M:%S)"
