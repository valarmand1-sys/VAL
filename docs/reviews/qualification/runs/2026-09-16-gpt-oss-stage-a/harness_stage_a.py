"""Stage A of the GPT-OSS Partner-quality qualification — the frozen 12-task local benchmark.

Owner phase ruling, 16 September 2026. Runs every task of `benchmark.json` through
the real candidate conversation path on the scratch store `val_test`:
`open_turn` / `assemble_turn` / `CandidateGateway.converse_candidate` / `settle_turn`
— the active persona whole, the Core record-state and capability-state
envelopes, the retained history, the exact local context preflight, the
OpenAI-compatible HTTP inference path. No classification, strip or blind call;
no cloud provider; cloud/provider API cost $0. Nothing here is a production
utterance, admits anything, or touches production routing.

Before the first prompt the runtime is verified read-only: exactly one resident
`openai/gpt-oss-20b` at the expected loaded context, or the run STOPs.

Per turn the evidence captured is the exact user prompt, the exact visible
answer (as persisted), the runtime identity, reasoning effort, prompt tokens,
output/reasoning/visible tokens, first-visible latency, total latency, the
terminal state, the exact-preflight result and parity, loaded context, cost and
certainty, any refusal, any truncation, any error, and the mechanical checks
frozen with the task. Hidden reasoning is never read, stored or printed.

Usage: harness_stage_a.py OUT.json [CANDIDATE_SLUG [EXPECTED_LOADED_CONTEXT]]

The optional candidate override (added for the Qwen3.8-27B challenger, owner
ruling of 16 September 2026) points the SAME frozen task set at another
NOT_ADMITTED registry entry; the tasks, prompts and mechanical checks in
`benchmark.json` are never modified and the frozen artifact stays the one
both runs are compared against.
"""

import json
import os
import plistlib
import re
import sys
import time
from pathlib import Path

# Credentials, by provider, never printed (owner ruling, 18 September 2026: the llama.cpp
# provider has its own dedicated key in a private file — never the LM Studio token).
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
if "VAL_LMSTUDIO_API_TOKEN" in env:
    os.environ["VAL_LMSTUDIO_API_TOKEN"] = env["VAL_LMSTUDIO_API_TOKEN"]
_LLAMACPP_KEY_FILE = Path.home() / ".config/val/llamacpp.key"
if _LLAMACPP_KEY_FILE.exists():
    os.environ["VAL_LLAMACPP_API_KEY"] = _LLAMACPP_KEY_FILE.read_text().strip()

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg://localhost:5433/val_test"
BENCHMARK = json.loads((HERE / "benchmark.json").read_text())

import lmstudio  # version provenance only; inference never goes through the SDK

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

sys.path.insert(0, str(HERE))
from qualification_gates import parity_halt  # noqa: E402  (owner ruling, 18 September 2026)

# --- scratch store: reset, migrate, seed ------------------------------------------------
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

# --- the candidate and its lane -----------------------------------------------------------
CANDIDATE_SLUG = sys.argv[2] if len(sys.argv) > 2 else BENCHMARK["candidate"]["slug"]
_candidate = by_slug(CANDIDATE_SLUG)
assert _candidate is not None, CANDIDATE_SLUG
PROVIDER = _candidate.provider
adapters, problems = build_adapters({PROVIDER})
assert not problems, problems
adapter = adapters[PROVIDER]
EXPECTED_CONTEXT = int(sys.argv[3]) if len(sys.argv) > 3 else BENCHMARK["candidate"]["expected_loaded_context"]
EXPECTED_CONTEXT_IS_AUTOFIT = EXPECTED_CONTEXT != BENCHMARK["candidate"]["expected_loaded_context"]
local = by_slug(CANDIDATE_SLUG)
assert local is not None, CANDIDATE_SLUG
if CANDIDATE_SLUG == BENCHMARK["candidate"]["slug"]:
    assert local.model_identifier == BENCHMARK["candidate"]["model"]
if CANDIDATE_SLUG == BENCHMARK["candidate"]["slug"]:
    assert local.reasoning_effort.value == BENCHMARK["candidate"]["reasoning_effort"], local.reasoning_effort
