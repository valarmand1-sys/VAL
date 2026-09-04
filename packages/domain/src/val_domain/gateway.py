"""The Model Gateway's typed contracts (`01-architecture.md` §5.1).

These are the shapes every component speaks — provider-neutral by construction.
Nothing here knows how any provider spells its request; that knowledge lives in
`val_providers`, and only there.
"""

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from val_domain.project import ProjectAttribution


class Classification(StrEnum):
    """Data classification (`01-architecture.md` §5.4). Ambiguity resolves upward."""

    PUBLIC = "public"
    INTERNAL = "internal"
    PROTECTED = "protected"
    RESTRICTED = "restricted"


class TaskType(StrEnum):
    """The Layer 0 task types of `04-layer-0.md` §2.2, exactly."""

    CONVERSATION = "conversation"
    CLASSIFICATION = "classification"
    STRIP = "strip"
    BLIND_POSITION = "blind_position"
    TITLE = "title"


class CallStatus(StrEnum):
    """`model_calls.status`, exactly."""

    OK = "ok"
    ERROR = "error"
    REFUSED = "refused"


class CostCertainty(StrEnum):
    """Whether this row's cost is a fact or an absence (`04-layer-0.md` §2.2).

    A provider attempt has exactly three accounting outcomes, and only two of
    them are rows:

    - **NOT_SENT** — no provider request occurred. Cost is definitively zero and
      this was not a model call, so **no row is written at all**. That is why
      there is no enum member for it: a row asserting a call that never happened
      is the error this distinction exists to prevent.
    - **SENT_COST_KNOWN** — `KNOWN`. The request occurred and the response or
      error carried reliable usage, so `tokens_in`, `tokens_out`, and `cost`
      hold real figures.
    - **SENT_COST_UNKNOWN** — `UNKNOWN`. The request occurred — or may have —
      and usage cannot be established from what came back. `tokens_in`,
      `tokens_out`, and `cost` are **NULL**, never zero. Zero is a claim, and it
      is the wrong one: a call that reached the provider consumed input tokens
      whatever the transport did afterwards.

    A NULL `cost_certainty` on a row means only that the row predates this
    distinction (17 August 2026). It is not a third state.
    """

    KNOWN = "known"
    UNKNOWN = "unknown"


class TerminalState(StrEnum):
    """How a provider call actually ended — the provider-neutral terminal contract.

    Added in the current-version closure pass, 18 August 2026, because the
    previous contract collapsed materially different outcomes into a boolean:
    `ProviderResult.refused`. Under that shape an OpenAI `incomplete` (an output
    that hit its cap) was recorded as a *refusal*, and an Anthropic `max_tokens`
    truncation was recorded as an ordinary completed answer. A truncated reply
    that is persisted as Val's message is a fabrication — she did not finish
    saying it.

    Every adapter maps its provider's own stop semantics onto these four values
    explicitly. **Anything a provider returns that the adapter does not
    recognise maps to `UNKNOWN`, and `UNKNOWN` fails closed**: the gateway
    records the call honestly (it happened, it cost money) and then raises
    rather than handing the text onward as an answer.

    | State | Meaning | Becomes a Val message? |
    |---|---|---|
    | `COMPLETE` | the model finished naturally | yes |
    | `REFUSED` | the model declined; its refusal is deliberate and complete | yes |
    | `TRUNCATED` | the output cap cut it off; the text is a fragment | **no** — evidence only |
    | `FILTERED` | the content filter cut it off; a fragment | **no** — evidence only |
    | `UNKNOWN` | a stop state this adapter does not recognise | **no** — the call fails closed |

    Tool/action handoff states (`tool_use`, `pause_turn`) are not reachable at
    Layer 0 — no tool is ever sent — so an adapter receiving one maps it to
    `UNKNOWN`, which is exactly right: a state that cannot legitimately occur is
    a state we do not understand.
    """

    COMPLETE = "complete"
    REFUSED = "refused"
    TRUNCATED = "truncated"
    #: *Independent-review correction, 18 August 2026.* A content-filter stop is
    #: an INCOMPLETE result, not a refusal: a refusal is the model's deliberate,
    #: complete utterance, while a filter cut generation off mid-stream. The
    #: first closure pass mapped OpenAI's `incomplete`/`content_filter` to
    #: REFUSED, which `loop.send` persists as Val's finished message — partial
    #: filtered text entering history as though she finished speaking, the exact
    #: semantic class the terminal-state repair existed to close.
    FILTERED = "filtered"
    UNKNOWN = "unknown"


