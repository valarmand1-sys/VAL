"""The resident voice: loaded once at Voice On, released when Voice ends — 25 Sept 2026.

Owner order, Voice-mode repair §5. **This file replaces the earlier warm-up tests of
the same name, and the reason is written here rather than hidden:** the warm-up they
tested was a separate process that loaded the model, exited, and left each sentence
to start its own process and load its own copy (~0.26 s interpreter start and
~1.0 s model load before every sentence — about half of each sentence's synthesis,
measured on this Mac). That process no longer exists, so "real speech stops a loading
warm-up" has nothing left to hold. What replaces it is the same runner in `serve`
mode — the same model, settings and conditioning, run by the same code — holding the
model while Voice is on, and these tests hold what that must guarantee instead:

- real speech is never slower for the worker's existence: a sentence that arrives
  while it loads waits for **that** load (the one it would otherwise do itself), and
  any failure of the worker falls back to the ordinary one-shot synthesis;
- a broken worker is never asked twice;
- the worker speaks nothing of its own, and exits — process gone — when released.

Each test runs a **real child process** speaking the worker's line protocol, as the
production worker does, and looks at that process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from test_speech_adapter import RecordingRunner, adapter, voice

from val_domain.speech import SpeechRequest


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


#: The worker protocol: a first line naming the model, `ready` once loaded, then one
#: JSON request per line and one JSON reply per request; `{"mode": "stop"}` ends it.
WORKER = """
import json, sys, time
LOAD, DIE = float(sys.argv[1]), sys.argv[2] == "die"
first = json.loads(sys.stdin.readline())
time.sleep(LOAD)
print("a library's chatter on stdout, which is not a reply")
print(json.dumps({"ok": True, "mode": "ready", "load_seconds": LOAD}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if request.get("mode") == "stop":
        break
    if DIE:
        sys.exit(3)
    with open(request["out_path"], "wb") as out:
        out.write(b"RIFF" + b"\\x00" * 60 + b"resident")
    print(json.dumps({
        "ok": True, "sample_rate": 24000, "duration_seconds": 1.2,
        "clone_prompt_sha256": "c" * 64, "resident_text": request["text"],
        "generation": {"temperature": 0.9, "kwargs_passed_to_generate": []},
    }), flush=True)
"""


class WorkerRunner(RecordingRunner):
    """Starts a real resident worker; one-shot runs are recorded as before."""

    def __init__(self, *replies: object, load: float = 0.0, die: bool = False) -> None:
        super().__init__(*replies)
        self.load = load
        self.die = die
        self.started: list[list[str]] = []
        self.processes: list[subprocess.Popen[str]] = []

    def start(self, argv: list[str]) -> subprocess.Popen[str]:
        self.started.append(list(argv))
        process = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed script
            [sys.executable, "-c", WORKER, str(self.load), "die" if self.die else "live"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.processes.append(process)
        return process


def speak(provider: object, text: str = "Good evening, my lord.") -> object:
    return provider.synthesize(SpeechRequest(text=text, voice=voice()))  # type: ignore[attr-defined]


def test_warm_starts_one_resident_worker_that_speaks_nothing(tmp_path: Path) -> None:
    runner = WorkerRunner()
    provider = adapter(runner, tmp_path)

    report = provider.warm()

    assert report["warmed"] is True and report["resident"] is True
    assert report["spoke_nothing"] is True
    assert runner.started[0][-1] == "serve"
    assert runner.calls == [], "nothing was synthesised by warming"
    assert provider.resident
    # A second Voice On while it serves starts nothing new.
    assert provider.warm().get("already_running") is True
    assert len(runner.processes) == 1
    provider.release()


def test_speech_goes_through_the_resident_worker_without_loading_again(tmp_path: Path) -> None:
    runner = WorkerRunner()
    provider = adapter(runner, tmp_path)
    provider.warm()

    first = speak(provider, "Good evening, my lord.")
    second = speak(provider, "The lamps are lit.")

    assert runner.calls == [], "no one-shot process was started for either sentence"
    assert first.audio.endswith(b"resident") and second.audio.endswith(b"resident")  # type: ignore[attr-defined]
    assert len(runner.processes) == 1
    provider.release()


def test_speech_arriving_while_the_worker_loads_waits_for_that_load(tmp_path: Path) -> None:
    runner = WorkerRunner(load=0.4)
    provider = adapter(runner, tmp_path)
    warming = threading.Thread(target=provider.warm, daemon=True)
    warming.start()
    while not runner.processes:
        time.sleep(0.01)

    result = speak(provider)

    assert runner.calls == [], "it waited for the load under way rather than doing its own"
    assert result.audio.endswith(b"resident")  # type: ignore[attr-defined]
    warming.join(timeout=10)
    provider.release()


def test_a_failed_worker_falls_back_to_one_shot_and_is_never_asked_again(tmp_path: Path) -> None:
    runner = WorkerRunner({}, {}, die=True)
    provider = adapter(runner, tmp_path)
    provider.warm()
    worker = runner.processes[0]

    result = speak(provider)

    assert len(runner.calls) == 1, "the sentence was spoken by the ordinary one-shot runner"
    assert result.audio.endswith(b"generated")  # type: ignore[attr-defined]
    worker.wait(timeout=5)
    assert not provider.resident
    speak(provider, "And again.")
    assert len(runner.calls) == 2, "the broken worker was not asked a second time"


def test_release_stops_the_worker_and_its_process_is_gone(tmp_path: Path) -> None:
    runner = WorkerRunner()
    provider = adapter(runner, tmp_path)
    provider.warm()
    worker = runner.processes[0]
    assert alive(worker.pid)

    assert provider.release() == {"released": True}

    assert worker.returncode is not None
    assert not provider.resident
    # With no worker, speech is the one-shot synthesis it always was.
    runner.replies.append({})
    speak(provider)
    assert len(runner.calls) == 1
    assert provider.release() == {"released": False}


def test_the_worker_is_told_the_model_and_asked_for_nothing_else(tmp_path: Path) -> None:
    captured: list[str] = []

    class Capturing(WorkerRunner):
        def start(self, argv: list[str]) -> subprocess.Popen[str]:
            process = super().start(argv)
            original = process.stdin
            assert original is not None

            class Tee:
                def write(self, text: str) -> int:
                    captured.append(text)
                    return original.write(text)

                def flush(self) -> None:
                    original.flush()

                def close(self) -> None:
                    original.close()

            process.stdin = Tee()  # type: ignore[assignment]
            return process

    provider = adapter(Capturing(), tmp_path)
    provider.warm()
    provider.release()
    requests = [json.loads(line) for line in "".join(captured).splitlines()]
    assert requests[0] == {"model_path": str(tmp_path / "model")}
    assert requests[1:] == [{"mode": "stop"}]
