"""Gemma 4 31B on the llama.cpp provider — the two pre-suite proofs (owner ruling, 18 September 2026).

    proof_llamacpp.py off OUT.json CANDIDATE_SLUG   — Proof A: Core can switch thinking OFF
    proof_llamacpp.py on  OUT.json CANDIDATE_SLUG   — Proof B: thinking ON, two turns, visible-history only

Serving-contract proofs only: not Stage A, not qualification or quality evidence.
Every gate is checked and the script STOPs (non-zero exit) on the first failure:

- the server is the ruled runtime: loopback, keyed, one slot, actual context exactly
  32,768, the active chat template byte-equal (SHA-256) to the pinned official
  template (google/gemma-4-31B-it @ 842da3794eaa), the served identifier the entry's;
- the request ON THE WIRE carries the declared thinking state, `preserve_thinking`
  false and the declared sampling, and no reasoning-effort field;
- the server's own rendering of that identical body shows the declared mode
  (`<|think|>` present for ON, absent for OFF);
- the server's own input-token count of that body equals `usage.prompt_tokens`;
- reasoning is separated: present for ON / absent for OFF, never in a visible delta,
  never in the persisted reply, never in the next turn's history;
- the visible answer is non-empty.

Proof A sends one synthetic request through the adapter with a thinking-OFF copy of
the entry (the registered entry itself declares ON). Proof B runs two Val-shaped
turns through the real candidate lane on the scratch store. Hidden reasoning text is
never read, stored or printed. The key is read from its private file and never shown.
Provider/API spend $0.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

MODE, OUT, SLUG = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
assert MODE in ("off", "on")
KEY_FILE = Path.home() / ".config/val/llamacpp.key"
os.environ["VAL_LLAMACPP_API_KEY"] = KEY_FILE.read_text().strip()

ROOT = Path("/Users/josepharmand/Projects/val")
PINNED_TEMPLATE = ROOT / "docs/reviews/qualification/runs/2026-09-18-gemma-4-31b-contract-reassessment/official-chat_template@842da37.jinja"
EXPECTED_CONTEXT = 32_768
THOUGHT_MARKERS = ("<|channel>", "<channel|>", "<|think|>")

sys.path.insert(0, str(ROOT / "docs/reviews/qualification/runs/2026-09-16-gpt-oss-stage-a"))
from qualification_gates import parity_halt  # noqa: E402

from val_domain.gateway import Classification, GatewayError, Message, ModelConfig, TurnReference  # noqa: E402
from val_domain.provider import TextDelta  # noqa: E402
from val_domain.registry import by_slug  # noqa: E402
from val_gateway.startup import build_adapters  # noqa: E402
from val_providers.llamacpp_inspector import compare_with_pinned_template  # noqa: E402
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS  # noqa: E402

out: dict[str, object] = {"mode": MODE, "gates": [], "stop": None}


def stop(reason: str) -> None:
    out["stop"] = reason
    OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
    print("STOP:", reason)
    sys.exit(4)


def gate(name: str, ok: bool, detail: object) -> None:
    out["gates"].append({"gate": name, "ok": bool(ok), "detail": detail})  # type: ignore[union-attr]
    print(("ok   " if ok else "FAIL ") + name, "|", detail)
    if not ok:
        stop(f"{name}: {detail}")


entry = by_slug(SLUG)
assert entry is not None, SLUG
adapters, problems = build_adapters({"llamacpp"})
assert not problems, problems
adapter = adapters["llamacpp"]
inspector = adapter._inspector

# --- the runtime is the ruled runtime ------------------------------------------------------
facts = inspector.runtime_facts()
out["runtime"] = facts
# The narrow rule (owner ruling, 18 September 2026): raw byte identity, or the pinned
# file minus its ONE terminal LF. All three hashes are kept; anything else stops.
identity = compare_with_pinned_template(PINNED_TEMPLATE.read_bytes(), str(inspector.props().get("chat_template") or ""))
out["template_identity"] = {
    "raw_official_sha256": identity.raw_official_sha256,
    "canonical_official_sha256": identity.canonical_official_sha256,
    "active_sha256": identity.active_sha256,
    "RAW OFFICIAL == ACTIVE": identity.raw_equal,
    "CANONICAL OFFICIAL == ACTIVE": identity.canonical_equal,
}
gate("actual server context is exactly 32,768", facts.get("n_ctx") == EXPECTED_CONTEXT, facts.get("n_ctx"))
gate("one slot", facts.get("total_slots") == 1, facts.get("total_slots"))
gate("active template is the pinned official template (raw, or minus exactly one terminal LF)", identity.accepted, out["template_identity"])
gate("the server answers to the entry's identifier", entry.model_identifier in inspector.model_ids(), inspector.model_ids())

# --- wire capture (what is actually sent; reasoning text never read) ---------------------------
wire: list[dict] = []  # type: ignore[type-arg]
seen: dict[str, object] = {}
_real = adapter._client.chat.completions.create


def _observed(**kwargs):  # type: ignore[no-untyped-def]
    extra = dict(kwargs.get("extra_body") or {})
    body = {k: v for k, v in kwargs.items() if k not in ("extra_body", "stream", "stream_options")} | extra
    wire.append(body)
    seen.clear()
    seen.update({"reasoning_field_seen": False, "marker_in_visible_delta": False, "sent_at": time.monotonic()})
    result = _real(**kwargs)
    if not kwargs.get("stream"):
        return result

    def _iter():  # type: ignore[no-untyped-def]
        for chunk in result:
            now = time.monotonic()
            seen.setdefault("first_chunk", now)
            for choice in getattr(chunk, "choices", None) or []:
                delta = getattr(choice, "delta", None)
                if delta is None:
                    continue
                extra_fields = getattr(delta, "model_extra", None) or {}
                if getattr(delta, "reasoning_content", None) or extra_fields.get("reasoning_content") or extra_fields.get("reasoning"):
                    seen["reasoning_field_seen"] = True  # presence only
                content = getattr(delta, "content", None)
                if content:
                    seen.setdefault("first_content", now)
                    if any(m in content for m in THOUGHT_MARKERS):
                        seen["marker_in_visible_delta"] = True
            yield chunk

    return _iter()


adapter._client.chat.completions.create = _observed  # type: ignore[method-assign]


def check_wire(body: dict, config: ModelConfig, label: str) -> None:  # type: ignore[type-arg]
    kwargs = body.get("chat_template_kwargs") or {}
    gate(f"{label}: thinking declared on the wire", kwargs.get("enable_thinking") is config.thinking_enabled, kwargs)
    gate(f"{label}: preserve_thinking false on the wire", kwargs.get("preserve_thinking") is False, kwargs)
    gate(f"{label}: sampling transmitted verbatim",
         (body.get("temperature"), body.get("top_p"), body.get("top_k")) == (config.temperature, config.top_p, config.top_k),
         {k: body.get(k) for k in ("temperature", "top_p", "top_k")})
    gate(f"{label}: no reasoning-effort or other thinking field sent",
         not any(k in body for k in ("reasoning_effort", "reasoning", "enable_thinking", "thinking")), sorted(body))


def check_rendering(body: dict, config: ModelConfig, label: str, *, prior_answers: list[str]) -> dict:  # type: ignore[type-arg]
    rendered = inspector.render(body)
    counted = inspector.count(body)
    think = "<|think|>" in rendered
    gate(f"{label}: rendering shows the declared mode", think is bool(config.thinking_enabled), {"think_token_present": think})
    history_part = rendered[: rendered.rfind("<|turn>model")] if "<|turn>model" in rendered else rendered
    gate(f"{label}: no prior thought text in the rendered history", "<|channel>thought" not in history_part, "checked the text before the final model turn")
    for answer in prior_answers:
        gate(f"{label}: the prior visible answer is in the rendered history", answer.strip()[:60] in rendered, answer.strip()[:60])
    return {"rendered_chars": len(rendered), "rendered_tail": rendered[-80:], "input_tokens": counted}


if MODE == "off":
    config = ModelConfig(**{**entry.model_dump(), "thinking_enabled": False, "preserve_thinking": False})
    system = "You are a careful assistant. Answer in one short sentence."
    messages = (Message(role="user", content="Name one colour of the rainbow."),)
    # Output reserve 6,144, as ruled: the body counted is the body sent.
    feasibility = adapter.measure_context(config, messages, system, CONVERSATION_MAX_OUTPUT_TOKENS)
    result = adapter.complete(config, messages, system, CONVERSATION_MAX_OUTPUT_TOKENS)
    body = wire[-1]
    out["wire_body"] = {k: v for k, v in body.items() if k != "messages"} | {"message_count": len(body["messages"])}
    check_wire(body, config, "OFF")
    rendering = check_rendering(body, config, "OFF", prior_answers=[])
    out["rendering"] = rendering
    gate("OFF: output reserve 6,144 on the wire", body.get("max_tokens") == 6_144 == CONVERSATION_MAX_OUTPUT_TOKENS, body.get("max_tokens"))
    gate("OFF: the rendering ends in the template's pre-closed empty thought channel",
         rendering["rendered_tail"].endswith("<|turn>model\n<|channel>thought\n<channel|>"), rendering["rendered_tail"])
    gate("OFF: preflight equals server usage exactly",
         feasibility.prompt_tokens == result.tokens_in == rendering["input_tokens"],
         {"preflight": feasibility.prompt_tokens, "server": result.tokens_in, "recount": rendering["input_tokens"]})
    gate("OFF: no reasoning returned", result.reasoning_present is False and not result.reasoning_tokens, {"present": result.reasoning_present, "tokens": result.reasoning_tokens})
    gate("OFF: no thought marker in the visible answer", not any(m in result.text for m in THOUGHT_MARKERS), None)
    gate("OFF: visible answer is non-empty", bool(result.text.strip()), {"chars": len(result.text), "terminal": result.terminal.value})
    gate("OFF: context still exactly 32,768", inspector.runtime_facts().get("n_ctx") == EXPECTED_CONTEXT, None)
    # Nothing is persisted by this proof (an adapter-direct call writes no row), and the
    # normalized result has no field that could carry reasoning text: only its presence
    # and a token count travel past the adapter boundary.
    import dataclasses  # noqa: E402

    carried = {f.name: getattr(result, f.name) for f in dataclasses.fields(result)}
    strings = {k: v for k, v in carried.items() if isinstance(v, str) and k != "text"}
    out["result_fields"] = sorted(carried)
    gate("OFF: no reasoning text is carried past the adapter, so none can be persisted",
         not any(any(m in v for m in THOUGHT_MARKERS) for v in strings.values())
         and not any("reasoning" in k and isinstance(v, str) for k, v in carried.items()), sorted(strings))
    out["answer"] = result.text
    out["usage"] = {"prompt_tokens": result.tokens_in, "completion_tokens": result.tokens_out}
    out["timings"] = (result.runtime_diagnostics or {}).get("timings")
else:
    from alembic import command  # noqa: E402
    from alembic.config import Config  # noqa: E402
    from sqlalchemy import create_engine, text  # noqa: E402

    from val_gateway.candidate import candidate_gateway_for_scratch_store  # noqa: E402
    from val_gateway.ledger import DatabaseLedger  # noqa: E402
    from val_gateway.loop import assemble_turn, open_turn, settle_turn  # noqa: E402
    from val_gateway.persistence import record_call  # noqa: E402
    from val_gateway.persona import DatabasePersonaLoader, seed  # noqa: E402
    from val_gateway.projects import load_catalogue  # noqa: E402
    from val_gateway.provenance import verifier  # noqa: E402
    from val_policy.project_resolution import ProjectSignals  # noqa: E402

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
    lane = candidate_gateway_for_scratch_store(
        engine, adapters={"llamacpp": adapter}, recorder=lambda record: record_call(engine, record),
        ledger=DatabaseLedger(engine), persona_loader=DatabasePersonaLoader(engine), verify_provenance=verifier(engine),
    )
    gate("the registered entry declares thinking ON and preserve false",
         entry.thinking_enabled is True and entry.preserve_thinking is False, {"thinking": entry.thinking_enabled, "preserve": entry.preserve_thinking})
    TURNS = [
        "Good evening, Val. I want your own view, in about three paragraphs, on how a house should keep a written "
        "record of the decisions it makes — what belongs in such a record, what does not, and what goes wrong when a "
        "house relies on memory instead.",
        "Take your second point further. Give me two concrete failure cases, each in its own short paragraph, and say "
        "which of the two you think is the more dangerous for a small house and why.",
    ]
    catalogue = load_catalogue(engine)
    conversation_id = None
    prior_answers: list[str] = []
    out["turns"] = []
    for index, content in enumerate(TURNS, start=1):
        label = f"ON T{index}"
        opened = open_turn(engine, content, catalogue=catalogue,
                           signals=None if conversation_id else ProjectSignals(explicit_no_project=True), conversation_id=conversation_id)
        conversation_id = opened.conversation.id
        messages, recalled = assemble_turn(engine, opened)
        gate(f"{label}: assembled history carries no thought text", not any(any(m in x.content for m in THOUGHT_MARKERS) for x in messages), None)
        assistant_history = [x.content for x in messages if x.role == "assistant"]
        gate(f"{label}: the assistant history is exactly the persisted visible answers, nothing more",
             [a.strip() for a in assistant_history] == [a.strip() for a in prior_answers], {"assistant_turns": len(assistant_history), "prior_answers": len(prior_answers)})
        ref = TurnReference(conversation_id=opened.conversation.id, message_id=opened.user_message.id)
        deltas: list[str] = []
        started = time.monotonic()
        try:
            response = lane.converse_candidate(messages, scope=opened.scope, classification=Classification.PROTECTED, turn=ref,
                                               configuration=entry, max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
                                               on_delta=lambda piece: deltas.append(piece))
        except GatewayError as failure:
            stop(f"{label}: {failure.kind.value}: {failure.detail[:300]}")
        ended = time.monotonic()
        settle_turn(engine, opened, recalled, response)
        with engine.connect() as c:
            persisted = c.execute(text("select content from messages where conversation_id = :cid and role = 'val' order by sequence desc limit 1"), {"cid": str(conversation_id)}).scalar()
            row = dict(c.execute(text(
                "select m.tokens_in, m.tokens_out, m.cost::text, m.cost_certainty::text, m.terminal_state::text, x.reasoning_present, "
                "x.reasoning_output_tokens, x.text_output_chars, x.runtime_diagnostics from model_calls m join model_call_measurements x "
                "on x.model_call_id = m.id order by m.created_at desc limit 1")).mappings().one())
        diag = row.pop("runtime_diagnostics") or {}
        parity = diag.get("parity")
        body = wire[-1]
        check_wire(body, entry, label)
        rendering = check_rendering(body, entry, label, prior_answers=prior_answers)
        halt = parity_halt(parity, label=label)
        gate(f"{label}: exact input-token parity", halt is None and rendering["input_tokens"] == row["tokens_in"], {"parity": parity, "recount": rendering["input_tokens"]})
        gate(f"{label}: preflight context is the server's actual 32,768", (diag.get("preflight") or {}).get("context_tokens") == EXPECTED_CONTEXT, (diag.get("preflight") or {}).get("context_tokens"))
        gate(f"{label}: reasoning separated from visible content", row["reasoning_present"] is True and bool(seen.get("reasoning_field_seen")), {"present": row["reasoning_present"], "field_seen": seen.get("reasoning_field_seen")})
        visible = "".join(deltas)
        gate(f"{label}: no thought text leaked through streaming", not seen.get("marker_in_visible_delta") and not any(m in visible for m in THOUGHT_MARKERS), None)
        gate(f"{label}: hidden reasoning absent from the persisted message", not any(m in (persisted or "") for m in THOUGHT_MARKERS), None)
        gate(f"{label}: the persisted message is exactly the visible content stream (the reasoning field contributes nothing)",
             (persisted or "").strip() == visible.strip(), {"persisted_chars": len(persisted or ""), "visible_chars": len(visible)})
        gate(f"{label}: output reserve 6,144 on the wire", body.get("max_tokens") == 6_144, body.get("max_tokens"))
        gate(f"{label}: visible content non-empty and complete", bool(visible.strip()) and row["terminal_state"] == "complete", {"chars": len(visible), "terminal": row["terminal_state"]})
        gate(f"{label}: settled at a known $0", row["cost"] == "0.000000" and row["cost_certainty"] == "known", {"cost": row["cost"], "certainty": row["cost_certainty"]})
        prior_answers.append(persisted or visible)
        out["turns"].append({  # type: ignore[union-attr]
            "turn": index, "wire_body": {k: v for k, v in body.items() if k != "messages"} | {"message_count": len(body["messages"])},
            "rendering": rendering, "parity": parity, "call": row, "timings": diag.get("timings"),
            "timing_s": {"total": round(ended - started, 3),
                         "first_visible": None if seen.get("first_content") is None else round(seen["first_content"] - seen["sent_at"], 3)},  # type: ignore[operator]
            "visible_answer": persisted,
        })
    gate("ON: context still exactly 32,768", inspector.runtime_facts().get("n_ctx") == EXPECTED_CONTEXT, None)

OUT.write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False))
print("all gates passed:", MODE)
