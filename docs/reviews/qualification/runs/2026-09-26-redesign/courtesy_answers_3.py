"""What LOW says to a farewell after a greeting exchange his words did not make light — release-gaps §6.

The desktop-integration run of 26 September 2026 (W2) heard "Good evening, Val." as
"Good evening, Vowel.": not a greeting to the router, so the exchange stayed in the
Tier-1 request, and LOW answered "Good night, Val." with "Good evening, my lord." The
omission now reads her answer's shape too. Here: openers the router does not call light
(a misheard name, a greeting to the house) on the ordinary route, then a farewell on
LOW, every answer printed for reading. Real path, scratch store, local, $0.
Usage: courtesy_answers_3.py OUT.json
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
for key in ("VAL_SPECULATION", "VAL_ADAPTIVE_GRACE", "VAL_OWNER_PRECEDENCE"):
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
    ("Good evening, Vowel.", "Good night, Val."),
    ("Good evening to the house.", "Good night, Val."),
    ("Evening, all.", "Good night, Val."),
    ("Good evening, Vowel, it's me.", "Sleep well, Val. Good night."),
    ("Hello, Vowel.", "Good night, Val."),
    ("Good evening, Vowel.", "Until tomorrow, Val."),
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
