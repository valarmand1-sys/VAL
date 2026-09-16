"""Live loopback proof of the LM Studio adapter — the candidate lane on the scratch store.

Ruling, 16 September 2026. Cloud/provider API cost: $0 — no cloud provider is
called. No classification, strip or blind call is made (those run on cloud
routes): the turn is assembled by Val Core's own loop functions — the whole
active persona, the record-state and capability-state envelopes, the retained
history — and sent through `CandidateGateway.converse_candidate`, pinned to the
NOT_ADMITTED local entry. Nothing here is a production utterance, admits
anything, or touches production routing. The scratch store `val_test` is reset.

Observers are non-mutating: the SDK client's `create` is wrapped only to
timestamp the first chunk of any kind (prefill end) and the first content
chunk; reasoning text is never read, stored or printed.

Usage: harness_loopback.py OUT.json [--turns N]
"""

import json
import os
import plistlib
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
if "VAL_LMSTUDIO_API_TOKEN" not in env:
    print("VAL_LMSTUDIO_API_TOKEN is not in the LaunchAgent plist; nothing was run.")
    sys.exit(2)
os.environ["VAL_LMSTUDIO_API_TOKEN"] = env["VAL_LMSTUDIO_API_TOKEN"]

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

from val_domain.gateway import Classification, GatewayError, TurnReference
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
from val_policy.tokens import estimate_tokens

seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()
adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
local = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio")
assert local is not None

lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# Non-mutating timing observer on the transport: first chunk of any kind, first content.
timing: dict[str, float | None] = {}
_real_create = adapter._client.chat.completions.create


def _observed_create(**kwargs):  # type: ignore[no-untyped-def]
    timing.clear()
    timing["sent"] = time.monotonic()
    result = _real_create(**kwargs)
    if not kwargs.get("stream"):
        timing["first_chunk"] = time.monotonic()
        return result

    def _iter():  # type: ignore[no-untyped-def]
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


adapter._client.chat.completions.create = _observed_create  # type: ignore[method-assign]

TURNS = [
    "Good evening, Val. I want your own view, in about three paragraphs, on how a house "
    "should keep a written record of the decisions it makes — what belongs in such a record, "
    "what does not, and what goes wrong when a house relies on memory instead.",
    "Take your second point further. Give me two concrete failure cases, each in its own "
    "short paragraph, and say which of the two you think is the more dangerous for a small "
    "house and why.",
    "Now summarise, in one paragraph, what we have settled in this conversation so far, "
    "and name the one question you would put back to me.",
]

out: dict[str, object] = {
    "persona": {"version": persona.semantic_version, "id": str(persona.id)},
    "configuration": {"slug": local.slug, "id": str(local.id), "model": local.model_identifier},
    "runtime_facts_at_start": adapter.runtime_facts(local.model_identifier),
    "turns": [],
}
catalogue = load_catalogue(engine)
conversation_id = None
label = sys.argv[2] if len(sys.argv) > 2 else "run"
for index, content in enumerate(TURNS, start=1):
    opened = open_turn(
        engine,
        content,
        catalogue=catalogue,
        signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
        conversation_id=conversation_id,
    )
    conversation_id = opened.conversation.id
    messages, recalled = assemble_turn(engine, opened)
    turn = TurnReference(conversation_id=opened.conversation.id, message_id=opened.user_message.id)
    estimated_prompt = estimate_tokens(persona.content) + sum(estimate_tokens(m.content) for m in messages)
    deltas: list[str] = []
    delta_times: list[float] = []
    started = time.monotonic()
    record: dict[str, object] = {
        "turn": index,
        "label": f"{label} T{index}",
        "loaded_state_before": adapter._read_native_models().get(local.model_identifier, {}).get("state"),
        "estimated_prompt_tokens_local": estimated_prompt,
        "messages_sent": len(messages) + 1,
    }
    try:
        response = lane.converse_candidate(
            messages,
            scope=opened.scope,
            classification=Classification.PROTECTED,
            turn=turn,
            configuration=local,
            max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
            on_delta=lambda piece: (deltas.append(piece), delta_times.append(time.monotonic())),
        )
        ended = time.monotonic()
        settled = settle_turn(engine, opened, recalled, response)
        record["outcome"] = type(settled).__name__
        record["visible_chars"] = len("".join(deltas))
        record["answer_head"] = "".join(deltas)[:400]
    except GatewayError as failure:
        ended = time.monotonic()
        record["outcome"] = "GatewayError"
        record["error"] = f"{failure.kind.value}: {failure.detail[:400]}"
    sent = timing.get("sent", started)
    record["timing_s"] = {
        "core_call_total": round(ended - started, 3),
        "prefill_to_first_chunk": None if timing.get("first_chunk") is None else round(timing["first_chunk"] - sent, 3),
        "first_visible_content": None if timing.get("first_content") is None else round(timing["first_content"] - sent, 3),
        "generation_after_first_chunk": None if timing.get("first_chunk") is None else round((timing.get("last_chunk") or ended) - timing["first_chunk"], 3),
    }
    out["turns"].append(record)
    if record["outcome"] == "GatewayError":
        break

with engine.connect() as c:
    out["calls"] = [dict(r) for r in c.execute(text(
        "select m.task_type::text, m.provider, m.model_identifier, m.model_config_id::text, m.tokens_in, m.tokens_out, "
        "m.cost::text, m.cost_certainty::text, m.latency_ms, m.terminal_state::text, m.status::text, m.persona_id::text, "
        "x.streamed, x.first_text_ms, x.text_output_chars, x.reasoning_present, x.reasoning_output_tokens, "
        "x.provider_reported_model, x.runtime_diagnostics, r.max_cost::text as reserved_max, r.settled_cost::text "
        "from model_calls m join model_call_measurements x on x.model_call_id = m.id "
        "left join budget_reservations r on r.model_call_id = m.id order by m.created_at")).mappings()]
    out["val_messages"] = c.execute(text("select count(*) from messages where role = 'val'")).scalar_one()
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
print(json.dumps({k: v for k, v in out.items() if k != "calls"}, indent=1, default=str))
for call in out["calls"]:
    print({k: call[k] for k in ("tokens_in", "tokens_out", "cost", "cost_certainty", "latency_ms", "terminal_state", "reasoning_output_tokens", "text_output_chars", "first_text_ms", "provider_reported_model")})
    print("  runtime:", call["runtime_diagnostics"])