class GatewayErrorKind(StrEnum):
    """The one normalized error contract (`01-architecture.md` §5.1).

    Provider timeouts, refusals, rate limits, invalid output, outages, and
    data-policy rejections all arrive as one of these, never as a provider's own
    exception type.
    """

    TIMEOUT = "timeout"
    REFUSAL = "refusal"
    RATE_LIMIT = "rate_limit"
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PROVIDER_ERROR = "provider_error"
    INVALID_OUTPUT = "invalid_output"
    BUDGET_EXCEEDED = "budget_exceeded"
    NOT_ELIGIBLE = "not_eligible"
    RESTRICTED_CONTENT = "restricted_content"
    #: The router found no configuration that is admitted, eligible, ready, and
    #: affordable. Truthful unavailability — never a reason to downgrade the
    #: content's classification or to reach for an unadmitted route.
    NO_ELIGIBLE_ROUTE = "no_eligible_route"


class Admission(StrEnum):
    """How far a configuration has got through `01-architecture.md` §5.2.1.

    The vocabulary exists because the architecture's routing rule said *qualified*
    while §5.2.1 said qualification cannot exist before the Layers 2-3 exam suite.
    Both are now true of different states, and Layer 0 asserts only the weaker one.

    `QUALIFIED` is reserved. Nothing may carry it until an exam record exists,
    and no code path sets it — a configuration is promoted to it by a recorded
    decision, never by an implementation that finds the word convenient.
    """

    #: Present in the registry but not permitted to carry traffic.
    NOT_ADMITTED = "not_admitted"
    #: Admitted for Layer 0 use on the strength of the eligibility ruling and a
    #: working adapter. This is the strongest state any Layer 0 route may hold.
    PROVISIONALLY_ADMITTED = "provisionally_admitted"
    #: Passed the system-specific exam suite. No such record exists yet.
    QUALIFIED = "qualified"


class AdapterStatus(StrEnum):
    """Whether code exists that speaks this provider's dialect (§5.2.1).

    Separate from admission on purpose: an implemented adapter is not a live
    provider, and neither is evidence of eligibility.
    """

    IMPLEMENTED = "implemented"
    NOT_IMPLEMENTED = "not_implemented"


class PricingFeature(StrEnum):
    """Whether caching or batch pricing applies to a configuration (§5.2).

    `NOT_VERIFIED` is the honest default and is not a synonym for absent: it
    records that the provider's own pricing page has not been read for this, in
    the same spirit as `rates_verified_on`. Layer 0 uses neither caching nor
    batch pricing (`01-architecture.md` §5.3 makes them first-class from the
    layer that has repetitive context to cache), so nothing here is load-bearing
    yet — but a guessed value would become load-bearing the moment it is.
    """

    NOT_VERIFIED = "not_verified"
    AVAILABLE = "available"
    NOT_AVAILABLE = "not_available"
    NOT_APPLICABLE = "not_applicable"


