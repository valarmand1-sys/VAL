#!/bin/bash
# Qwen3-Omni against the acceptance test frozen at commit 0d41337, run once.
#
# Deliberately unturned: no temperature, top-p, top-k or repeat-penalty is
# passed, so the model's own generation defaults apply. The only settings given
# are the context size, full Metal offload, and the media and prompt themselves.
# Nothing here is adjusted between cases or between runs.
set -uo pipefail

MODELS="$HOME/.val-models/Qwen3-Omni-30B-A3B-Instruct-GGUF"
LLM="$MODELS/Qwen3-Omni-30B-A3B-Instruct-Q4_K_M.gguf"
MMPROJ="$MODELS/mmproj-Qwen3-Omni-30B-A3B-Instruct-Q8_0.gguf"
FIX="/private/tmp/claude-501/-Users-josepharmand-Projects-val/6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/fixtures"
OUT="/private/tmp/claude-501/-Users-josepharmand-Projects-val/6dad0650-9c42-4a9a-80d9-cb88832215bf/scratchpad/qwen_results"
mkdir -p "$OUT"

# The frozen prompts, verbatim from FROZEN_ACCEPTANCE_TEST.md.
P_A='Report only what you can actually see in this image. Do not guess, do not interpret motives, and do not add anything that is not visible. Cover: how many people are present; what the child is wearing; what the people are doing; the setting; and any major visible continuity details.'
P_B='Report the substantive content of this recording. State the information it conveys. Do not add anything that was not said.'
P_C='Describe what happens in this video and the order in which it happens. Report only what is visible.'

COMMON=(-c 16384 -ngl 99)

run_case () {
  local name="$1" flag="$2" media="$3" prompt="$4"
  echo "=== $name: $flag $(basename "$media")"
  local start end code
  start=$(date +%s.%N)
  llama-mtmd-cli -m "$LLM" --mmproj "$MMPROJ" "${COMMON[@]}" \
      "$flag" "$media" -p "$prompt" > "$OUT/$name.out" 2> "$OUT/$name.err"
  code=$?
  end=$(date +%s.%N)
  echo "exit=$code seconds=$(echo "$end - $start" | bc)" | tee "$OUT/$name.meta"
}

case "${1:-all}" in
  a) run_case case_a --image "$FIX/case_a_image.png" "$P_A" ;;
  b) run_case case_b --audio "$FIX/case_b_audio.wav" "$P_B" ;;
  c) run_case case_c --video "$FIX/case_c_video.mp4" "$P_C" ;;
  *) run_case case_a --image "$FIX/case_a_image.png" "$P_A"
     run_case case_b --audio "$FIX/case_b_audio.wav" "$P_B"
     run_case case_c --video "$FIX/case_c_video.mp4" "$P_C" ;;
esac
