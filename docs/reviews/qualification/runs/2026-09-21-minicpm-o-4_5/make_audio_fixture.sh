#!/bin/bash
# Case B's fixture: one deterministic local recording, made by this Mac.
#
# The Mac's own speech synthesis, at the 16 kHz mono the model's audio encoder
# (Whisper) expects. No cloud service is involved and nothing is downloaded.
# The semantic content is frozen in FROZEN_ACCEPTANCE_TEST.md; the sentences
# below must match it exactly. Natural pauses come from the punctuation.
set -euo pipefail
OUT="${1:?usage: make_audio_fixture.sh <output.wav>}"
say -v Daniel -r 145 \
  --data-format=LEI16@16000 \
  --file-format=WAVE \
  -o "$OUT" \
  "The lantern is beside the blue book. The number is forty-two. After breakfast, Mara will meet Daniel at the old stone bridge. She should bring the red envelope, not the green one."
echo "wrote $OUT"
