"""Bounded GPT-OSS reasoning-effort latency probe — owner execution order, WP2 §2.

Three local calls on the governed ordinary evaluation path, all $0:

    warm-up   MEDIUM   — excluded from the comparison, and recorded as such
    measured  MEDIUM   — the production effort
    measured  LOW      — the evaluation-only twin entry

The path is the Stage A harness's path exactly: `open_turn` / `assemble_turn` /
`CandidateGateway.converse_candidate` / `settle_turn` on the scratch store, with
the active persona whole and the Core envelopes. **No classification call, no
strip call, no blind-position call** — the probe never enters the deliberated
path, which is what keeps it local and $0 and what puts both efforts on one
identical request.

Each call gets its own isolated scratch conversation, so no measured answer
becomes history for another.

The two measured configurations differ in exactly one field: reasoning effort.
Everything else — artifact, quantization, runtime, loaded context, output
ceiling, persona, envelopes, prompt, history shape, sampling — is the same
registry shape and the same code path.

Hidden reasoning is never read, stored or printed. Only that it was generated,
and how many tokens the runtime counted, is recorded.

This measures latency. It decides nothing. Production remains MEDIUM.
"""

import json
import os
import plistlib
import sys
import time
from pathlib import Path

# The local server's own token, read from the installed launch agent and never printed.
with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    _env = plistlib.load(f)["EnvironmentVariables"]
if "VAL_LMSTUDIO_API_TOKEN" in _env:
    os.environ["VAL_LMSTUDIO_API_TOKEN"] = _env["VAL_LMSTUDIO_API_TOKEN"]

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

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
from val_policy.speech_segments import SpeechSegmenter

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg://localhost:5433/val_test"
EXPECTED_CONTEXT = 32_768

MEDIUM_SLUG = "gpt-oss-20b-mxfp4-mlx-lmstudio"
LOW_SLUG = "gpt-oss-20b-mxfp4-mlx-lmstudio-low"

#: The frozen A1 conversational prompt, verbatim from the order.
A1 = (
    "Evening, Val. Rough week. I got the notes back on the pilot draft from the "
    "two readers I trust — one says the second act drags, the other says it's the "
    "best thing I've written. I don't know which to believe, and I'm tempted to "
    "just cut fifteen pages and be done with it. What do you think?"
)

# --- scratch store: reset, migrate, seed -------------------------------------------------
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

# --- the lane ----------------------------------------------------------------------------
adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

medium = by_slug(MEDIUM_SLUG)
low = by_slug(LOW_SLUG)
assert medium is not None and low is not None
# The two configurations differ in exactly one field, and this says so mechanically.
differences = {
    name: (getattr(medium, name), getattr(low, name))
    for name in medium.__class__.model_fields
    if getattr(medium, name) != getattr(low, name)
}
IDENTITY_FIELDS = {"id", "slug", "display_name", "activated_on", "rates_verified_on"}
substantive = {k: v for k, v in differences.items() if k not in IDENTITY_FIELDS}

# --- the runtime, brought up exactly as production brings it up --------------------------
# The production path asks the adapter to make its own runtime ready before any
# call (owner ruling, 21 September 2026), naming the registered 32,768-token
# context rather than inheriting LM Studio's smaller just-in-time default. The
# probe does the same thing, through the same method, so what is measured is the
# ordinary production runtime state and not a hand-arranged one.
readiness = adapter.ensure_runtime_ready(medium)
print("runtime readiness:", json.dumps(dict(readiness), indent=1, default=str))
# The adapter reads the server's model listing once, when it is built — which was
# before the load above. Re-read it so the provenance below describes the runtime
# as it actually is now rather than as it was a moment earlier. Provenance only;
# nothing about the call path changes.
adapter._native_models = adapter._read_native_models()

# --- runtime verification, read-only, before any prompt ----------------------------------
native = adapter.runtime_facts(medium.model_identifier)
instance, handle = adapter._inspector.loaded_instance(medium.model_identifier)
loaded = handle.get_context_length()
app_plist = Path("/Applications/LM Studio.app/Contents/Info.plist")
app_version = None
if app_plist.exists():
    with app_plist.open("rb") as f:
        app_version = plistlib.load(f).get("CFBundleShortVersionString")
