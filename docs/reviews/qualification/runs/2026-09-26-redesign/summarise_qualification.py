"""Read one condition's measurement into the figures §10 asks for — 26 September 2026.

Per group (tier 1, tier 2, ineligible): sample count, route taken as the record says
(`model_calls.task_type` of the call that produced her answer), substantive false
positives (an ineligible turn on the light route — the count that must be zero),
false negatives (an eligible turn on the substantive route, reported with their
latency), fallbacks (a light call followed by a conversation call on one turn),
speech end to first playback start (median, p90, maximum), the words the recognizer
actually gave the router where they differ from the phrase, and every answer text so
its quality can be read. Speculation outcomes and completion states come from the
scratch store and the service log, never inferred.

Usage: summarise_qualification.py RESULT.json [RESULT.json ...]
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path


def normalise(text: str) -> str:
    text = text.lower().replace("||", " ")
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def quantiles(values: list[float]) -> dict[str, float | int | None]:
    values = sorted(v for v in values if v is not None)
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None}
    p90 = values[min(len(values) - 1, int(round(0.9 * (len(values) - 1))))]
    return {
        "n": len(values),
        "median": round(statistics.median(values), 1),
        "p90": round(p90, 1),
        "max": round(values[-1], 1),
    }


def summarise(path: Path) -> dict:
    report = json.loads(path.read_text())
    dialogue = report["dialogue"]
    by_conversation: dict[str, list[dict]] = {}
    for message in dialogue:
        by_conversation.setdefault(message["conversation_id"], []).append(message)
    for messages in by_conversation.values():
        messages.sort(key=lambda m: m["sequence"])

    # The route of each user message: the task types of the calls attached to it.
    turns_out: list[dict] = []
    for session in report["sessions"]:
        if session.get("failed"):
            for phrase in session.get("phrases", []):
                turns_out.append({"phrase": phrase, "session_failed": True})
            continue
        # Match this session's turns to the conversation's user messages in order.
        conversation_id = None
        for turn in session["turns"]:
            for seg in turn.get("segments", []):
                if seg.get("message_id") and seg["message_id"] != "00000000-0000-0000-0000-000000000000":
                    for cid, messages in by_conversation.items():
                        if any(m["id"] == seg["message_id"] for m in messages):
                            conversation_id = cid
        messages = by_conversation.get(conversation_id, []) if conversation_id else []
        users = [m for m in messages if m["role"] == "user"]
        for index, turn in enumerate(session["turns"]):
            user = users[index] if index < len(users) else None
            answer = None
            if user is not None:
                following = [m for m in messages if m["sequence"] == user["sequence"] + 1]
                answer = following[0] if following and following[0]["role"] == "val" else None
            route = (user or {}).get("own_calls") or ""
            tasks = sorted({part.split("@")[0] for part in route.split(",") if part})
            # An answer bound from a speculative preparation has its call attached to no
            # message; the preparation row names the user message it was accepted for.
            accepted = user is not None and any(
                row["outcome"] == "accepted" and row["user_message_id"] == user["id"]
                for row in report.get("preparations", [])
            )
            if accepted:
                tasks = sorted(set(tasks) | {"speculative_light_conversation"})
            light = "light_conversation" in tasks or accepted
            substantive = "conversation" in tasks
            transcript = (user or {}).get("content")
            expected_group = turn.get("group")
            turns_out.append(
                {
                    "session": session["label"],
                    "phrase": turn["phrase"],
                    "group": expected_group,
                    "transcript": transcript,
                    "recognised_as_phrase": (
                        None if transcript is None else normalise(transcript) == normalise(turn["phrase"])
                    ),
                    "tasks": tasks,
                    "route": (
                        "light" if light and not substantive
                        else "fallback" if light and substantive
                        else "substantive" if substantive
                        else "none"
                    ),
                    "answer": None if answer is None else answer["content"],
                    "speech_end_to_first_playback_ms": turn["speech_end_to"]["first_playback_start"],
                    "speech_end_to_answer_read_ms": turn["speech_end_to"]["answer_read_via_answered"]
                    or turn["speech_end_to"]["answer_read_via_turn"],
                    "speech_end_to_committed_ms": turn["speech_end_to"]["committed_seen"],
                    "underrun_ms": sum(s.get("underrun_ms", 0) for s in turn.get("segments", [])),
                    "segments": len(turn.get("segments", [])),
                    "answered": answer is not None,
                    "speculative": accepted,
                    "previous_answer": (
                        next((m["content"] for m in reversed(messages)
                              if user is not None and m["role"] == "val" and m["sequence"] < user["sequence"]), None)
                    ),
                }
            )

    groups: dict[str, dict] = {}
    for group in ("tier_1", "tier_2", "ineligible"):
        mine = [t for t in turns_out if t.get("group") == group and not t.get("session_failed")]
        routes = {r: sum(1 for t in mine if t["route"] == r) for r in ("light", "fallback", "substantive", "none")}
        groups[group] = {
            "n": len(mine),
            "routes": routes,
            "unanswered": [t["phrase"] for t in mine if not t["answered"]],
            "misrecognised": [
                {"phrase": t["phrase"], "transcript": t["transcript"]}
                for t in mine if t["recognised_as_phrase"] is False
            ],
            "speech_end_to_first_playback_ms": {
                "all": quantiles([t["speech_end_to_first_playback_ms"] for t in mine]),
                "light": quantiles([t["speech_end_to_first_playback_ms"] for t in mine if t["route"] == "light"]),
                "substantive": quantiles(
                    [t["speech_end_to_first_playback_ms"] for t in mine if t["route"] in ("substantive", "fallback")]
                ),
            },
            "speech_end_to_answer_read_ms": quantiles([t["speech_end_to_answer_read_ms"] for t in mine]),
            "underruns": sum(1 for t in mine if t["underrun_ms"] > 0),
        }
    false_positives = [
        {"phrase": t["phrase"], "transcript": t["transcript"], "answer": t["answer"]}
        for t in turns_out if t.get("group") == "ineligible" and t.get("route") in ("light", "fallback")
    ]
    false_negatives = [
        {"phrase": t["phrase"], "transcript": t["transcript"], "latency_ms": t["speech_end_to_first_playback_ms"]}
        for t in turns_out if t.get("group") in ("tier_1", "tier_2") and t.get("route") == "substantive"
    ]
    fallbacks = [t["phrase"] for t in turns_out if t.get("route") == "fallback"]
    preparations = report.get("preparations", [])
    outcomes: dict[str, int] = {}
    for row in preparations:
        outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
    completions = report.get("completions", [])
    states: dict[str, int] = {}
    for row in completions:
        states[row.get("state", "?")] = states.get(row.get("state", "?"), 0) + 1
    return {
        "condition": report["condition"],
        "revision": report["revision"],
        "dirty": report["dirty"],
        "switches": {
            "fast_route_tiers": report.get("fast_route_tiers"),
            "speculation": report.get("speculation"),
            "adaptive_grace": report.get("adaptive_grace"),
        },
        "sessions": len(report["sessions"]),
        "sessions_failed": sum(1 for s in report["sessions"] if s.get("failed")),
        "turns": len([t for t in turns_out if not t.get("session_failed")]),
        "groups": groups,
        "substantive_false_positives": false_positives,
        "false_negatives": false_negatives,
        "fallbacks": fallbacks,
        "speculation_outcomes": outcomes,
        "speculation_prepared_ms": quantiles([r["prepared_ms"] for r in preparations if r.get("prepared_ms")]),
        "completion_states": states,
        "machine": report["machine"],
        "voice_on_to_first_speech_ms": [s.get("voice_on_to_first_speech_start_ms") for s in report["sessions"] if not s.get("failed")],
        "turns_detail": turns_out,
    }


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        summary = summarise(Path(arg))
        out = Path(arg).with_name(Path(arg).stem + "-summary.json")
        out.write_text(json.dumps(summary, indent=1) + "\n")
        brief = {k: v for k, v in summary.items() if k != "turns_detail"}
        print(json.dumps(brief, indent=1))
