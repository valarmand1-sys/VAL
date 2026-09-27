"""One Voice session, two utterances, the second on a trigger — owner precedence, §3.

Release-gaps order of 26 September 2026. Talks to the scratch service (port 8766) exactly
as `drive_session.py` does — 20 ms blocks of 16 kHz PCM in real time through one ordered
sender, the session polled every 100 ms, speech collected every 80 ms and "played" on a
serial software queue with start and completion reported as the desktop reports them —
and speaks the second phrase when a **trigger** is met:

    t:<s>              <s> seconds after the first phrase's speech end
    progress:<stage>   the first time the session reports that progress stage
                       (thinking, writing, voicing, speaking)
    played             the first time the software player has started a segment

Every session-view change is recorded with its time on the shared monotonic clock (the
service logs its own decision on the same clock), every hand-off and every playback
report's HTTP status too, and the conversation is read back at the end — so late tokens,
late audio and late completion events can be looked for rather than assumed absent. The
software player is the player boundary here; the desktop runs are separate.

Usage: precedence_drive.py LABEL OUT.json FIRST SECOND TRIGGER [TAIL_S]
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
NOISE = 33
LEAD_S = float(__import__("os").environ.get("DRIVE_LEAD_S", "12.0"))  # after Ready, unless asked otherwise


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
    return speech[loud[0] : loud[-1] + 1]


class Drive:
    def __init__(self, label: str, first: str, second: str, trigger: str, tail: float) -> None:
        self.label, self.first, self.second, self.trigger, self.tail = label, first, second, trigger, tail
        self.client = httpx.Client(base_url=BASE, timeout=120.0)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.queue: list[bytes] = []
        self.rng = random.Random(7)
        self.session = ""
        self.t0 = 0.0
        self.samples_sent = 0
        self.events: list[dict] = []
        self.views: list[dict] = []
        self.handoffs: list[dict] = []
        self.reports: list[dict] = []
        self.player_free_at = 0.0
        self.open: dict | None = None
        self.speech_end: list[float] = []
        self.trigger_fired = threading.Event()
        self.last_view: dict | None = None
        self.player_started = threading.Event()

    def now(self) -> float:
        return time.monotonic()

    def event(self, name: str, **data: object) -> None:
        with self.lock:
            self.events.append({"mono": self.now(), "event": name, **data})

    # --- microphone -----------------------------------------------------------------

    def stream(self, samples: array.array) -> None:
        for index in range(0, len(samples), BLOCK):
            due = self.t0 + (self.samples_sent + index) / RATE
            delay = due - self.now()
            if delay > 0:
                time.sleep(delay)
            with self.lock:
                self.queue.append(samples[index : index + BLOCK].tobytes())
        self.samples_sent += len(samples)

    def noise(self, seconds: float) -> array.array:
        return array.array("h", (int(self.rng.gauss(0, NOISE)) for _ in range(int(seconds * RATE))))

    def say(self, phrase: str) -> None:
        speech = spoken(phrase)
        start = self.t0 + self.samples_sent / RATE
        end = start + len(speech) / RATE
        self.event("speech_start", phrase=phrase, at=start)
        self.stream(speech)
        self.speech_end.append(end)
        self.event("speech_end", phrase=phrase, at=end)

    def evict(self) -> None:
        """Push both persona checkpoints out of the runtime's cache (six distinct one-token
        prompts; `ORDINARY_TURN.md` §12), so the next turn prefills cold — the "during
        prefill" case. Run after Ready and just before the first phrase, or the initial
        primes would simply re-establish them."""
        import plistlib

        with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
            env = plistlib.load(handle)["EnvironmentVariables"]
        base = env.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
        client = httpx.Client(base_url=base, timeout=120.0, headers={"Authorization": f"Bearer {env['VAL_LMSTUDIO_API_TOKEN']}"})
        for i in range(6):
            words = " ".join(f"unrelated prompt {i} token {j}" for j in range(40))
            client.post("/chat/completions", json={"model": "openai/gpt-oss-20b", "messages": [{"role": "user", "content": words}], "max_tokens": 1, "stream": False})
        self.event("checkpoints_evicted")

    def microphone(self) -> None:
        self.stream(self.noise(LEAD_S))
        if __import__("os").environ.get("EVICT_BEFORE_SPEECH") == "1":
            evicting = threading.Thread(target=self.evict, daemon=True)
            evicting.start()
            while evicting.is_alive():
                self.stream(self.noise(0.1))
        self.say(self.first)
        # Wait for the trigger, keeping the room live.
        while not self.trigger_fired.is_set() and not self.stop.is_set():
            self.stream(self.noise(0.1))
        if self.stop.is_set():
            return
        self.event("trigger_fired", trigger=self.trigger)
        self.say(self.second)
        deadline = self.now() + self.tail
        while self.now() < deadline and not self.stop.is_set():
            self.stream(self.noise(0.2))
        self.stop.set()

    def watch_trigger(self) -> None:
        kind, _, arg = self.trigger.partition(":")
        while not self.stop.is_set() and not self.trigger_fired.is_set():
            if kind == "t" and self.speech_end and self.now() >= self.speech_end[0] + float(arg):
                self.trigger_fired.set()
            elif kind == "progress" and self.last_view and self.last_view.get("progress") in arg.split(","):
                self.trigger_fired.set()
            elif kind == "played" and self.player_started.is_set():
                self.trigger_fired.set()
            time.sleep(0.01)

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

    # --- polling and the player -----------------------------------------------------

    def poller(self) -> None:
        keys = ("state", "progress", "pending", "queued", "committed", "answered", "superseded", "hearing")
        while not self.stop.is_set():
            started = self.now()
            view = self.client.get(f"/voice/sessions/{self.session}").json()
            slim = {k: view.get(k) for k in keys}
            slim["turns"] = len(view.get("turns") or [])
            if slim != (self.last_view or {}):
                with self.lock:
                    self.views.append({"mono": started, **slim})
            self.last_view = slim
            time.sleep(max(0.0, 0.1 - (self.now() - started)))

    def speaker(self) -> None:
        while not self.stop.is_set():
            started = self.now()
            offer = self.client.get(f"/voice/sessions/{self.session}/speech/next").json()
            segment = offer.get("segment")
            if offer.get("stop"):
                self.event("stop_offered", reason=offer.get("reason"), message_id=offer.get("message_id"))
                self.player_free_at = self.now()
                self.open = None
            if segment:
                arrived = self.now()
                audio = base64.b64decode(segment["audio_base64"])
                duration = float(segment["duration_seconds"])
                chunk, last = segment.get("chunk", 0), segment.get("last", True)
                with self.lock:
                    self.handoffs.append(
                        {"mono": arrived, "message_id": segment["message_id"], "segment": segment["segment_index"],
                         "chunk": chunk, "last": last, "duration_s": duration, "bytes": len(audio),
                         "text": segment["text"][:80]}
                    )
                if chunk == 0:
                    start = max(arrived, self.player_free_at)
                    entry = {"index": segment["segment_index"], "message_id": segment["message_id"],
                             "start": start, "end": start + duration}
                    self.open = entry
                    threading.Thread(target=self.report, args=(entry, "playback_started", start), daemon=True).start()
                elif self.open is not None and self.open["index"] == segment["segment_index"]:
                    entry = self.open
                    if duration > 0:
                        entry["end"] = max(arrived, entry["end"]) + duration
                else:
                    entry = None
                if entry is not None:
                    self.player_free_at = entry["end"]
                    if last:
                        self.open = None
                        threading.Thread(target=self.report, args=(entry, "playback_completed", entry["end"]), daemon=True).start()
            time.sleep(max(0.0, 0.08 - (self.now() - started)))

    def report(self, entry: dict, state: str, at: float) -> None:
        delay = at - self.now()
        if delay > 0:
            time.sleep(delay)
        if state == "playback_started":
            self.player_started.set()
        message_id = entry["message_id"]
        if message_id == "00000000-0000-0000-0000-000000000000" and self.last_view and self.last_view.get("answered"):
            message_id = self.last_view["answered"]["message_id"]
        response = self.client.post(
            f"/voice/sessions/{self.session}/speech/played",
            json={"message_id": message_id, "segment_index": entry["index"], "state": state, "elapsed_ms": 0},
        )
        with self.lock:
            self.reports.append({"mono": self.now(), "state": state, "segment": entry["index"],
                                 "message_id": message_id, "http": response.status_code})

    # --- the run --------------------------------------------------------------------

    def run(self) -> dict:
        opened = self.client.post("/voice/sessions", json={"no_project": True})
        opened.raise_for_status()
        self.session = opened.json()["session"]
        self.event("voice_on")
        self.t0 = self.now()
        threads = [threading.Thread(target=t, daemon=True) for t in
                   (self.microphone, self.sender, self.poller, self.speaker, self.watch_trigger)]
        for thread in threads:
            thread.start()
        self.stop.wait(timeout=240)
        self.stop.set()
        for thread in threads:
            thread.join(timeout=5)
        conversation = None
        for view in reversed(self.views):
            for key in ("committed", "answered"):
                if view.get(key):
                    conversation = view[key]["conversation_id"]
                    break
            if conversation:
                break
        messages = self.client.get(f"/conversations/{conversation}").json()["messages"] if conversation else []
        self.client.post(f"/voice/sessions/{self.session}/close")
        return {
            "label": self.label, "session": self.session, "trigger": self.trigger,
            "phrases": [self.first, self.second], "speech_end_mono": self.speech_end,
            "events": self.events, "views": self.views, "handoffs": self.handoffs, "reports": self.reports,
            "messages": [{"role": m["role"], "content": m["content"], "id": m["id"]} for m in messages],
            "conversation": conversation,
        }


if __name__ == "__main__":
    label, out, first, second, trigger = sys.argv[1:6]
    tail = float(sys.argv[6]) if len(sys.argv) > 6 else 45.0
    result = Drive(label, first, second, trigger, tail).run()
    Path(out).write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps({"label": label, "messages": [(m["role"], m["content"][:60]) for m in result["messages"]],
                      "reports": [(r["state"], r["http"]) for r in result["reports"]]}, ensure_ascii=False))
