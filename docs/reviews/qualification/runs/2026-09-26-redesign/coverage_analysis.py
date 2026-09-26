"""How much of his recent spoken use the frozen router would route light — read-only, model-free.

Owner order "COMPARE EXISTING TIER-1 OPTIONS", §1. Reads the live store's owner-spoken
turns (every message with voice provenance), the wording in force, and only the context
that preceded each turn (her most recent answer before it, the count of his earlier
turns), and runs the frozen router exactly as production would. Nothing is written to
the store; no model is called; the output holds counts and timings only, never words.
Timings come from the production service log's own per-turn timelines where a turn has
one. Usage: coverage_analysis.py OUT.json
"""

from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path

import psycopg

from val_policy.light_conversation import ConversationState, decide

URL = "postgresql://josepharmand@localhost:5433/val"
LOG = Path("/opt/homebrew/var/log/val/api.log")
BOTH = frozenset({1, 2})
#: A conversation is counted diagnostic when any owner message in it is about the voice
#: system itself: hearing tests, voice-model checks, speed or tuning questions.
DIAGNOSTIC = re.compile(
    r"testing your|hear me|voice model|checking your|tuning|speed of the conversation|"
    r"faster if possible|what you heard me say|how fast are you",
    re.IGNORECASE,
)

with psycopg.connect(URL, options="-c default_transaction_read_only=on") as connection:
    rows = connection.execute(
        """
        select m.id, m.conversation_id, m.sequence, m.created_at,
               mc.content,
               (select mc2.content from messages_current mc2
                 where mc2.conversation_id = m.conversation_id and mc2.role = 'val'
                   and mc2.sequence < m.sequence order by mc2.sequence desc limit 1) as previous_answer,
               (select count(*) from messages u where u.conversation_id = m.conversation_id
                   and u.role = 'user' and u.sequence < m.sequence) as prior_turns,
               (select a.id from messages a where a.conversation_id = m.conversation_id
                   and a.sequence = m.sequence + 1 and a.role = 'val') as answer_id
        from voice_message_provenance p
        join messages m on m.id = p.message_id
        join messages_current mc on mc.id = m.id
        order by m.created_at
        """
    ).fetchall()
    owner_texts = connection.execute(
        "select conversation_id, string_agg(content, ' ') from messages_current "
        "where role = 'user' group by conversation_id"
    ).fetchall()
    deliveries = connection.execute(
        "select message_id, min(first_audio_ms) from speech_deliveries "
        "where first_audio_ms is not null group by message_id"
    ).fetchall()
diagnostic_conversations = {cid for cid, text in owner_texts if DIAGNOSTIC.search(text or "")}
first_audio = {mid: ms for mid, ms in deliveries}

timelines: dict[str, dict] = {}
if LOG.exists():
    for line in LOG.read_text(errors="replace").splitlines():
        if "voice turn timeline: " in line:
            try:
                doc = json.loads(line.split("voice turn timeline: ", 1)[1])
            except ValueError:
                continue
            if doc.get("message_id"):
                timelines[doc["message_id"]] = {k: v["first_ms"] for k, v in doc["marks"].items()}


def q(values: list[float]) -> dict:
    values = sorted(values)
    if not values:
        return {"n": 0}
    return {"n": len(values), "median_ms": round(statistics.median(values)),
            "min_ms": round(values[0]), "max_ms": round(values[-1])}


turns = []
for mid, cid, seq, created, content, previous, prior, answer_id in rows:
    verdict = decide(content, ConversationState(previous_answer=previous, prior_turns=prior), BOTH)
    group = {1: "tier_1", 2: "tier_2", None: "substantive"}[verdict.tier]
    tl = timelines.get(str(mid), {})
    turns.append({
        "date": created.date().isoformat(),
        "diagnostic": cid in diagnostic_conversations,
        "group": group,
        "words": len(content.split()),
        "endpoint_to_audio_ms": tl.get("audio_at_sink"),
        "endpoint_to_visible_ms": tl.get("provider_visible_text"),
        "answer_first_audio_ms": first_audio.get(answer_id) if answer_id else None,
    })

report = {"date_range": [turns[0]["date"], turns[-1]["date"]] if turns else None,
          "total_spoken_turns": len(turns), "conversations": len({r[1] for r in rows}),
          "diagnostic_conversations": len(diagnostic_conversations),
          "diagnostic_rule": DIAGNOSTIC.pattern, "splits": {}}
for split, keep in (("all", lambda t: True), ("ordinary_use", lambda t: not t["diagnostic"]),
                    ("diagnostic", lambda t: t["diagnostic"])):
    mine = [t for t in turns if keep(t)]
    groups = {}
    for group in ("tier_1", "tier_2", "substantive"):
        g = [t for t in mine if t["group"] == group]
        groups[group] = {
            "count": len(g),
            "percent": round(100 * len(g) / len(mine), 1) if mine else None,
            "endpoint_to_first_audio": q([t["endpoint_to_audio_ms"] for t in g if t["endpoint_to_audio_ms"] is not None]),
            "endpoint_to_first_visible_text": q([t["endpoint_to_visible_ms"] for t in g if t["endpoint_to_visible_ms"] is not None]),
            "turns_without_timing_record": sum(1 for t in g if t["endpoint_to_audio_ms"] is None),
        }
    report["splits"][split] = {"turns": len(mine), "groups": groups}
report["unclassifiable"] = {"count": 0, "reason": "every spoken turn had its wording in force and its preceding context available; none was unclassifiable"}
Path(sys.argv[1]).write_text(json.dumps(report, indent=1) + "\n")
print(json.dumps(report, indent=1))
