"""Assembling what Val is sent: the persona, then the conversation.

`03-persona.md` §10 says the document is injected into every context on every
surface and is **loaded whole, never summarised**. `04-layer-0.md` WP-0.5 says it
loads from the active `personas` row. This module is where those two meet.

**Where the persona sits in the normalized request.** `GatewayRequest.system`,
whole, alone, and exactly once. Not prepended to the first user message, and not
repeated as a trailing reminder. Two reasons:

1. **Every adapter already sends `system` ahead of every message**, by the
   provider contract rather than by our arrangement — Anthropic takes a `system`
   parameter, OpenAI's Responses API takes `instructions`. Stable instruction
   order therefore holds without this module ordering anything, which is a
   guarantee worth having in the shape that cannot be got wrong.
2. **`system` is a single field**, so "exactly once" is structural rather than
   something a test has to keep watching. A persona appended into the message
   list could be duplicated by any later caller that appended again.

**Stable-prefix-first ordering, deliberately, without enabling caching.**
`01-architecture.md` §5.3 wants context assembled stable-prefix-first so cached
segments hit. The persona is the most stable prefix Val has, and putting it in
`system` puts it there. **Nothing here requests caching**, and the executive
decision of 17 August 2026 forbids enabling any billing feature whose cost
semantics are unqualified — a prompt-cache write is billed *above* the base input
rate and would invalidate the `maximum_cost` bound. The ordering is free; the
billing change is not, and is Layer 3's.

**Persona is identity, not project knowledge.** It does not vary by project, and
project content does not enter through it. A conversation in one project and a
conversation in another receive the same Val.
"""

from uuid import UUID

from val_domain.gateway import Classification, GatewayRequest, Message, TaskType
from val_domain.project import ProjectScope, attribution_of, attribution_state_of
from val_gateway.persona import ActivePersona


def assemble(
    persona: ActivePersona,
    messages: tuple[Message, ...],
    *,
    classification: Classification = Classification.PROTECTED,
    task_type: TaskType = TaskType.CONVERSATION,
    scope: ProjectScope,
    conversation_id: UUID | None = None,
    message_id: UUID | None = None,
    max_output_tokens: int = 4096,
) -> GatewayRequest:
    """One normal Val conversational request, with her persona whole in it.

    The persona's content goes into `system` verbatim — the complete active row,
    not an excerpt of it and not a rewrite of it for brevity. `persona_id` rides
    along so the resulting `model_calls` row can name the revision that produced
    it without anyone having to guess from a timestamp.

    Defaults to `PROTECTED` because Layer 0's conversations carry unreleased
    creative IP (`04-layer-0.md` §1.1) and the safe default is the one that would
    be right if the caller forgot to think about it.
    """
    return GatewayRequest(
        task_type=task_type,
        classification=classification,
        messages=messages,
        system=persona.content,
        max_output_tokens=max_output_tokens,
        # One argument, not two that must agree. Corrective round, 18 August
        # 2026: this took `project_id` and `project_attribution` separately, with
        # a default on the second, so a caller could pass a real id alongside
        # `EXPLICIT_NONE` and produce a request that contradicted itself. A
        # `ProjectScope` carries both and cannot disagree with itself.
        project_id=attribution_of(scope),
        project_attribution=attribution_state_of(scope),
        conversation_id=conversation_id,
        message_id=message_id,
        persona_id=persona.id,
    )


def persona_occurrences(request: GatewayRequest, persona: ActivePersona) -> int:
    """How many times this persona's content appears in the assembled request.

    Used by the tests that hold "exactly once". Counts the system prompt and
    every message body, so a persona duplicated into the conversation would be
    caught rather than merely being unlikely.
    """
    found = 1 if request.system == persona.content else 0
    return found + sum(1 for message in request.messages if message.content == persona.content)
