"""The speech-length bound, forced, on the real voice — remaining latency work, 27 Sept 2026, §6.

The ordinary runs never reached the bound, so it is forced here: the bounded runner as the
resident worker, `VAL_TTS_BOUND_FORCE_SECONDS=2.0` in its environment only, the governed
voice and the admitted local model, through `QwenTTSSpeech.synthesize_stream` exactly as
the delivery calls it. A segment whose natural reading is ~10 s must stop at ~2 s and end
as a named failure, not a completion; a short segment afterwards must be voiced normally
by the same worker; releasing the worker must end its process. Local, $0; nothing is
written to a file (the pieces' durations are kept, never their audio).

Usage: speech_bound_probe.py OUT.json
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["VAL_TTS_BOUND_FORCE_SECONDS"] = "2.0"  # inherited by the worker it spawns

from val_domain.speech import SpeechRequest, SpeechUnavailableError  # noqa: E402
from val_providers.qwen_tts_speech import (  # noqa: E402
    BOUNDED_RUNNER,
    QwenTTSSpeech,
    load_canonical_voice,
)

LONG = (
    "A caesura is a pause within a line of verse, marked by sense or punctuation, and a "
    "poet uses it to slow the reader, to weigh a word, or to turn the line against itself."
)
SHORT = "Yes, my lord."


def rss_kb(pid: int) -> int | None:
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
    return int(out.stdout.strip()) if out.stdout.strip() else None


def cpu(pid: int) -> float | None:
    out = subprocess.run(["ps", "-o", "%cpu=", "-p", str(pid)], capture_output=True, text=True)
    return float(out.stdout.strip()) if out.stdout.strip() else None


def main() -> None:
    voice = load_canonical_voice()
    speech = QwenTTSSpeech(runner_path=BOUNDED_RUNNER)
    record: dict[str, object] = {"forced_bound_seconds": 2.0, "runner": BOUNDED_RUNNER.name}
    record["warm"] = speech.warm(voice)
    process = speech._resident  # noqa: SLF001 - the probe observes the worker's process
    assert process is not None
    pid = process.pid
    record["worker_rss_kb_ready"] = rss_kb(pid)

    for label, text in (("long", LONG), ("short", SHORT)):
        pieces: list[float] = []
        began = time.monotonic()
        outcome: dict[str, object] = {"characters": len(text)}
        try:
            result = speech.synthesize_stream(
                SpeechRequest(text=text, voice=voice), lambda _audio, seconds: pieces.append(seconds)
            )
            outcome["result"] = "completed" if result is not None else "not streamed"
            outcome["duration_seconds"] = None if result is None else result.duration_seconds
        except SpeechUnavailableError as failure:
            outcome["result"] = "failed"
            outcome["reason"] = str(failure)
        outcome["pieces"] = len(pieces)
        outcome["seconds_handed_over"] = round(sum(pieces), 3)
        outcome["elapsed_seconds"] = round(time.monotonic() - began, 3)
        time.sleep(1.0)
        outcome["worker_alive_after"] = process.poll() is None
        outcome["worker_cpu_percent_1s_after"] = cpu(pid)
        outcome["worker_rss_kb_after"] = rss_kb(pid)
        record[label] = outcome

    record["release"] = speech.release()
    time.sleep(1.0)
    record["worker_exited_after_release"] = process.poll() is not None
    Path(sys.argv[1]).write_text(json.dumps(record, indent=1) + "\n")
    print(json.dumps(record, indent=1))


if __name__ == "__main__":
    main()
