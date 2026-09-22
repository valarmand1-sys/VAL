#!/bin/bash
# Case B's fixture: one deterministic local recording, made by this Mac.
#
# The Mac's own speech synthesis, at the 16 kHz mono the model's audio encoder
# (Whisper) expects. No cloud service is involved and nothing is downloaded.
# The semantic content is frozen in FROZEN_ACCEPTANCE_TEST.md; the sentences
# below must match it exactly.
#
# The pauses are the ones the frozen definition permits: at a natural speaking
# rate the four sentences run to about 12 seconds, short of the 20-30 the
# definition requires, so three silences separate them. Corrected before any
# inference was run, and recorded: the information is untouched, only the
# spacing between sentences changes.
set -euo pipefail
OUT="${1:?usage: make_audio_fixture.sh <output.wav>}"
say -v Daniel -r 145 \
  --data-format=LEI16@16000 \
  --file-format=WAVE \
  -o "$OUT" \
  "The lantern is beside the blue book. [[slnc 3200]] The number is forty-two. [[slnc 3200]] After breakfast, Mara will meet Daniel at the old stone bridge. [[slnc 3200]] She should bring the red envelope, not the green one."
echo "wrote $OUT"
