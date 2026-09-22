"""Val's provider-neutral perception boundary.

Owner ruling, 22 September 2026, on Qwen3.5-9B's qualification. Val Core stops
handing raw media to a cognition provider and starts **perceiving** it: the
house's own machine looks at the image, and what the cognition provider receives
is a grounded observation rather than pixels.

The distinction this module exists to keep is between two verbs.

    A provider that *receives* media can be asked anything about it, and its
    answer is cognition — it may reason, advise, and speak as Val.

    A provider that *perceives* media reports what is there. Its product is
    evidence. It does not answer as Val, it does not advise, and nothing it
    returns is Val's response to anybody.

Perception is therefore not a `TaskType` of the model-call machinery, and a
perception run is not a `model_calls` row. It is its own boundary, with its own
record, because it is a different kind of act: the cognition path's accounting
(tokens, reservations, cache splits, metered rates) describes calls that buy
thinking, and this one buys none. What it produces is recorded as evidence
derived from *source media plus the owner's question*, which is what
`perception_runs` says.

Like `val_domain.provider`, nothing here imports a provider package. The core
depends on this boundary; only the composition root knows what implements it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

#: The modalities this boundary carries. `audio` is deliberately absent: it is
#: not qualified, not admitted, and not reachable — a member here would be a
#: capability waiting for someone to use it (owner order §27).
Modality = Literal["image", "video"]


class PerceptionUnavailableError(Exception):
    """Local perception could not be performed, after its one bounded recovery.

    Raised rather than returned, and never swallowed into a partial result. The
    turn that meets this fails closed and says so: the alternative — quietly
    sending the owner's pixels to a paid provider instead — is the thing the
    21 September local-first ruling and §19 of the 22 September order both
    forbid. An honest stop is the cheap outcome; a silent charge is not.
    """


class PerceptionRefusedError(Exception):
    """The request was malformed or outside what this provider is admitted for.

    Separate from unavailability because it is not a runtime condition and a
    retry cannot help it: an unadmitted modality, an empty source set, a source
    whose bytes do not match its digest. Nothing is started.
    """


@dataclass(frozen=True)
class PerceptionSource:
    """One medium to be perceived, named by the record that already holds it.

    `digest` is the authority on identity. The bytes are carried alongside it
    because the perception runtime reads files, not database rows, but the two
    are checked against each other before anything is perceived: a run against
    bytes that are not the recorded attachment would produce evidence about
    something the House never received.
    """

    modality: Modality
    #: The attachment act this medium arrived on. Present for owner media;
    #: `None` only for house-internal qualification fixtures.
    act_id: str | None
    sha256: str
    media_type: str
    byte_size: int
    content: bytes = field(repr=False)


@dataclass(frozen=True)
class PerceptionRequest:
    """What one perception run is asked to do.

    `question` is the owner's actual words, not a paraphrase and not a generic
    caption instruction (§21). Perception that does not know what is being asked
    reports the wrong details thoroughly.
    """

    sources: tuple[PerceptionSource, ...]
    question: str
    #: The full instruction actually transmitted, assembled by Core. Held here so
    #: that the exact prompt reaching the provider is the exact prompt recorded.
    prompt: str
    max_output_tokens: int


@dataclass(frozen=True)
class PerceptionObservation:
    """What the provider reported about one source."""

    source_sha256: str
    modality: Modality
    text: str


@dataclass(frozen=True)
class PerceptionResult:
    """One completed perception run, with everything needed to prove it happened.

    `reasoning_separated` records the observation-discipline finding of §14: the
    usable product is grounded observation, and any reasoning channel the
    runtime produced was separated from it rather than mixed into it.
    """

    observations: tuple[PerceptionObservation, ...]
    #: Provider identity, as the provider itself reports it — never assembled
    #: from what the registry believes.
    provider: str
    model_identifier: str
    model_revision: str
    quantization: str
    runtime: str
    runtime_version: str
    #: The generation settings actually in force, read back from the runtime.
    generation: dict[str, object]
    duration_seconds: float
    #: Always 0.0 on an admitted local route, and recorded rather than assumed.
    cost_usd: float
    local: bool
    reasoning_separated: bool

    def text(self) -> str:
        return "\n\n".join(observation.text for observation in self.observations)


@runtime_checkable
class PerceptionProvider(Protocol):
    """What a perception provider must do, and the little it is allowed to be.

    It owns no identity, no memory, no conversation state, no policy, no
    permission and no durable record. It is handed sources and a question, and
    it reports observations. Replacing it changes nothing above this line.
    """

    def perceive(self, request: PerceptionRequest) -> PerceptionResult:
        """Perceive these sources, or raise.

        One bounded recovery attempt belongs to the implementation; after it,
        `PerceptionUnavailableError`. Never a partial result, and never a
        silently substituted provider.
        """
        ...

    def release(self) -> None:
        """Give the machine its memory back.

        Sequential residency is the architecture (§4): the visual model and the
        cognition model are not required to be resident together, so a provider
        that holds a model open must be able to let it go.
        """
        ...


def supports_perception(candidate: object) -> bool:
    """Whether this object implements the perception boundary."""
    return isinstance(candidate, PerceptionProvider)


def sources_are_coherent(sources: Sequence[PerceptionSource]) -> str | None:
    """Why these sources may not be perceived, or `None`.

    Checked before anything is written to disk or loaded into memory, because a
    perception run recorded against the wrong bytes is worse than no perception
    at all — it is evidence that says it is about something it is not.
    """
    import hashlib

    if not sources:
        return "a perception run needs at least one source"
    for source in sources:
        if source.byte_size != len(source.content):
            return (
                f"{source.sha256[:12]}: the recorded byte size ({source.byte_size:,}) is not "
                f"the size of the bytes supplied ({len(source.content):,})"
            )
        actual = hashlib.sha256(source.content).hexdigest()
        if actual != source.sha256:
            return (
                f"{source.sha256[:12]}: the bytes supplied hash to {actual[:12]}, so they are "
                "not the recorded attachment"
            )
    return None
