"""Signal properties of a generated WAV, measured from the waveform itself.

Clipping, silence and duration are properties of the signal, not of the words —
so none of them is inferred from a transcript. The thresholds are stated here,
before any file is read, and the measured values are reported beside them so the
interpretation can be checked rather than taken.
"""

from __future__ import annotations

import json
import sys
import wave

import numpy as np

#: Stated before measuring.
#:
#: `CLIP_LEVEL` — |x| at or above this counts as at-or-near full scale. A model
#: that never approaches full scale has headroom; one that sits there is clipped.
#: `CLIP_FRACTION_MAX` — more than this share of samples at full scale is severe
#: clipping rather than an occasional transient.
#: `SILENCE_LEVEL` / `SILENCE_SECONDS_MAX` — a contiguous run quieter than this,
#: longer than this, **inside** the utterance is an unintended gap. Leading and
#: trailing quiet are normal and are reported separately rather than failed.
#: `DURATION_*` — a band wide enough for ordinary pacing and narrow enough that a
#: collapse (a fragment) or a runaway (repetition) falls outside it.
CLIP_LEVEL = 0.999
CLIP_FRACTION_MAX = 0.005
SILENCE_LEVEL = 0.01
SILENCE_SECONDS_MAX = 2.0
DURATION_SECONDS_MIN = 2.0
DURATION_SECONDS_MAX = 30.0


def measure(path: str, words: int) -> dict[str, object]:
    with wave.open(path, "rb") as reader:
        channels = reader.getnchannels()
        rate = reader.getframerate()
        width = reader.getsampwidth()
        frames = reader.getnframes()
        raw = reader.readframes(frames)

    audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    duration = len(audio) / rate

    loud = np.abs(audio)
    at_full_scale = int(np.count_nonzero(loud >= CLIP_LEVEL))
    clip_fraction = at_full_scale / max(len(audio), 1)

    quiet = loud < SILENCE_LEVEL
    # Longest contiguous quiet run, and where it sits.
    longest, longest_at, run, run_start = 0, 0, 0, 0
    for index, is_quiet in enumerate(quiet):
        if is_quiet:
            if run == 0:
                run_start = index
            run += 1
            if run > longest:
                longest, longest_at = run, run_start
        else:
            run = 0
    leading = int(np.argmax(~quiet)) if (~quiet).any() else len(audio)
    trailing = len(audio) - (int(np.argmax(~quiet[::-1])) if (~quiet).any() else 0)
    interior = longest_at > leading and (longest_at + longest) < trailing

    interior_silence = longest / rate if interior else 0.0
    expected = words / 3.0, words / 1.4  # ordinary English pacing, words per second

    checks = {
        "duration_in_band": DURATION_SECONDS_MIN <= duration <= DURATION_SECONDS_MAX,
        "no_severe_clipping": clip_fraction <= CLIP_FRACTION_MAX,
        "no_long_interior_silence": interior_silence <= SILENCE_SECONDS_MAX,
        "duration_plausible_for_word_count": expected[0] * 0.5 <= duration <= expected[1] * 2.0,
        "audio_is_readable": len(audio) > 0,
        "single_channel": channels == 1,
    }
    return {
        "path": path,
        "thresholds": {
            "clip_level": CLIP_LEVEL,
            "clip_fraction_max": CLIP_FRACTION_MAX,
            "silence_level": SILENCE_LEVEL,
            "interior_silence_seconds_max": SILENCE_SECONDS_MAX,
            "duration_seconds_min": DURATION_SECONDS_MIN,
            "duration_seconds_max": DURATION_SECONDS_MAX,
        },
        "measured": {
            "sample_rate": rate,
            "channels": channels,
            "sample_width_bytes": width,
            "samples": len(audio),
            "duration_seconds": round(duration, 3),
            "peak_amplitude": round(float(loud.max()) if len(audio) else 0.0, 6),
            "rms_amplitude": round(float(np.sqrt((audio**2).mean())) if len(audio) else 0.0, 6),
            "samples_at_or_near_full_scale": at_full_scale,
            "fraction_at_or_near_full_scale": round(clip_fraction, 8),
            "longest_near_silent_run_seconds": round(longest / rate, 3),
            "longest_near_silent_run_starts_at_seconds": round(longest_at / rate, 3),
            "longest_near_silent_run_is_interior": bool(interior),
            "interior_silence_seconds": round(interior_silence, 3),
            "leading_silence_seconds": round(leading / rate, 3),
            "trailing_silence_seconds": round((len(audio) - trailing) / rate, 3),
            "word_count": words,
            "expected_duration_band_seconds": [round(expected[0], 2), round(expected[1], 2)],
        },
        "checks": checks,
        "verdict": "PASS" if all(checks.values()) else "FAIL",
    }


if __name__ == "__main__":
    print(json.dumps(measure(sys.argv[1], int(sys.argv[2])), indent=1))
