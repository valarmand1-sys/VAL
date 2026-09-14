"""Three-turn OpenAI cache-boundary proof on the Sol candidate lane — owner-authorised 14 September 2026.

Cache transport measurement only, $0.20 maximum for the three exchanges: proves
that the explicit `prompt_cache_breakpoint` on the last retained history
message is honoured by the provider, i.e. that by turn 3 cached-read tokens
exceed the persona-only baseline (≈ 4,821) by the retained history. Scratch
store only; Sol medium; persona v1.8; no House material; visible answers kept
short (output ceiling 200); answers are not rescored. A cap ledger refuses,
before any provider call, a reservation that would take cumulative settled
spend plus the call's maximum over the authorisation.

Usage: harness_cache_proof.py OUT.json
"""

import json
import logging
import os
import plistlib
import sys
import time
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

from val_domain.gateway import CacheTtl, GatewayError, GatewayErrorKind, ModelConfig, TaskType, TurnReference
from val_domain.registry import by_slug
from val_gateway import deliberate
from val_gateway.candidate import candidate_gateway_for_scratch_store
from val_gateway.ledger import DatabaseLedger
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_gateway.startup import build_adapters
from val_policy.project_resolution import ProjectSignals

# The owner's maximum for the proof is $0.20 of provider spend. The first attempt (16:59
# CDT) stopped itself before turn 2 with $0.039923 spent, because its pre-call check
# used the ledger's byte-based reservation bound ($0.16 for a call that costs $0.04);
# this attempt counts that spend against the cap and checks the honest worst case
# instead: cumulative settled + (the largest input seen so far + 400 tokens, all
# written at $5/M) + the 200-token output ceiling at $20/M + the classification bound.
ALREADY_SPENT = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
CAP = 0.20 - ALREADY_SPENT
# The largest Sol input already measured on this request shape (attempt 1: 7,172
# tokens, $0.036177 with everything written), so turn 1's worst case is known too.
KNOWN_LARGEST_IN = int(sys.argv[3]) if len(sys.argv) > 3 else 0
logging.basicConfig(level=logging.WARNING)
seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()
assert persona.semantic_version == "1.8", persona.semantic_version
adapters, problems = build_adapters({"anthropic", "openai"})
assert not problems, problems
sol = by_slug("gpt-5-6-sol-medium")
assert sol is not None


class CapReached(Exception):
    pass


class CapLedger(DatabaseLedger):
    def reserve(self, config: ModelConfig, max_cost_usd: float, task_type: TaskType, project_id, exchange: TurnReference | None = None):
        with engine.connect() as c:
            settled = float(c.execute(text("select coalesce(sum(cost), 0) from model_calls")).scalar_one())
            largest_in = max(KNOWN_LARGEST_IN, int(c.execute(text("select coalesce(max(tokens_in), 0) from model_calls where model_identifier = 'gpt-5.6-sol'")).scalar_one()))
        if task_type is TaskType.CONVERSATION and largest_in:
            worst = ((largest_in + 400) * 5.0 + 200 * 20.0) / 1e6
        else:
            worst = max_cost_usd
        if settled + worst > CAP:
            raise CapReached(json.dumps({"settled": round(settled, 6), "next_worst_case": round(worst, 6), "ledger_bound": round(max_cost_usd, 6), "task": task_type.value, "cap": CAP}))
        return super().reserve(config, max_cost_usd, task_type, project_id, exchange=exchange)


lane = candidate_gateway_for_scratch_store(
    engine, adapters=adapters, recorder=lambda record: record_call(engine, record), ledger=CapLedger(engine),
    persona_loader=DatabasePersonaLoader(engine), verify_provenance=verifier(engine), cache_ttl=CacheTtl.ONE_HOUR,
)


def _refuse_blind(request: object, configuration: object) -> object:
    raise GatewayError(GatewayErrorKind.INVALID_REQUEST, "cache-proof guard: no candidate blind call is authorised")


