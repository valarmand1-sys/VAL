"""Rerun ONLY the Stage A calls whose exact parity was nonzero — owner ruling, 18 September 2026 (§10–§11).

Each affected call is rebuilt in its own fresh conversation on the scratch store
from the ORIGINAL captured material of the first run: the preceding user turns
are opened as they were, and the preceding Val answers are persisted exactly as
captured (never regenerated), so the affected turn sees the same retained
history the first run saw. The affected turn is then sent through the real
candidate path — persona v1.8 whole, the Core envelopes, the canonical local
wire form, the exact preflight, the OpenAI-compatible inference path — under
the same configuration (temperature 0.15, NOT_APPLICABLE reasoning, output
reserve 6,144, configured 32,768 / actual runtime context as verified). Any
nonzero parity halts at once (`parity_halt`). The original answers are never
overwritten: this script writes a separate reruns file with the lineage.

Usage: rerun_affected_calls.py ORIGINAL_RESULTS.json OUT.json CANDIDATE_SLUG EXPECTED_LOADED_CONTEXT
"""

import json
import os
import plistlib
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    env = plistlib.load(f)["EnvironmentVariables"]
os.environ["VAL_LMSTUDIO_API_TOKEN"] = env["VAL_LMSTUDIO_API_TOKEN"]

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

ROOT = Path("/Users/josepharmand/Projects/val")
GPT_OSS_RUN = ROOT / "docs/reviews/qualification/runs/2026-09-16-gpt-oss-stage-a"
sys.path.insert(0, str(GPT_OSS_RUN))
from mechanical_checks import check  # noqa: E402
from qualification_gates import parity_halt  # noqa: E402

import lmstudio  # noqa: E402  (version provenance only)

from val_domain.conversation import StoredRole  # noqa: E402
from val_domain.gateway import Classification, GatewayError, TurnReference  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_gateway import conversations  # noqa: E402
from val_gateway.candidate import candidate_gateway_for_scratch_store  # noqa: E402
from val_gateway.ledger import DatabaseLedger  # noqa: E402
from val_gateway.loop import assemble_turn, open_turn, settle_turn  # noqa: E402
from val_gateway.persistence import record_call  # noqa: E402
from val_gateway.persona import DatabasePersonaLoader, seed  # noqa: E402
from val_gateway.projects import load_catalogue  # noqa: E402
from val_gateway.provenance import verifier  # noqa: E402
from val_gateway.startup import build_adapters  # noqa: E402
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS  # noqa: E402
from val_policy.project_resolution import ProjectSignals  # noqa: E402

ORIGINAL = json.loads(Path(sys.argv[1]).read_text())
OUT = Path(sys.argv[2])
SLUG = sys.argv[3]
EXPECTED = int(sys.argv[4])
BENCHMARK = json.loads((GPT_OSS_RUN / "benchmark.json").read_text())
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
seed(engine, ROOT)
persona = DatabasePersonaLoader(engine).active()

adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
local = by_slug(SLUG)
assert local is not None
lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# runtime verification, read-only
native = adapter.runtime_facts(local.model_identifier)
inst, handle = adapter._inspector.loaded_instance(local.model_identifier)
loaded = handle.get_context_length()
if native.get("state") != "loaded" or loaded != EXPECTED or native.get("loaded_context_length") != EXPECTED:
    print(f"STOP: resident instance not at the expected loaded context {EXPECTED} (got {loaded}); nothing sent.")
    sys.exit(3)
provenance = {
    "model_identifier": inst.identifier, "quantization": native.get("quantization"), "architecture": inst.architecture,
    "lmstudio_sdk_version": lmstudio.__version__, "configured_context": local.context_window_tokens,
    "actual_loaded_context": loaded, "context_source": "MLX runtime substitution (owner exception, 17 September 2026)",
    "declared_temperature": local.temperature, "reasoning_effort": local.reasoning_effort.value,
    "output_reserve_tokens": CONVERSATION_MAX_OUTPUT_TOKENS, "persona_version": persona.semantic_version,
    "configuration_id": str(local.id), "original_results": str(sys.argv[1]),
}

# timing observer (non-mutating) and request capture
timing: dict[str, float | None] = {}
sent_last: dict[str, object] = {}
_real_create = adapter._client.chat.completions.create


def _observed_create(**kwargs):  # type: ignore[no-untyped-def]
    timing.clear()
    timing["sent"] = time.monotonic()
    sent_last.clear()
    sent_last.update({k: v for k, v in kwargs.items() if k != "messages"})
    result = _real_create(**kwargs)

    def _iter():  # type: ignore[no-untyped-def]
        for chunk in result:
            now = time.monotonic()
            timing.setdefault("first_chunk", now)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is not None and getattr(delta, "content", None):
                    timing.setdefault("first_content", now)
            yield chunk

    return _iter() if kwargs.get("stream") else result


adapter._client.chat.completions.create = _observed_create  # type: ignore[method-assign]

seen_call_ids: set[str] = set()


def _new_call_rows():  # type: ignore[no-untyped-def]
    with engine.connect() as c:
        rows = [dict(r) for r in c.execute(text(
            "select m.id::text as id, m.tokens_in, m.tokens_out, m.cost::text, m.cost_certainty::text, m.latency_ms, "
            "m.terminal_state::text, m.status::text, x.first_text_ms, x.text_output_chars, x.reasoning_present, "
            "x.reasoning_output_tokens, x.provider_reported_model, x.runtime_diagnostics "
            "from model_calls m join model_call_measurements x on x.model_call_id = m.id order by m.created_at")).mappings()]
    fresh = [r for r in rows if r["id"] not in seen_call_ids]
    seen_call_ids.update(r["id"] for r in rows)
    return fresh


