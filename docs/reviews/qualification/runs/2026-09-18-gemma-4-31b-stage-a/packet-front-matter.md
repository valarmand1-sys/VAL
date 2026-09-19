## How to read this packet

Every answer below is marked **ORIGINAL — EXACT PARITY**: all sixteen calls of the frozen suite ran once, in order, with exact preflight/server prompt-token parity, and none was rerun, retried or regenerated. Engineer text appears only under the label **PROVISIONAL ENGINEER NOTES**, separated from the raw answers; it is a reading against the frozen notes, not a score, and no PASS, FAIL, comparison or admission verdict is made anywhere in this packet.

**Primary qualitative review points, as ruled:** D1, D2, E2, F1, F2 — reconciling intersecting constraints, distinguishing evidence from inference, avoiding unsupported causal claims, interpreting capability-state metadata, preserving corrections, multi-turn continuity, operating without stored hidden thought, and persona without stage-direction leakage. A1, A2, B1, B2, C1, C2 and E1 follow in order.

**Record-state material on every call.** Each conversation was opened unassigned on the scratch store, so every call carried the Core record-state envelope as a user message immediately before the user's turn: no prior record, no project volumes, `capability_state: {books: unavailable}`, plus the current local time; persona v1.8 travelled whole as the system message. The envelope and the user's turn were joined into one wire message by the accepted local canonicalization. F2's supplied memo is the first user turn of F2, shown in full.

**Hidden thought.** Thinking was ON for every call. The server returned thought in its separate reasoning field on all sixteen; the adapter discarded it at the boundary. It appears nowhere in this packet, in the store, or in any later turn's history. Multi-turn tasks F1 and F2 ran on the visible answers alone.

## Qualification provenance

| | |
|---|---|
| Artifact | `lmstudio-community/gemma-4-31B-it-GGUF` @ `67a72ce46218`, `gemma-4-31B-it-Q6_K.gguf`, 25,201,483,424 bytes; expected and local SHA-256 both `3baf863a64af732e1fc597baf1c6ea147d4b1c30f5d1203e0f8018ad258bb1ac` |
| Served identity | `gemma-4-31b-it-q6_k`; GGUF v3, `gemma4`, Q6_K |
| Runtime | standalone llama.cpp server b10360 (`48d22e295`), Metal, loopback `127.0.0.1:8766`, keyed, one slot; read-only HTTP inspector, no SDK |
| Template | raw official `ae53464b…c6d4` != active; canonical official (one terminal LF removed) `6a1015c4…ab82` == active `6a1015c4…ab82` |
| Configured / actual context | 32,768 / 32,768 on every call; no substitution |
| Thinking | `thinking_enabled` true, `preserve_thinking` false, transmitted as `chat_template_kwargs` on every call |
| Sampling | temperature 1.0, top_p 0.95, top_k 64 — the official values, transmitted verbatim; no tuning |
| Output reserve | 6,144 |
| Benchmark | frozen commit `60b65b7`, twelve tasks, sixteen calls, file byte-identical to the freeze |
| Persona | v1.8, whole, as the system message |
| Local provider/API spend | $0 (every call $0 KNOWN); cloud $0 |
| Production route | unchanged; Sol remains the production Partner |
| Admission state | NOT_ADMITTED, pending owner/VAL qualitative review |

## Latency and hidden-thought volume

Median first visible text 109 s; median total 141 s; slowest call C1 at 449 s to first visible text. The server reports one completion figure per call and no separate reasoning count. By the server's own tokenizer, run read-only over the visible answers, 2,166 of the 20,528 completion tokens were visible text; the remaining 18,362 were hidden thought and its channel markers (derived, not provider-reported; `reasoning-token-derivation.json`). These are recorded facts about serving, not a verdict.

**COMPARABILITY NOTE.** GPT-OSS Stage A ran with no pinned sampling; Mistral ran at temperature 0.15; Gemma ran at its official 1.0 / 0.95 / 64 with thinking ON. Same frozen tasks and qualification structure, not an identical sampling or reasoning state.
