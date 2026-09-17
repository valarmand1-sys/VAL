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

Usage: harness_stage_a.py OUT.json
"""

import json
import os
import plistlib
import re
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
adapters, problems = build_adapters({"lmstudio"})
assert not problems, problems
adapter = adapters["lmstudio"]
local = by_slug(BENCHMARK["candidate"]["slug"])
assert local is not None and local.model_identifier == BENCHMARK["candidate"]["model"]
assert local.reasoning_effort is not None
assert local.reasoning_effort.value == BENCHMARK["candidate"]["reasoning_effort"], local.reasoning_effort

lane = candidate_gateway_for_scratch_store(
    engine,
    adapters={"lmstudio": adapter},
    recorder=lambda record: record_call(engine, record),
    ledger=DatabaseLedger(engine),
    persona_loader=DatabasePersonaLoader(engine),
    verify_provenance=verifier(engine),
)

# --- runtime verification, read-only, before any prompt ----------------------------------
native = adapter.runtime_facts(local.model_identifier)
inspector = adapter._inspector
instance, handle = inspector.loaded_instance(local.model_identifier)
loaded_by_sdk = handle.get_context_length()
expected = BENCHMARK["candidate"]["expected_loaded_context"]
LMSTUDIO_APP_PLIST = Path("/Applications/LM Studio.app/Contents/Info.plist")
app_version = None
if LMSTUDIO_APP_PLIST.exists():
    with LMSTUDIO_APP_PLIST.open("rb") as f:
        app_version = plistlib.load(f).get("CFBundleShortVersionString")
provenance = {
    "runtime": native.get("runtime"),
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
    "loaded_context_sdk": loaded_by_sdk,
    "max_context_length": instance.max_context_length,
    "reasoning_effort": local.reasoning_effort.value,
    "output_reserve_tokens": CONVERSATION_MAX_OUTPUT_TOKENS,
    "registry_context_window_tokens": local.context_window_tokens,
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

# --- mechanical checks (frozen with the benchmark) ----------------------------------------
NUMBERED = re.compile(r"^\s*\d+[.)]\s+\S", re.M)
BULLET = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)\S", re.M)
STAGE = re.compile(r"\*[^*\n]{2,}\*")
WORD = re.compile(r"\S+")


def check(answer: str, rule: dict) -> tuple[bool, str]:  # type: ignore[type-arg]
    kind = rule["type"]
    low = answer.lower()
    if kind == "max_words":
        n = len(WORD.findall(answer))
        return n <= rule["max"], f"{n} words (max {rule['max']})"
    if kind == "min_words":
        n = len(WORD.findall(answer))
        return n >= rule["min"], f"{n} words (min {rule['min']})"
    if kind == "contains_all":
        missing = [v for v in rule["values"] if v.lower() not in low]
        return not missing, "all present" if not missing else f"missing {missing}"
    if kind == "contains_any":
        return any(v.lower() in low for v in rule["values"]), f"any of {rule['values']}"
    if kind == "excludes_all":
        present = [v for v in rule["values"] if v.lower() in low]
        return not present, "none present" if not present else f"present {present}"
    if kind == "excludes_regex":
        m = re.search(rule["pattern"], answer)
        return m is None, "no match" if m is None else f"matched {m.group(0)!r}"
    if kind == "pattern_count_max":
        n = len(re.findall(rule["pattern"], answer))
        return n <= rule["max"], f"{n} matches (max {rule['max']})"
    if kind == "numbered_items":
        n = len(NUMBERED.findall(answer))
        return n == rule["exactly"], f"{n} numbered items (exactly {rule['exactly']})"
    if kind == "first_numbered_item_contains":
        lines = [ln for ln in answer.splitlines() if NUMBERED.match(ln)]
        first = lines[0].lower() if lines else ""
        return any(v.lower() in first for v in rule["values"]), f"first item: {first[:80]!r}"
    if kind == "text_after_list":
        lines = answer.rstrip().splitlines()
        idx = max((i for i, ln in enumerate(lines) if NUMBERED.match(ln)), default=-1)
        tail = "\n".join(lines[idx + 1 :]).strip()
        return bool(tail), "text follows the list" if tail else "nothing after the list"
    if kind == "no_list":
        n = len(BULLET.findall(answer))
        return n == 0, "no list lines" if n == 0 else f"{n} list lines"
    if kind == "no_heading":
        bad = [ln for ln in answer.splitlines() if ln.startswith("#") or re.match(r"^\*\*[^*]+\*\*\s*$", ln)]
        return not bad, "no heading" if not bad else f"heading-like line {bad[0][:60]!r}"
    if kind == "no_stage_directions":
        m = STAGE.search(answer)
        return m is None, "none" if m is None else f"found {m.group(0)[:60]!r}"
    if kind == "address_count_max":
        n = low.count("my lord")
        return n <= rule["max"], f"'my lord' × {n} (max {rule['max']})"
    if kind == "max_nonempty_lines":
        n = len([ln for ln in answer.splitlines() if ln.strip()])
        return n <= rule["max"], f"{n} non-empty lines (max {rule['max']})"
    if kind == "max_paragraphs":
        n = len([p for p in re.split(r"\n\s*\n", answer.strip()) if p.strip()])
        return n <= rule["max"], f"{n} paragraphs (max {rule['max']})"
    raise ValueError(kind)


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