class ReasoningEffort(StrEnum):
    """The configuration's reasoning setting, or a typed absence (§5.2).

    `NOT_APPLICABLE` means the provider has no such concept for this model. It
    is a recorded fact, not a missing value, and it is why this is an enum rather
    than an optional string that would leave "unset" and "unsupported"
    indistinguishable.
    """

    NOT_APPLICABLE = "not_applicable"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GatewayError(Exception):
    """A failed gateway call, in normalized form.

    `model_call_ids` names every `model_calls` row the failed call wrote on its
    way to failing — one per route attempted whose provider was contacted
    (3 September 2026). Empty when nothing was transmitted. A caller that
    records evidence about an attempt can then name the calls it paid for,
    without inferring them from timestamps.
    """

    def __init__(
        self, kind: GatewayErrorKind, detail: str, model_call_ids: tuple[UUID, ...] = ()
    ) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail
        self.model_call_ids = model_call_ids


class ModelConfig(BaseModel):
    """One entry of the Model Configuration Registry (`01-architecture.md` §5.2).

    A versioned record, not a model name in a settings file. `id` is the stable
    key `model_calls.model_config_id` refers to; `slug` is the stable
    human-readable name every cost view displays. Costs are per million tokens,
    as published by the provider, and are the rates `model_calls.cost` is
    computed from at call time — never recomputed later.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    slug: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    provider: str
    model_identifier: str
    display_name: str
    context_window_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    #: Reasoning or sampling settings (§5.2). `temperature = None` means the
    #: configuration sets none and the provider's own default stands — recorded
    #: rather than filled in with an invented number.
    reasoning_effort: ReasoningEffort
    temperature: float | None = None
    cost_per_mtok_in_usd: float = Field(gt=0)
    cost_per_mtok_out_usd: float = Field(gt=0)
    #: Closure pass, 18 August 2026. Some providers re-price a call whose input
    #: crosses a threshold — GPT-5.5 bills 2x input and 1.5x output for the full
    #: session above 272K input tokens (developers.openai.com, verified 18
    #: August 2026). The threshold and multipliers live HERE, on the registry
    #: entry, because a pricing fact embedded in code is a pricing fact nobody
    #: re-verifies. `None` means the provider documents no such rule.
    long_context_threshold_tokens: int | None = None
    long_context_in_multiplier: float = Field(default=1.0, ge=1.0)
    long_context_out_multiplier: float = Field(default=1.0, ge=1.0)
    #: Whether caching or batch pricing applies (§5.2). See `PricingFeature`:
    #: `NOT_VERIFIED` records that this has not been read from the provider.
    caching: PricingFeature = PricingFeature.NOT_VERIFIED
    batch_pricing: PricingFeature = PricingFeature.NOT_VERIFIED
    eligible_classifications: frozenset[Classification]
    #: Weaknesses observed in this house's own use (§5.2). Written from
    #: observation, never from a provider's or a benchmark's claims, so an empty
    #: tuple means "none observed here yet" rather than "none exist".
    known_weaknesses: tuple[str, ...] = ()
    #: The preferred successor when this route cannot answer, or None for an
    #: explicit NONE. A fallback is re-checked against every admission and
    #: eligibility rule when it is reached; it never inherits the failed route's
    #: standing (`01-architecture.md` §5.4).
    fallback_slug: str | None
    #: How far this configuration has got through §5.2.1, and whether code exists
    #: that speaks its dialect. Independent: neither implies the other, and
    #: neither implies eligibility.
    admission: Admission
    adapter_status: AdapterStatus
    #: When this configuration became routable, and when it stopped being so.
    activated_on: date
    retired_on: date | None = None
    #: The day the rates above were read from the provider's own documentation.
    #: Rates go stale silently, and a stale rate makes cost attribution quietly
    #: wrong rather than visibly wrong — so the date is carried per entry and
    #: surfaced as a startup warning once it ages (`registry.stale_rates`).
    rates_verified_on: date
    #: The day this exact route last answered a real call successfully, or None
    #: if it never has. An implemented adapter is not a live provider
    #: (`01-architecture.md` §5.2.1): only a real answer proves the route works.
    #: Set from an observed `model_calls` row, never from the fact code exists.
    last_live_call_on: date | None = None
    #: Google-only structural requirement (`01-architecture.md` §5.4 amendment):
    #: True only when startup has verified the key is attached to paid billing.
    #: Configuration cannot claim it; the verifier sets it.
    billing_verified: bool = False
    retired: bool = False


class Message(BaseModel):
    """One conversational turn, provider-neutral."""

    model_config = ConfigDict(frozen=True)

    role: str = Field(pattern=r"^(user|assistant)$")
    content: str


class TurnReference(BaseModel):
    """The turn a conversation call answers: a conversation and its user message.

    What a caller holds *before* the persona is loaded. `converse` takes this;
    context assembly adds the persona revision it just read and produces the
    complete `ConversationProvenance`. Two objects rather than one optional
    field, so no code path can construct provenance with the persona missing and
    no code path has to pass `None` for a value it is about to supply.

    Both ids are required. They are the pair `val_gateway.loop.send` already
    holds by the time it calls the gateway, because it persisted the message.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    message_id: UUID


