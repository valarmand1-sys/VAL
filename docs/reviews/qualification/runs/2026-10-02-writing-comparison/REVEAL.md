# Reveal — models and timings (harness receipt on the loopback, not desktop display)

| prompt | A | B | first visible s (A / B) | complete s (A / B) | chars (A / B) |
|---|---|---|---|---|---|
| P1 | gemma | gptoss | 1.909 / 5.665 | 4.39 / 7.376 | 544 / 513 |
| P2 | gemma | gptoss | 1.839 / 6.298 | 2.868 / 6.898 | 321 / 273 |
| P3 | gemma | gptoss | 1.668 / 22.531 | 5.669 / 24.779 | 756 / 627 |
| P4 | gemma | gptoss | 1.795 / 16.04 | 4.475 / 17.044 | 741 / 400 |
| P5 | gptoss | gemma | 9.986 / 1.747 | 14.605 / 7.53 | 1406 / 1448 |
| P6 | gptoss | gemma | 21.686 / 1.673 | 27.129 / 8.188 | 1242 / 1482 |
| P7 | gemma | gptoss | 1.692 / 9.476 | 3.153 / 17.113 | 320 / 2288 |
| P8 | gptoss | gemma | 6.961 / 1.682 | 7.519 / 1.993 | 213 / 71 |

**gptoss** (W1-gptoss, order forward): routes seen ['gpt-oss-20b-mxfp4-mlx-lmstudio-partner']; prime {"at": 1790996959.689, "primed": true, "outcome": "established", "slug": "gpt-oss-20b-mxfp4-mlx-lmstudio-partner", "engine": "mlx-llm-mac-arm64-apple-metal-advsimd@1.11.0", "boundary_tokens": 5790, "boundary_sha256": "a52ae96b6cd6cabbb41bcea35283e7021009bba0e9cc02788a2399d234ae6e24", "prime_tokens": 5801, "model_call_id": "01a0ffbc-d1c1-732d-b754-cdc0bd45d02f", "seconds": 7.639}

**gemma** (W1-gemma, order reverse): routes seen ['gemma-4-26b-a4b-q4km-llamacpp-voice']; prime {"at": 1790997699.103, "primed": true, "outcome": "established", "slug": "gemma-4-26b-a4b-q4km-llamacpp-voice", "engine": "llama.cpp", "boundary_tokens": 5824, "boundary_sha256": "", "prime_tokens": 5832, "model_call_id": "01a0ffc8-1a14-7b28-884c-2a4099cdb287", "seconds": 8.373}
