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

Exact preflight and parity (ruling, later on 16 September 2026): before each
turn the read-only LM Studio SDK inspector's count of the exact serialised
prompt is taken through the lane (`measure_candidate_context`); after each
admitted call the gateway's own `runtime_diagnostics.parity` row — the SDK
count beside the server's `usage.prompt_tokens` — is read back. Any inexact
parity STOPS the run before the next turn. Version provenance (SDK, LM Studio
app, the loaded instance's facts) is recorded on the output.

Usage: harness_loopback.py OUT.json [label]
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
import lmstudio  # version provenance only; the inspector is built by startup

LMSTUDIO_APP_PLIST = Path("/Applications/LM Studio.app/Contents/Info.plist")
app_version = None
if LMSTUDIO_APP_PLIST.exists():
    with LMSTUDIO_APP_PLIST.open("rb") as f:
        app_version = plistlib.load(f).get("CFBundleShortVersionString")

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
    "provenance": {
        "lmstudio_sdk_version": lmstudio.__version__,
        "lmstudio_app_version": app_version,
        "reasoning_effort": local.reasoning_effort.value if local.reasoning_effort else None,
        "registry_context_window_tokens": local.context_window_tokens,
        "output_reserve_tokens": CONVERSATION_MAX_OUTPUT_TOKENS,
    },
    "turns": [],
}
seen_call_ids: set[str] = set()


def _new_call_rows() -> list[dict]:  # type: ignore[type-arg]
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            "select m.id::text as id, m.tokens_in, x.runtime_diagnostics from model_calls m "
            "join model_call_measurements x on x.model_call_id = m.id order by m.created_at")).mappings()]
    fresh = [r for r in rows if r["id"] not in seen_call_ids]
    seen_call_ids.update(r["id"] for r in rows)
    return fresh

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
    # The exact preflight measurement, taken read-only through the lane before the call.
    feasibility = lane.measure_candidate_context(
        messages, scope=opened.scope, turn=turn, configuration=local, classification=Classification.PROTECTED
    )
    record["sdk_preflight"] = None if feasibility is None else {
        "prompt_tokens": feasibility.prompt_tokens,
        "context_tokens": feasibility.context_tokens,
        "source": feasibility.source,
        "fits_with_reserve": feasibility.prompt_tokens + CONVERSATION_MAX_OUTPUT_TOKENS <= feasibility.context_tokens,
        "details": feasibility.details,
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
    fresh = _new_call_rows()
    record["parity"] = [
        {"tokens_in": r["tokens_in"], **{k: (r["runtime_diagnostics"] or {}).get(k) for k in ("preflight", "parity")}}
        for r in fresh
    ]
    out["turns"].append(record)
    if record["outcome"] == "GatewayError":
        break
    inexact = [r for r in record["parity"] if not ((r.get("parity") or {}).get("exact") is True)]
    if inexact:
        record["stop"] = "PARITY NOT EXACT — run stopped for owner review"
        print(record["stop"], json.dumps(inexact, default=str))
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
