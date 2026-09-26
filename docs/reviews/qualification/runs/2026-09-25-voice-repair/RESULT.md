# Voice-mode repair — owner text, response time, text and speech together

Owner order "VOICE MODE REPAIR: PROMPT OWNER TEXT, FASTER RESPONSES, COORDINATED TEXT
AND SPEECH", 25 September 2026. Starting point `d134e34` (installed build and service
revision; the service code is `6cb3901`'s, `d134e34` changed only records). **WP3
remains PARTIAL. Physical acceptance is his.**

## 1. Baseline — three kinds of evidence, kept apart

**A. His earlier satisfactory short reply (OBSERVED by him, before the priming deploy).**
The answer was one segment. Under the old rule the desktop read the answer once every
segment had been synthesised — for a one-segment answer, the moment that segment was
ready — so the text appeared about when the voice started. DERIVED: the same rule
produces the failure below for any answer with more than one segment.

**B. His failing run (OBSERVED, service log and desktop panel).** Session
`a1cd4a6f…` (store `01a0dade-efbf…`), conversation `01a0dade-d67c…`, two turns:
"Good evening Val." and "I'm testing your voice model right now."

| | turn 1 | turn 2 |
|---|---|---|
| speech end (est.) → his words in thread (DOM) | 2,075 ms | 2,093 ms |
| of which: endpoint → final transcript | 120 ms | 168 ms |
| of which: endpoint → submitted (confirming silence + 1.1 s resume grace) | 1,247 ms | 1,299 ms |
| committed seen → DOM | 27 ms | 30 ms |
| request → first model output (persona prefix reused) | 1.58 s | 1.56 s |
| first output → first visible text (hidden MEDIUM reasoning) | 4.75 s | 9.11 s |
| first sentence synthesis (one-shot process) | 2.68 s | 2.48 s |
| his words → her playback start (panel) | 9,033 ms | 13,243 ms |
| segments in her answer | 2 | 3 |

