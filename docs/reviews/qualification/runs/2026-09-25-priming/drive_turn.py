"""One spoken turn, driven the way the desktop drives it, timed on one clock.

WP3 Step B latency pass, 25 September 2026. Talks to `serve_scratch.py` on port 8766
exactly as `apps/desktop/src/voiceController.ts` talks to the service:

- 20 ms blocks of 16 kHz int16 PCM produced in real time, sent by an ordered sender
  with **one request in flight**, coalescing whatever queued meanwhile (as
  `pcmSender.ts` does, up to two seconds a request);
- the session polled every 120 ms, never overlapping (`POLL_INTERVAL_MS`);
- the conversation read the moment a poll shows a new `committed` message, and again
  when an answered turn appears — through the same newest-issued-wins rule;
- speech collected every 80 ms (`SPEECH_POLL_INTERVAL_MS`), its start and
  completion reported as the desktop reports them.

The utterance is "Good evening, Val." from the local macOS voice, after a second of
room-level noise, followed by silence the microphone keeps sending. Because this
script *is* the microphone, the end of speech is known exactly: it is the fixture
sample where the synthesised speech ends, on this script's own clock.

What this cannot measure, and does not claim: the desktop's React commit and paint,
and sound leaving a speaker. "Read returned" and "audio received" are the software
boundaries named as such.

Usage: drive_turn.py LABEL OUT.json
"""

from __future__ import annotations

import array
import base64
import json
import random
import subprocess
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8766"
RATE = 16_000
BLOCK = 320
LEAD_S = float(__import__("os").environ.get("DRIVE_LEAD_S", "1.0"))
TAIL_S = 30.0  # the microphone stays live while she thinks and speaks


PHRASE = "Good evening, Val."


def fixture() -> tuple[bytes, int]:
    """The utterance with its lead-in and a long live tail; and where speech ends."""
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "speech.wav"
        subprocess.run(
            [
                "say",
                "-v",
                "Daniel",
                "-o",
                str(target),
                f"--data-format=LEI16@{RATE}",
                PHRASE,
            ],
            check=True,
        )
        with wave.open(str(target)) as handle:
            speech = array.array("h", handle.readframes(handle.getnframes()))
    loud = [i for i, sample in enumerate(speech) if abs(sample) > 33]
    speech = speech[loud[0] : loud[-1] + 1]  # onset to offset, exactly
    rng = random.Random(7)
    noise = lambda n: array.array("h", (int(rng.gauss(0, 33)) for _ in range(n)))  # noqa: E731
    lead = noise(int(LEAD_S * RATE))
    stream = lead + speech + noise(int(TAIL_S * RATE))
    return stream.tobytes(), len(lead) + len(speech)


