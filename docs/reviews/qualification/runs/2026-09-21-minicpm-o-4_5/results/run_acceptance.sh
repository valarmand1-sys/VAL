#!/bin/bash
# The MiniCPM-o 4.5 acceptance test, run once, from the frozen definitions.
#
# Local only: one binary on this machine, one artifact on this disk, no network
# call of any kind. Each case records its own latency and exit status.
set -uo pipefail

MODELS="$HOME/.val-models/MiniCPM-o-4_5-gguf"
# The fork OpenBMB's own cookbook points to, built from source: vanilla
# llama.cpp b10360 cannot load this model's projector at all.
MTMD="$HOME/.val-runtimes/llama.cpp-omni/build/bin/llama-mtmd-cli"
LLM="$MODELS/MiniCPM-o-4_5-Q4_K_M.gguf"
VISION="$MODELS/vision/MiniCPM-o-4_5-vision-F16.gguf"
AUDIO="$MODELS/audio/MiniCPM-o-4_5-audio-F16.gguf"
FIX="/private/tmp/claude-501/-Users-josepharmand-Projects-val/6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/fixtures"
OUT="/private/tmp/claude-501/-Users-josepharmand-Projects-val/6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/results"
mkdir -p "$OUT"

# The frozen prompts, verbatim from FROZEN_ACCEPTANCE_TEST.md.
P_A='Report only what you can actually see in this image. Do not guess, do not interpret motives, and do not add anything that is not visible. Cover: how many people are present; what the child is wearing; what the people are doing; the setting; and any major visible continuity details.'
P_B='Report the substantive content of this recording. State the information it conveys. Do not add anything that was not said.'
P_C='Describe what happens in this video and the order in which it happens. Report only what is visible.'

# The official sampling settings from OpenBMB's own llama.cpp guide. The context
# is larger than the guide's 4096 because the Case A image is 2752x1536 and the
# vision encoder slices a high-resolution image into many tiles; that is an
# operational allowance, not a change to any case's criteria.
COMMON=(-c 16384 --temp 0.7 --top-p 0.8 --top-k 100 --repeat-penalty 1.05 -ngl 99)

run_case () {
  local name="$1" projector="$2" flag="$3" media="$4" prompt="$5"
  echo "=== $name: $flag $(basename "$media") with $(basename "$projector")"
  local start end
  start=$(date +%s.%N)
  "$MTMD" -m "$LLM" --mmproj "$projector" "${COMMON[@]}" \
      "$flag" "$media" -p "$prompt" > "$OUT/$name.out" 2> "$OUT/$name.err"
  local code=$?
  end=$(date +%s.%N)
  echo "exit=$code seconds=$(echo "$end - $start" | bc)" | tee "$OUT/$name.meta"
}

case "${1:-all}" in
  a) run_case case_a "$VISION" --image "$FIX/case_a_image.png" "$P_A" ;;
  b) run_case case_b "$AUDIO"  --audio "$FIX/case_b_audio.wav" "$P_B" ;;
  c) run_case case_c "$VISION" --video "$FIX/case_c_video.mp4" "$P_C" ;;
  *) run_case case_a "$VISION" --image "$FIX/case_a_image.png" "$P_A"
     run_case case_b "$AUDIO"  --audio "$FIX/case_b_audio.wav" "$P_B"
     run_case case_c "$VISION" --video "$FIX/case_c_video.mp4" "$P_C" ;;
esac
