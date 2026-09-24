# Owner acceptance step A failed: the CSP refusal, and the two defects behind it

Owner acceptance, 24 September 2026. Voice reached `Voice Starting…`, macOS presented
the microphone prompt with the expected `NSMicrophoneUsageDescription` text, and
startup then failed with the visible error **`Not allowed by CSP`**, returning to
Voice Off.

Three separate defects, found in that order. The first is the one he saw; the second
and third were found by testing the fix rather than by reading it.

---

## 1. The violated directive and the blocked resource

**Directive:** `default-src 'self'` — as the fallback for the script source, because
the desktop's policy sets no `script-src`. The whole policy, verbatim from
`apps/desktop/src-tauri/tauri.conf.json`:

```
default-src 'self'; img-src 'self' data: blob: http://127.0.0.1:8756;
media-src 'self' blob: http://127.0.0.1:8756; style-src 'self' 'unsafe-inline';
connect-src 'self' http://127.0.0.1:8756
```

**Blocked resource:** the AudioWorklet processor module, fetched from a `blob:` URL
that the desktop constructed at runtime — `context.audioWorklet.addModule(blobUrl)`
in `apps/desktop/src/microphone.ts`, where the processor was a template string
wrapped in `URL.createObjectURL(new Blob([...], {type: "text/javascript"}))`.

`blob:` is permitted in this policy for `img-src` and `media-src` — attachment
previews and media playback — and **not** for scripts. A worklet module is a script,
so it fell back to `default-src 'self'`, which a blob URL does not satisfy.

### Reproduced under the application's exact policy

`serve_with_val_csp.py` reads the policy string out of `tauri.conf.json` and serves
this directory under it, so the probe runs under the real policy rather than a
paraphrase of it. `probe.js` attempts the same module load twice: once from a blob
URL, once from a same-origin file.

```
BLOB URL: blob:http://127.0.0.1:8791/d7e0abc4-e0ef-414a-839b-bc384191fac6
BLOB RESULT: REFUSED — AbortError: Unable to load a worklet's module.
SAME-ORIGIN RESULT: loaded
```

and, from the console, the refusal in full:

> Loading the script `blob:http://127.0.0.1:8791/d7e0abc4-…` violates the following
> Content Security Policy directive: **"default-src 'self'"**. Note that
> `'script-src-elem'` was not explicitly set, so `'default-src'` is used as a
> fallback. The action has been blocked.
>
> Failed to load worklet module script: blob:… (CORS or access check error)

**Labelled honestly:** this reproduction ran in the in-app browser, which is not
WKWebView. The policy, the URL scheme and the resource are identical, and the engines
agree on the rule; WebKit's wording for the same refusal is the `Not allowed by CSP`
he saw. One console line in the transcript — an inline-script refusal — is an artifact
of the probe page itself and not of the application, whose script is an external
bundle; the probe's script was moved to a file for exactly that reason.

---

## 2. The fix: stop needing the exception

The processor now lives in **`apps/desktop/public/pcm-worklet.js`**, which the
application serves at `/pcm-worklet.js`, and `microphone.ts` loads it from that path.

**No CSP change was made.** A same-origin script is what `default-src 'self'` already
permits.

**Why this does not widen egress.** The policy is byte-for-byte unchanged, so nothing
that was forbidden before is permitted now. The alternative — adding `script-src
'self' blob:` — would have permitted *any* blob-backed script this window could
construct, which is a real loosening of what an injected string could execute, for no
benefit beyond convenience. The module is fetched from the application's own bundle
over the Tauri origin: no remote origin, no new host, no change to `connect-src`, and
the loopback boundary to `127.0.0.1:8756` is exactly as it was. Nothing moved out of
the ruled desktop architecture: capture is still `getUserMedia` plus an AudioWorklet
in `apps/desktop`, still the only call site in the application, and the recognizer
still owns no device.

### Verified under the same policy, with the real built file

The application's actual `dist/` served under the same policy:

```json
{"moduleLoaded": true, "nodeConstructed": true, "csp": "satisfied by default-src self"}
```

The module loads and the `val-pcm` node constructs.

---

## 3. The second defect: the extracted file was not valid JavaScript

Loading the real built file is what found it. The processor had been a template
literal in TypeScript, and extracting it into a plain file left the interpolations
behind as literal text:

```
this.targetRate = settings.targetRate || ${TARGET_SAMPLE_RATE};
```

> SyntaxError: Unexpected token '{' (at http://127.0.0.1:8792/pcm-worklet.js:23)

Had the first fix shipped on its own, Voice would have failed again — with a
different error, in the same place. The fallbacks are now literal numbers, and two
tests hold the file to being parseable and to agreeing with the TypeScript constants,
so the file and the code cannot drift apart.

---

## 4. The third defect, and the one that matters most

**On the failure he hit, the microphone was not released deterministically.**

The order of operations in `open()` was: acquire the stream into a local variable →
create the context → load the module → *then* assign everything to the object. The
module load threw between the acquisition and the assignment, so `release()` in the
`catch` found `this.stream === null` and stopped nothing. The granted track was left
live, referenced only by a local variable that had gone out of scope — to be stopped
whenever the engine happened to collect it.

His screenshot showed no active microphone, and that is consistent with collection
having happened, or with the context closing. But **§1.3 says a failure moves toward
released, and "eventually, probably" is not that.** The honest answer to his question
5 is therefore:

> **No.** In the build he tested, the acquired stream was not deterministically
> released by the failure path. The indicator going dark was not guaranteed by the
> code, and that it appeared dark is not evidence that it was.

Each resource is now assigned to the object the instant it is created, so `release()`
can take down whatever exists no matter where the failure lands. A regression test
drives a platform whose `addModule` throws `Not allowed by CSP` **after** the device
has been granted, and asserts that every track is stopped, that the capture reports
not-live, and that `released` is reported **before** the failure — and reverting the
assignment order makes that test fail, which was run to check.

---

## 5. What was not changed

- **The CSP**: unchanged, byte for byte.
- **The capability file and the native bridge**: unchanged. Still one plugin, four
  permissions, no filesystem, no shell, no process, no HTTP.
- **The loopback boundary**: unchanged. `connect-src` still names only
  `http://127.0.0.1:8756`.
- **Every WP3 privacy invariant**: Voice remains owner-activated only and defaults
  Off; a failure ends Off or Muted and never reacquires; audio stays local and
  ephemeral; no cloud STT or TTS exists on any path; the model and Core cannot
  acquire a device — all still asserted by the tests that asserted them before, which
  were not touched.

---

## 6. State

Desktop suite **162** passed (three new regression tests, one of them proved by
mutation). Structural device-authority proofs unchanged and green. The bundle was
rebuilt and reinstalled, and acceptance returns to **step A only**.
