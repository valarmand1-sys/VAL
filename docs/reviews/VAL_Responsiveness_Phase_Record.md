# The responsiveness phase — the Val Core stream carried to the API and the desktop; the unassigned-chat model; the classification-latency question — 11 September 2026

Phase 1 (`VAL_Core_Phase1_Record.md`) is closed as accepted: Lord Armand confirmed in the native desktop that Val answered normally, in persona, with the live cost display updating. This record covers the phase that followed his instruction of the same day.

## 1. Implementation completed

**The stream, through the API.** `POST /turns/stream` (`apps/api/src/val_api/streaming.py`) runs the same deliberated turn as `POST /turns` on a worker thread and answers with server-sent events: `delta` frames carrying Val's generated text, then one `settled` frame carrying the identical object the plain route returns — built by the same `render_turn` function from the same outcome — plus a `timing` object; a Restricted refusal arrives as `refused`, any other failure as `error`. The only sink the gateway ever forwards to is the one this route owns; the orchestrator withholds the reconciliation verdict block before that sink sees it; the route reads no provider. The plain route is unchanged.

**The stream, in the desktop.** `api.turnStream` reads the event stream through a tested frame parser (`sse.ts`); the App shows his message and Val's words as they arrive in a thread marked as in progress, then replaces them with the settled, persisted message. The moment the first words are painted is recorded on the animation frame after the first delta rendered (`firstVisibleMs`) — the nearest a script can stand to the screen. A timing line under the thread reports the last turn from three vantage points kept distinct: first words visible (interface), gateway first token (provider, as the gateway saw it), first delta at the client, and completion at the client.

**The unassigned-chat interaction model** (`scope.ts`, ruled 11 September 2026). Opening Val places him in a new unassigned conversation; New chat does the same and leaves any entered project; "No project" is gone as a sidebar filter and as a selector, with no replacement selector; entering a project from the sidebar is the one intentional act that makes the next new conversation project-scoped, and a second button offers a new conversation inside that project; a continued conversation sends only its id, so its record's attribution governs. The service contract is untouched: the desktop sends the existing explicit `no_project: true` for an unassigned conversation, `project` for an entered one, `conversation_id` for a continuation. No schema change, no migration.

**Not changed:** classification, strip, blind position, deliberation records, persistence, cost accounting, reservations, the persona, the plain route, the OpenAI adapter.

## 2. Tests

Pre-existing: **1,140 Python and 16 desktop tests pass unchanged; no pre-existing test file was touched** (`git status` on every test directory shows only new files). New: `apps/api/tests/test_turn_stream.py` (10) — deltas then the identical settled object; the settled event equals the plain route's shape; reservations and cost settle under streaming; a truncated stream is shown then settles truncated with no Val message persisted; a mid-stream failure settles unanswered with the cost recorded unknown; a Restricted refusal arrives as an event without echoing the credential; the verdict block never reaches the stream even when the marker is split across deltas, and the streamed prose equals the persisted message; a non-streaming adapter answers through the same route with no deltas; the desktop's default payload creates a null-project conversation; intentional project entry attributes. `apps/desktop/src/scope.test.ts` (7) — launch defaults to unassigned with no selection; New chat defaults to unassigned; no selector is required; the previously entered project does not carry into a new chat; entering a project scopes a new conversation; an existing conversation sends only its id; the service's null semantics are untouched. `apps/desktop/src/sse.test.ts` (3) — frames parsed in order and at every chunk boundary; the streamed text equals the settled text; a partial frame is held and reported. Totals: **1,150 Python, 28 desktop.** Lint, types, dependency direction, pin scan and scope check green.

## 3. Latency measurements

Two live turns through `POST /turns/stream` from a byte-granular Python client on this machine, in one new unassigned conversation labelled as an engineering verification (`01a09264-534e-7e17-8c54-ac991195c686`; not gate evidence). Cost stated before running: under $0.15; measured **$0.0730** (turn 1 $0.06487, turn 2 $0.00811).