# A candidate override carries its own declared reasoning configuration (recorded as
# provenance, never asserted against the frozen GPT-OSS block): NOT_APPLICABLE for a
# Category-A candidate (owner ruling, 17 September 2026) sends no reasoning control.

lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={PROVIDER: adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# --- runtime verification, read-only, before any prompt ----------------------------------
expected = EXPECTED_CONTEXT
inspector = adapter._inspector
if PROVIDER == "llamacpp":
    import hashlib
    from types import SimpleNamespace

    PINNED_TEMPLATE = ROOT / "docs/reviews/qualification/runs/2026-09-18-gemma-4-31b-contract-reassessment/official-chat_template@842da37.jinja"
    pinned_sha = hashlib.sha256(PINNED_TEMPLATE.read_bytes()).hexdigest()
    facts = inspector.runtime_facts()
    served = inspector.model_ids()
    models_payload = inspector._get("/v1/models")
    meta = next((m.get("meta") or {} for m in models_payload.get("data", []) if m.get("id") == local.model_identifier), {})
    if local.model_identifier not in served or facts.get("total_slots") != 1 or facts.get("chat_template_sha256") != pinned_sha:
        print(f"STOP: the server is not the ruled runtime (served {served}, slots {facts.get('total_slots')}, "
              f"template {facts.get('chat_template_sha256')} vs pinned {pinned_sha}); nothing was sent.")
        sys.exit(3)
    native = {"runtime": "llama.cpp server", "state": "loaded", "loaded_context_length": facts.get("n_ctx"),
              "quantization": "Q6_K" if "Q6_K" in str(facts.get("model_path")) else None, "compatibility_type": "gguf"}
    instance = SimpleNamespace(identifier=local.model_identifier, model_key=str(facts.get("model_path")),
                               architecture=meta.get("architecture") or "gemma4", format="gguf",
                               max_context_length=meta.get("n_ctx_train") or 0)
    loaded_by_sdk = facts.get("n_ctx")
    RUNTIME_VERSION, INSPECTOR_VERSION = str(facts.get("build_info")), "HTTP inspector (no SDK)"
    EXTRA_PROVENANCE = {"chat_template_sha256": facts.get("chat_template_sha256"), "pinned_template_sha256": pinned_sha,
                        "model_path": facts.get("model_path"), "total_slots": facts.get("total_slots"), "gguf_meta": meta}
else:
    native = adapter.runtime_facts(local.model_identifier)
    instance, handle = inspector.loaded_instance(local.model_identifier)
    loaded_by_sdk = handle.get_context_length()
    RUNTIME_VERSION, INSPECTOR_VERSION, EXTRA_PROVENANCE = None, lmstudio.__version__, {}
LMSTUDIO_APP_PLIST = Path("/Applications/LM Studio.app/Contents/Info.plist")
app_version = None
if LMSTUDIO_APP_PLIST.exists():
    with LMSTUDIO_APP_PLIST.open("rb") as f:
        app_version = plistlib.load(f).get("CFBundleShortVersionString")
provenance = {
    "runtime": native.get("runtime"),
    "lmstudio_app_version": RUNTIME_VERSION or app_version,
    "lmstudio_sdk_version": INSPECTOR_VERSION,
    "model_identifier": instance.identifier,
    "model_key": instance.model_key,
    "quantization": native.get("quantization"),
    "compatibility_type": native.get("compatibility_type"),
    "architecture": instance.architecture,
    "format": instance.format,
    "state": native.get("state"),
    "loaded_context_native": native.get("loaded_context_length"),
    "loaded_context_sdk": loaded_by_sdk,
    "max_context_length": instance.max_context_length,
    "reasoning_effort": local.reasoning_effort.value,
    # Owner amendment, 17 September 2026: a declared temperature is an upstream
    # configuration pin transmitted on every call; None means no pin (GPT-OSS).
    "declared_temperature": local.temperature,
    # Owner ruling, 18 September 2026: the binary thinking declaration and the
    # verbatim upstream sampling, transmitted on every call where declared.
    "thinking_enabled": local.thinking_enabled,
    "preserve_thinking": local.preserve_thinking,
    "top_p": local.top_p,
    "top_k": local.top_k,
    **EXTRA_PROVENANCE,
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
    "persona_id": str(persona.id),
    "configuration_id": str(local.id),
}
print("runtime:", json.dumps(provenance, indent=1))
if native.get("state") != "loaded" or loaded_by_sdk != expected or native.get("loaded_context_length") != expected:
    print(f"STOP: the resident instance is not at the expected loaded context {expected}; nothing was sent.")
    sys.exit(3)

# --- non-mutating timing observer on the transport ----------------------------------------
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

from mechanical_checks import check  # noqa: E402  (one implementation, shared with the reruns)

# --- the run -----------------------------------------------------------------------------
seen_call_ids: set[str] = set()


def _new_call_rows() -> list[dict]:  # type: ignore[type-arg]
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            "select m.id::text as id, m.tokens_in, m.tokens_out, m.cost::text, m.cost_certainty::text, "
            "m.latency_ms, m.terminal_state::text, m.status::text, m.model_identifier, "
            "x.first_text_ms, x.text_output_chars, x.reasoning_present, x.reasoning_output_tokens, "
            "x.provider_reported_model, x.runtime_diagnostics, x.streamed "
            "from model_calls m join model_call_measurements x on x.model_call_id = m.id "
            "order by m.created_at")).mappings()]
    fresh = [r for r in rows if r["id"] not in seen_call_ids]
    seen_call_ids.update(r["id"] for r in rows)
    return fresh


