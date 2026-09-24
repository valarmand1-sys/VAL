"""Read-only exact request differential — latency pass §5. No provider call.

What differs between two otherwise-identical A1 turns, and where. The comparison
uses the **existing** exact-preflight machinery: the loaded runtime's own chat
template and tokenizer through the read-only LM Studio SDK inspector. No new
approximate prompt renderer was built, and **no inference request is sent by this
script**.

The historical WP2 requests were not retained byte for byte, so what is compared
here is a **CURRENT RECONSTRUCTION** through the same governed path: the same
persona, Core envelopes, history shape, user prompt, sampling state, output
ceiling and 32,768 loaded context. It is labelled as such and is not claimed to be
the historical bytes.

Owner content is not dumped: divergences are reported as offsets, lengths, digests
and short excerpts.
"""

import hashlib
import json
import os
import plistlib
import sys
import time
from pathlib import Path

with open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb") as f:
    _env = plistlib.load(f)["EnvironmentVariables"]
if "VAL_LMSTUDIO_API_TOKEN" in _env:
    os.environ["VAL_LMSTUDIO_API_TOKEN"] = _env["VAL_LMSTUDIO_API_TOKEN"]

ROOT = Path("/Users/josepharmand/Projects/val")
HERE = Path(__file__).resolve().parent
URL = "postgresql+psycopg://localhost:5433/val_test"
os.environ["VAL_DATABASE_URL"] = URL

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

import lmstudio

from val_domain.gateway import Classification, TaskType, TurnReference
from val_domain.registry import by_slug
from val_gateway.context import assemble, record_state_block
from val_gateway.loop import assemble_turn, open_turn
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.startup import build_adapters
from val_policy.budget import CONVERSATION_MAX_OUTPUT_TOKENS
from val_policy.project_resolution import ProjectSignals
from val_providers.lmstudio_adapter import _chat_turns

A1 = (
    "Evening, Val. Rough week. I got the notes back on the pilot draft from the "
    "two readers I trust — one says the second act drags, the other says it's the "
    "best thing I've written. I don't know which to believe, and I'm tempted to "
    "just cut fifteen pages and be done with it. What do you think?"
)
SLUG = "gpt-oss-20b-mxfp4-mlx-lmstudio-partner"

# --- scratch store ------------------------------------------------------------------------
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
inspector = adapter._inspector
config = by_slug(SLUG)
assert config is not None
# The production supervisor, doing exactly what it does before every ordinary turn:
# serve if not serving, load at the registered 32,768 window if not loaded. The
# inspector itself never loads, and LM Studio is not restarted.
readiness = dict(adapter.ensure_runtime_ready(config))
instance, handle = inspector.loaded_instance(config.model_identifier)


def rendered(turns: list[dict[str, str]]) -> str:
    """The exact serialised prompt the runtime's own template produces."""
    chat = lmstudio.Chat()
    for turn in turns:
        if turn["role"] == "system":
            chat.add_system_prompt(turn["content"])
        elif turn["role"] == "user":
            chat.add_user_message(turn["content"])
        else:
            chat.add_assistant_response(turn["content"])
    from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS

    return handle.apply_prompt_template(chat, dict(INGRESS_RENDER_OPTIONS))


def tokens_of(body: str) -> list[int]:
    ids = handle.tokenize(body)
    return list(ids)


def a_turn() -> tuple[list[dict[str, str]], object]:
    """One production-shaped A1 turn, through the governed path. No provider call."""
    opened = open_turn(
        engine,
        A1,
        catalogue=load_catalogue(engine),
        signals=ProjectSignals(explicit_no_project=True),
    )
    messages, _ = assemble_turn(engine, opened)
    request = assemble(
        persona,
        messages,
        classification=Classification.PROTECTED,
        task_type=TaskType.CONVERSATION,
        scope=opened.scope,
        # The provenance a conversation call must carry. Supplied because this is
        # the real assembly path, not a stand-in for it.
        turn=TurnReference(
            conversation_id=opened.conversation.id, message_id=opened.user_message.id
        ),
        max_output_tokens=CONVERSATION_MAX_OUTPUT_TOKENS,
    )
    return _chat_turns(request.messages, request.system), request


def first_divergence(a, b):  # noqa: ANN001, ANN201
    for index, (left, right) in enumerate(zip(a, b, strict=False)):
        if left != right:
            return index
    return None if len(a) == len(b) else min(len(a), len(b))


