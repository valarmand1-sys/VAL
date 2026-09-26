"""Does the fast candidate answer the light turn it was given? — 26 September 2026.

The qualification pilot showed light answers that were persona example lines or
answers to the previous turn. This puts the candidate on the **real** preparation
path (`prepare_light_answer`: persona whole, record-state envelope, history, seal,
light route) against a scratch store, with and without history, and prints what it
says. Local only, $0. Usage: light_quality_probe.py [repeats]
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
os.environ["VAL_FAST_ROUTE_TIERS"] = "1,2"

from sqlalchemy import create_engine  # noqa: E402

from val_gateway import conversations  # noqa: E402
from val_gateway.deliberate import prepare_light_answer, send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

ROOT = Path(__file__).resolve().parents[5]
repeats = int(sys.argv[1]) if len(sys.argv) > 1 else 1
engine = create_engine(URL)
seed(engine, ROOT)
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)
BOTH = FastRoute(frozenset({1, 2}))
NO_PROJECT = ProjectSignals(explicit_no_project=True)
LIGHT = [
    "Good evening, Val.",
    "Thank you so much, Val.",
    "How are you tonight, Val?",
    "I'm well tonight, Val.",
    "Good night to you, Val.",
    "Thanks very much indeed.",
]


def prepared_text(content: str, conversation_id):  # noqa: ANN001, ANN201
    prepared = prepare_light_answer(
        engine, gateway, content,
        catalogue=catalogue,
        signals=NO_PROJECT if conversation_id is None else None,
        conversation_id=conversation_id,
        fast_route=BOTH,
    )
    if prepared is None:
        return {"prepared": False}
    return {"prepared": True, "tier": prepared.tier, "ms": prepared.prepared_ms,
            "slug": prepared.response.slug, "text": prepared.response.text}


results = {"no_history": [], "with_history": []}
print("--- no history (a conversation these words would open)")
for phrase in LIGHT:
    for _ in range(repeats):
        got = prepared_text(phrase, None)
        results["no_history"].append({"phrase": phrase, **got})
        print(json.dumps({"phrase": phrase, **got}, ensure_ascii=False))

# A conversation with a substantive exchange in it, as the pilot's had: the answer is
# GPT-OSS's own, on the partner route, so the history is what production would hold.
print("--- with history: one substantive spoken exchange first")
outcome = send(
    engine, gateway, "Good evening, Val. Did you finish the invitation?",
    catalogue=catalogue, signals=NO_PROJECT, spoken=True,
    seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=BOTH,
)
conversation_id = outcome.turn.conversation.id  # type: ignore[attr-defined]
print(json.dumps({"history_answer": outcome.turn.val_message.content[:200]}, ensure_ascii=False))  # type: ignore[attr-defined]
for phrase in LIGHT:
    for _ in range(repeats):
        got = prepared_text(phrase, conversation_id)
        results["with_history"].append({"phrase": phrase, **got})
        print(json.dumps({"phrase": phrase, **got}, ensure_ascii=False))
Path(__file__).with_name("light-quality-probe.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