def _persisted_answer(conversation_id) -> str | None:  # type: ignore[no-untyped-def]
    with engine.connect() as c:
        return c.execute(text(
            "select content from messages where conversation_id = :cid and role = 'val' "
            "order by sequence desc limit 1"), {"cid": str(conversation_id)}).scalar()


out: dict[str, object] = {
    "benchmark": BENCHMARK["name"],
    "benchmark_path": str(HERE / "benchmark.json"),
    "candidate_slug": CANDIDATE_SLUG,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "provenance": provenance,
    "runtime_facts_at_start": native,
    "tasks": [],
}
catalogue = load_catalogue(engine)
for task in BENCHMARK["tasks"]:
    task_record: dict[str, object] = {"id": task["id"], "area": task["area"], "turns": [], "failed": False}
    conversation_id = None
    for index, content in enumerate(task["turns"], start=1):
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
        feasibility = lane.measure_candidate_context(
            messages, scope=opened.scope, turn=turn, configuration=local, classification=Classification.PROTECTED
        )
        rec: dict[str, object] = {
            "turn": index,
            "user_prompt": content,
            "messages_sent": len(messages) + 1,
            "exact_preflight": None if feasibility is None else {
                "prompt_tokens": feasibility.prompt_tokens,
                "context_tokens": feasibility.context_tokens,
                "source": feasibility.source,
                "fits_with_reserve": feasibility.prompt_tokens + CONVERSATION_MAX_OUTPUT_TOKENS <= feasibility.context_tokens,
            },
        }
        deltas: list[str] = []
        started = time.monotonic()
        try:
            response = lane.converse_candidate(
                messages,
                scope=opened.scope,
                classification=Classification.PROTECTED,
                turn=turn,
                configuration=local,
                max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
                on_delta=lambda piece: deltas.append(piece),
            )
            ended = time.monotonic()
            settle_turn(engine, opened, recalled, response)
            rec["outcome"] = "answered"
            rec["visible_answer"] = _persisted_answer(conversation_id) or "".join(deltas)
            rec["refusal"] = None
        except GatewayError as failure:
            ended = time.monotonic()
            rec["outcome"] = "refused" if failure.kind.value in {"budget", "context", "eligibility"} else "error"
            rec["visible_answer"] = None
            rec["refusal"] = f"{failure.kind.value}: {failure.detail}"
            task_record["failed"] = True
        except Exception as error:  # a runtime/provider failure is evidence too
            ended = time.monotonic()
            rec["outcome"] = "error"
            rec["visible_answer"] = None
            rec["refusal"] = f"{type(error).__name__}: {str(error)[:400]}"
            task_record["failed"] = True
        sent = timing.get("sent", started)
        rec["timing_s"] = {
            "core_call_total": round(ended - started, 3),
            "prefill_to_first_chunk": None if timing.get("first_chunk") is None else round(timing["first_chunk"] - sent, 3),
            "first_visible_content": None if timing.get("first_content") is None else round(timing["first_content"] - sent, 3),
        }
        rows = _new_call_rows()
        rec["calls"] = []
        for r in rows:
            diag = r["runtime_diagnostics"] or {}
            rec["calls"].append({
                "model_identifier": r["model_identifier"],
                "provider_reported_model": r["provider_reported_model"],
                "prompt_tokens": r["tokens_in"],
                "output_tokens": r["tokens_out"],
                "reasoning_tokens": r["reasoning_output_tokens"],
                "reasoning_present": r["reasoning_present"],
                "visible_tokens": None if r["tokens_out"] is None or r["reasoning_output_tokens"] is None else r["tokens_out"] - r["reasoning_output_tokens"],
                "visible_chars": r["text_output_chars"],
                "first_text_ms": r["first_text_ms"],
                "latency_ms": r["latency_ms"],
                "terminal_state": r["terminal_state"],
                "status": r["status"],
                "streamed": r["streamed"],
                "cost": r["cost"],
                "cost_certainty": r["cost_certainty"],
                "preflight": diag.get("preflight"),
                "parity": diag.get("parity"),
                "loaded_context": (diag.get("preflight") or {}).get("context_tokens"),
            })
        rec["truncated"] = any(c["terminal_state"] != "complete" for c in rec["calls"]) if rec["calls"] else None
        rules = task["mechanical_checks"].get(str(index), [])
        answer = rec["visible_answer"] or ""
        rec["mechanical_checks"] = [
            {"rule": rule, "passed": passed if rec["visible_answer"] is not None else None, "detail": detail}
            for rule in rules
            for passed, detail in [check(answer, rule) if rec["visible_answer"] is not None else (False, "no answer")]
        ]
        task_record["turns"].append(rec)
        print(f"{task['id']} T{index}: {rec['outcome']} | preflight {rec['exact_preflight'] and rec['exact_preflight']['prompt_tokens']} "
              f"| first visible {rec['timing_s']['first_visible_content']} s | total {rec['timing_s']['core_call_total']} s "
              f"| checks {[c['passed'] for c in rec['mechanical_checks']]}")
        if rec["outcome"] != "answered":
            print("   ", rec["refusal"])
            break
        # A technical contract failure: hidden-thought markers in a visible answer.
        leaked = [m for m in ("<|channel>", "<channel|>", "<|think|>", "<think>") if m in (rec["visible_answer"] or "")]
        if leaked:
            halt = f"HIDDEN-REASONING MARKER IN VISIBLE ANSWER on {task['id']} T{index}: {leaked}. STOP."
            rec["stop"] = halt
            out["tasks"].append(task_record)
            out["stopped"] = halt
            Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
            print(halt)
            sys.exit(5)
        # Owner ruling, 18 September 2026: any nonzero parity halts qualification at once.
        for call in rec["calls"]:
            halt = parity_halt(call.get("parity"), label=f"{task['id']} T{index}")
            if halt:
                rec["stop"] = halt
                out["tasks"].append(task_record)
                out["stopped"] = halt
                Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
                print(halt)
                sys.exit(4)
    out["tasks"].append(task_record)
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))

out["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
out["runtime_facts_at_end"] = adapter.runtime_facts(local.model_identifier)
with engine.connect() as c:
    out["totals"] = {
        "model_calls": c.execute(text("select count(*) from model_calls")).scalar_one(),
        "providers": [r[0] for r in c.execute(text("select distinct provider from model_calls"))],
        "cost_sum": str(c.execute(text("select coalesce(sum(cost), 0) from model_calls")).scalar_one()),
        "val_messages": c.execute(text("select count(*) from messages where role = 'val'")).scalar_one(),
    }
Path(sys.argv[1]).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
print("totals:", out["totals"])
