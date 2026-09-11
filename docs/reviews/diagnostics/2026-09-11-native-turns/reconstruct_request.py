"""Reconstruct the exact provider request the response call sent for one live turn.

Usage: reconstruct_request.py BUILD TURN OUT.json
  BUILD  "current" (the working tree) or "base" (the worktree at
         val-core-refactor-base-2026-09-11; PYTHONPATH must point at it)
  TURN   1 or 2 — the two native turns of 16:59 and 17:00, 11 September 2026

Reads the live store read-only: the active persona, the conversation's
messages as they stood before the turn (later messages excluded by sequence),
and the registry entry. Runs the house's own assembly — `assemble_turn`,
`assemble`, `Gateway._cache_ttl_for` — with the clock pinned to the minute the
API log recorded, then captures the SDK kwargs the Anthropic adapter would
send: on the current build via `AnthropicAdapter._request` (the one builder
both modes share); on the base build by calling `complete` against a fake
client that records `messages.create(**kwargs)` and sends nothing. No
provider is contacted and nothing is written.
"""

import json
import os
import plistlib
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

build, turn_number, out = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
env = plistlib.load(open(Path.home() / "Library/LaunchAgents/house.armand.val.api.plist", "rb"))["EnvironmentVariables"]
for k in ("VAL_ANTHROPIC_API_KEY", "VAL_OPENAI_API_KEY", "VAL_CACHE_TTL"):
    os.environ[k] = env[k]
from sqlalchemy import create_engine

import val_gateway
from val_domain.gateway import Classification, TaskType, TurnReference
from val_domain.project import ExplicitNoProject
from val_domain.registry import by_slug
from val_gateway import conversations, loop
from val_gateway.context import assemble
from val_gateway.loop import OpenedTurn, assemble_turn
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.startup import start
from val_providers.anthropic_adapter import AnthropicAdapter

print("build:", build, "val_gateway from:", val_gateway.__file__)
engine = create_engine(env["VAL_DATABASE_URL"])
CONVERSATION = "01a0927b-5ccd-71bc-81eb-0670283dc98a"
user_sequence = 1 if turn_number == 1 else 3
clock = datetime(2026, 9, 11, 16, 59, 14, tzinfo=ZoneInfo("America/Chicago")) if turn_number == 1 else datetime(2026, 9, 11, 17, 0, 51, tzinfo=ZoneInfo("America/Chicago"))

from uuid import UUID
conversation = conversations.load(engine, UUID(CONVERSATION))
full_history = conversations.history(engine, UUID(CONVERSATION))
as_of = tuple(m for m in full_history if m.sequence <= user_sequence)
user_message = as_of[-1]
assert user_message.role.value == "user", user_message
# History as it stood: everything later is excluded; the clock as logged.
conversations.history = lambda engine_, conversation_id: as_of  # type: ignore[assignment]
loop.conversations.history = conversations.history  # type: ignore[attr-defined]
loop.local_now = lambda: clock  # type: ignore[assignment]

gateway = start(engine).gateway
persona = DatabasePersonaLoader(engine).active()
opened = OpenedTurn(conversation=conversation, scope=ExplicitNoProject(), user_message=user_message)
messages, recalled = assemble_turn(engine, opened, recall_limit=loop.DEFAULT_LIMIT if hasattr(loop, "DEFAULT_LIMIT") else 8)
request = assemble(
    persona,
    messages,
    classification=Classification.PROTECTED,
    task_type=TaskType.CONVERSATION,
    scope=opened.scope,
    turn=TurnReference(conversation_id=conversation.id, message_id=user_message.id),
    max_output_tokens=4096,
)
config = by_slug("opus-5-medium")
assert config is not None
cache_ttl = gateway._cache_ttl_for(config, request)

adapter = AnthropicAdapter.__new__(AnthropicAdapter)
captured: dict = {}
if hasattr(adapter, "_request"):
    kwargs = adapter._request(config, request.messages, request.system, request.max_output_tokens, request.output_schema, cache_ttl)
    mode = "current: AnthropicAdapter._request (shared by complete and stream)"
else:
    class _Fake:
        def __init__(self): self.messages = self
        def create(self, **kw):
            captured.update(kw)
            raise RuntimeError("captured")
    adapter._client = _Fake()  # type: ignore[attr-defined]
    try:
        adapter.complete(config, request.messages, request.system, request.max_output_tokens, output_schema=request.output_schema, cache_ttl=cache_ttl)
    except Exception:
        pass
    kwargs = captured
    mode = "base: kwargs captured from messages.create in AnthropicAdapter.complete"

def plain(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    return f"<{type(value).__name__}: {value!r}>"

record = {
    "build": build,
    "capture_mode": mode,
    "turn": turn_number,
    "clock_pinned": clock.isoformat(),
    "persona_id": str(persona.id),
    "persona_chars": len(persona.content),
    "config": {"slug": config.slug, "model": config.model_identifier, "effort": config.reasoning_effort.value},
    "cache_ttl": None if cache_ttl is None else cache_ttl.value,
    "gateway_request": {
        "task_type": request.task_type.value,
        "max_output_tokens": request.max_output_tokens,
        "output_schema": request.output_schema,
        "system_is_persona_verbatim": request.system == persona.content,
        "messages": [
            {"role": m.role, "cache_breakpoint": getattr(m, "cache_breakpoint", None), "content": m.content}
            for m in request.messages
        ],
    },
    "sdk_kwargs": plain(kwargs),
}
out.write_text(json.dumps(record, indent=2, ensure_ascii=False))
print("wrote", out, "| messages:", len(request.messages), "| cache_ttl:", cache_ttl, "| system==persona:", request.system == persona.content)