provenance = {
    "runtime": native.get("runtime"),
    "runtime_readiness": dict(readiness),
    "lmstudio_app_version": app_version,
    "lmstudio_sdk_version": lmstudio.__version__,
    "model_identifier": instance.identifier,
    "model_key": instance.model_key,
    "quantization": native.get("quantization"),
    "compatibility_type": native.get("compatibility_type"),
    "architecture": instance.architecture,
    "format": instance.format,
    "state": native.get("state"),
    "loaded_context_native": native.get("loaded_context_length"),
    "loaded_context_sdk": loaded,
    "max_context_length": instance.max_context_length,
    "output_reserve_tokens": CONVERSATION_MAX_OUTPUT_TOKENS,
    # The scratch store is seeded fresh from `docs/baselines/03-persona.md`, so it
    # holds revision 1 of the same semantic version production is running. The
    # DIGEST is what makes the claim: identical content to production's active
    # persona, which is what the measurement needs.
    "persona_semantic_version": persona.semantic_version,
    "persona_scratch_revision": persona.version,
    "persona_source_sha256": persona.source_sha256,
    "persona_source_path": persona.source_path,
    "persona_id": str(persona.id),
    "medium_configuration_id": str(medium.id),
    "low_configuration_id": str(low.id),
    "configurations_differ_only_in": sorted(substantive),
    "declared_efforts": {
        MEDIUM_SLUG: medium.reasoning_effort.value,
        LOW_SLUG: low.reasoning_effort.value,
    },
}
print("runtime:", json.dumps(provenance, indent=1))
if native.get("state") != "loaded" or loaded != EXPECTED_CONTEXT:
    print(f"STOP: the resident instance is not loaded at {EXPECTED_CONTEXT}; nothing was sent.")
    sys.exit(3)
if set(substantive) != {"reasoning_effort"}:
    print(f"STOP: the two configurations differ in more than effort: {sorted(substantive)}")
    sys.exit(3)

# --- non-mutating timing observer on the transport ----------------------------------------
timing: dict[str, float] = {}
_real_create = adapter._client.chat.completions.create


def _observed_create(**kwargs):
    timing.clear()
    timing["sent"] = time.monotonic()
    timing["transmitted_reasoning_effort"] = kwargs.get("reasoning_effort")
    timing["transmitted_max_tokens"] = kwargs.get("max_tokens")
    timing["transmitted_messages"] = len(kwargs.get("messages") or [])
    timing["transmitted_stream"] = bool(kwargs.get("stream"))
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
                if delta is None:
                    continue
                if any(getattr(delta, f, None) for f in ("reasoning", "reasoning_content")):
                    # A timestamp only. The hidden reasoning text is never read.
                    timing.setdefault("first_reasoning_chunk", now)
                if getattr(delta, "content", None):
                    timing.setdefault("first_content", now)
            timing["last_chunk"] = now
            yield chunk

    return _iter()


adapter._client.chat.completions.create = _observed_create

seen: set[str] = set()


def new_calls():
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            "select m.id::text as id, m.tokens_in, m.tokens_out, m.cost::text, "
            "m.cost_certainty::text, m.latency_ms, m.terminal_state::text, m.status::text, "
            "m.model_identifier, m.model_config_id::text as config_id, "
            "x.first_text_ms, x.text_output_chars, x.reasoning_present, "
            "x.reasoning_output_tokens, x.provider_reported_model, x.runtime_diagnostics, "
            "x.streamed from model_calls m join model_call_measurements x "
            "on x.model_call_id = m.id order by m.created_at")).mappings()]
    fresh = [r for r in rows if r["id"] not in seen]
    seen.update(r["id"] for r in rows)
    return fresh


catalogue = load_catalogue(engine)