**Deployment at the time (OBSERVED):** desktop `60e4e81` (built 10:20, the last desktop
change, so the intended build); service restarted 17:40 CDT on `6cb3901`, the priming
deployment; `openai/gpt-oss-20b` loaded at parallel 1, 32,768 context; both turns reused
the 5,048-token persona prefix (LM Studio's log, `5048/…`).

**Her voice and her text, per segment** (service clock; `speech_playbacks` rows are the
desktop's own reports, `speech_deliveries` the delivery's transitions; text time
DERIVED as delivery `completed` + at most one 120 ms poll + a ~15 ms read, since the old
build read her answer only when the turn was appended):

| | turn 1 (answer written 23:20:38.586) | turn 2 (answer written 23:21:05.548) |
|---|---|---|
| segment 1 playback | 41.320 – 42.916 | 07.847 – 08.885 |
| segment 2 playback | 43.914 – 45.595 (1.0 s silence before) | 10.786 – 13.346 (1.9 s silence before) |
| segment 3 playback | — | 13.896 – 16.938 (0.55 s silence before) |
| delivery completed | 44.037 | 13.920 |
| her text shown (DERIVED) | ~44.05 – 44.17: 2.7–2.9 s after she began, during segment 2 | ~13.93 – 14.06: 6.1–6.2 s after she began, during the last segment |

His report — about half-way through the first answer, near the end of the second —
matches the record. Her answer had been written **2.7 s and 2.3 s before her first
playback**, so it could have been shown with her voice. NOT RECORDED: the paint of her
text; the DOM moment of her text (the old panel measured only his words).

**C. Synthetic qualification (this pass).** Below, labelled as such.

## 2. The three causes, demonstrated

1. **His words.** The final transcript exists ~0.12–0.17 s after the endpoint (~1.0 s
   after speech end); the canonical message follows the resume grace (1.1 s) and is
   in the DOM 27–30 ms after the commit is seen. Nothing was shown in between: the
   settled text (`pending`) was never rendered, and the in-progress guess was shown
   only beside the composer.
2. **Her response.** The dominant part of the wait is MEDIUM's hidden reasoning before
   visible text (1.1–9.1 s, unchangeable under the order), then the first sentence's
   synthesis: 2.7–4.9 s one-shot, of which ~1.3 s was starting an interpreter and
   loading the model **for every sentence**. Later sentences queued behind the same
   serial per-process synthesis, which is what left silent gaps.
3. **Text after speech.** Cause stated in §1B: the answer was read at turn-append,
   after the whole delivery had been synthesised.

## 3. What changed

- **Provisional owner words** (`HeardWords`): the settled transcript is shown in the
  thread the moment the session carries it, marked "Heard — not yet your message",
  and removed when the canonical message is in the thread (never a second copy, never
  sent from there). The in-progress guess moves into the thread too, marked
  "Hearing…". Recognition, endpoint and resume grace are unchanged.
- **Her answer announced at commit** (`VoiceSessionView.answered`): the session names
  her message the moment Core has written it; the desktop reads it then.
- **Playback-linked presentation** (`spokenPresentation.ts`): her answer is shown one
  segment at a time, each at **its own playback start** (the `SpeechPlayer.onStarted`
  scheduling call), never by a timer or a speaking rate. Segments are exact contiguous
  slices, so the revealed text is always a prefix of the canonical message. Failure
  shows the rest at once, marked: interrupted, failed, stalled (12 s without playback
  progress while waiting for the next segment), or Voice ended. A segment of another
  answer is neither played nor revealed; every speech offer now names its answer
  (`SpeechOfferView.message_id`), because a delivery's `completed`/stop state is
  repeated until the next delivery replaces it and would otherwise land on the next
  answer. Ordinary text mode is unchanged.
- **Resident speech worker**: the same runner in `serve` mode — same model, settings,
  conditioning, code — started at Voice On and stopped when the last Voice session
  ends. A sentence arriving during the load waits for that load; any worker failure
  falls back to one-shot synthesis and the worker is not asked again.
- **Timing report**: provisional-words interval, per-segment text offsets and gaps.
- **Test hygiene found on the way**: tests leaving an API call unmocked were reaching
  the production service through Node's `fetch` (16 refused requests in the log, two
  of them mine). Every desktop test now starts with a `fetch` that refuses.

## 4. Before and after (synthetic, `measure.py` + `drive_session.py`)

The real service on the scratch store, the **production** model instance (parallel 1,
priming on), three Voice sessions × three turns each, the first turn one second after
Voice On; the same phrases, driver and machine for both builds. Before = clean
worktree of `d134e34`; after = this repair. $0: every call local.

| | before (n=9) | after (n=9) |
|---|---|---|
| speech end → his words shown (provisional) | not shown | **0.87–0.99 s** |
| speech end → his message canonical | 2.01–2.18 s | 2.01–2.15 s (unchanged, reported separately) |
| request → first model output | 1.66–1.92 s | 1.65–1.86 s |
| first sentence synthesis | 2.66–4.89 s (median 2.92) | **1.23–4.18 s (median 2.02)** |
| speech end → first playback | 8.81–15.32 s (median 10.29) | **6.35–12.45 s (median 9.13)** |
| her answer readable before her voice starts | 0 of 9 turns | **9 of 9** |
| text shown − segment playback start | −5.6 s … **+17.0 s** | **0 for all 28 segments** (the rule; DOM commit not included) |
| silent gaps between segments | 7 of 18, max 2.74 s, total 10.6 s | **2 of 19, max 0.45 s, total 0.6 s** |

Per turn position (speech end → first playback): first turn after Voice On
8.81 / 9.49 / 10.06 s → 6.35 / 7.66 / 8.92 s; later turns 9.74–15.32 s →
7.58–12.45 s. The remaining spread is the length of her hidden reasoning, which
varies with the answer and is the same in both builds (request → first visible text
4.0–8.1 s before, 2.8–7.7 s after, answers differing).

**Did not improve:** his canonical message (2.0–2.2 s — endpoint confirmation plus the
1.1 s resume grace, which the order keeps; shortening the grace would trade it for
split sentences) and the time to her first model output (already reused).