class PersonaAttribution(BaseModel):
    """Which persona revision is assembled into a `blind_position` call.

    *WP-0.9 ruling, 19 August 2026.* The blind position must be **Val's**
    position, so the blind call carries the active persona whole (`04-layer-0.md`
    WP-0.5, as amended) — and once a persona is assembled, the call must
    attribute it: a NULL `model_calls.persona_id` on a persona-bearing call
    would mean "assembled and failed to attribute," a false record.

    Deliberately **not** `ConversationProvenance`. Conversation provenance is
    conversation-only — a blind call is machinery, not Val answering a turn —
    and reusing the conversation shape here would hand machinery the ids that
    attribute utterances. This is the smallest separate contract that carries
    the one fact the record needs.

    The id must name the **active** persona; the gateway verifies that against
    the WP-0.5 loader before transmission rather than trusting the caller.
    """

    model_config = ConfigDict(frozen=True)

    persona_id: UUID


class ConversationProvenance(BaseModel):
    """What caused a conversation call, as one indivisible fact — WP-0.7 corrective.

    Independent review of `VAL_Source_Snapshot_d137925.zip` found that a
    `TaskType.CONVERSATION` request could still be built with
    `conversation_id`, `message_id` and `persona_id` all `None` — a Val
    utterance with nothing tying it to a conversation, a question, or an
    identity. WP-0.7's persistence guarantee held for `loop.send` and for
    nothing else.

    **Three optional fields were the defect, not three missing checks.** They
    were independently defaultable, so "all three or none" was a convention any
    caller could break one field at a time. Here they are one object with no
    defaults: a caller either has the provenance or cannot construct it, which
    is the same device that kept `AmbiguousProject` out of persistence in
    WP-0.6.

    | Field | Means |
    |---|---|
    | `conversation_id` | the conversation this turn belongs to |
    | `message_id` | the **persisted user message** that caused the call |
    | `persona_id` | the persona revision assembled into it (WP-0.5) |

    `message_id` is the *triggering* turn — the question — not Val's reply,
    which does not exist when the call is made.

    **This object asserts the three ids exist together. It does not assert they
    agree.** Coherence — that the message really belongs to the conversation and
    that the conversation's scope matches the call's — is a fact about the
    database, and is checked in `val_gateway.provenance` before transmission.
    """

    model_config = ConfigDict(frozen=True)

    conversation_id: UUID
    message_id: UUID
    persona_id: UUID


