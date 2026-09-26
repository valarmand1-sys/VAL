"""The complete answer-onset path, stage by stage — §5.

From one measurement's service log (the per-turn timelines Core writes, ms from the
recognizer's endpoint) joined to the driver's own clock (speech end, the player's first
playback start), for every turn, grouped by the route the record says it took. Stages:

  speech end → endpoint (the confirming silence)            driver + service
  endpoint → owner turn submitted (transcript + resume window)
  submitted → provider dispatch (open, assemble, preflight)
  dispatch → first provider event                            (`provider_chunk`, streamed routes)
  first event → first user-facing answer token               (`provider_visible_text`: hidden reasoning)
  → first speech-safe segment                                (`speech_first_visible_text`)
  → generation complete / Core confirmation                  (`message_persisted`)
  → TTS start (`tts_synthesize_start`) → first audio ready (`audio_at_sink`)
  → first audio written by the player                        (driver `first_playback_start`)

A Tier-1 answer is not streamed: it is complete and checked before a word is shown, so
its `provider_chunk`/`provider_visible_text` marks coincide with completion.
Usage: onset_decomposition.py RESULT.json SERVICE.log
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())
lines = Path(sys.argv[2]).read_text(errors="replace").splitlines()
timelines: dict[str, dict] = {}
for line in lines:
    if "voice turn timeline: " in line:
        doc = json.loads(line.split("voice turn timeline: ", 1)[1])
        if doc.get("message_id"):
            timelines[doc["message_id"]] = {k: v["first_ms"] for k, v in doc["marks"].items()}
routes: dict[str, str] = {}
for message in result["dialogue"]:
    if message["role"] == "user" and message.get("own_calls"):
        tasks = {part.split("@")[0] for part in message["own_calls"].split(",")}
        routes[message["id"]] = "light" if "light_conversation" in tasks else "substantive"
# user message id per turn: the answer segments carry the val message; the user message
# is the one before it in the conversation
answer_to_user = {}
by_conv: dict[str, list] = {}
for m in result["dialogue"]:
    by_conv.setdefault(m["conversation_id"], []).append(m)
for msgs in by_conv.values():
    msgs.sort(key=lambda m: m["sequence"])
    for i, m in enumerate(msgs):
        if m["role"] == "val" and i > 0:
            answer_to_user[m["id"]] = msgs[i - 1]["id"]

STAGES = [
    ("endpoint → submitted", "endpoint", "owner_turn_submitted"),
    ("submitted → dispatch", "owner_turn_submitted", "provider_dispatch"),
    ("dispatch → first provider event", "provider_dispatch", "provider_chunk"),
    ("first event → first answer text", "provider_chunk", "provider_visible_text"),
    ("first answer text → first speech-safe segment", "provider_visible_text", "speech_first_visible_text"),
    ("dispatch → generation complete (persisted)", "provider_dispatch", "message_persisted"),
    ("first speech-safe segment → TTS start", "speech_first_visible_text", "tts_synthesize_start"),
    ("TTS start → first audio ready", "tts_synthesize_start", "audio_at_sink"),
    ("endpoint → first audio ready", "endpoint", "audio_at_sink"),
]
rows = []
for session in result["sessions"]:
    for turn in session.get("turns", []):
        segs = turn.get("segments", [])
        answer_id = next((s["message_id"] for s in segs if s.get("message_id") and not s["message_id"].startswith("00000000")), None)
        user_id = answer_to_user.get(answer_id)
        marks = timelines.get(user_id or "", {})
        row = {"phrase": turn["phrase"], "group": turn.get("group"), "route": routes.get(user_id, "?"),
               "speech_end_to_endpoint_ms": turn["speech_end_to"]["endpoint_seen"],
               "speech_end_to_first_playback_ms": turn["speech_end_to"]["first_playback_start"],
               "endpoint_to_first_audio_ready_ms": marks.get("audio_at_sink"),
               "stages": {name: (None if a not in marks or b not in marks else round(marks[b] - marks[a], 1)) for name, a, b in STAGES}}
        rows.append(row)


def q(values):  # noqa: ANN001, ANN201
    v = sorted(x for x in values if x is not None)
    return None if not v else f"n={len(v)} median {statistics.median(v):.0f} p90 {v[int(0.9*(len(v)-1))]:.0f} max {v[-1]:.0f}"


for route in ("light", "substantive"):
    mine = [r for r in rows if r["route"] == route]
    if not mine:
        continue
    print(f"\n=== {route} route: {len(mine)} turns")
    print(f"  speech end → endpoint (driver)          {q([r['speech_end_to_endpoint_ms'] for r in mine])}")
    for name, _, _ in STAGES:
        print(f"  {name:46s} {q([r['stages'][name] for r in mine])}")
    print(f"  speech end → first playback (driver)    {q([r['speech_end_to_first_playback_ms'] for r in mine])}")
Path(sys.argv[1]).with_name(Path(sys.argv[1]).stem + "-onset.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
