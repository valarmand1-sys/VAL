#!/bin/zsh
# Milestone A measurement sequence (owner order of 26 September 2026): readiness, eviction, collisions.
set -u
cd /Users/josepharmand/Projects/val/docs/reviews/qualification/runs/2026-09-26-redesign
export VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low VAL_MEASURE_SERVE=$PWD/serve_variant.py
run() { # name plan lead pause
  echo "=== $1 lead=$3 pause=$4 $(date +%H:%M:%S)"
  VAL_MEASURE_PLAN=$PWD/$2 DRIVE_LEAD_S=$3 VAL_MEASURE_PAUSE_S=$4 uv run --project /Users/josepharmand/Projects/val python measure.py $1 /Users/josepharmand/Projects/val 0 $1.json 2>&1 | tail -2
}
echo "--- cold start: model unloaded"; lms unload openai/gpt-oss-20b 2>&1 | tail -1; sleep 2
run A2-cold-speech-during-warming plan_readiness.json 1.0 2.0
lms unload openai/gpt-oss-20b 2>&1 | tail -1; sleep 2
run A2-cold-speech-after-ready plan_readiness.json 45.0 2.0
run A2-warm-reopen-speech-during-warming plan_readiness.json 1.0 2.0
run A2-warm-reopen-speech-after-ready plan_readiness.json 12.0 2.0
run A2-eviction plan_eviction.json 12.0 2.0
run A3-collision-pause-0.3 plan_collision.json 12.0 0.3
run A3-collision-pause-2.0 plan_collision.json 12.0 2.0
echo "ALL-DONE $(date +%H:%M:%S)"
