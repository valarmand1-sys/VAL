"""The four-way Tier-1 quality comparison — owner order "COMPARE EXISTING TIER-1 OPTIONS", §3.

One process per condition (the route promotion is process-wide), each on the scratch
store `val_repro_test` rebuilt empty, through the real Core (`deliberate.send`), with the
production model instances. No speculation, no voice, no streaming: the question here
is what each configuration *says* to a Tier-1 utterance under the same semantic
contract, and how long its answer took.

  A  ordinary MEDIUM, the ordinary request (fast route off)
  B  MEDIUM with the Core-owned Tier-1 request     VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=medium
  C  LOW with the Tier-1 request                   VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=low
  D  Qwen3-4B with the Tier-1 request              VAL_FAST_ROUTE_TIERS=1 VAL_TIER1_ROUTE=qwen

Each fixture case is a small conversation: its history exchanges are answered by the
condition's ordinary route first (so history is what production would hold), then the
Tier-1 utterance is asked. Every answer is written out for reading; nothing is scored by
a model. Local, $0. Usage: tier1_compare.py CONDITION FIXTURE.json OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
import time
from pathlib import Path

CONDITION = sys.argv[1]
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as handle:
    for name, value in plistlib.load(handle)["EnvironmentVariables"].items():
        if name != "VAL_DATABASE_URL":
            os.environ[name] = value
URL = "postgresql+psycopg://localhost:5433/val_repro_test"
os.environ["VAL_DATABASE_URL"] = URL
SWITCHES = {
    "A": {},
    "B": {"VAL_FAST_ROUTE_TIERS": "1", "VAL_TIER1_ROUTE": "medium"},
    "C": {"VAL_FAST_ROUTE_TIERS": "1", "VAL_TIER1_ROUTE": "low"},
    "D": {"VAL_FAST_ROUTE_TIERS": "1", "VAL_TIER1_ROUTE": "qwen"},
}
for key in ("VAL_FAST_ROUTE_TIERS", "VAL_TIER1_ROUTE", "VAL_SPECULATION", "VAL_ADAPTIVE_GRACE"):
    os.environ.pop(key, None)
os.environ.update(SWITCHES[CONDITION])

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
fast = started.fast_route if CONDITION != "A" else FastRoute()
NO_PROJECT = ProjectSignals(explicit_no_project=True)
fixture = json.loads(Path(sys.argv[2]).read_text())


def calls_for(message_id) -> list[dict]:  # noqa: ANN001
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "select task_type::text, model_config_id::text, tokens_in, tokens_out, latency_ms, "
                "terminal_state::text, status::text from model_calls where message_id = :m order by id"
            ),
            {"m": message_id},
        ).all()
        prep = connection.execute(
            text(
                "select p.outcome, c.task_type::text, c.model_config_id::text, c.tokens_out, "
                "c.latency_ms from speculative_preparations p join model_calls c on c.id = p.model_call_id "
                "where p.user_message_id = :m"
            ),
            {"m": message_id},
        ).all()
    return [dict(r._mapping) for r in rows] + [dict(r._mapping) for r in prep]


def speak(content: str, conversation_id, fast_route: FastRoute):  # noqa: ANN001, ANN201
    started_at = time.monotonic()
    outcome = send(
        engine, gateway, content,
        catalogue=catalogue,
        signals=NO_PROJECT if conversation_id is None else None,
        conversation_id=conversation_id,
        spoken=True,
        seal_route=SealRoute.UTTERANCE_FINALIZED,
        fast_route=fast_route,
    )
    elapsed = time.monotonic() - started_at
    turn = outcome.turn
    answer = getattr(getattr(turn, "val_message", None), "content", None)
    user_id = getattr(getattr(turn, "user_message", None), "id", None)
    return {
        "conversation_id": str(turn.conversation.id),
        "answer": answer,
        "kind": type(turn).__name__,
        "core_seconds": round(elapsed, 3),
        "calls": calls_for(user_id) if user_id else [],
    }


results = []
for case in fixture["cases"]:
    conversation_id = None
    history_answers = []
    for line in case.get("history", []):
        # History exchanges take the ordinary route in every condition.
        got = speak(line, conversation_id, FastRoute())
        conversation_id = got["conversation_id"]
        history_answers.append({"said": line, "answer": got["answer"]})
    got = speak(case["utterance"], conversation_id, fast)
    row = {
        "id": case["id"], "set": case.get("set", "design"), "utterance": case["utterance"],
        "history": history_answers, **got,
    }
    results.append(row)
    print(json.dumps({k: row[k] for k in ("id", "utterance", "answer", "core_seconds", "kind")}, ensure_ascii=False))
    print("   calls:", json.dumps(row["calls"]))

with engine.connect() as connection:
    routes = connection.execute(
        text("select task_type::text, model_config_id::text, count(*) from model_calls group by 1, 2")
    ).all()
Path(sys.argv[3]).write_text(
    json.dumps(
        {
            "condition": CONDITION, "switches": SWITCHES[CONDITION],
            "route_counts": [dict(r._mapping) for r in routes],
            "results": results,
        },
        indent=1, ensure_ascii=False,
    )
    + "\n"
)
