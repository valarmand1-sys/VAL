"""Stage A2 — one Val Core exchange on GPT-5.6 Sol through the candidate lane.

Owner-authorised 14 September 2026 for ONE ordinary, non-consequential exchange
(maximum $0.23). Scratch store only (the lane refuses anything else); persona
v1.8 asserted before any call; every call recorded under `gpt-5-6-sol-medium`.

The consequential path is NOT authorised: if the real classifier marks the
prompt consequential, a harness-level guard on the lane's blind-position method
refuses before any candidate blind call is made, the turn ends unanswered, and
the spend to that point is reported. The guard is on the harness's own object
and changes nothing in `val_gateway.candidate`.

Usage: harness_a2.py OUT.json CAP_USD
"""

import json
import logging
import os
import plistlib
import sys
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

from val_domain.gateway import CacheTtl
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

logging.basicConfig(level=logging.INFO)
seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()
assert persona.semantic_version == "1.8", persona.semantic_version
adapters, problems = build_adapters({"anthropic", "openai"})
assert not problems, problems
sol = by_slug("gpt-5-6-sol-medium")
assert sol is not None
lane = candidate_gateway_for_scratch_store(
    engine,
    adapters=adapters,
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
    cache_ttl=CacheTtl.ONE_HOUR,
)
cap = float(sys.argv[2])
deltas: list[str] = []
PROMPT = "Good morning, Val. What is the time by the house's clock, and how are you today?"


def _refuse_blind(request: object, configuration: object) -> object:
    from val_domain.gateway import GatewayError, GatewayErrorKind

    raise GatewayError(
        GatewayErrorKind.INVALID_REQUEST,
        "A2 harness guard: the consequential path is not authorised; no candidate "
        "blind-position call is made under this authorisation.",
    )


lane.complete_candidate = _refuse_blind  # type: ignore[method-assign]
outcome = deliberate.send(
    engine,
    lane,
    PROMPT,
    catalogue=load_catalogue(engine),
    signals=ProjectSignals(explicit_no_project=True),
    candidate=sol,
    on_delta=deltas.append,
)
with engine.connect() as c:
    calls = [dict(r) for r in c.execute(text(
        "select m.id::text, m.task_type::text, m.model_config_id::text, m.provider, m.model_identifier, "
        "m.tokens_in, m.tokens_out, m.cost::text, m.latency_ms, m.status::text, m.terminal_state::text, "
        "m.persona_id::text, m.provider_request_id, "
        "x.streamed, x.first_text_ms, x.text_output_chars, x.reasoning_present, x.reasoning_output_tokens, "
        "x.provider_cached_input_tokens, x.provider_cache_write_tokens, x.exchange_message_id::text "
        "from model_calls m join model_call_measurements x on x.model_call_id = m.id order by m.created_at"
    )).mappings()]
    reservations = [dict(r) for r in c.execute(text(
        "select task_type::text, slug, state::text, max_cost::text, settled_cost::text, cost_certainty::text "
        "from budget_reservations order by created_at"
    )).mappings()]
    classification = [dict(r) for r in c.execute(text(
        "select verdict::text, hard_exclusion::text, attempts from classifications"
    )).mappings()]
    messages = [dict(r) for r in c.execute(text(
        "select role::text, sequence, content from messages order by sequence"
    )).mappings()]
    spent = float(c.execute(text("select coalesce(sum(cost),0) from model_calls")).scalar_one())
out = {"persona": {"version": persona.semantic_version, "id": str(persona.id), "sha256": persona.source_sha256},
       "prompt": PROMPT, "outcome": type(outcome).__name__, "deltas": len(deltas),
       "streamed_text": "".join(deltas), "classification": classification, "messages": messages,
       "calls": calls, "reservations": reservations, "spent": spent, "cap": cap, "over_cap": spent > cap}
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
