"""COLD -> WARM measurement pair on GPT-5.6 Sol through the candidate lane.

Owner-authorised 14 September 2026: two ordinary exchanges in one fresh scratch
conversation, $0.45 maximum for the pair, cumulative spend checked before the
second partner call, the consequential path refused by a harness guard on the
lane's blind method, no retry, no replacement prompt. The expected solution of
the reasoning prompt is never sent to the provider; it is compared afterward.

Usage: harness_pair.py OUT.json
"""

import json
import logging
import os
import plistlib
import re
import sys
import time
from itertools import permutations
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY"):
    os.environ[k] = env[k]
os.environ["VAL_CACHE_TTL"] = "1h"

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path("/Users/josepharmand/Projects/val")
URL = "postgresql+psycopg://localhost:5433/val_test"
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

from val_domain.gateway import CacheTtl, GatewayError, GatewayErrorKind
from val_domain.registry import by_slug
from val_gateway import deliberate
from val_gateway.candidate import candidate_gateway_for_scratch_store
from val_gateway.ledger import DatabaseLedger
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_gateway.startup import build_adapters
from val_policy.budget import maximum_cost
from val_policy.project_resolution import ProjectSignals

logging.basicConfig(level=logging.WARNING)
seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()
assert persona.semantic_version == "1.8", persona.semantic_version
adapters, problems = build_adapters({"anthropic", "openai"})
assert not problems, problems
sol = by_slug("gpt-5-6-sol-medium")
haiku = by_slug("haiku-4-5-20251001")
assert sol is not None and haiku is not None
lane = candidate_gateway_for_scratch_store(
    engine,
    adapters=adapters,
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
    cache_ttl=CacheTtl.ONE_HOUR,
)


def _refuse_blind(request: object, configuration: object) -> object:
    raise GatewayError(
        GatewayErrorKind.INVALID_REQUEST,
        "pair harness guard: the consequential path is not authorised; no candidate "
        "blind-position call is made.",
    )


lane.complete_candidate = _refuse_blind  # type: ignore[method-assign]

AUTHORISED = 0.45
PRIMER = "Good morning, Val. Please tell me the current time by the house's clock in one brief sentence."
PROBLEM = (
    "Five deployment jobs, A, B, C, D, and E, must each run exactly once. B must run after A. "
    "D must run after both B and C. E must run before C. A must run after E. Give every valid "
    "execution order and briefly explain why no others are possible."
)
EXPECTED = {("E", "A", "B", "C", "D"), ("E", "A", "C", "B", "D"), ("E", "C", "A", "B", "D")}


def spent() -> float:
    with engine.connect() as c:
        return float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one())


def snapshot() -> dict[str, object]:
    with engine.connect() as c:
        return {
            "calls": [dict(r) for r in c.execute(text(
                "select m.id::text, m.task_type::text, m.model_config_id::text, m.provider, "
                "m.model_identifier, m.tokens_in, m.tokens_out, m.cost::text, m.latency_ms, "
                "m.status::text, m.terminal_state::text, m.persona_id::text, m.provider_request_id, "
                "m.created_at::text, x.streamed, x.first_text_ms, x.text_output_chars, "
                "x.reasoning_present, x.reasoning_output_tokens, x.provider_cached_input_tokens, "
                "x.provider_cache_write_tokens, x.exchange_message_id::text "
                "from model_calls m join model_call_measurements x on x.model_call_id = m.id "
                "order by m.created_at")).mappings()],
            "reservations": [dict(r) for r in c.execute(text(
                "select task_type::text, slug, state::text, max_cost::text, settled_cost::text, "
                "cost_certainty::text, exchange_message_id::text from budget_reservations "
                "order by created_at")).mappings()],
            "classifications": [dict(r) for r in c.execute(text(
                "select message_id::text, verdict::text, hard_exclusion::text, attempts "
                "from classifications order by created_at")).mappings()],
            "messages": [dict(r) for r in c.execute(text(
                "select role::text, sequence, content from messages order by sequence")).mappings()],
        }