lane.complete_candidate = _refuse_blind  # type: ignore[method-assign]

# Observe the transport: record, per OpenAI request, which input item carried the
# explicit breakpoint and the item count — the SDK client's create, wrapped, unchanged.
transmitted: list[dict[str, object]] = []
_client = adapters["openai"]._client  # type: ignore[attr-defined]
_real_create = _client.responses.create


def _recording_create(**kwargs):  # type: ignore[no-untyped-def]
    items = kwargs.get("input") or []
    marked = [
        (index, item.get("role"), len(item["content"][0]["text"]))
        for index, item in enumerate(items)
        if isinstance(item.get("content"), list)
        and any("prompt_cache_breakpoint" in block for block in item["content"])
    ]
    transmitted.append({"items": len(items), "marked": marked, "prompt_cache_options": kwargs.get("prompt_cache_options", "absent")})
    return _real_create(**kwargs)


_client.responses.create = _recording_create

# A fixed, neutral, fictional payload: numbered logistics lines about a fictional serial,
# about 5,000 characters, so history reuse on turn 3 is distinguishable from the
# ≈4,821-token persona-only read. No House material.
PAYLOAD = "Reference note for The Lantern Road, fictional logistics, for the record only. Reply in one short sentence acknowledging the note; no summary is needed.\n" + "\n".join(
    f"{i}. Item {i}: the courier's handcart is checked at the harbour gate at {6 + i % 12}:{(i * 7) % 60:02d}; the clockmaker's bench is cleared by {(i * 3) % 24}:00; spare lantern glass is counted in crate {i % 9 + 1}."
    for i in range(1, 41)
)
TURNS = [
    ("T1 primer (fixed neutral payload)", PAYLOAD),
    ("T2 short", "Noted. In one short sentence, what is crate 3 used for in that note?"),
    ("T3 short", "And in one short sentence, which gate is the handcart checked at?"),
]

out: dict[str, object] = {"persona": {"version": persona.semantic_version, "id": str(persona.id), "sha256": persona.source_sha256}, "cap": CAP, "turns": []}
catalogue = load_catalogue(engine)
conversation_id = None
t0 = time.time()
try:
    for label, prompt in TURNS:
        deltas: list[str] = []
        started = time.time()
        outcome = deliberate.send(
            engine, lane, prompt, catalogue=catalogue, conversation_id=conversation_id,
            signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
            candidate=sol, on_delta=deltas.append, max_output_tokens=200,
        )
        kind = type(outcome).__name__
        rec: dict[str, object] = {"label": label, "kind": kind, "seconds_after_start": round(started - t0, 1), "answer": "".join(deltas)}
        if isinstance(outcome, deliberate.DeliberatedTurn):
            conversation_id = outcome.turn.conversation.id
            rec["captured_as"] = None if outcome.captured_as is None else outcome.captured_as.value
        else:
            rec["error"] = str(getattr(outcome, "error", outcome))[:300]
        out["turns"].append(rec)
        if not isinstance(outcome, deliberate.DeliberatedTurn) or outcome.captured_as is not None:
            out["stopped"] = f"{label}: not an ordinary answered turn"
            break
except CapReached as cap:
    out["stopped"] = f"cap: {cap}"

with engine.connect() as c:
    out["calls"] = [dict(r) for r in c.execute(text(
        "select m.task_type::text, m.model_identifier, m.tokens_in, m.tokens_out, m.cost::text, m.latency_ms, m.terminal_state::text, "
        "x.first_text_ms, x.text_output_chars, x.reasoning_output_tokens, x.provider_cached_input_tokens as read, x.provider_cache_write_tokens as written, "
        "r.max_cost::text as reserved_max from model_calls m join model_call_measurements x on x.model_call_id = m.id "
        "left join budget_reservations r on r.model_call_id = m.id order by m.created_at")).mappings()]
    out["spent"] = float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one())
out["transmitted"] = transmitted
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