report: dict[str, object] = {
    "investigation": "exact request differential, two successive A1 turns",
    "order": "pre-WP3 latency pass §5, owner execution order 24 September 2026",
    "label": "CURRENT RECONSTRUCTION — the historical WP2 request bytes were not retained",
    "provider_calls_made_by_this_script": 0,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    "runtime": {
        "supervisor_readiness": readiness,
        "model_identifier": instance.identifier,
        "loaded_context": instance.context_length,
        "architecture": instance.architecture,
        "format": instance.format,
        "lmstudio_sdk_version": lmstudio.__version__,
    },
    "persona": {
        "semantic_version": persona.semantic_version,
        "source_sha256": persona.source_sha256,
        "characters": len(persona.content),
    },
}

# Two turns, each in its own fresh conversation, exactly as the WP2 probe made them.
first_turns, first_request = a_turn()
time.sleep(1.1)  # so the record-state clock differs, as it does between real turns
second_turns, second_request = a_turn()

first_text, second_text = rendered(first_turns), rendered(second_turns)
first_ids, second_ids = tokens_of(first_text), tokens_of(second_text)

byte_index = first_divergence(first_text.encode(), second_text.encode())
char_index = first_divergence(first_text, second_text)
token_index = first_divergence(first_ids, second_ids)

# Which component contains the divergence? Locate the envelope and the user words.
envelope = next(t["content"] for t in first_turns if "VAL-STATE-V1" in t["content"])
component = "NOT LOCATED"
if char_index is not None:
    marker_at = first_text.find("VAL-STATE-V1")
    a1_at = first_text.find(A1[:40])
    if marker_at != -1 and char_index >= marker_at and (a1_at == -1 or char_index < a1_at):
        component = "record-state envelope"
    elif a1_at != -1 and char_index >= a1_at:
        component = "the owner's own words"
    elif char_index < len(persona.content):
        component = "persona / system prompt"
    else:
        component = "before the record-state envelope"

excerpt_window = 90
report["diff"] = {
    "identical": byte_index is None,
    "first_differing_byte_offset": byte_index,
    "first_differing_character": char_index,
    "first_differing_token_index": token_index,
    "component_containing_the_divergence": component,
    "excerpt_around_the_divergence": (
        None
        if char_index is None
        else {
            "first": first_text[max(0, char_index - 20) : char_index + excerpt_window],
            "second": second_text[max(0, char_index - 20) : char_index + excerpt_window],
        }
    ),
    "serialized": {
        "first_bytes": len(first_text.encode()),
        "second_bytes": len(second_text.encode()),
        "first_characters": len(first_text),
        "first_sha256": hashlib.sha256(first_text.encode()).hexdigest(),
        "second_sha256": hashlib.sha256(second_text.encode()).hexdigest(),
    },
    "tokens": {
        "first_total": len(first_ids),
        "second_total": len(second_ids),
        "stable_prefix_tokens": token_index,
        "stable_prefix_percent": (
            None if token_index is None else round(token_index / len(first_ids) * 100, 2)
        ),
        "tokens_after_the_divergence": (
            None if token_index is None else len(first_ids) - token_index
        ),
    },
    "stable_prefix_bytes": byte_index,
    "stable_prefix_characters": char_index,
    "stable_prefix_percent_of_characters": (
        None if char_index is None else round(char_index / len(first_text) * 100, 2)
    ),
}

# --- §5.3 component composition, by cumulative exact render -------------------------------
#
# Each figure is the difference between two REAL template renders, so every count
# includes that component's own template wrapper. That is stated rather than
# silently folded away: there is no way to price a message without its wrapper
# while still using the runtime's own template.
system_only = [t for t in first_turns if t["role"] == "system"]
without_last_user = first_turns[:-1] if len(first_turns) > 1 else first_turns
empty_ids = tokens_of(rendered([{"role": "system", "content": ""}]))
system_ids = tokens_of(rendered(system_only))
all_ids = first_ids

last_user = first_turns[-1]["content"]
envelope_marker = "VAL-STATE-V1"
if envelope_marker in last_user:
    # canonicalize joined the envelope and the owner's words into one user message.
    split_at = last_user.find(A1[:40])
    envelope_part = last_user[:split_at].rstrip()
    words_part = last_user[split_at:]
else:
    envelope_part, words_part = "", last_user