out: dict[str, object] = {
    "persona": {"version": persona.semantic_version, "id": str(persona.id), "sha256": persona.source_sha256},
    "authorised_usd": AUTHORISED,
}
catalogue = load_catalogue(engine)

# --- Turn 1: cold primer --------------------------------------------------------------
deltas1: list[str] = []
t1_started = time.time()
outcome1 = deliberate.send(
    engine, lane, PRIMER, catalogue=catalogue,
    signals=ProjectSignals(explicit_no_project=True), candidate=sol, on_delta=deltas1.append,
)
out["turn1"] = {"kind": type(outcome1).__name__, "started_at": t1_started, "streamed_text": "".join(deltas1),
                "error": str(getattr(outcome1, "error", "")) or None}
spent1 = spent()
out["spent_after_turn1"] = spent1
if not isinstance(outcome1, deliberate.DeliberatedTurn) or outcome1.captured_as is not None:
    out["stopped"] = "turn 1 did not complete as an ordinary answered turn"
    out["store"] = snapshot()
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
    sys.exit(0)
conversation_id = outcome1.turn.conversation.id

# --- Cumulative-spend check before the second exchange -------------------------------
remaining_max = (
    maximum_cost(haiku, (PROBLEM,), 256)
    + maximum_cost(sol, (persona.content, PRIMER, "".join(deltas1), "x" * 3000, PROBLEM), 4096)
)
out["turn2_admission"] = {"spent_after_turn1": spent1, "remaining_conservative_max": remaining_max,
                          "sum": spent1 + remaining_max, "admitted": spent1 + remaining_max <= AUTHORISED}
if spent1 + remaining_max > AUTHORISED:
    out["stopped"] = "cumulative bound would exceed the authorisation"
    out["store"] = snapshot()
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
    sys.exit(0)

# --- Turn 2: warm substantive turn, same conversation, immediately ----------------------
deltas2: list[str] = []
t2_started = time.time()
outcome2 = deliberate.send(
    engine, lane, PROBLEM, catalogue=catalogue, conversation_id=conversation_id,
    signals=ProjectSignals(explicit_no_project=True), candidate=sol, on_delta=deltas2.append,
)
answer = "".join(deltas2)
out["turn2"] = {"kind": type(outcome2).__name__, "started_at": t2_started,
                "seconds_after_turn1_start": round(t2_started - t1_started, 1),
                "streamed_text": answer, "error": str(getattr(outcome2, "error", "")) or None}

# --- Mechanical comparison (never sent to the provider) -------------------------------
found: set[tuple[str, ...]] = set()
for perm in permutations("ABCDE"):
    pattern = r"\b" + r"\s*(?:,|->|→|>|-|–|—|then|\s)\s*".join(perm) + r"\b"
    if re.search(pattern, answer):
        found.add(perm)
out["comparison"] = {
    "expected": sorted(" ".join(p) for p in EXPECTED),
    "found_in_answer": sorted(" ".join(p) for p in found),
    "all_expected_present": EXPECTED <= found,
    "omitted": sorted(" ".join(p) for p in EXPECTED - found),
    "extra": sorted(" ".join(p) for p in found - EXPECTED),
}
out["spent_total"] = spent()
out["over_authorisation"] = out["spent_total"] > AUTHORISED
out["store"] = snapshot()
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps({k: v for k, v in out.items() if k != "store"}, indent=1))
print(json.dumps([{k: r[k] for k in ("task_type", "model_identifier", "tokens_in", "tokens_out", "cost", "latency_ms", "terminal_state", "first_text_ms", "text_output_chars", "reasoning_present", "reasoning_output_tokens", "provider_cached_input_tokens", "provider_cache_write_tokens")} for r in out["store"]["calls"]], indent=1))
print(json.dumps(out["store"]["reservations"], indent=1))
print(json.dumps(out["store"]["classifications"], indent=1))
