"""Optional voice warming never takes priority over real speech — owner diagnostic, 25 Sept 2026.

Voice On starts a warm-up of the speech model so that the first real synthesis
reads weights the operating system has just cached. His diagnostic's first turn
came right after Voice On, while warm-ups may still have been running, and the
owner's order is that **real owner work takes priority** and that this is proved
structurally, not by timing: if cancellation is the mechanism, the underlying work
must actually stop and release what it held — a cancelled wait is not preemption.

So the warm-up here is a **real child process**, as it is in production, and each
test looks at that process — whether it has exited and whether its process id still
exists — at the instant real synthesis begins.
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


#: Stands in for the model load: reads its instructions, then holds the machine until
#: it is stopped. It never finishes on its own inside a test's lifetime.
LOADING = "import sys, time; sys.stdin.read(); time.sleep(60)"
#: A load that completes, reporting as the real runner's warm mode does.
LOADED = (
    "import json, sys; sys.stdin.read(); print(json.dumps({'warmed': True, 'load_seconds': 0.01}))"
)


class WarmingRunner(RecordingRunner):
    """Starts real processes for warm-ups, and notes their state when speech begins."""

    def __init__(self, *replies: object, warm_script: str = LOADING) -> None:
        super().__init__(*replies)
        self.warm_script = warm_script
        self.processes: list[subprocess.Popen[str]] = []
        self.at_speech: list[list[tuple[int | None, bool]]] = []
        self.speaking = threading.Event()
        self.finish_speaking = threading.Event()
        self.finish_speaking.set()

    def start(self, argv: list[str]) -> subprocess.Popen[str]:
        process = subprocess.Popen(  # noqa: S603 - this interpreter, a fixed script
            [sys.executable, "-c", self.warm_script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.processes.append(process)
        return process

    def run(self, argv: list[str], payload: str, timeout: float) -> tuple[int, str, str]:
        # The instant real synthesis begins: is any warm-up still running?
        self.at_speech.append([(p.poll(), alive(p.pid)) for p in self.processes])
        self.speaking.set()
        assert self.finish_speaking.wait(10)
        return super().run(argv, payload, timeout)


def wait_until(condition: object, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if callable(condition) and condition():
            return
        time.sleep(0.01)
    raise AssertionError("the condition was never reached")


def test_real_speech_stops_a_loading_warm_up_and_waits_for_it_to_exit(tmp_path: Path) -> None:
    runner = WarmingRunner({})
    provider = adapter(runner, tmp_path)
    outcome: list[dict[str, object]] = []
    warming = threading.Thread(target=lambda: outcome.append(provider.warm()), daemon=True)
    warming.start()
    wait_until(lambda: runner.processes and runner.processes[0].poll() is None)
    warm_up = runner.processes[0]
    assert alive(warm_up.pid), "the warm-up is running when his answer needs the voice"

    provider.synthesize(SpeechRequest(text="Good evening, my lord.", voice=voice()))

    # When real synthesis began, the warm-up had exited and its process was gone:
    # released, not merely no longer awaited.
    assert runner.at_speech == [[(warm_up.returncode, False)]]
    assert warm_up.returncode is not None
    warming.join(timeout=10)
    assert outcome and outcome[0]["preempted"] is True
    assert outcome[0]["warmed"] is False
    assert provider.last_preemption is not None
    assert provider.last_preemption["pid"] == warm_up.pid


def test_no_warm_up_starts_while_real_speech_is_running(tmp_path: Path) -> None:
    runner = WarmingRunner({})
    runner.finish_speaking.clear()
    provider = adapter(runner, tmp_path)
    speaking = threading.Thread(
        target=lambda: provider.synthesize(SpeechRequest(text="Indeed.", voice=voice())),
        daemon=True,
    )
    speaking.start()
    assert runner.speaking.wait(10)

    report = provider.warm()

    assert report["warmed"] is False
    assert "real speech is running" in str(report["reason"])
    assert runner.processes == [], "no warm-up process was started at all"
    runner.finish_speaking.set()
    speaking.join(timeout=10)


def test_a_warm_up_left_alone_completes_and_says_what_it_did(tmp_path: Path) -> None:
    runner = WarmingRunner(warm_script=LOADED)
    provider = adapter(runner, tmp_path)

    report = provider.warm()

    assert report["warmed"] is True
    assert report["spoke_nothing"] is True
    assert "preempted" not in report
    assert runner.processes[0].returncode == 0
    # What was asked of it: the warm mode, which generates nothing.
    assert runner.calls == []


def test_the_warm_up_is_asked_to_load_and_nothing_else(tmp_path: Path) -> None:
    captured: list[str] = []

    class Capturing(WarmingRunner):
        def start(self, argv: list[str]) -> subprocess.Popen[str]:
            process = super().start(argv)
            original = process.communicate

            def communicate(
                payload: str | None = None, timeout: float | None = None
            ) -> tuple[str, str]:
                captured.append(payload or "")
                return original(payload, timeout=timeout)

            process.communicate = communicate  # type: ignore[method-assign]
            return process

    runner = Capturing(warm_script=LOADED)
    provider = adapter(runner, tmp_path)
    provider.warm()
    request = json.loads(captured[0])
    assert request["mode"] == "warm"
    assert "text" not in request
