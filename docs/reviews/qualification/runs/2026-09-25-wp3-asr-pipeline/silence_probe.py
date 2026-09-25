"""What the recognizer produces from non-speech — WP3 Step B, §7.

A canonical owner message appeared in his run containing `Hello.`, which he never
said. The retained records place its audio in a stretch where Val was not speaking
and he reports he was not either. So the question is what the production recognizer
does when it is handed material that is not speech.

Driven exactly as the application drives it: same pinned whisper.cpp, same admitted
models, same helper, same endpoint configuration. **No owner audio.** The material
is generated here — digital silence, and low-level noise at a few amplitudes — and
nothing is persisted but the numbers.

The point is not to blacklist a word. It is to find out whether the VAD's own
evidence can tell a hallucination from speech, and at what threshold.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from pipeline_probe import BLOCK, ENDPOINT, HERE, SAMPLE_RATE, blocks_of, listen, read_fixture

RNG = np.random.default_rng(20260925)


def noise(seconds: float, amplitude: float) -> np.ndarray:
    return (RNG.standard_normal(int(SAMPLE_RATE * seconds)) * amplitude).astype(np.float32)


def silence(seconds: float) -> np.ndarray:
    return np.zeros(int(SAMPLE_RATE * seconds), dtype=np.float32)


def a_brief_word(fixture: np.ndarray, seconds: float) -> np.ndarray:
    """A genuinely short piece of real speech, to check the rule is not too strict."""
    return fixture[: int(SAMPLE_RATE * seconds)]


def main() -> None:
    fixture = read_fixture()
    cases: dict[str, np.ndarray] = {
        "digital_silence_3s": silence(3.0),
        "noise_0.002_3s": noise(3.0, 0.002),
        "noise_0.01_3s": noise(3.0, 0.01),
        "noise_0.05_3s": noise(3.0, 0.05),
        "noise_0.05_with_gaps": np.concatenate(
            [noise(0.4, 0.05), silence(1.0), noise(0.4, 0.05), silence(1.0)]
        ),
        "real_speech_0.4s": np.concatenate([a_brief_word(fixture, 0.4), silence(1.5)]),
        "real_speech_0.8s": np.concatenate([a_brief_word(fixture, 0.8), silence(1.5)]),
        "real_speech_whole": fixture,
    }
    report: dict[str, object] = {
        "probe": "what the production recognizer produces from non-speech",
        "endpoint": ENDPOINT,
        "owner_audio_involved": False,
        "block_samples": BLOCK,
    }
    for name, material in cases.items():
        outcome = listen(blocks_of(material))
        report[name] = {
            "seconds_in": round(material.size / SAMPLE_RATE, 3),
            "peak": round(float(np.max(np.abs(material))), 4),
            "rms": round(float(np.sqrt(np.mean(material**2))), 5),
            **outcome,
        }
        got = report[name]
        print(
            f"{name:24s} utterances={got['utterances']} "  # type: ignore[index]
            f"starts={got['speech_starts']} text={got['transcript']!r}"  # type: ignore[index]
        )

    (HERE / "silence-probe.json").write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
