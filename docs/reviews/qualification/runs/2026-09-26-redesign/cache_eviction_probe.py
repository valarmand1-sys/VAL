"""Why the persona checkpoints go cold — Milestone A §2's investigation, 26 September 2026.

The prime's own duration is the instrument: ~0.85 s for both entries when their
checkpoints are resident, ~13 s when both must be prefilled. Controlled sequences, each
through the real Core on the scratch store (LOW promoted for the light route, so a
prime covers both efforts):

  idle    P, then P again after 5 s, 30 s, 90 s of nothing            — time-based eviction?
  count   P, then k distinct short unrelated prompts, then P (k = 1..5)  — entry-count LRU?
  size    P, then one ordinary MEDIUM turn (a 5.8k-token prompt), then P — size/KV-bytes bound?
  session P, open and close a Voice session with no speech, then P       — does session lifecycle clear it?

Local, $0. Usage: cache_eviction_probe.py OUT.json
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
import time
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

import httpx  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_gateway.deliberate import send  # noqa: E402
from val_gateway.persona import seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.seal import SealRoute  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_gateway.voice import VoiceSession  # noqa: E402
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
BASE = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
client = httpx.Client(base_url=BASE, timeout=120.0,
                      headers={"Authorization": f"Bearer {os.environ['VAL_LMSTUDIO_API_TOKEN']}"})
results: list[dict] = []


def P(label: str) -> float:  # noqa: N802
    t = time.monotonic()
    r = dict(gateway.prime_prefix())
    seconds = round(time.monotonic() - t, 2)
    results.append({"step": label, "prime_seconds": seconds, "medium": r.get("seconds"),
                    "low": (r.get("light") or {}).get("seconds")})
    print(label, seconds, "medium", r.get("seconds"), "low", (r.get("light") or {}).get("seconds"), flush=True)
    return seconds


def M(words: str) -> None:  # noqa: N802
    send(engine, gateway, words, catalogue=catalogue, signals=NO_PROJECT, spoken=True,
         seal_route=SealRoute.UTTERANCE_FINALIZED, fast_route=FastRoute())


def short_unrelated(k: int) -> None:
    # A distinct ~120-token prompt that shares nothing with the persona: adds one cache
    # entry of its own without touching the checkpoints' content.
    body = {"model": "openai/gpt-oss-20b", "max_tokens": 1,
            "messages": [{"role": "system", "content": f"Probe {k}. " + ("Count the stones in the wall. " * 12)},
                         {"role": "user", "content": f"How many stones, probe {k}?"}]}
    client.post("/chat/completions", json=body).raise_for_status()


P("baseline (may be cold)")
P("immediately again")
# idle
for wait in (5, 30, 90):
    time.sleep(wait)
    P(f"idle {wait}s then prime")
# count
for k in (1, 2, 3, 5):
    P(f"count: prime before {k} unrelated")
    for i in range(k):
        short_unrelated(i)
    P(f"count: prime after {k} unrelated")
# size: one ordinary MEDIUM turn between primes, repeated
for i in range(4):
    M("Explain three ways to make a film scene feel tense without using dialogue.")
    P(f"size: prime after one MEDIUM turn ({i})")
# session lifecycle: open and close a Voice session with no speech
session = VoiceSession(engine, started.recognizers(), submit=lambda *a, **k: None,  # type: ignore[arg-type]
                       conversation_id=None, signals=NO_PROJECT)
session.start(); time.sleep(2.0); session.close()
P("session: prime after a Voice session opened and closed with no speech")
Path(sys.argv[1]).write_text(json.dumps(results, indent=1) + "\n")