envelope_only_ids = tokens_of(rendered([*system_only, {"role": "user", "content": envelope_part}]))
words_only_ids = tokens_of(rendered([*system_only, {"role": "user", "content": words_part}]))

report["composition"] = {
    "method": (
        "differences between real template renders through the runtime's own "
        "tokenizer; each component's figure therefore includes its template wrapper"
    ),
    "total_prompt_tokens": len(all_ids),
    "template_scaffolding_with_empty_system": len(empty_ids),
    "system_prompt_render_total": len(system_ids),
    "persona_tokens_net_of_scaffolding": len(system_ids) - len(empty_ids),
    "final_user_message_render_total": len(all_ids) - len(system_ids),
    "record_state_envelope_alone_net": len(envelope_only_ids) - len(system_ids),
    "owner_words_alone_net": len(words_only_ids) - len(system_ids),
    "history_messages_in_this_turn": len(first_turns) - 2,
    "turn_roles": [t["role"] for t in first_turns],
    "turn_characters": [len(t["content"]) for t in first_turns],
    "note_history": (
        "This A1 turn is the first message of a fresh conversation, so there is no "
        "history to price. History is NOT SEPARATELY OBSERVABLE here because there "
        "is none."
    ),
}

# The persona's share of the stable prefix, which is what a prefix cache would reuse.
report["composition"]["persona_percent_of_prompt"] = round(
    (len(system_ids) - len(empty_ids)) / len(all_ids) * 100, 2
)
report["composition"]["stable_prefix_is_persona_and_scaffolding"] = (
    token_index is not None and token_index >= len(system_ids) - 2
)

# --- the same pair one minute apart, so the clock actually moves -------------------------
#
# The record-state clock is minute-granular (`%H:%M`), which is why the pair above
# is byte-identical: two turns inside one minute render the same prompt. This
# second pair forces the clock forward so the divergence can be located, using the
# `local_now` seam the gateway documents as replaceable.
import val_gateway.loop as loop_module
from datetime import timedelta

real_now = loop_module.local_now
fixed = real_now()
try:
    loop_module.local_now = lambda: fixed
    early_turns, _ = a_turn()
    loop_module.local_now = lambda: fixed + timedelta(minutes=1)
    later_turns, _ = a_turn()
finally:
    loop_module.local_now = real_now

early_text, later_text = rendered(early_turns), rendered(later_turns)
early_ids, later_ids = tokens_of(early_text), tokens_of(later_text)
byte_at = first_divergence(early_text.encode(), later_text.encode())
char_at = first_divergence(early_text, later_text)
token_at = first_divergence(early_ids, later_ids)

where = "NOT LOCATED"
if char_at is not None:
    marker_at = early_text.find("VAL-STATE-V1")
    words_at = early_text.find(A1[:40])
    if marker_at != -1 and char_at >= marker_at and (words_at == -1 or char_at < words_at):
        where = "record-state envelope (the clock)"
    elif words_at != -1 and char_at >= words_at:
        where = "the owner's own words"
    elif char_at < len(persona.content):
        where = "persona / system prompt"
    else:
        where = "before the record-state envelope"

report["diff_across_a_minute_boundary"] = {
    "why": (
        "the record-state clock is minute-granular, so this is the smallest real "
        "change two successive turns can produce"
    ),
    "identical": byte_at is None,
    "first_differing_byte_offset": byte_at,
    "first_differing_character": char_at,
    "first_differing_token_index": token_at,
    "component_containing_the_divergence": where,
    "excerpt_around_the_divergence": (
        None
        if char_at is None
        else {
            "earlier": early_text[max(0, char_at - 30) : char_at + 50],
            "later": later_text[max(0, char_at - 30) : char_at + 50],
        }
    ),
    "stable_prefix_bytes": byte_at,
    "stable_prefix_characters": char_at,
    "stable_prefix_tokens": token_at,
    "total_tokens": len(early_ids),
    "stable_prefix_percent_of_tokens": (
        None if token_at is None else round(token_at / len(early_ids) * 100, 2)
    ),
    "tokens_after_the_divergence": (
        None if token_at is None else len(early_ids) - token_at
    ),
    "the_divergence_is_after_the_persona": (
        char_at is not None and char_at > len(persona.content)
    ),
}

out = HERE / "request-diff.json"
out.write_text(json.dumps(report, indent=1, default=str))
print(json.dumps({k: report[k] for k in ("label", "diff", "diff_across_a_minute_boundary", "composition")}, indent=1, default=str))
print("written:", out)
