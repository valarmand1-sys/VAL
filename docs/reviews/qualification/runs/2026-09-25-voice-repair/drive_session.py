"""One Voice session, several spoken turns, driven the way the desktop drives them.

Voice-mode repair, 25 September 2026 (§2, §8). The priming pass's driver opened a new
session for every turn; the owner's failing run was **one** session with two turns,
the first said soon after Voice On. This driver keeps one session open for the whole
sequence and talks to the scratch service (port 8766) exactly as
`apps/desktop/src/voiceController.ts` does:

- 20 ms blocks of 16 kHz int16 PCM in real time through one ordered sender;
- the session polled every 120 ms, speech collected every 80 ms;
- the conversation read at a new `committed`, at a new `answered` when the service
  announces one (this build's rule) and at a newly appended turn (both builds);
- each collected segment "played" on one serial output queue: it starts when it has
  arrived **and** the previous one has ended, lasts its own duration, and its start
  and completion are reported as the desktop reports them.

Because this script is the microphone, speech end is exact on its own clock.

What each presentation rule would show, derived from the same marks:

- **before** (build d134e34): his words appear when the read issued at `committed`
  returns; her whole answer appears when the read issued at the appended turn
  returns — after every segment has been synthesised.
- **after** (this repair): his settled words appear, marked provisional, at the first
  poll that carries them (`pending`); the canonical message as before; each of her
  segments appears at its own playback start, provided her answer has been read by
  then — otherwise when the read returns.

Not measured, and not claimed: the React commit and paint (the jsdom tests hold the
reveal rule; the desktop panel measures it in the room) and sound leaving a speaker.

Usage: drive_session.py LABEL OUT.json PAUSE_S PHRASE [PHRASE ...]
"""

from __future__ import annotations

import array
import base64
import json
import os
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
LEAD_S = float(os.environ.get("DRIVE_LEAD_S", "1.0"))
NOISE = 33


def spoken(phrase: str) -> array.array:
    with tempfile.TemporaryDirectory() as scratch:
        target = Path(scratch) / "speech.wav"
        subprocess.run(
            ["say", "-v", "Daniel", "-o", str(target), f"--data-format=LEI16@{RATE}", phrase],
            check=True,
        )
        with wave.open(str(target)) as handle:
            speech = array.array("h", handle.readframes(handle.getnframes()))
    loud = [i for i, sample in enumerate(speech) if abs(sample) > NOISE]
    return speech[loud[0] : loud[-1] + 1]  # onset to offset, exactly


