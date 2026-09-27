"""The speech runner with a length bound per segment — candidate only (27 September 2026).

**What it corrects.** The runner lets every segment generate up to the library's declared
`max_tokens` (4,096 codec tokens, 327.7 s of audio at the codec's 12.5 per second). If the
model fails to emit its end of speech on one segment it keeps generating: in the 27
September bench one segment of an ordinary answer played for exactly those 327.7 s, another
for 128 s until his next utterance stopped it, and every later segment of each answer
waited behind it. Nothing bounded it.

**The change.** This wrapper runs the **unmodified** `qwen_tts_speak.py` (same model, voice,
conditioning, sampling and pace) and only passes each `generate` call a `max_tokens` bound
proportional to the text it speaks: `MIN_SECONDS + len(text) / SLOWEST_CHARS_PER_SECOND`
seconds at the codec's 12.5 tokens per second (measured: the runaway's 7,864,320 samples at
24 kHz are 4,096 tokens exactly). Her ordinary pace is ~13 to 15 characters per
second, so a normal segment ends at its own end of speech far inside the bound (the bound
is about three times her ordinary duration); only a runaway reaches it.

**When the bound is reached** (remaining latency work, 27 September 2026, §6) the segment
is not reported as spoken. Generation has already stopped — the library ends its token
loop at `max_tokens` — and the pieces made so far have gone out, but the segment ends in
`SpeechLengthBoundReached` instead of a completion: the unchanged runner reports that as
a failed request (`{"ok": false, ...}`), the provider raises, and the delivery ends
FAILED with that reason. The segment's words are then not counted as delivered, the
desktop stops what it is playing, and the rest of her answer — whose full text stays in
the record — is shown as not spoken, through the presentation that already exists for
a voice failure. The worker itself carries on for the next answer. Production does not
spawn this file; the original runner is untouched.

`VAL_TTS_BOUND_FORCE_SECONDS`, when set, replaces the computed bound with that many
seconds. It exists for the forced-bound test only (the normal runs never reached the
bound) and is never set by the service.
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

#: Seconds allowed whatever the text (a greeting is short; the bound must not clip it).
MIN_SECONDS = 4.0
#: A deliberately slow pace: a segment is never cut while it is still being spoken.
SLOWEST_CHARS_PER_SECOND = 5.0
CODEC_TOKENS_PER_SECOND = 12.5


class SpeechLengthBoundReached(RuntimeError):  # noqa: N818 - the name says what happened
    """A segment's synthesis ran to its length bound without ending its speech."""


def max_speech_tokens(text: str) -> int:
    forced = os.environ.get("VAL_TTS_BOUND_FORCE_SECONDS")
    if forced:
        return math.ceil(float(forced) * CODEC_TOKENS_PER_SECOND)
    seconds = MIN_SECONDS + len(text or "") / SLOWEST_CHARS_PER_SECOND
    return math.ceil(seconds * CODEC_TOKENS_PER_SECOND)


def _bounded(model: object) -> object:
    original = model.generate  # type: ignore[attr-defined]

    def generate(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202 - the library's own signature
        text = kwargs.get("text", args[0] if args else "")
        if "max_tokens" not in kwargs:
            kwargs["max_tokens"] = max_speech_tokens(str(text))
        bound = kwargs["max_tokens"]
        produced = 0.0
        for item in original(*args, **kwargs):
            audio = getattr(item, "audio", None)
            rate = getattr(item, "sample_rate", None) or 24000
            if audio is not None:
                size = audio.size if hasattr(audio, "size") else len(audio)
                produced += float(size) / float(rate)
            yield item
        # A segment that ended its own speech stops well inside the bound (about a third
        # of it at her pace); one that reached the bound produced the bound's worth.
        if produced >= 0.95 * bound / CODEC_TOKENS_PER_SECOND:
            detail = (
                f"speech length bound reached: a segment of {len(str(text))} characters ran "
                f"to its bound ({bound} codec tokens, {produced:.1f} s of audio) without "
                "ending its speech; it is not counted as spoken"
            )
            print(f"val-tts-bound: {detail}", file=sys.stderr, flush=True)
            raise SpeechLengthBoundReached(detail)

    model.generate = generate  # type: ignore[attr-defined]
    return model


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mlx_audio.tts.utils as utils
    import qwen_tts_speak as runner

    load_model = utils.load_model
    utils.load_model = lambda *a, **k: _bounded(load_model(*a, **k))
    return runner.main()


if __name__ == "__main__":
    sys.exit(main())