| Vantage | Turn 1 (fresh conversation, persona cache written afresh) | Turn 2 (same conversation, cache warm) |
|---|---|---|
| Classification call (serial, before the partner call) | 1,624 ms | 1,674 ms |
| **Time-to-first-token** — gateway `first_output_ms` (provider's first generated-text delta) | 3,653 ms into the partner call | 527 ms into the partner call |
| Partner call complete — gateway `latency_ms` | 4,365 ms | 1,427 ms |
| API first delta handed to the response (from request start) | 5,338 ms | 2,241 ms |
| **First delta at the client** (from request sent) | 5,352 ms | 2,245 ms |
| **Total completion at the client** | 6,076 ms | 3,161 ms |
| Deltas | 13 | 8 |
| Streamed text equals settled text | claimed "yes" by the measuring client — see the correction below | as turn 1 |

**Correction, later on 11 September 2026.** The Python client that took these two measurements decoded the event stream one byte at a time with decoding errors ignored, which dropped multi-byte characters (Val's dashes) from both the deltas and the settled JSON it compared; its equality check therefore compared two equally damaged strings, and turn 2's reply, which contains an em-dash, was recorded by it without the dash. The timing figures are unaffected (they do not depend on decoding). The equality claim for these turns is withdrawn as evidence from this client and rests instead on the deterministic tests (`test_turn_stream.py`, including the multi-byte case added on finding this) and on the corrected-client turn recorded in `VAL_Persona_v1.5_Verification.md` §5, where streamed text, settled event and persisted row were byte-equal (that reply had no multi-byte characters; the multi-byte case is the deterministic test's). The desktop's own decoder is a streaming `TextDecoder` and was never affected.

Which of the three governing figures each vantage supplies:
- **Time-to-first-token — produced.** 527 ms on the warm turn, 3,653 ms on the turn that paid the persona cache write (Opus 5 with a 6,000-token prefix to cache).
- **Time-to-first-generated-text-visible-in-the-native-UI — NOT produced by me.** The desktop now measures its own first-paint moment and displays it, but that is a script's view of the frame after render, in whichever window runs it; the governing figure is what Lord Armand sees in the native window, and it remains **OPEN** (§6).
- **Total completion — produced at the provider (gateway latency), at the service (`api_total_ms`) and at the client (`client_total_ms`)**, kept distinct above; the user-visible completion is likewise his to observe.

**What the arithmetic says about the target.** On a warm turn the first delta reached the client 2.25 s after the request was sent: 1.67 s of serial classification, 0.53 s of provider time to first token, and about 50 ms of everything else (service, loopback, framing). Streaming has removed the wait for full generation (previously the whole 1.4–3 s partner call, or 8–22 s on the longer turns of the morning), but the approximately 1–2 s target for Val's first words cannot be met on ordinary turns while a 1.2–1.9 s classification call runs serially before the partner call — even an instantaneous first token would land at the top of the window. The first turn after an idle hour additionally pays the provider's cache write: 3.65 s to first token.

## 4. The classification-latency investigation — status: surfaced for ruling, nothing changed

Every classification call since 10 September (ten calls): latency 1,051–1,907 ms, median about 1,460 ms; input 718–1,000 tokens (the instruction, the data envelope, the message); output 18–30 tokens; about $0.0009 each. The latency is almost entirely the provider's time to first token plus request setup for an 800-token prompt on `haiku-4-5-20251001`; the 20-token verdict adds nothing measurable. Nothing within the existing behavioural contract reduces it: the call is already the smallest it can be for what it classifies; Haiku 4.5's caching is not verified in the registry and its documented minimum cacheable prefix exceeds the classifier instruction's length, so prefix caching is not available to it; streaming the classifier gains nothing for a 20-token reply. Every reduction available changes when classification occurs, what is classified, its route, or the meaning of an ordering, and is therefore presented rather than made:

1. **Speculative partner response in parallel with classification.** Start the partner call at the same moment as the classifier; hold its deltas (never present them) until the verdict is `not_consequential`, then release the stream; if the verdict is consequential, discard the speculative response and run the deliberated path as today. Saves the full classification time on ordinary turns (first words at roughly the provider's TTFT, about 0.5 s warm). Costs: a discarded partner call on every consequential turn (about $0.06–0.10 each; a few per day at current volume); and it changes what classification gates — today it gates whether the partner call is *made*, afterwards it would gate whether the response is *shown and persisted*. The ordering is meaningful (a response formed before the verdict, discarded on a consequential verdict, still leaves a `model_calls` row and a reservation). A ruling.
2. **A deterministic pre-filter before the classifier** — the classifier fast path of the turn-path inventory (§4), deferred on 10 September until the fifty hand-labelled classifications exist. An applicability rule; the fifty do not yet exist. A ruling, and not yet ripe.
3. **A faster classifier route** (a different configuration or effort). Requires a qualification matrix, excluded from this phase.
4. **A shorter classifier input** (trimming the instruction or the envelope). Changes what is classified against the contract of 3 September. A ruling.
5. **Accept the floor for ordinary turns** and report the target as met only for the first words after classification, which the ruling explicitly forbids.

Recommendation for consideration, not action: option 1 is the only one that reaches the target without touching the classifier's contract or route; its price is one discarded partner call per consequential turn and a recorded rule that the speculative call is never shown, persisted or reconciled unless the verdict permits.

## 5. Costs of the live verification calls

| Call | Cost |
|---|---|
| Turn 1 classification | $0.000896 |
| Turn 1 response (persona cache written) | $0.063970 |
| Turn 2 classification | $0.000863 |
| Turn 2 response (cache read) | $0.007248 |
| **Total** | **$0.072977** |

## 6. Native-desktop acceptance — OPEN, for Lord Armand

The native window was not driven (the limitation of Phase 1 holds: I cannot operate the Tauri window, and the service admits only the Tauri origins). The installed `/Applications/Val.app` was built on 7 September and does not contain this phase; the rebuilt bundle and its installation are recorded in §7.

Remaining for him to verify personally:
1. **Streaming is visible:** Val's words appear progressively, not all at once.
2. **First words visible within about 1–2 s:** the governing measurement. Procedure: open Val (a new unassigned conversation opens with no selection); send a short ordinary message, for example "Good evening, Val."; note the moment of pressing Send and the moment her first word appears; after the turn settles, read the timing line under the thread — "first words visible after X s" is the interface's own measurement of the frame painted after the first delta rendered, "gateway first token" is the provider figure, "complete after" is the settled arrival. Please report the three figures and whether the first word appeared before or after the timing line's figure by your own count. Two turns are worth taking: the first turn after an idle hour pays the persona cache write and will be slower; the second is the warm figure.
3. **The unassigned-chat model:** opening Val needs no project choice; New chat starts unassigned; the sidebar has no "No project"; entering a project and pressing "New conversation in …" scopes a conversation there; existing project conversations open with their attribution intact.
4. **Honesty under streaming:** the streamed text is replaced by the settled message; a truncated or failed turn shows the notice and no persisted Val message.

Expected result on the warm turn, from the client measurement: first words about 2.2 s after Send — outside the 1–2 s target — with the classification call the reason (§4). I do not claim the responsiveness target demonstrated.

## 7. Build and installation

`npm run tauri build` in `apps/desktop` (the interface is compiled into the binary) produced `src-tauri/target/release/bundle/macos/Val.app` at 16:36, 11 September 2026, containing the streaming client. The previously installed bundle, built 7 September, was moved to `/Applications/Val (built 2026-09-07).app`, and the new bundle was copied to `/Applications/Val.app`; the app was not running at the time. Commit and CI: recorded in the evidence index §45 and below.
