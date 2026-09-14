"""Three-turn OpenAI cache-boundary proof, second authorisation — 14 September 2026.

Cache transport measurement only, $0.20 maximum, self-contained: proves the
explicit breakpoint — translated by the adapter to the nearest preceding user
message — is accepted by the provider and that cached-read tokens on turn 3
exceed the persona-only baseline (≈ 4,821) by the retained history. Scratch
store only; Sol medium; persona v1.8; no House material; visible answers short
(output ceiling 200); no candidate blind call; answers are not rescored.

Cap predicate (no command-line figures): before every paid call, cumulative
actual provider spend plus an internal conservative maximum for that call must
stay within $0.20. The maximum for a Sol call is the fixed proof shape's
measured largest input (7,172 tokens on the cold primer, 14 September 2026)
plus a 1,500-token margin, all priced as written at $5/M, plus the 200-token
output ceiling at $20/M: (8,672 × 5 + 200 × 20) / 1e6 = $0.04736. Turns 2 and 3
add at most a few hundred tokens to that input, inside the margin. The
classification call uses the ledger's own bound (about $0.01). This is far
above any possible actual cost of a proof call and far below the byte-based
production bound, which is not used here.

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
from val_providers.openai_adapter import logical_cache_boundary, physical_cache_boundary

AUTHORISED_USD = 0.20
OUTPUT_CEILING = 200
MEASURED_LARGEST_PRIMER_INPUT = 7_172  # cold primer of this fixed shape, 14 September 2026
INPUT_MARGIN = 1_500
SOL_CALL_MAX_USD = ((MEASURED_LARGEST_PRIMER_INPUT + INPUT_MARGIN) * 5.0 + OUTPUT_CEILING * 20.0) / 1e6

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
        worst = SOL_CALL_MAX_USD if config.model_identifier == "gpt-5.6-sol" else max_cost_usd
        if settled + worst > AUTHORISED_USD:
            raise CapReached(json.dumps({"settled": round(settled, 6), "next_maximum": round(worst, 6), "task": task_type.value, "cap": AUTHORISED_USD}))
        return super().reserve(config, max_cost_usd, task_type, project_id, exchange=exchange)


lane = candidate_gateway_for_scratch_store(
    engine, adapters=adapters, recorder=lambda record: record_call(engine, record), ledger=CapLedger(engine),
    persona_loader=DatabasePersonaLoader(engine), verify_provenance=verifier(engine), cache_ttl=CacheTtl.ONE_HOUR,
)


def _refuse_blind(request: object, configuration: object) -> object:
    raise GatewayError(GatewayErrorKind.INVALID_REQUEST, "cache-proof guard: no candidate blind call is authorised")


lane.complete_candidate = _refuse_blind  # type: ignore[method-assign]

# Observers, non-mutating: the logical boundary as Core supplied it (at the adapter's
# input) and the physical request as sent (at the SDK client).
logical_log: list[dict[str, object]] = []
transmitted: list[dict[str, object]] = []
_openai = adapters["openai"]
_real_stream = _openai.stream


def _observing_stream(config, messages, *args, **kwargs):  # type: ignore[no-untyped-def]
    logical_log.append({"logical_boundary": logical_cache_boundary(messages), "physical_boundary": physical_cache_boundary(messages),
                        "roles": [m.role for m in messages]})
    return _real_stream(config, messages, *args, **kwargs)


_openai.stream = _observing_stream  # type: ignore[method-assign]
_client = _openai._client  # type: ignore[attr-defined]
_real_create = _client.responses.create


def _recording_create(**kwargs):  # type: ignore[no-untyped-def]
    items = kwargs.get("input") or []
    described = []
    for index, item in enumerate(items):
        content = item.get("content")
        if isinstance(content, list):
            described.append({"index": index, "role": item.get("role"), "block": content[0].get("type"), "marked": "prompt_cache_breakpoint" in content[0], "chars": len(content[0].get("text", ""))})
        else:
            described.append({"index": index, "role": item.get("role"), "block": "string", "marked": False, "chars": len(content or "")})
    transmitted.append({"items": described, "implicit_mode": "prompt_cache_options" not in kwargs})
    return _real_create(**kwargs)


_client.responses.create = _recording_create

PAYLOAD = "Reference note for The Lantern Road, fictional logistics, for the record only. Reply in one short sentence acknowledging the note; no summary is needed.\n" + "\n".join(
    f"{i}. Item {i}: the courier's handcart is checked at the harbour gate at {6 + i % 12}:{(i * 7) % 60:02d}; the clockmaker's bench is cleared by {(i * 3) % 24}:00; spare lantern glass is counted in crate {i % 9 + 1}."
    for i in range(1, 41)
)
TURNS = [
    ("T1 primer (fixed neutral payload)", PAYLOAD),
    ("T2 short", "Noted. In one short sentence, what is crate 3 used for in that note?"),
    ("T3 short", "And in one short sentence, which gate is the handcart checked at?"),
]

out: dict[str, object] = {"persona": {"version": persona.semantic_version, "id": str(persona.id), "sha256": persona.source_sha256},
                          "authorised_usd": AUTHORISED_USD, "sol_call_max_usd": round(SOL_CALL_MAX_USD, 6), "turns": []}
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
            candidate=sol, on_delta=deltas.append, max_output_tokens=OUTPUT_CEILING,
        )
        rec: dict[str, object] = {"label": label, "kind": type(outcome).__name__, "seconds_after_start": round(started - t0, 1), "answer": "".join(deltas)}
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
out["logical"] = logical_log
out["transmitted"] = transmitted
Path(sys.argv[1]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
