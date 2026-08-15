"""The Model Gateway's typed contracts (`01-architecture.md` §5.1).

These are the shapes every component speaks — provider-neutral by construction.
Nothing here knows how any provider spells its request; that knowledge lives in
`val_providers`, and only there.
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class GatewayError(Exception):
    """A failed gateway call, in normalized form."""

    def __init__(self, kind: GatewayErrorKind, detail: str) -> None:
        super().__init__(f"{kind.value}: {detail}")
        self.kind = kind
        self.detail = detail


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
    cost_per_mtok_in_usd: float = Field(gt=0)
    cost_per_mtok_out_usd: float = Field(gt=0)
    eligible_classifications: frozenset[Classification]
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
    project_id: UUID | None = None
    conversation_id: UUID | None = None
    message_id: UUID | None = None


class GatewayResponse(BaseModel):
    """What the gateway returns, with the cost already attributed and recorded."""

    model_config = ConfigDict(frozen=True)

    text: str
    model_config_id: UUID
    slug: str
    provider: str
    model_identifier: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    provider_request_id: str | None
