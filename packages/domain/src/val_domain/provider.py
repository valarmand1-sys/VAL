"""The provider-neutral boundary — Val Core Phase 1 (ruling, 11 September 2026).

Val Core — identity and persona, memory, projects, permissions and policy,
classification, the strip and blind-position machinery, deliberation records,
durable execution history, cost accounting, routing policy, and final response
governance — speaks to any model provider through exactly the shapes in this
module and nothing else. A provider adapter (`val_providers`) translates these
shapes to and from one SDK's dialect; no SDK concept crosses upward. This
module lives in the domain, not in the providers package, so that the core
depends on the boundary and the providers depend on the core's terms — never
the other way round.

Two calling modes, one result:

- `ProviderAdapter.complete` — one request in, one `ProviderResult` out.
- `StreamingProviderAdapter.stream` — the same request, answered as an ordered
  sequence of `ProviderEvent`s: zero or more `TextDelta`s carrying the model's
  own generated text as it is produced, then exactly one `ProviderResult` as
  the terminal event, identical in meaning to what `complete` would have
  returned. The result is the only thing settlement, persistence, and the
  evidence tables ever see; deltas are presentation, forwarded by the gateway
  through a Val Core-owned `DeltaSink` and never handed to anything outside
  the core directly. Streaming is a per-adapter capability, declared by
  implementing `stream`, never assumed: an adapter that only completes is
  still a full adapter.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from val_domain.gateway import CacheTtl, Message, ModelConfig, TerminalState


@dataclass(frozen=True)
class ProviderResult:
    """What a provider returned, before cost is attributed to it.

    *Current-version closure pass, 18 August 2026.* Two corrections:

    - **`terminal` replaced the `refused` boolean.** A boolean could not say
      "truncated", so an OpenAI `incomplete` was recorded as a refusal and an
      Anthropic `max_tokens` cut-off passed as an ordinary completed answer.
      Each adapter now maps its provider's own documented stop semantics onto
      `TerminalState` explicitly, and anything unrecognised is `UNKNOWN`, which
      the gateway fails closed on.
    - **`tokens_*` are `None` when the provider did not report usage.** The
      previous contract typed them `int`, and the OpenAI adapter filled missing
      usage with `0` — which the gateway then priced and recorded as a *known*
      cost of $0. A zero that is not known to be zero is a fabrication; `None`
      is the honest value, and the gateway records the cost as UNKNOWN.

    Moved from `val_providers.base` to the domain on 11 September 2026 (Val
    Core Phase 1); `val_providers.base` re-exports it unchanged.
    """

    text: str
    terminal: TerminalState
    #: Input tokens billed at the base rate — after any cache breakpoint. When a
    #: provider reports caching figures, this is the **uncached remainder**, and
    #: the total input is the sum of this and the three cache figures below.
    tokens_in: int | None
    tokens_out: int | None
    provider_request_id: str | None
    #: Ruling, 8 September 2026. Prompt-cache usage as the provider reported it:
    #: tokens read from cache, and tokens written at each documented lifetime.
    #: `None` means the provider reported no such figure — which, for a
    #: provider that reported usage at all, is priced as zero cache activity.
    cache_read_tokens: int | None = None
    cache_write_5m_tokens: int | None = None
    cache_write_1h_tokens: int | None = None
    #: Ruling, 8 September 2026: the provider's own terminal fields, verbatim,
    #: so a call that ended with no text can be reported by its observed cause
    #: rather than by a guess. `stop_reason` is the provider's stop reason or
    #: status string; `stop_details` is whatever structured detail rode with it
    #: (a refusal category and explanation, an incomplete reason), rendered as
    #: text. `None` when the provider gave none.
    stop_reason: str | None = None
    stop_details: str | None = None
    #: Ruling, 13 September 2026: measurement the provider comparison needs.
    #: `reasoning_present` — whether the response carried reasoning or thinking
    #: output, where the provider's response exposes that fact; `None` where it
    #: does not. `reasoning_tokens` — reasoning tokens the provider reported
    #: inside `tokens_out`; `None` unless the provider reports the split, never
    #: inferred. `cache_write_auto_tokens` (ruling, 14 September 2026) — the
    #: prompt-cache writes an automatically caching provider reported, priced at
    #: the route's verified automatic write rate; disjoint from `tokens_in` and
    #: from `cache_read_tokens`, so no token is billed twice.
    reasoning_present: bool | None = None
    reasoning_tokens: int | None = None
    cache_write_auto_tokens: int | None = None
    #: Ruling, 15 September 2026: prompt-cache diagnostics, so the next genuine
    #: miss is diagnosable from the record. `prompt_cache_key` — the stable
    #: routing key the adapter sent, where the provider supports one; `None`
    #: otherwise. `cache_diagnostics` — what was requested of the cache and
    #: what the provider reported back about it (its echo of the key and
    #: options, the read/write split, and any miss reason or reusable/missed
    #: counts a provider returns), verbatim, JSON-serialisable; `None` where
    #: the provider exposes nothing of the kind. Never inferred.
    prompt_cache_key: str | None = None
    cache_diagnostics: Mapping[str, object] | None = None
    #: Ruling, 16 September 2026: runtime provenance. `provider_reported_model`
    #: — the model identifier the provider's response itself named; an adapter
    #: that finds it differing from the requested identifier refuses rather
    #: than attributing the answer. `runtime_diagnostics` — what the runtime
    #: reported about itself and the call (a local server's loaded model,
    #: context length, its own timing figures), verbatim and JSON-serialisable;
    #: `None` where nothing of the kind is exposed. Never inferred.
    provider_reported_model: str | None = None
    runtime_diagnostics: Mapping[str, object] | None = None

    @property
    def total_input_tokens(self) -> int | None:
        """Everything the provider processed as input: uncached plus cached."""
        if self.tokens_in is None:
            return None
        return (
            self.tokens_in
            + (self.cache_read_tokens or 0)
            + (self.cache_write_5m_tokens or 0)
            + (self.cache_write_1h_tokens or 0)
            + (self.cache_write_auto_tokens or 0)
        )


@dataclass(frozen=True)
class TextDelta:
    """A piece of the model's own generated text, in generation order.

    Only generated text — never thinking, never tool traffic, never a
    provider's status chatter. An adapter that cannot separate generated text
    from anything else does not implement streaming.
    """

    text: str


#: One event of a streamed call: a text delta, or the terminal result.
ProviderEvent = TextDelta | ProviderResult

#: Where the gateway forwards generated text as it arrives. Owned by Val Core:
#: the loop or the deliberation orchestrator constructs it, decides what may
#: be shown (the reconciliation verdict block, for one, is withheld), and hands
#: it down. A provider adapter never sees a sink; the gateway calls it.
DeltaSink = Callable[[str], None]


class ProviderAdapter(Protocol):
    """One provider, speaking the normalized contract."""

    name: str

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        """Run one completion, or raise `GatewayError`.

        `output_schema`, when given, is a JSON Schema the reply **must** conform
        to, enforced by the provider's schema-constrained output mechanism. An
        adapter for a provider that cannot enforce it raises
        `GatewayErrorKind.INVALID_REQUEST` rather than sending the request
        unconstrained (3 September 2026).

        `cache_ttl`, when given, asks the provider to cache the stable prefix —
        the `system` text, whole — for that lifetime (ruling, 8 September
        2026). An adapter for a provider with no such mechanism ignores it and
        reports no cache figures; it never pretends.
        """
        ...


@runtime_checkable
class StreamingProviderAdapter(Protocol):
    """A provider adapter that can also answer as a stream of events.

    `stream` takes exactly the arguments `complete` takes and yields
    `TextDelta`s as the model produces text, then exactly one `ProviderResult`
    as its final event — carrying the whole text, the terminal state, and the
    usage figures, exactly as `complete` would have reported them. A stream
    that ends without a `ProviderResult` is a failed call, which the gateway
    settles as unknown. Errors are raised as `GatewayError`, normalized.
    """

    name: str

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult: ...

    def stream(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> Iterator[ProviderEvent]: ...


@dataclass(frozen=True)
class ContextFeasibility:
    """An exact, runtime-derived measurement of one request against one loaded window.

    Ruling, 16 September 2026 (the local context preflight). `prompt_tokens` is
    the token count of the request as the runtime itself serialises it — its
    own prompt template applied, its own tokenizer — never an estimate;
    `context_tokens` is the context length of the instance that is actually
    loaded, read from the runtime, never the registry's nominal figure. `source`
    names the mechanism; `details` carries the runtime's provenance (instance
    identity, versions, rendered length) verbatim for the evidence row.
    """

    prompt_tokens: int
    context_tokens: int
    source: str
    details: Mapping[str, object]


class ContextInspectionUnavailableError(Exception):
    """The runtime could not be measured authoritatively — the caller fails closed.

    Raised, never caught into a guess: no matching loaded instance, an ambiguous
    instance, an identity that cannot be proven, a missing context length, a
    runtime that cannot be reached, or a measurement the runtime refused.
    """


@runtime_checkable
class ContextInspectingAdapter(Protocol):
    """An adapter that can measure a request exactly against its runtime's loaded window.

    Declared by implementing `measure_context`; consulted by the gateway only for
    `Metering.LOCAL_NO_METERED_COST` configurations. The measurement never sends
    the request, never generates, never loads a model.
    """

    name: str

    def measure_context(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int | None = None,
    ) -> ContextFeasibility:
        """`max_output_tokens` (owner ruling, 18 September 2026) is the allowance the
        call will carry, so an adapter whose runtime counts a whole request body can
        count exactly the body it will send. Adapters that measure the message
        structure alone ignore it."""
        ...


def supports_context_inspection(adapter: object) -> bool:
    """Whether this adapter declares exact context measurement — by implementing it."""
    return callable(getattr(adapter, "measure_context", None))


class LocalRuntimeUnavailableError(Exception):
    """A local runtime could not be brought up, or the model could not be loaded.

    Raised after the adapter's own bounded recovery attempt has been made and
    failed. It is an honest end to the turn, never a signal to try a different
    provider: what to do when local cognition is unavailable is a decision with
    a cost attached, and it belongs to the owner.
    """


@runtime_checkable
class LocalRuntimeAdapter(Protocol):
    """An adapter that can bring its own runtime up before a call — 21 September 2026.

    Owner ruling: ordinary use must not require opening a terminal, starting a
    server, or loading a model by hand. An adapter declares this the way every
    other capability here is declared, by implementing the method; the core calls
    it through the adapter it already holds and learns nothing about which
    runtime is underneath.

    `ensure_runtime_ready` is expected to be cheap and idempotent when the
    runtime is already serving the configuration, because it runs before calls on
    that route. It raises `LocalRuntimeUnavailableError` when it cannot get
    there, having already made whatever single bounded recovery attempt it
    considers appropriate — the core does not retry it.
    """

    name: str

    def ensure_runtime_ready(self, config: ModelConfig) -> Mapping[str, object]:
        """Make this configuration servable now, and describe what was done.

        The returned mapping is provenance for the evidence record: what state
        the runtime was found in, what was started or loaded, and the context
        length the instance now holds.
        """
        ...


def supports_local_runtime(adapter: object) -> bool:
    """Whether this adapter can bring its own runtime up — by implementing it."""
    return callable(getattr(adapter, "ensure_runtime_ready", None))


@dataclass(frozen=True)
class PrefixPrimePlan:
    """How to leave the computation of a stable prompt prefix in a local runtime.

    Owner order, 25 September 2026 (priming-cache pass). `filler` is the content of
    the one user message the prime sends after the system prompt — chosen, by token
    identity through the runtime's own rendering, so the runtime's checkpoint lands
    exactly on `boundary_tokens`: the system block and the opening of the next user
    message, which every real turn renders identically. `refused` names why no prime
    may be sent, in which case nothing else is set and ordinary cognition proceeds.
    """

    filler: str = ""
    boundary_tokens: int = 0
    prime_tokens: int = 0
    boundary_sha256: str = ""
    engine: str = ""
    refused: str | None = None


@runtime_checkable
class PrefixPrimingAdapter(Protocol):
    """An adapter that can plan a prefix prime for a configuration it serves."""

    def plan_prefix_prime(self, config: ModelConfig, system: str) -> PrefixPrimePlan: ...


def supports_prefix_priming(adapter: object) -> bool:
    """Whether this adapter can plan a prefix prime — by implementing it."""
    return callable(getattr(adapter, "plan_prefix_prime", None))


def supports_streaming(adapter: object) -> bool:
    """Whether this adapter declares the streaming capability.

    Declared by implementing `stream`; nothing is inferred from the provider's
    name or its SDK. An adapter without it is served by `complete`, and a
    caller that asked for deltas simply receives none — the result is the
    same either way.
    """
    return callable(getattr(adapter, "stream", None))