def one_call(label: str, config, *, excluded: bool) -> dict:
    """One isolated conversation, one call, on the ordinary evaluation path."""
    opened = open_turn(
        engine, A1, catalogue=catalogue, signals=ProjectSignals(explicit_no_project=True)
    )
    messages, recalled = assemble_turn(engine, opened)
    turn = TurnReference(
        conversation_id=opened.conversation.id, message_id=opened.user_message.id
    )
    feasibility = lane.measure_candidate_context(
        messages, scope=opened.scope, turn=turn, configuration=config,
        classification=Classification.PROTECTED,
    )
    segmenter = SpeechSegmenter()
    first_segment_at: list[float] = []
    first_delta_at: list[float] = []

    def on_delta(piece: str) -> None:
        now = time.monotonic()
        if not first_delta_at:
            first_delta_at.append(now)
        if segmenter.feed(piece) and not first_segment_at:
            first_segment_at.append(now)

    started = time.monotonic()
    answer, refusal = None, None
    try:
        response = lane.converse_candidate(
            messages, scope=opened.scope, classification=Classification.PROTECTED,
            turn=turn, configuration=config,
            max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS, on_delta=on_delta,
        )
        ended = time.monotonic()
        settle_turn(engine, opened, recalled, response)
        with engine.connect() as c:
            answer = c.execute(text(
                "select content from messages where conversation_id = :cid and role = 'val' "
                "order by sequence desc limit 1"), {"cid": str(opened.conversation.id)}).scalar()
    except GatewayError as failure:
        ended = time.monotonic()
        refusal = f"{failure.kind.value}: {failure.detail}"
    except Exception as error:
        ended = time.monotonic()
        refusal = f"{type(error).__name__}: {str(error)[:400]}"
    if segmenter.source and not segmenter._closed:
        segmenter.flush()

    sent = timing.get("sent", started)
    rows = new_calls()
    calls = []
    for r in rows:
        diag = r["runtime_diagnostics"] or {}
        visible = (
            None if r["tokens_out"] is None or r["reasoning_output_tokens"] is None
            else r["tokens_out"] - r["reasoning_output_tokens"]
        )
        calls.append({
            "config_id": r["config_id"],
            "model_identifier": r["model_identifier"],
            "provider_reported_model": r["provider_reported_model"],
            "prompt_tokens": r["tokens_in"],
            "total_output_tokens": r["tokens_out"],
            "reasoning_tokens": r["reasoning_output_tokens"],
            "reasoning_present": r["reasoning_present"],
            "visible_tokens": visible,
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
    segments = [
        {"index": s.index, "reason": s.reason, "characters": s.characters, "text": s.text}
        for s in segmenter.segments
    ]
    total_s = round(ended - started, 3)
    return {
        "label": label,
        "excluded_from_comparison": excluded,
        "configuration": config.slug,
        "configuration_id": str(config.id),
        "declared_reasoning_effort": config.reasoning_effort.value,
        "transmitted_reasoning_effort": timing.get("transmitted_reasoning_effort"),
        "transmitted_max_tokens": timing.get("transmitted_max_tokens"),
        "transmitted_messages": timing.get("transmitted_messages"),
        "streamed": timing.get("transmitted_stream"),
        "conversation_id": str(opened.conversation.id),
        "exact_preflight": None if feasibility is None else {
            "prompt_tokens": feasibility.prompt_tokens,
            "context_tokens": feasibility.context_tokens,
            "source": feasibility.source,
        },
        "timing_s": {
            "request_start_to_first_provider_chunk": (
                None if "first_chunk" not in timing else round(timing["first_chunk"] - sent, 3)
            ),
            "request_start_to_first_hidden_reasoning_chunk": (
                None if "first_reasoning_chunk" not in timing
                else round(timing["first_reasoning_chunk"] - sent, 3)
            ),
            "request_start_to_first_core_visible_text": (
                None if not first_delta_at else round(first_delta_at[0] - sent, 3)
            ),
            "request_start_to_first_speech_safe_segment": (
                None if not first_segment_at else round(first_segment_at[0] - sent, 3)
            ),
            "request_start_to_generation_complete": (
                None if "last_chunk" not in timing else round(timing["last_chunk"] - sent, 3)
            ),
            "core_call_total": total_s,
            "prompt_processing_prefill": "NOT DIRECTLY OBSERVABLE — "
            "the local server reports no separate prefill figure; "
            "request_start_to_first_provider_chunk is the observable "
            "prefill-to-generation boundary",
        },
        "visible_answer": answer,
        "answer_characters": None if answer is None else len(answer),
        "refusal": refusal,
        "speech_segments": segments,
        "first_speech_safe_segment": segments[0]["text"] if segments else None,
        "calls": calls,
        "throughput_visible_tokens_per_s": (
            None if not calls or calls[0]["visible_tokens"] is None or total_s == 0
            else round(calls[0]["visible_tokens"] / total_s, 2)
        ),
        "throughput_total_output_tokens_per_s": (
            None if not calls or calls[0]["total_output_tokens"] is None or total_s == 0
            else round(calls[0]["total_output_tokens"] / total_s, 2)
        ),
    }


results = {
    "probe": "GPT-OSS reasoning-effort latency, A1",
    "order": "Voice mode work package 2 §2, owner execution order 23 September 2026",
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "prompt": A1,
    "provenance": provenance,
    "runtime_facts_at_start": native,
    "runs": [],
}

print("\n=== warm-up (MEDIUM, excluded from the comparison) ===")
warm = one_call("warm_up", medium, excluded=True)
print(f"  first visible {warm['timing_s']['request_start_to_first_core_visible_text']} s | "
      f"total {warm['timing_s']['core_call_total']} s")
results["runs"].append(warm)

print("\n=== measured MEDIUM ===")
measured_medium = one_call("measured_medium", medium, excluded=False)
print(f"  first visible {measured_medium['timing_s']['request_start_to_first_core_visible_text']} s | "
      f"first speech-safe {measured_medium['timing_s']['request_start_to_first_speech_safe_segment']} s | "
      f"total {measured_medium['timing_s']['core_call_total']} s")
results["runs"].append(measured_medium)

print("\n=== measured LOW ===")
measured_low = one_call("measured_low", low, excluded=False)
print(f"  first visible {measured_low['timing_s']['request_start_to_first_core_visible_text']} s | "
      f"first speech-safe {measured_low['timing_s']['request_start_to_first_speech_safe_segment']} s | "
      f"total {measured_low['timing_s']['core_call_total']} s")
results["runs"].append(measured_low)


def delta(metric: str) -> dict:
    a = measured_medium["timing_s"].get(metric)
    b = measured_low["timing_s"].get(metric)
    if a is None or b is None:
        return {"medium": a, "low": b, "faster_by_s": None, "faster_by_percent": None}
    return {
        "medium": a,
        "low": b,
        "faster_by_s": round(a - b, 3),
        "faster_by_percent": None if a == 0 else round((a - b) / a * 100, 1),
    }


visible = delta("request_start_to_first_core_visible_text")
speech = delta("request_start_to_first_speech_safe_segment")
total = delta("core_call_total")
triggers = []
if visible["faster_by_s"] is not None and visible["faster_by_s"] >= 3.0:
    triggers.append("first Core-visible text at least 3.0 s faster")
if visible["faster_by_percent"] is not None and visible["faster_by_percent"] >= 25.0:
    triggers.append("first Core-visible text at least 25% faster")
if speech["faster_by_s"] is not None and speech["faster_by_s"] >= 3.0:
    triggers.append("first speech-safe boundary at least 3.0 s faster")
if speech["faster_by_percent"] is not None and speech["faster_by_percent"] >= 25.0:
    triggers.append("first speech-safe boundary at least 25% faster")

results["comparison"] = {
    "first_core_visible_text": visible,
    "first_speech_safe_segment": speech,
    "total": total,
    "reasoning_tokens": {
        "medium": measured_medium["calls"][0]["reasoning_tokens"] if measured_medium["calls"] else None,
        "low": measured_low["calls"][0]["reasoning_tokens"] if measured_low["calls"] else None,
    },
    "visible_tokens": {
        "medium": measured_medium["calls"][0]["visible_tokens"] if measured_medium["calls"] else None,
        "low": measured_low["calls"][0]["visible_tokens"] if measured_low["calls"] else None,
    },
    "decision_relevant_conditions_met": triggers,
    "section_2_5_triggered": bool(triggers),
}
results["production_unchanged"] = (
    "Production text cognition remains gpt-oss-20b-mxfp4-mlx-lmstudio-partner at MEDIUM. "
    "This probe measures latency and decides nothing."
)
results["cost_usd"] = float(sum(float(c["cost"] or 0) for r in results["runs"] for c in r["calls"]))

out = HERE / "results-latency.json"
out.write_text(json.dumps(results, indent=1, default=str))
print("\n=== comparison ===")
print(json.dumps(results["comparison"], indent=1))
print("total provider cost:", results["cost_usd"])
print("written:", out)