class GatewayRequest(BaseModel):
    """What a caller asks of the gateway.

    The caller states the classification; the gateway never infers it
    (`01-architecture.md` §5.4 — classification is computed before routing,
    never by the model that will receive the content). Attribution fields
    mirror `model_calls` and are recorded on every call.
    """

    model_config = ConfigDict(frozen=True)

    task_type: TaskType
    classification: Classification
    messages: tuple[Message, ...]
    system: str | None = None
    max_output_tokens: int = Field(default=4096, gt=0)
    #: WP-0.6 corrective round, 18 August 2026. **Both are required and neither
    #: has a default.** `project_id` alone cannot say whether a NULL is a
    #: decision, and the default it used to carry let any caller write a
    #: semantically empty NULL without deciding anything — which is precisely how
    #: the claim "NULL means exactly explicit no-project" stopped being true.
    #:
    #: `LEGACY_UNKNOWN` is rejected here (see the validator). It describes rows
    #: written before this distinction existed and is never a way to avoid
    #: deciding now.
    project_id: UUID | None
    project_attribution: ProjectAttribution
    #: WP-0.7 corrective round, 18 August 2026. **One object, not three
    #: independently optional ids.** Required for `TaskType.CONVERSATION` and
    #: absent on the task types that legitimately have no conversation behind
    #: them — classification, strip, blind_position, title. Those are machinery
    #: the house runs on its own behalf; a conversation is Val speaking to Lord
    #: Armand, and it must be possible to say which turn it answered.
    conversation: ConversationProvenance | None = None
    #: WP-0.9 ruling, 19 August 2026. Present iff `task_type` is BLIND_POSITION:
    #: the blind call carries the active persona and must attribute it, and no
    #: other non-conversation task assembles one (WP-0.5's deliberate narrowing —
    #: classification and strip are the house reading content, not Val speaking).
    #: A conversation's persona rides in `ConversationProvenance`, never here.
    persona: PersonaAttribution | None = None
    #: 3 September 2026. A JSON Schema the provider must constrain its reply
    #: to, for callers whose contract is a machine-readable document — the §4.8
    #: classifier first. Added after the classifier's instruction-only JSON
    #: contract was observed failing on real replies (a correct verdict followed
    #: by prose answering the exchange; prose followed by a fenced verdict):
    #: an output contract enforced by instruction alone is asserted, not
    #: structural. An adapter that cannot enforce the schema refuses the call
    #: rather than dropping it — a constraint silently not applied would be the
    #: same defect through a different door.
    output_schema: dict[str, object] | None = None

    @property
    def conversation_id(self) -> UUID | None:
        """The conversation, if this call has one. Read by the recorder."""
        return None if self.conversation is None else self.conversation.conversation_id

    @property
    def message_id(self) -> UUID | None:
        """The persisted user message that caused this call, if there is one."""
        return None if self.conversation is None else self.conversation.message_id

    @property
    def persona_id(self) -> UUID | None:
        """The persona revision assembled into this request, if any.

        From conversation provenance on a conversation call, from the separate
        persona attribution on a blind-position call, and None on the paths
        that legitimately assemble none.
        """
        if self.conversation is not None:
            return self.conversation.persona_id
        if self.persona is not None:
            return self.persona.persona_id
        return None

    @model_validator(mode="after")
    def _provenance_iff_conversation(self) -> GatewayRequest:
        """Conversation provenance is present iff the task is conversation.

        *Independent-review correction, 18 August 2026.* The first closure pass
        enforced only the forward direction — a conversation must carry
        provenance — and left the inverse open: a CLASSIFICATION request could
        carry real conversation, message, and persona ids and, through a
        generic entrance that never runs the conversation verifier, write
        coherent-looking `model_calls` attribution for machinery that was never
        part of any conversation. The contract was always meant as an iff, and
        now it is one.

        Forward: a Val utterance must say which turn it answered
        (`04-layer-0.md` WP-0.7) — use `val_gateway.loop.send`, which persists
        the message first and supplies all three ids.

        Inverse: classification and strip are the house reasoning about content
        before it is routed, `blind_position` is a deliberation step, and
        `title` names something. None of them is Val answering Lord Armand, and
        provenance on one would be attribution to a conversation that did not
        cause it.
        """
        if self.task_type is TaskType.CONVERSATION and self.conversation is None:
            raise ValueError(
                "a conversation call must carry its provenance: the conversation it "
                "belongs to, the persisted user message that caused it, and the "
                "persona revision assembled into it. Without them a Val utterance is "
                "recorded with nothing tying it to what was said or who said it "
                "(04-layer-0.md WP-0.7). Use `val_gateway.loop.send`, which persists "
                "the message first and supplies all three."
            )
        if self.task_type is not TaskType.CONVERSATION and self.conversation is not None:
            raise ValueError(
                f"a {self.task_type.value!r} request may not carry conversation "
                "provenance. Only a conversation is caused by a conversation turn; "
                "attaching real conversation, message, and persona ids to machinery "
                "would record model_calls attribution for a conversation that never "
                "made the call (current-version closure, independent-review "
                "correction, 18 August 2026)."
            )
        return self

    @model_validator(mode="after")
    def _persona_iff_blind_position(self) -> GatewayRequest:
        """Separate persona attribution is present iff the task is blind_position.

        *WP-0.9 ruling, 19 August 2026.* Forward: a blind-position call carries
        the active persona (WP-0.5 as amended), and a persona assembled without
        attribution writes a false NULL. Inverse: classification, strip, and
        title assemble no persona — attributing one would record an identity
        that was never in the call — and a conversation's persona rides in
        `ConversationProvenance`, so a second copy here could only disagree
        with it. Guarded at the entrances too, because `model_copy` skips
        validators.
        """
        if self.task_type is TaskType.BLIND_POSITION and self.persona is None:
            raise ValueError(
                "a blind_position call must carry its persona attribution: the blind "
                "position is Val's position, so the call assembles the active persona "
                "(04-layer-0.md WP-0.5, amended 19 August 2026) and must say which "
                "revision it assembled — a persona-bearing call recording NULL would "
                "be a false record, not a missing feature."
            )
        if self.task_type is not TaskType.BLIND_POSITION and self.persona is not None:
            raise ValueError(
                f"a {self.task_type.value!r} request may not carry persona "
                "attribution. Classification, strip, and title assemble no persona "
                "(WP-0.5's deliberate narrowing), and a conversation's persona rides "
                "in its ConversationProvenance (WP-0.9 ruling, 19 August 2026)."
            )
        return self

    @model_validator(mode="after")
    def _attribution_agrees_with_the_id(self) -> GatewayRequest:
        """The two fields must say the same thing, or the record would lie."""
        if self.project_attribution is ProjectAttribution.LEGACY_UNKNOWN:
            raise ValueError(
                "LEGACY_UNKNOWN describes rows written before project attribution "
                "existed. It is not a way for new code to avoid deciding scope: "
                "resolve the exchange, or state that it is explicitly outside every "
                "project (04-layer-0.md WP-0.6, corrective round)."
            )
        resolved = self.project_attribution is ProjectAttribution.RESOLVED
        if resolved and self.project_id is None:
            raise ValueError("attribution says RESOLVED but carries no project id")
        if not resolved and self.project_id is not None:
            raise ValueError("attribution says EXPLICIT_NONE but carries a project id")
        return self


class GatewayResponse(BaseModel):
    """What the gateway returns, with the cost already attributed and recorded.

    `terminal` says how the call actually ended; callers that persist the text
    as a Val message must branch on it (`val_gateway.loop` does). `tokens_*` and
    `cost_usd` are `None` exactly when the provider did not report usage — the
    closure pass removed the path where missing usage became a fabricated zero.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    terminal: TerminalState
    model_config_id: UUID
    slug: str
    provider: str
    model_identifier: str
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float | None
    latency_ms: int
    provider_request_id: str | None
    #: WP-0.9, 19 August 2026. The `model_calls` row this call wrote, so
    #: evidence that must name its call — a `blind_positions` row — can name
    #: it without a second query that might not find the same row. None only
    #: when the recorder declined to return an id (test fakes).
    model_call_id: UUID | None = None
