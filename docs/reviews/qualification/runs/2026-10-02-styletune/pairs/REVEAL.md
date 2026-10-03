# Reveal — models and timings (harness receipt on the loopback, not desktop display)

| prompt | A | B | first visible s (A / B) | complete s (A / B) | chars (A / B) |
|---|---|---|---|---|---|
| P1 | styletune | gptoss | 1.901 / 5.665 | 4.305 / 7.376 | 541 / 513 |
| P2 | gptoss | styletune | 6.298 / 1.787 | 6.898 / 3.11 | 273 / 429 |
| P3 | styletune | gptoss | 1.645 / 22.531 | 4.524 / 24.779 | 647 / 627 |
| P4 | styletune | gptoss | 1.744 / 16.04 | 2.541 / 17.044 | 228 / 400 |
| P5 | styletune | gptoss | 1.686 / 9.986 | 7.261 / 14.605 | 1467 / 1406 |
| P6 | styletune | gptoss | 1.645 / 21.686 | 7.014 / 27.129 | 1384 / 1242 |
| P7 | gptoss | styletune | 9.476 / 1.65 | 17.113 / 2.127 | 2288 / 102 |
| P8 | gptoss | styletune | 6.961 / 1.634 | 7.519 / 2.298 | 213 / 173 |

**gptoss** (W1-gptoss, order forward): routes seen ['gpt-oss-20b-mxfp4-mlx-lmstudio-partner']; prime {"at": 1790996959.689, "primed": true, "outcome": "established", "slug": "gpt-oss-20b-mxfp4-mlx-lmstudio-partner", "engine": "mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0", "boundary_tokens": 5790, "boundary_sha256": "a52ae96b6cd6cabbb41bcea35283e7021009bba0e9cc02788a2399d234ae6e24", "prime_tokens": 5801, "model_call_id": "01a0ffbc-d1c1-732d-b754-cdc0bd45d02f", "seconds": 7.639}

**styletune** (W2-styletune, order forward): routes seen ['gemma-4-26b-a4b-styletune-v2-q4km-llamacpp-typed-experiment']; prime {"at": 1791003038.701, "primed": true, "outcome": "established", "slug": "gemma-4-26b-a4b-styletune-v2-q4km-llamacpp-typed-experiment", "engine": "llama.cpp", "boundary_tokens": 5824, "boundary_sha256": "", "prime_tokens": 5832, "model_call_id": "01a10019-93e0-7d17-b0af-45fdb5d15f87", "seconds": 8.323}