class Session:
    def __init__(self, label: str, phrases: list[str], pause: float) -> None:
        self.label = label
        self.phrases = phrases
        self.pause = pause
        self.client = httpx.Client(base_url=BASE, timeout=120.0)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.queue: list[bytes] = []
        self.rng = random.Random(7)
        self.session = ""
        self.t0 = 0.0
        self.samples_sent = 0  # samples scheduled so far, on the stream's own clock
        self.turn = -1
        self.turns: list[dict] = []
        self.seen_committed: str | None = None
        self.seen_answered: str | None = None
        self.seen_turns = 0
        self.issued = 0
        self.applied = 0
        self.player_free_at = 0.0
        self.playing_done = threading.Event()

    def now(self) -> float:
        return time.monotonic()

    def mark(self, name: str, at: float | None = None) -> None:
        with self.lock:
            if 0 <= self.turn < len(self.turns):
                self.turns[self.turn]["marks"].setdefault(name, at if at is not None else self.now())

    # --- the microphone: noise, then each phrase when its turn comes ---------------

    def stream(self, samples: array.array) -> None:
        step = BLOCK
        for index in range(0, len(samples), step):
            due = self.t0 + (self.samples_sent + index) / RATE
            delay = due - self.now()
            if delay > 0:
                time.sleep(delay)
            with self.lock:
                self.queue.append(samples[index : index + step].tobytes())
        self.samples_sent += len(samples)

    def noise(self, seconds: float) -> array.array:
        return array.array("h", (int(self.rng.gauss(0, NOISE)) for _ in range(int(seconds * RATE))))

    def microphone(self) -> None:
        self.stream(self.noise(LEAD_S))
        for index, phrase in enumerate(self.phrases):
            speech = spoken(phrase)
            with self.lock:
                self.turn = index
                self.turns.append({"phrase": phrase, "marks": {}, "segments": []})
            self.mark("speech_start", self.t0 + self.samples_sent / RATE)
            speech_end = self.t0 + (self.samples_sent + len(speech)) / RATE
            self.turns[index]["speech_end"] = speech_end
            self.stream(speech)
            # The room stays live: silence (noise) until her answer has been spoken,
            # then the pause before he speaks again.
            while not self.turn_over(index) and not self.stop.is_set():
                self.stream(self.noise(0.2))
            if self.stop.is_set():
                return
            self.stream(self.noise(self.pause))
        self.stop.set()

    def turn_over(self, index: int) -> bool:
        marks = self.turns[index]["marks"]
        return "turn_appended" in marks and "delivery_completed" in marks and self.player_idle()

    def player_idle(self) -> bool:
        return self.now() >= self.player_free_at

    def sender(self) -> None:
        while not self.stop.is_set():
            with self.lock:
                taken, total = [], 0
                while self.queue and total + len(self.queue[0]) <= RATE * 2 * 2:
                    block = self.queue.pop(0)
                    taken.append(block)
                    total += len(block)
            if not taken:
                time.sleep(0.005)
                continue
            self.client.post(
                f"/voice/sessions/{self.session}/audio",
                content=b"".join(taken),
                headers={"content-type": "application/octet-stream"},
            )

    # --- reads, polling, speech ------------------------------------------------------

    def read(self, why: str, conversation: str, turn: int) -> None:
        with self.lock:
            self.issued += 1
            mine = self.issued
        body = self.client.get(f"/conversations/{conversation}").json()
        at = self.now()
        with self.lock:
            if mine < self.applied:
                return
            self.applied = mine
            marks = self.turns[turn]["marks"]
            marks.setdefault(f"{why}_read_returned", at)
            roles = [m["role"] for m in body["messages"]]
            if roles.count("user") > turn:
                marks.setdefault("owner_message_in_read", at)
            if roles.count("val") > turn:
                marks.setdefault("answer_in_read", at)
                marks.setdefault(f"answer_in_read_via_{why}", at)

    def poller(self) -> None:
        while not self.stop.is_set():
            started = self.now()
            view = self.client.get(f"/voice/sessions/{self.session}").json()
            turn = self.turn
            if turn >= 0:
                if view["pending"]:
                    self.mark("pending_seen", started)
                if view.get("speech_end") and view["speech_end"]["utterance"] >= turn + 1:
                    self.mark("endpoint_seen", started)
                committed = view.get("committed")
                if committed and committed["message_id"] != self.seen_committed:
                    self.seen_committed = committed["message_id"]
                    self.mark("committed_seen", started)
                    threading.Thread(
                        target=self.read, args=("owner", committed["conversation_id"], turn), daemon=True
                    ).start()
                answered = view.get("answered")
                if answered and answered["message_id"] != self.seen_answered:
                    self.seen_answered = answered["message_id"]
                    self.mark("answered_seen", started)
                    threading.Thread(
                        target=self.read, args=("answered", answered["conversation_id"], turn), daemon=True
                    ).start()
                if len(view["turns"]) > self.seen_turns:
                    self.seen_turns = len(view["turns"])
                    self.mark("turn_appended", started)
                    threading.Thread(
                        target=self.read, args=("turn", view["turns"][-1]["conversation_id"], turn), daemon=True
                    ).start()
            time.sleep(max(0.0, 0.12 - (self.now() - started)))

    def speaker(self) -> None:
        while not self.stop.is_set():
            started = self.now()
            offer = self.client.get(f"/voice/sessions/{self.session}/speech/next").json()
            turn = self.turn
            segment = offer.get("segment")
            if segment and turn >= 0:
                arrived = self.now()
                audio = base64.b64decode(segment["audio_base64"])
                start = max(arrived, self.player_free_at)
                end = start + float(segment["duration_seconds"])
                self.player_free_at = end
                with self.lock:
                    self.turns[turn]["segments"].append(
                        {
                            "index": segment["segment_index"],
                            "chars": len(segment["text"]),
                            "duration_s": segment["duration_seconds"],
                            "audio_bytes": len(audio),
                            "arrived": arrived,
                            "start": start,
                            "end": end,
                        }
                    )
                threading.Thread(target=self.report, args=(segment, start, end), daemon=True).start()
            if turn >= 0 and offer.get("delivery_state") == "completed":
                if self.turns[turn]["marks"].get("turn_appended") is not None:
                    self.mark("delivery_completed", started)
            time.sleep(max(0.0, 0.08 - (self.now() - started)))

    def report(self, segment: dict, start: float, end: float) -> None:
        for state, at in (("playback_started", start), ("playback_completed", end)):
            delay = at - self.now()
            if delay > 0:
                time.sleep(delay)
            self.client.post(
                f"/voice/sessions/{self.session}/speech/played",
                json={
                    "message_id": segment["message_id"],
                    "segment_index": segment["segment_index"],
                    "state": state,
                    "elapsed_ms": 0,
                },
            )

    # --- the run ---------------------------------------------------------------------

    def run(self) -> dict:
        voice_on = self.now()
        opened = self.client.post("/voice/sessions", json={"no_project": True})
        opened.raise_for_status()
        self.session = opened.json()["session"]
        self.t0 = self.now()
        threads = [
            threading.Thread(target=target, daemon=True)
            for target in (self.microphone, self.sender, self.poller, self.speaker)
        ]
        for thread in threads:
            thread.start()
        self.stop.wait(timeout=60 * len(self.phrases) + 60)
        self.stop.set()
        for thread in threads:
            thread.join(timeout=5)
        self.client.post(f"/voice/sessions/{self.session}/close")
        return {
            "label": self.label,
            "session": self.session,
            "voice_on_to_first_speech_start_ms": round(
                ((self.turns[0]["marks"].get("speech_start") or voice_on) - voice_on) * 1000, 1
            ),
            "turns": [summarise(turn) for turn in self.turns],
        }


