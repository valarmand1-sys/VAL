"""Why the fast candidate does not answer the light turn — a bounded diagnostic, 26 Sept 2026.

Captures the exact request the real preparation path builds (persona whole, envelope,
history, canonical wire form) by intercepting the gateway just before transmission,
then replays it against the loaded Qwen3-4B instance through LM Studio's
OpenAI-compatible endpoint under controlled variants. Diagnostic only: nothing here
is a production change; variants that alter the assembled structure are evidence for
a ruling, not an implementation. Local, $0.
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

import httpx  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from val_gateway.deliberate import prepare_light_answer  # noqa: E402
from val_gateway.gateway import Gateway  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.startup import start  # noqa: E402
from val_policy.light_conversation import FastRoute  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402
from val_providers.lmstudio_adapter import _chat_turns  # noqa: E402

engine = create_engine(URL)
started = start(engine)
gateway = started.gateway
catalogue = load_catalogue(engine)
BOTH = FastRoute(frozenset({1, 2}))
with engine.connect() as connection:
    conversation_id = connection.execute(
        text("select id from conversations order by started_at desc limit 1")
    ).scalar_one()


class Captured(Exception):
    def __init__(self, messages, persona):  # noqa: ANN001
        self.messages, self.persona = messages, persona


def intercept(self, messages, *, scope, max_output_tokens, egress):  # noqa: ANN001, ANN201
    persona = self._persona_loader.active()
    raise Captured(messages, persona.content)


Gateway.converse_prospectively = intercept  # type: ignore[method-assign]


def capture(phrase: str, history: bool):  # noqa: ANN201
    import val_gateway.deliberate as d
    original = d.record_preparation
    d.record_preparation = lambda *a, **k: None  # the interception is not a failure to record
    try:
        prepare_light_answer(
            engine, gateway, phrase, catalogue=catalogue,
            signals=None if history else ProjectSignals(explicit_no_project=True),
            conversation_id=conversation_id if history else None, fast_route=BOTH,
        )
    except Captured as got:
        return got
    finally:
        d.record_preparation = original
    raise SystemExit("not captured")


BASE = os.environ.get("VAL_LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
client = httpx.Client(base_url=BASE, timeout=120.0,
                      headers={"Authorization": f"Bearer {os.environ['VAL_LMSTUDIO_API_TOKEN']}"})
MODEL = "qwen3-4b-instruct-2507"


def ask(turns, **sampling):  # noqa: ANN001, ANN201
    body = {"model": MODEL, "messages": turns, "max_tokens": 200, "stream": False, **sampling}
    r = client.post("/chat/completions", json=body)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


RECOMMENDED = {"temperature": 0.7, "top_p": 0.8, "top_k": 20}
LOW = {"temperature": 0.2, "top_p": 0.8, "top_k": 20}
PHRASES = ["Good evening, Val.", "Thank you so much, Val.", "How are you tonight, Val?",
           "I'm well tonight, Val.", "Good night to you, Val.", "Thanks very much indeed."]
results = []
for history in (False, True):
    for phrase in PHRASES:
        got = capture(phrase, history)
        wire = _chat_turns(got.messages, got.persona)  # exactly what the adapter sends
        # Variant: his words as their own final user message (the envelope stays whole).
        split = list(wire[:-1])
        merged = wire[-1]["content"]
        envelope, _, words = merged.rpartition("\n\n")
        split_turns = split + [{"role": "user", "content": envelope}, {"role": "user", "content": words}]
        # Diagnostic control: the envelope removed (NOT a deployable form).
        no_envelope = split + [{"role": "user", "content": words}]
        row = {"history": history, "phrase": phrase, "wire_turns": len(wire),
               "last_user_chars": len(merged), "words_at_end": merged.endswith(phrase)}
        row["as_is"] = ask(wire)
        row["recommended_sampling"] = ask(wire, **RECOMMENDED)
        row["low_temperature"] = ask(wire, **LOW)
        row["words_separate"] = ask(split_turns, **RECOMMENDED)
        row["no_envelope_control"] = ask(no_envelope, **RECOMMENDED)
        results.append(row)
        print(json.dumps(row, ensure_ascii=False, indent=1))
Path(__file__).with_name("light-prompt-diagnostic.json").write_text(json.dumps(results, indent=1, ensure_ascii=False) + "\n")
