#!/bin/bash
# Launch contract for the Gemma 4 31B qualification server — owner ruling, 18 September 2026.
# llama.cpp stable b10360 (Homebrew). Loopback only, keyed from a private file (never printed,
# never the LM Studio token), no Web UI, no vision projector, one slot, an explicit 32,768
# context with automatic fitting off, the official template pinned by file
# (google/gemma-4-31B-it @ 842da3794eaa, SHA-256 ae53464bf3be25802b3a5b37def7fd89667067d7577049b3b2d74c4d8de4c6d4),
# reasoning extracted by the server's own Gemma 4 parser into reasoning_content.
# Thinking is NOT set here: Core declares it per request (chat_template_kwargs).
set -euo pipefail
REPO=/Users/josepharmand/Projects/val
MODEL="$HOME/Models/val-llamacpp/gemma-4-31B-it-Q6_K.gguf"
TEMPLATE="$REPO/docs/reviews/qualification/runs/2026-09-18-gemma-4-31b-contract-reassessment/official-chat_template@842da37.jinja"
exec llama-server \
  --model "$MODEL" \
  --alias gemma-4-31b-it-q6_k \
  --host 127.0.0.1 --port 8766 \
  --api-key-file "$HOME/.config/val/llamacpp.key" \
  --ctx-size 32768 --parallel 1 --fit off \
  --jinja --chat-template-file "$TEMPLATE" \
  --reasoning-format auto \
  --no-mmproj --no-webui \
  --no-context-shift \
  --metrics
