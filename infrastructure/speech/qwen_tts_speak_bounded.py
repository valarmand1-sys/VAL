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
is about three times her ordinary duration); only a runaway reaches it, and when one does
it is said on stderr. Production does not spawn this file; the original runner is untouched.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

#: Seconds allowed whatever the text (a greeting is short; the bound must not clip it).
MIN_SECONDS = 4.0
#: A deliberately slow pace: a segment is never cut while it is still being spoken.
SLOWEST_CHARS_PER_SECOND = 5.0
CODEC_TOKENS_PER_SECOND = 12.5


def max_speech_tokens(text: str) -> int:
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
                produced += float(getattr(audio, "size", len(audio))) / float(rate)
            yield item
        if produced >= 0.95 * bound / CODEC_TOKENS_PER_SECOND:
            print(
                f"val-tts-bound: a segment of {len(str(text))} characters reached its length "
                f"bound ({bound} tokens, {produced:.1f} s of audio)",
                file=sys.stderr,
                flush=True,
            )

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
