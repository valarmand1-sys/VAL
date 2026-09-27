"""What LOW actually says in the contexts the courtesy decision newly permits — Milestone A §4.

A greeting or a short answered question on the ordinary route (MEDIUM), whose answer
ends in a generic closing of courtesy often enough; then his thanks or farewell, which
the decision may now route to LOW. Real path, scratch store, every answer printed for
reading. Contexts where her answer happens to leave something open are recorded as
routed MEDIUM. Local, $0. Usage: courtesy_answers.py OUT.json
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
os.environ["VAL_FAST_ROUTE_TIERS"] = "1"
os.environ["VAL_TIER1_ROUTE"] = "low"
for key in ("VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

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
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)
NO_PROJECT = ProjectSignals(explicit_no_project=True)
LIGHT = FastRoute(frozenset({1}))

CONTEXTS = [
    ("Good evening, Val.", "Thank you, Val."),
    ("Hello, Val.", "Good night, Val."),
    ("Good morning, Val.", "Thanks. Until this evening."),
    ("Evening, Val.", "Thank you kindly."),
    ("Hello there, Val.", "Sleep well, Val. Good night."),
    ("Good evening, Val, it's me.", "Just saying good night, Val."),
    ("How long should a cold open run before the title card?", "Thanks very much indeed."),
    ("Is the house quiet tonight?", "Good night, Val."),
    ("Explain the difference between suspense and surprise in a scene.", "Thank you, that was helpful."),
    ("Name two ways to end a chapter so the reader turns the page.", "Much obliged, Val."),
    ("What makes a villain's monologue land without becoming a speech?", "That's all for tonight. Thank you."),
    ("Which is stronger to open a chapter, dialogue or description?", "Thank you. Good night."),
]
rows = []
for opener, closing in CONTEXTS:
    first = send(engine, gateway, opener, catalogue=catalogue, signals=NO_PROJECT, spoken=True,
                 seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=LIGHT)
    conversation = first.turn.conversation.id
    her = first.turn.val_message.content  # type: ignore[attr-defined]
    second = send(engine, gateway, closing, catalogue=catalogue, conversation_id=conversation, spoken=True,
                  seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=LIGHT)
    with engine.connect() as connection:
        task = connection.execute(
            text("select task_type::text from model_calls where message_id = :m order by id desc limit 1"),
            {"m": second.turn.user_message.id},  # type: ignore[attr-defined]
        ).scalar()
        opener_task = connection.execute(
            text("select task_type::text from model_calls where message_id = :m order by id desc limit 1"),
            {"m": first.turn.user_message.id},  # type: ignore[attr-defined]
        ).scalar()
    row = {"opener": opener, "opener_route": opener_task, "her_answer": her, "closing": closing,
           "closing_route": task, "answer": second.turn.val_message.content}  # type: ignore[attr-defined]
    rows.append(row)
    print(json.dumps(row, ensure_ascii=False))
Path(sys.argv[1]).write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n")