# the affected calls: every turn of the first run whose parity was not exact
affected = []
for task in ORIGINAL["tasks"]:
    for turn in task["turns"]:
        parity = turn["calls"][0]["parity"] if turn["calls"] else None
        if not parity or parity.get("exact") is not True:
            affected.append((task, turn))
print("affected calls:", [(t["id"], turn["turn"]) for t, turn in affected])

catalogue = load_catalogue(engine)
out: dict[str, object] = {"provenance": provenance, "reruns": [], "stopped": None}
for task, turn in affected:
    spec = next(t for t in BENCHMARK["tasks"] if t["id"] == task["id"])
    index = turn["turn"]
    # rebuild the conversation from the ORIGINAL captured preceding turns
    conversation_id = None
    for prior in task["turns"][: index - 1]:
        opened = open_turn(engine, prior["user_prompt"], catalogue=catalogue,
                           signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
                           conversation_id=conversation_id)
        conversation_id = opened.conversation.id
        conversations.append(engine, conversation_id, role=StoredRole.VAL, content=prior["visible_answer"])
    # the affected turn itself, through the real candidate path
    opened = open_turn(engine, turn["user_prompt"], catalogue=catalogue,
                       signals=None if conversation_id else ProjectSignals(explicit_no_project=True),
                       conversation_id=conversation_id)
    conversation_id = opened.conversation.id
    messages, recalled = assemble_turn(engine, opened)
    ref = TurnReference(conversation_id=opened.conversation.id, message_id=opened.user_message.id)
    history_answers = [m.content for m in messages if m.role == "assistant"]
    assert history_answers == [p["visible_answer"] for p in task["turns"][: index - 1]], "history is the original captured material"
    feasibility = lane.measure_candidate_context(messages, scope=opened.scope, turn=ref, configuration=local,
                                                 classification=Classification.PROTECTED)
    deltas: list[str] = []
    started = time.monotonic()
    rec: dict[str, object] = {
        "task": task["id"], "turn": index, "label": f"{task['id']} T{index}",
        "original_parity": turn["calls"][0]["parity"], "original_visible_answer": turn["visible_answer"],
        "history_reconstructed_from_original_answers": len(history_answers),
        "exact_preflight": None if feasibility is None else {"prompt_tokens": feasibility.prompt_tokens, "context_tokens": feasibility.context_tokens, "render_options": feasibility.details.get("render_options")},
    }
    try:
        response = lane.converse_candidate(messages, scope=opened.scope, classification=Classification.PROTECTED, turn=ref,
                                           configuration=local, max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
                                           on_delta=lambda piece: deltas.append(piece))
        ended = time.monotonic()
        settle_turn(engine, opened, recalled, response)
        with engine.connect() as c:
            persisted = c.execute(text("select content from messages where conversation_id = :cid and role = 'val' order by sequence desc limit 1"), {"cid": str(conversation_id)}).scalar()
        rec["outcome"] = "answered"
        rec["visible_answer"] = persisted or "".join(deltas)
    except GatewayError as failure:
        ended = time.monotonic()
        rec["outcome"] = "error"
        rec["visible_answer"] = None
        rec["error"] = f"{failure.kind.value}: {failure.detail[:400]}"
    sent = timing.get("sent", started)
    rec["request_sent"] = dict(sent_last)
    rec["timing_s"] = {"core_call_total": round(ended - started, 3),
                       "prefill_to_first_chunk": None if timing.get("first_chunk") is None else round(timing["first_chunk"] - sent, 3),
                       "first_visible_content": None if timing.get("first_content") is None else round(timing["first_content"] - sent, 3)}
    rows = _new_call_rows()
    rec["calls"] = []
    for r in rows:
        diag = r["runtime_diagnostics"] or {}
        rec["calls"].append({"prompt_tokens": r["tokens_in"], "output_tokens": r["tokens_out"], "reasoning_tokens": r["reasoning_output_tokens"],
                             "reasoning_present": r["reasoning_present"], "visible_chars": r["text_output_chars"], "first_text_ms": r["first_text_ms"],
                             "latency_ms": r["latency_ms"], "terminal_state": r["terminal_state"], "status": r["status"], "cost": r["cost"],
                             "cost_certainty": r["cost_certainty"], "provider_reported_model": r["provider_reported_model"],
                             "preflight": diag.get("preflight"), "parity": diag.get("parity")})
    rules = spec["mechanical_checks"].get(str(index), [])
    answer = rec["visible_answer"] or ""
    rec["mechanical_checks"] = [{"rule": rule, "passed": passed if rec["visible_answer"] is not None else None, "detail": detail}
                                for rule in rules for passed, detail in [check(answer, rule) if rec["visible_answer"] is not None else (False, "no answer")]]
    out["reruns"].append(rec)
    parity = rec["calls"][0]["parity"] if rec["calls"] else None
    print(f"{rec['label']}: {rec['outcome']} | preflight {rec['exact_preflight'] and rec['exact_preflight']['prompt_tokens']} | server {rec['calls'][0]['prompt_tokens'] if rec['calls'] else None} "
          f"| parity {parity} | first visible {rec['timing_s']['first_visible_content']} s | total {rec['timing_s']['core_call_total']} s | checks {[c['passed'] for c in rec['mechanical_checks']]}")
    OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    halt = parity_halt(parity, label=rec["label"]) if rec["outcome"] == "answered" else f"{rec['label']} did not answer: {rec.get('error')}"
    if halt:
        out["stopped"] = halt
        OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
        print(halt)
        sys.exit(4)

out["runtime_facts_at_end"] = adapter.runtime_facts(local.model_identifier)
OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
print("all affected calls rerun with exact parity")
