"""The decisive cross-request reuse probe — latency pass §6.1.

Two **byte-identical** requests, sent in immediate succession, locally, at
production MEDIUM, at $0. Byte-identity is confirmed through the exact-preflight
renderer **before** either is sent. The question it settles outright: does this
serving path reuse prompt/KV state across independent requests?

Diagnostic only. Recorded truthfully as evaluation evidence and **excluded from
every latency comparison**. Nothing enters Lord Armand's conversation history.
"""

import hashlib
import json
import os
import plistlib
import time
from datetime import timedelta
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    _env = plistlib.load(f)["EnvironmentVariables"]
if "VAL_LMSTUDIO_API_TOKEN" in _env:
    os.environ["VAL_LMSTUDIO_API_TOKEN"] = _env["VAL_LMSTUDIO_API_TOKEN"]

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg://localhost:5433/val_test"
os.environ["VAL_DATABASE_URL"] = URL

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import lmstudio

import val_gateway.loop as loop_module
from val_domain.gateway import Classification, TurnReference
from val_domain.registry import by_slug
from val_gateway.candidate import candidate_gateway_for_scratch_store
from val_gateway.ledger import DatabaseLedger
from val_gateway.loop import assemble_turn, open_turn, settle_turn
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_gateway.startup import build_adapters
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS
from val_policy.project_resolution import ProjectSignals
from val_providers.lmstudio_adapter import _chat_turns
from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS

A1 = (
    "Evening, Val. Rough week. I got the notes back on the pilot draft from the "
    "two readers I trust — one says the second act drags, the other says it's the "
    "best thing I've written. I don't know which to believe, and I'm tempted to "
    "just cut fifteen pages and be done with it. What do you think?"
)
#: The evaluation-only twin of the production artifact at the production effort.
SLUG = "gpt-oss-20b-mxfp4-mlx-lmstudio"

engine = create_engine(URL)
with engine.begin() as c:
    c.execute(text("DROP SCHEMA public CASCADE"))
    c.execute(text("CREATE SCHEMA public"))
cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("script_location", str(ROOT / "packages/domain/migrations"))
cfg.set_main_option("sqlalchemy.url", URL)
command.upgrade(cfg, "head")
engine.dispose()
engine = create_engine(URL)
seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()

adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
config = by_slug(SLUG)
assert config is not None
readiness = dict(adapter.ensure_runtime_ready(config))
inspector = adapter._inspector
instance, handle = inspector.loaded_instance(config.model_identifier)

lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# --- freeze every dynamic field, so the two requests cannot differ -----------------------
real_now = loop_module.local_now
frozen_at = real_now()
loop_module.local_now = lambda: frozen_at


def prepare() -> tuple[object, tuple, list[dict[str, str]]]:
    opened = open_turn(
        engine,
        A1,
        catalogue=load_catalogue(engine),
        signals=ProjectSignals(explicit_no_project=True),
    )
    messages, recalled = assemble_turn(engine, opened)
    turns = _chat_turns(messages, persona.content)
    return opened, (messages, recalled), turns


def rendered(turns: list[dict[str, str]]) -> str:
    chat = lmstudio.Chat()
    for turn in turns:
        if turn["role"] == "system":
            chat.add_system_prompt(turn["content"])
        elif turn["role"] == "user":
            chat.add_user_message(turn["content"])
        else:
            chat.add_assistant_response(turn["content"])
    return handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))


first_opened, first_parts, first_turns = prepare()
second_opened, second_parts, second_turns = prepare()
first_text, second_text = rendered(first_turns), rendered(second_turns)
first_digest = hashlib.sha256(first_text.encode()).hexdigest()
second_digest = hashlib.sha256(second_text.encode()).hexdigest()

print("first :", first_digest)
print("second:", second_digest)
if first_digest != second_digest:
    print("STOP: the two requests are not byte-identical; nothing was sent.")
    loop_module.local_now = real_now
    raise SystemExit(3)

# --- the transport observer, non-mutating -------------------------------------------------
timing: dict[str, float] = {}
_real_create = adapter._client.chat.completions.create


