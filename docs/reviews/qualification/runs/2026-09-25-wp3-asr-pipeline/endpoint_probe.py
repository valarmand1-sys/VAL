"""Does unordered delivery also end utterances early? — WP3 repair pass §1.0, §2.1.

The acceptance record shows endpoints firing inside ordinary owner sentences: five
of five spoken turns were revised by a resume-merge that joined two halves of one
utterance. Two candidate causes, and they call for opposite repairs:

**(a) his pauses exceeded the 650 ms minimum silence** — which would justify the one
endpoint adjustment §2.1 authorises; or

**(b) unordered chunk delivery** — a silent block arriving early, while speech blocks
are still in flight, lengthens the silence run and trips the endpoint. If this is the
cause, adjusting the endpoint would be tuning against a broken pipeline.

So: the same audio, with an internal pause **shorter** than the configured minimum
silence, fed in order and out of order, counting endpoints.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

import numpy as np

from pipeline_probe import (
    BLOCK,
    ENDPOINT,
    FIXTURE,
    HERE,
    SAMPLE_RATE,
    blocks_of,
    listen,
    reordered,
)


def with_internal_pause(samples: np.ndarray, pause_ms: int) -> np.ndarray:
    """The utterance, cut in half, with a pause between the halves."""
    middle = samples.size // 2
    gap = np.zeros(int(SAMPLE_RATE * pause_ms / 1000), dtype=np.float32)
    return np.concatenate([samples[:middle], gap, samples[middle:]])


def main() -> None:
    with wave.open(str(FIXTURE), "rb") as handle:
        raw = handle.readframes(handle.getnframes())
    original = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0

    report: dict[str, object] = {
        "probe": "does unordered delivery end utterances early?",
        "endpoint": ENDPOINT,
        "note": (
            "A pause of 400 ms is comfortably under the configured 650 ms minimum "
            "silence, so a correctly ordered stream must NOT end the utterance there."
        ),
        "owner_audio_involved": False,
    }

    for pause_ms in (400, 500):
        material = with_internal_pause(original, pause_ms)
        blocks = blocks_of(material)
        report[f"pause_{pause_ms}ms"] = {
            "in_order": listen(blocks),
            "a_block_arrives_2_late": listen(reordered(blocks, 2)),
            "a_block_arrives_4_late": listen(reordered(blocks, 4)),
        }

    (HERE / "endpoint-probe.json").write_text(json.dumps(report, indent=1) + "\n")
    for key, value in report.items():
        if not isinstance(value, dict) or "in_order" not in value:
            continue
        print(key)
        for shape, outcome in value.items():
            print(
                f"  {shape:24s} utterances={outcome['utterances']} "
                f"starts={outcome['speech_starts']} endpoints={outcome['endpoints']} "
                f"text={outcome['transcript']!r}"
            )


if __name__ == "__main__":
    main()
