#!/bin/zsh
set -u
D=/Users/josepharmand/Projects/val/docs/reviews/qualification/runs/2026-09-26-redesign
cd $D
echo "=== courtesy answers $(date +%H:%M:%S)"
(dropdb -h localhost -p 5433 --if-exists val_repro_test; createdb -h localhost -p 5433 val_repro_test) >/dev/null 2>&1
uv run --project /Users/josepharmand/Projects/val python $D/courtesy_answers.py $D/courtesy-answers.json 2> $D/courtesy-answers.stderr.log | cut -c1-300
export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_MEASURE_SERVE=$D/serve_variant.py
run() { echo "=== $1 lead=$3 pause=$4 $(date +%H:%M:%S)"; VAL_MEASURE_PLAN=$D/$2 DRIVE_LEAD_S=$3 VAL_MEASURE_PAUSE_S=$4 uv run --project /Users/josepharmand/Projects/val python $D/measure.py $1 /Users/josepharmand/Projects/val 0 $D/$1.json 2>&1 | tail -1; }
run A3b-collision-pause-0.3 plan_collision.json 12.0 0.3
run A3b-collision-pause-2.0 plan_collision.json 12.0 2.0
run A2b-warm-reopen-speech-after-ready plan_readiness.json 12.0 2.0
echo "ALL-DONE $(date +%H:%M:%S)"