class Turn:
    def __init__(self, label: str) -> None:
        self.label = label
        self.client = httpx.Client(base_url=BASE, timeout=120.0)
        self.marks: dict[str, float] = {}
        self.lock = threading.Lock()
        self.done = threading.Event()
        self.queue: list[bytes] = []
        self.issued = 0
        self.applied = 0
        self.shown: dict | None = None
        self.committed: str | None = None
        self.answered = False
        self.session = ""
        self.t0 = 0.0
        self.t0_wall = 0.0
        self.requests = {"audio": 0, "poll": 0, "speech": 0}

    def mark(self, name: str) -> None:
        with self.lock:
            self.marks.setdefault(name, time.monotonic())

    # --- the microphone and the ordered sender -------------------------------------

    def microphone(self, pcm: bytes) -> None:
        step = BLOCK * 2
        for index in range(0, len(pcm), step):
            if self.done.is_set():
                return
            due = self.t0 + (index // 2) / RATE
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            with self.lock:
                self.queue.append(pcm[index : index + step])

    def sender(self) -> None:
        while not self.done.is_set():
            with self.lock:
                taken, total = [], 0
                while self.queue and total + len(self.queue[0]) <= RATE * 2 * 2:
                    block = self.queue.pop(0)
                    taken.append(block)
                    total += len(block)
            if not taken:
                time.sleep(0.005)
                continue
            self.requests["audio"] += 1
            self.client.post(
                f"/voice/sessions/{self.session}/audio",
                content=b"".join(taken),
                headers={"content-type": "application/octet-stream"},
            )

    # --- polling, reads, speech ----------------------------------------------------

    def read(self, why: str, conversation: str) -> None:
        with self.lock:
            self.issued += 1
            mine = self.issued
        self.mark(f"{why}_read_issued")
        body = self.client.get(f"/conversations/{conversation}").json()
        self.mark(f"{why}_read_returned")
        with self.lock:
            if mine < self.applied:
                return
            self.applied = mine
            self.shown = body
        roles = [m["role"] for m in body["messages"]]
        if "user" in roles:
            self.mark("owner_message_in_applied_read")
        if "val" in roles:
            self.mark("answer_text_in_applied_read")

    def poller(self) -> None:
        while not self.done.is_set():
            started = time.monotonic()
            self.requests["poll"] += 1
            view = self.client.get(f"/voice/sessions/{self.session}").json()
            if view["pending"]:
                self.mark("pending_seen")
            committed = view.get("committed")
            if committed and committed["message_id"] != self.committed:
                self.committed = committed["message_id"]
                self.mark("committed_seen")
                threading.Thread(
                    target=self.read, args=("owner", committed["conversation_id"]), daemon=True
                ).start()
            if view["turns"] and not self.answered:
                self.answered = True
                self.mark("answered_turn_seen")
                threading.Thread(
                    target=self.read,
                    args=("answer", view["turns"][-1]["conversation_id"]),
                    daemon=True,
                ).start()
            time.sleep(max(0.0, 0.12 - (time.monotonic() - started)))

    def speaker(self) -> None:
        while not self.done.is_set():
            started = time.monotonic()
            self.requests["speech"] += 1
            offer = self.client.get(f"/voice/sessions/{self.session}/speech/next").json()
            segment = offer.get("segment")
            if segment:
                audio = base64.b64decode(segment["audio_base64"])
                self.mark("first_audio_received")
                self.marks.setdefault("first_audio_bytes", float(len(audio)))
                self.client.post(
                    f"/voice/sessions/{self.session}/speech/played",
                    json={
                        "message_id": segment["message_id"],
                        "segment_index": segment["segment_index"],
                        "state": "playback_started",
                        "elapsed_ms": 0,
                    },
                )
                self.mark("playback_started")
                time.sleep(segment["duration_seconds"])
                self.client.post(
                    f"/voice/sessions/{self.session}/speech/played",
                    json={
                        "message_id": segment["message_id"],
                        "segment_index": segment["segment_index"],
                        "state": "playback_completed",
                        "elapsed_ms": int(segment["duration_seconds"] * 1000),
                    },
                )
                self.mark("playback_completed")
            if offer.get("delivery_state") == "completed" and "playback_completed" in self.marks:
                if "answer_read_returned" in self.marks:
                    self.done.set()
            time.sleep(max(0.0, 0.08 - (time.monotonic() - started)))

    # --- the run -------------------------------------------------------------------

    def run(self) -> dict:
        pcm, speech_end = fixture()
        self.mark("voice_on")
        opened = self.client.post("/voice/sessions", json={"no_project": True})
        opened.raise_for_status()
        self.session = opened.json()["session"]
        self.mark("session_opened")
        self.t0 = time.monotonic()
        self.t0_wall = time.time()
        threads = [
            threading.Thread(target=self.microphone, args=(pcm,), daemon=True),
            threading.Thread(target=self.sender, daemon=True),
            threading.Thread(target=self.poller, daemon=True),
            threading.Thread(target=self.speaker, daemon=True),
        ]
        for thread in threads:
            thread.start()
        self.done.wait(timeout=120)
        self.done.set()
        for thread in threads:
            thread.join(timeout=5)
        self.client.post(f"/voice/sessions/{self.session}/close")
        speech_end_at = self.t0 + speech_end / RATE
        since = {
            name: round((at - speech_end_at) * 1000, 1)
            for name, at in self.marks.items()
            if name != "first_audio_bytes"
        }

        def span(a: str, b: str) -> float | None:
            return None if a not in since or b not in since else round(since[b] - since[a], 1)

        return {
            "label": self.label,
            "session": self.session,
            "speech_end_wall": self.t0_wall + speech_end / RATE,
            "ms_from_speech_end": dict(sorted(since.items(), key=lambda item: item[1])),
            "owner_facing": {
                "A_speech_end_to_owner_message_read_returned": span_from(
                    since, "owner_message_in_applied_read"
                ),
                "B_owner_message_read_returned_to_playback_start": span(
                    "owner_message_in_applied_read", "playback_started"
                ),
                "C_speech_end_to_playback_start": span_from(since, "playback_started"),
                "answer_text_read_returned_minus_playback_start": span(
                    "playback_started", "answer_text_in_applied_read"
                ),
            },
            "requests": self.requests,
        }


def span_from(since: dict[str, float], name: str) -> float | None:
    return since.get(name)


if __name__ == "__main__":
    if len(sys.argv) > 3:
        PHRASE = sys.argv[3]  # a genuinely different owner suffix for each turn
    result = Turn(sys.argv[1]).run()
    Path(sys.argv[2]).write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result["owner_facing"], indent=1))
