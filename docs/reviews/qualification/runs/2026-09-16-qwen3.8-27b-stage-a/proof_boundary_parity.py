"""Qwen3.8-27B challenger — hidden-reasoning boundary and exact-preflight parity proof.

Owner ruling, 16 September 2026 (§6–§8). Before the frozen Stage A suite may run
against the challenger, prove through the real candidate path — the active
persona whole, the Core envelopes, retained history, the exact local context
preflight, the OpenAI-compatible HTTP inference path, the scratch store — that:

1. `reasoning_effort=medium` is transmitted (the request the transport sends
   is observed, not assumed) and the runtime honours it (LM Studio's own model
   input log, streamed separately, is checked for the rendered effort marker);
2. visible response content stays distinct from reasoning content — no
   `<think>` text reaches a visible delta or the persisted message, and the
   runtime's reasoning field is present only as a fact;
3. reasoning text is not persisted as visible VAL content;
4. reasoning text is not streamed through `on_delta`;
5. a second turn assembled from VAL persistence carries no hidden reasoning;
6. reasoning token counts/presence remain diagnostic metadata only;
7. the request does not run at the preset's `xhigh` default — the effort the
   house declares is what is sent.

And that exact-preflight parity holds on the first transmitted call: the SDK
inspector's count of the exact serialised prompt equals the server's
`usage.prompt_tokens`. Any difference STOPs (exit 4) before anything else.

The model is verified resident at the expected loaded context first (exit 3
otherwise). Nothing is loaded or unloaded here. Hidden reasoning text is never
read, stored or printed. Cloud spend $0.

Usage: proof_boundary_parity.py OUT.json CANDIDATE_SLUG [EXPECTED_LOADED_CONTEXT [MAX_TURNS]]
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
SLUG = sys.argv[2]
EXPECTED = int(sys.argv[3]) if len(sys.argv) > 3 else 32_768
EXPECTED_CONTEXT_IS_AUTOFIT = EXPECTED != 32_768
MAX_TURNS = int(sys.argv[4]) if len(sys.argv) > 4 else 2

import lmstudio  # version provenance only

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
local = by_slug(SLUG)
assert local is not None, SLUG
lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# --- runtime verification, read-only ---------------------------------------------------------
native = adapter.runtime_facts(local.model_identifier)
inspector = adapter._inspector
instance, handle = inspector.loaded_instance(local.model_identifier)
loaded_by_sdk = handle.get_context_length()
app_plist = Path("/Applications/LM Studio.app/Contents/Info.plist")
app_version = plistlib.load(app_plist.open("rb")).get("CFBundleShortVersionString") if app_plist.exists() else None
provenance = {
    "runtime": native.get("runtime"),
    "lmstudio_app_version": app_version,
    "lmstudio_sdk_version": lmstudio.__version__,
    "canonical_identifier": instance.identifier,
    "model_key": instance.model_key,
    "path": instance.path,
    "quantization": native.get("quantization"),
    "compatibility_type": native.get("compatibility_type"),
    "architecture": instance.architecture,
    "format": instance.format,
    "state": native.get("state"),
    "loaded_context_native": native.get("loaded_context_length"),
    "loaded_context_sdk": loaded_by_sdk,
    "max_context_length": instance.max_context_length,
    "declared_reasoning_effort": local.reasoning_effort.value if local.reasoning_effort else None,
    "declared_temperature": local.temperature,
    "output_reserve_tokens": CONVERSATION_MAX_OUTPUT_TOKENS,
    "registry_context_window_tokens": local.context_window_tokens,
    # Owner amendment, 17 September 2026 (Qwen MLX auto-fit exception): the
    # per-model load configuration requests 32,768; LM Studio's MLX runtime
    # (1.11.0) substitutes its auto-fitted value at load time. Both recorded;
    # the actual loaded context governs the exact preflight.
    "configured_context": 32_768 if EXPECTED_CONTEXT_IS_AUTOFIT else local.context_window_tokens,
    "actual_loaded_context": native.get("loaded_context_length"),
    "context_source": "MLX runtime auto-fit (owner exception, 17 September 2026)" if EXPECTED_CONTEXT_IS_AUTOFIT else "as configured",
    "persona_version": persona.semantic_version,
    "configuration_id": str(local.id),
}
print("runtime:", json.dumps(provenance, indent=1))
if native.get("state") != "loaded" or loaded_by_sdk != EXPECTED or native.get("loaded_context_length") != EXPECTED:
    print(f"STOP: the resident instance is not at the expected loaded context {EXPECTED}; nothing was sent.")
    sys.exit(3)

# --- transport observer: what is SENT, and what kind of deltas come back (no reasoning text read)
sent: list[dict] = []  # type: ignore[type-arg]
observed: dict[str, object] = {}
_real_create = adapter._client.chat.completions.create


def _observed_create(**kwargs):  # type: ignore[no-untyped-def]
    sent.append({k: v for k, v in kwargs.items() if k != "messages"} | {"message_count": len(kwargs.get("messages", []))})
    observed.clear()
    observed.update({"reasoning_field_seen": False, "think_tag_in_content": False, "content_chunks": 0, "sent_at": time.monotonic()})
    result = _real_create(**kwargs)
    if not kwargs.get("stream"):
        return result

    def _iter():  # type: ignore[no-untyped-def]
        for chunk in result:
            now = time.monotonic()
            observed.setdefault("first_chunk", now)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                if getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None):
                    observed["reasoning_field_seen"] = True  # presence only; the text is not read
                content = getattr(delta, "content", None)
                if content:
                    observed["content_chunks"] = observed["content_chunks"] + 1  # type: ignore[operator]
                    observed.setdefault("first_content", now)
                    if "<think>" in content or "</think>" in content:
                        observed["think_tag_in_content"] = True
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
]


def _rows():  # type: ignore[no-untyped-def]
    with engine.connect() as c:
        return [dict(r) for r in c.execute(text(
            "select m.tokens_in, m.tokens_out, m.cost::text, m.cost_certainty::text, m.latency_ms, "
            "m.terminal_state::text, m.status::text, x.reasoning_present, x.reasoning_output_tokens, "
            "x.text_output_chars, x.first_text_ms, x.provider_reported_model, x.runtime_diagnostics "
            "from model_calls m join model_call_measurements x on x.model_call_id = m.id order by m.created_at")).mappings()]


out: dict[str, object] = {"provenance": provenance, "turns": [], "stop": None}
catalogue = load_catalogue(engine)
conversation_id = None
for index, content in enumerate(TURNS[:MAX_TURNS], start=1):
    opened = open_turn(engine, content, catalogue=catalogue,
                       signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
                       conversation_id=conversation_id)
    conversation_id = opened.conversation.id
    messages, recalled = assemble_turn(engine, opened)
    turn = TurnReference(conversation_id=opened.conversation.id, message_id=opened.user_message.id)
    history_has_think = any("<think>" in m.content or "</think>" in m.content for m in messages)
    feasibility = lane.measure_candidate_context(messages, scope=opened.scope, turn=turn, configuration=local,
                                                 classification=Classification.PROTECTED)
    deltas: list[str] = []
    started = time.monotonic()
    rec: dict[str, object] = {"turn": index, "messages_sent": len(messages) + 1,
                              "assembled_history_contains_think_tags": history_has_think,
                              "sdk_preflight_prompt_tokens": feasibility.prompt_tokens if feasibility else None,
                              "sdk_context_tokens": feasibility.context_tokens if feasibility else None}
    try:
        response = lane.converse_candidate(messages, scope=opened.scope, classification=Classification.PROTECTED,
                                           turn=turn, configuration=local,
                                           max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
                                           on_delta=lambda piece: deltas.append(piece))
        ended = time.monotonic()
        settle_turn(engine, opened, recalled, response)
        with engine.connect() as c:
            persisted = c.execute(text("select content from messages where conversation_id = :cid and role = 'val' "
                                       "order by sequence desc limit 1"), {"cid": str(conversation_id)}).scalar()
        visible = "".join(deltas)
        rec.update({
            "outcome": "answered",
            "visible_chars": len(visible),
            "visible_head": visible[:300],
            "on_delta_contains_think_tags": "<think>" in visible or "</think>" in visible,
            "persisted_contains_think_tags": "<think>" in (persisted or "") or "</think>" in (persisted or ""),
            "persisted_equals_streamed": (persisted or "").strip() == visible.strip(),
        })
    except GatewayError as failure:
        ended = time.monotonic()
        rec.update({"outcome": "refused_or_error", "error": f"{failure.kind.value}: {failure.detail[:400]}"})
    rec["request_sent"] = sent[-1] if sent else None
    rec["stream_observed"] = {k: v for k, v in observed.items() if k not in {"sent_at", "first_chunk", "first_content"}}
    rec["timing_s"] = {
        "core_call_total": round(ended - started, 3),
        "prefill_to_first_chunk": None if observed.get("first_chunk") is None else round(observed["first_chunk"] - observed["sent_at"], 3),  # type: ignore[operator]
        "first_visible_content": None if observed.get("first_content") is None else round(observed["first_content"] - observed["sent_at"], 3),  # type: ignore[operator]
    }
    rows = _rows()
    row = rows[-1] if len(rows) == index else None
    if row is not None:
        diag = row["runtime_diagnostics"] or {}
        rec["call"] = {k: row[k] for k in row if k != "runtime_diagnostics"}
        rec["preflight"] = diag.get("preflight")
        rec["parity"] = diag.get("parity")
    out["turns"].append(rec)
    print(json.dumps(rec, indent=1, default=str))
    parity = rec.get("parity") or {}
    if rec.get("outcome") != "answered":
        out["stop"] = f"turn {index} did not answer: {rec.get('error')}"
        break
    if parity.get("exact") is not True:
        out["stop"] = (f"PARITY NOT EXACT on turn {index}: SDK {parity.get('preflight_prompt_tokens')} vs server "
                       f"{parity.get('server_prompt_tokens')} (difference {parity.get('difference')}). STOP.")
        print(out["stop"])
        Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
        sys.exit(4)

out["runtime_facts_at_end"] = adapter.runtime_facts(local.model_identifier)
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str))
print("stop:", out["stop"])
