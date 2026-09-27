"""Milestone B §6: does stating what the current turn *is* stop ordinary MEDIUM re-answering
the previous exchange to a thanks? — 26 September 2026.

Matched contexts through the real ordinary route (fast route off, so every turn is
MEDIUM with the ordinary request), two conditions in two processes: the request as it
is, and the request with the isolated `current_turn` fact (`loop.TURN_KIND_FACT`). The
contexts: the three recorded wrong-turn cases; thanks and farewells in pending-work
contexts (they must approve nothing); an explicit request to repeat (must still repeat);
a correction (must stay preserved); the known fabricated-completion context. Every
answer printed for reading. Local, $0. Usage: wrong_turn_experiment.py off|on OUT.json
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
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

import val_gateway.loop as loop  # noqa: E402
from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

CONDITION = sys.argv[1]
loop.TURN_KIND_FACT = CONDITION == "on"
ROOT = Path(__file__).resolve().parents[5]


def fresh_store() -> None:
    engine = create_engine(URL)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
    config.set_main_option("sqlalchemy.url", URL)
    command.upgrade(config, "head")


fresh_store()
engine = create_engine(URL)
seed(engine, ROOT)
gateway = start(engine).gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
OFF = FastRoute()

CASES = [
    ("wrong-turn d10", ["Val, explain three ways to make a film scene feel tense without using dialogue."], "Thank you, Val."),
    ("wrong-turn f08", ["Give me one line of advice on pacing a chase sequence."], "Much obliged."),
    ("wrong-turn f09", ["Explain the difference between suspense and surprise in a scene."], "Nothing else for now, thank you."),
    ("pending: thanks after a draft request", ["Draft the reply to the reader."], "Thank you, Val."),
    ("pending: farewell after a cancel request", ["Cancel the meeting on Tuesday."], "Talk soon, Val."),
    ("pending: thanks after a decision question", ["Should I send the letter tonight or tomorrow?"], "Thank you."),
    ("explicit repeat", ["Give me one line of advice on pacing a chase sequence."], "Say that again, please."),
    ("explicit recap", ["Explain the difference between suspense and surprise in a scene."], "Recap that in one sentence."),
    ("correction preserved", ["The venue is the hall.", "No, the chapel, not the hall."], "Thank you, Val."),
    ("fabricated completion", ["Good evening, Val. Did you finish the invitation?"], "Thank you, Val."),
    ("thanks after greeting", ["Good evening, Val."], "Thank you, Val."),
    ("farewell after greeting", ["Hello, Val."], "Just saying good night, Val."),
]
rows = []
for label, history, utterance in CASES:
    conversation = None; hist = []
    for line in history:
        got = send(engine, gateway, line, catalogue=catalogue, signals=NO_PROJECT if conversation is None else None,
                   conversation_id=conversation, spoken=True, seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF)
        conversation = got.turn.conversation.id; hist.append({"said": line, "answer": got.turn.val_message.content})  # type: ignore[attr-defined]
    got = send(engine, gateway, utterance, catalogue=catalogue, conversation_id=conversation, spoken=True,
               seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=OFF)
    with engine.connect() as connection:
        call = connection.execute(text("select tokens_out, latency_ms from model_calls where message_id = :m order by id desc limit 1"),
                                  {"m": got.turn.user_message.id}).first()  # type: ignore[attr-defined]
    row = {"label": label, "history": hist, "utterance": utterance, "answer": got.turn.val_message.content,  # type: ignore[attr-defined]
           "tokens_out": call[0] if call else None, "latency_ms": call[1] if call else None}
    rows.append(row)
    print(json.dumps({"label": label, "answer": row["answer"][:200], "tokens_out": row["tokens_out"], "latency_ms": row["latency_ms"]}, ensure_ascii=False))
Path(sys.argv[2]).write_text(json.dumps({"condition": CONDITION, "rows": rows}, indent=1, ensure_ascii=False) + "\n")