**Priming** retained unchanged: every turn reused the prefix (first output ≤ 1.92 s);
refreshes cost 0.46–0.51 s, and twice per condition 6.7–6.9 s when the runtime had
evicted the entry. Every refresh ended ≥ 3 s before the next request in these runs.

## 4a. When he speaks during a refresh (§6)

*Wording corrected 25 September 2026 (targeted voice latency order, §5): the first
version of this section overstated what the two probes show. What follows says what
each source establishes, and nothing more; the probes were not rerun.*

**Why the entry is evicted — from reading the engine's source, not from the probes**
(`mlx_engine/cache_wrapper.py` in `app-mlx-generate-mac14-arm64@34` and the vendored
`mlx_lm.models.cache.LRUPromptCache(max_size=10)`): snapshots are ordered by **insertion only** — a
read does not renew one — and a prime that finds its checkpoint cached stores nothing.
Each spoken turn inserts one conversation checkpoint and two full snapshots; when the
checkpoints outnumber the snapshots the oldest checkpoint goes, and that is the
persona's. It therefore lasts about five turns (typed turns count too) from when it was
last *computed*, whatever the refresh does; the refresh then pays the full prefill.

**Closing the client did not shorten the next request's wait** (`abort_probe.py`,
three repeats): a short request sent 2 s into an uncached ~6.6 s request waited
4.65–4.77 s for its first streamed event; with the first request's client killed just
before it was sent, 4.56–4.67 s. That is all this shows. Whether the server went on
computing the aborted request is not observed here: the figures are consistent with it,
but a direct claim about server-side execution needs evidence this probe does not
collect.

**Time to first streamed event behind a re-prime** (`collision_probe.py`, the
production instance while idle, three repeats). Both probes return at the first SSE
`data:` line without reading its payload, so every figure is **time to the first
streamed event**, not proven to be generated output (the JSON key
`seconds_from_his_request_to_first_output` overstates it). Each request asks for one
token, over a persona the runtime has never seen:

| his turn arrives | wait |
|---|---|
| persona evicted, no refresh | 6.57–6.58 |
| 0.5 s into a full re-prime | 6.24–6.27 |
| 2 s into it | 4.75–4.76 |
| 4 s into it | 2.74–2.76 |
| 6 s into it | 0.74–0.75 |
| persona held | 0.19–0.32 |

Within this probe, a request arriving during the re-prime never waited longer than
the same request with no re-prime, and waited less the longer the re-prime had run —
consistent with the re-prime doing the persona work the request would otherwise do.
**It does not establish** that maintenance never worsens a complete spoken turn:
one-token requests are not a Voice turn, and the probe measured neither recognition
nor synthesis under contention (the priming pass saw a full re-prime slow Whisper's
final decode by ~0.5 s). The policy stays as built — never started while any part of
his turn is under way, not cancelled once sent — because nothing measured here showed
cancellation shortening a wait, not because harm under contention has been excluded.

**Machine** (sampled once a second): the resident worker held 3,195 MB, the same as
each one-shot run (3,188 MB), for the length of the session instead of a sentence;
lowest free memory 32% (before 34%); swap 1,558 → 1,550 MB during the after run (it
grew 1,117 → 1,566 MB during the before run; cause not established). The worker was
gone after each session closed.

## 5. Covered and not covered

Covered: service and desktop-shaped client end to end (this record); the desktop's
reveal rule through the real `VoiceController`, `SpeechPlayer`, read rule and `Thread`
in jsdom (`spokenThread.test.tsx`, `spokenPresentation.test.ts`); the worker against a
real child process (`test_speech_warm_priority.py`); the session announcement and
release (gateway), the offer's message id (API). **Not covered:** the React paint and
sound leaving the speakers in the room — the panel now reports per-segment text
offsets and gaps for his physical test.

Files: `measure-before.json`, `measure-after.json` (every turn and segment),
`service-timelines.log` (the service's content-free timeline, prime and warm lines
from both runs; the full service logs were not kept), `tts-resident-probe.json`
(one-shot against resident synthesis of the same phrases, before implementation),
`abort-probe.json` and `collision-probe.json` (§4a).