def summarise(turn: dict) -> dict:
    end = turn["speech_end"]
    marks = turn["marks"]
    ms = lambda at: None if at is None else round((at - end) * 1000, 1)  # noqa: E731
    segments = sorted(turn["segments"], key=lambda s: s["index"])
    first_start = segments[0]["start"] if segments else None
    answer_before = marks.get("answer_in_read_via_turn")
    answer_after = marks.get("answer_in_read")  # the earliest read that carried it
    rows = []
    for i, seg in enumerate(segments):
        rows.append(
            {
                "index": seg["index"],
                "chars": seg["chars"],
                "duration_s": seg["duration_s"],
                "arrived_ms": ms(seg["arrived"]),
                "playback_start_ms": ms(seg["start"]),
                "waited_for_previous_ms": round((seg["start"] - seg["arrived"]) * 1000, 1),
                "gap_after_previous_ms": None
                if i == 0
                else round((seg["start"] - segments[i - 1]["end"]) * 1000, 1),
                # Text shown less this segment's playback start: negative = text ahead
                # of her voice, positive = text after her voice began.
                "text_offset_before_ms": None
                if answer_before is None
                else round((answer_before - seg["start"]) * 1000, 1),
                "text_offset_after_ms": None
                if answer_after is None
                else round((max(answer_after, seg["start"]) - seg["start"]) * 1000, 1),
            }
        )
    return {
        "phrase": turn["phrase"],
        "speech_end_to": {
            "endpoint_seen": ms(marks.get("endpoint_seen")),
            "words_provisional_after": ms(marks.get("pending_seen")),
            "committed_seen": ms(marks.get("committed_seen")),
            "owner_message_canonical": ms(marks.get("owner_message_in_read")),
            "answered_seen": ms(marks.get("answered_seen")),
            "answer_read_via_answered": ms(marks.get("answer_in_read_via_answered")),
            "turn_appended": ms(marks.get("turn_appended")),
            "answer_read_via_turn": ms(marks.get("answer_in_read_via_turn")),
            "first_playback_start": ms(first_start),
        },
        "segments": rows,
    }


if __name__ == "__main__":
    label, out, pause, phrases = sys.argv[1], Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4:]
    result = Session(label, phrases, pause).run()
    out.write_text(json.dumps(result, indent=1) + "\n")
    for turn in result["turns"]:
        print(json.dumps(turn["speech_end_to"]))