def _observed_create(**kwargs):
    timing.clear()
    timing["sent"] = time.monotonic()
    result = _real_create(**kwargs)
    if not kwargs.get("stream"):
        timing["first_chunk"] = time.monotonic()
        return result

    def _iter():
        for chunk in result:
            now = time.monotonic()
            timing.setdefault("first_chunk", now)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is not None and getattr(delta, "content", None):
                    timing.setdefault("first_content", now)
            timing["last_chunk"] = now
            yield chunk

    return _iter()


adapter._client.chat.completions.create = _observed_create


def one_call(label: str, opened, parts, digest: str) -> dict:
    messages, recalled = parts
    turn = TurnReference(
        conversation_id=opened.conversation.id, message_id=opened.user_message.id
    )
    started = time.monotonic()
    response = lane.converse_candidate(
        messages,
        scope=opened.scope,
        classification=Classification.PROTECTED,
        turn=turn,
        configuration=config,
        max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
        on_delta=lambda piece: None,
    )
    ended = time.monotonic()
    settle_turn(engine, opened, recalled, response)
    sent = timing.get("sent", started)
    with engine.connect() as c:
        row = c.execute(
            text(
                "select m.tokens_in, m.tokens_out, m.latency_ms, x.reasoning_output_tokens, "
                "x.first_text_ms from model_calls m join model_call_measurements x "
                "on x.model_call_id = m.id order by m.created_at desc limit 1"
            )
        ).mappings().one()
    return {
        "label": label,
        "diagnostic_excluded_from_every_latency_comparison": True,
        "request_sha256": digest,
        "pre_generation_interval_s": (
            None if "first_chunk" not in timing else round(timing["first_chunk"] - sent, 3)
        ),
        "request_start_to_first_core_visible_text_s": (
            None if "first_content" not in timing else round(timing["first_content"] - sent, 3)
        ),
        "core_call_total_s": round(ended - started, 3),
        "prompt_tokens": row["tokens_in"],
        "output_tokens": row["tokens_out"],
        "reasoning_tokens": row["reasoning_output_tokens"],
        "latency_ms": row["latency_ms"],
    }


print("=== call 1 ===")
first = one_call("probe_call_1", first_opened, first_parts, first_digest)
print(json.dumps(first, indent=1))
print("=== call 2, immediately after, byte-identical ===")
second = one_call("probe_call_2", second_opened, second_parts, second_digest)
print(json.dumps(second, indent=1))
loop_module.local_now = real_now

a = first["pre_generation_interval_s"]
b = second["pre_generation_interval_s"]
delta = None if a is None or b is None else round(a - b, 3)
percent = None if not a else round((a - b) / a * 100, 1)
# "Materially shorter" is read as at least a third faster: a prefix cache that
# reused 93% of the prompt would be far larger than that, and ordinary run-to-run
# noise on this machine is far smaller.
material = percent is not None and percent >= 33.0
finding = (
    "CROSS-REQUEST PREFIX REUSE CONFIRMED AND ACTIVE"
    if material
    else "CROSS-REQUEST PREFIX REUSE NOT SUPPORTED ON THIS SERVING PATH"
)

report = {
    "probe": "decisive cross-request reuse probe",
    "order": "pre-WP3 latency pass §6.1, owner execution order 24 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "byte_identical_confirmed_before_sending": True,
    "request_sha256": first_digest,
    "runtime": {
        "supervisor_readiness": readiness,
        "model_identifier": instance.identifier,
        "loaded_context": instance.context_length,
        "lmstudio_sdk_version": lmstudio.__version__,
    },
    "configuration": {"slug": config.slug, "reasoning_effort": config.reasoning_effort.value},
    "calls": [first, second],
    "pre_generation_interval_delta_s": delta,
    "pre_generation_interval_delta_percent": percent,
    "materiality_threshold_percent": 33.0,
    "finding": finding,
    "cost_usd": 0.0,
}
out = HERE / "reuse-probe.json"
out.write_text(json.dumps(report, indent=1, default=str))
print("\n=== finding ===")
print(json.dumps({k: report[k] for k in
                  ("pre_generation_interval_delta_s", "pre_generation_interval_delta_percent",
                   "finding")}, indent=1))
print("written:", out)
