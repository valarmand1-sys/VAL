"""Val's provider-neutral speech-output boundary.

Owner execution order, 22 September 2026. Val's words become a voice on the
house's own machine. The boundary is deliberately thin, and the reason is the
thing it protects:

    **Val Core decides what is said. The speech provider decides only how the
    already-final text is spoken.**

So a `SpeechRequest` carries text that is *already Val's answer* — settled,
persisted, final — and the provider's only product is a waveform of exactly
those words. It does not rewrite, summarise, embellish, answer, or alter the
semantic content, and it owns no identity, persona, memory, conversation state,
policy or routing authority. Replacing it changes nothing above this line.

**The voice is a governed object, not a parameter.** `VoiceConditioning` names
the canonical local reference recording and its transcript by digest, together
with the frozen textual description and the VoiceDesign model that produced the
reference. Speech is generated from that anchor every time, so repeated
utterances keep one speaker identity rather than drifting — and so the record
can say, months later, exactly which voice spoke and where it came from.

Like `val_domain.provider` and `val_domain.perception`, nothing here imports a
provider package. The core depends on this boundary; only the composition root
knows what implements it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class SpeechUnavailableError(Exception):
    """Local speech could not be produced, after its one bounded recovery.

    Raised rather than returned. A turn that meets this **fails closed**: no
    cloud text-to-speech is called, and in particular ElevenLabs is never
    invoked automatically. It may later be an explicit, owner-selected external
    voice service; it is not a fallback, and a fallback nobody chose is a
    decision nobody made.
    """


class SpeechRefusedError(Exception):
    """The request was malformed or outside what this provider is admitted for.

    Not a runtime condition, so a retry cannot help it: empty text, a voice
    whose reference bytes do not match their recorded digest. Nothing is
    started.
    """


def digest_of(value: bytes | str) -> str:
    """The one hashing rule, so two callers cannot disagree about identity."""
    return hashlib.sha256(value.encode("utf-8") if isinstance(value, str) else value).hexdigest()


@dataclass(frozen=True)
class VoiceConditioning:
    """The governed identity Val speaks in, and where it came from.

    Every field here is provenance the record must be able to state. The
    reference audio is carried as bytes because the runtime reads files, and it
    is checked against `reference_sha256` before anything is synthesised: speech
    generated from bytes that are not the recorded reference would be a
    different voice wearing this voice's name.
    """

    #: A stable name for this voice in the record.
    name: str
    #: The canonical locally generated reference recording, and its transcript.
    reference_audio: bytes = field(repr=False)
    reference_sha256: str = ""
    reference_text: str = ""
    #: The frozen natural-language description the reference was designed from.
    voice_description: str = ""
    #: The VoiceDesign model that produced the reference — the provenance of the
    #: voice itself, distinct from the Base model that speaks with it.
    designed_by_model: str = ""
    designed_by_revision: str = ""

    @property
    def reference_text_sha256(self) -> str:
        return digest_of(self.reference_text)

    @property
    def voice_description_sha256(self) -> str:
        return digest_of(self.voice_description)

    def incoherent(self) -> str | None:
        """Why this voice may not be used, or `None`.

        Checked before synthesis, because a voice record that cannot vouch for
        its own reference is not provenance — it is a label.
        """
        if not self.reference_audio:
            return f"{self.name}: the canonical reference recording is empty"
        actual = digest_of(self.reference_audio)
        if actual != self.reference_sha256:
            return (
                f"{self.name}: the reference bytes hash to {actual[:12]}, not the recorded "
                f"{self.reference_sha256[:12]}; this is not the governed voice reference"
            )
        if not self.reference_text.strip():
            return f"{self.name}: the reference transcript is empty"
        return None


@dataclass(frozen=True)
class SpeechRequest:
    """What one synthesis is asked to do.

    `text` is Val's finished answer, verbatim. There is no instruction field and
    no style field on purpose: anything that could change *what is said* has no
    business crossing this boundary.
    """

    text: str
    voice: VoiceConditioning


@dataclass(frozen=True)
class SpeechResult:
    """One completed synthesis, with everything needed to prove it happened."""

    #: The waveform itself, as a complete WAV file.
    audio: bytes = field(repr=False)
    sample_rate: int = 0
    duration_seconds: float = 0.0
    #: Provider identity, as the provider itself reports it.
    provider: str = ""
    model_identifier: str = ""
    model_revision: str = ""
    quantization: str = ""
    runtime: str = ""
    runtime_version: str = ""
    #: The generation settings actually in force, read back from the runtime.
    generation: dict[str, object] = field(default_factory=dict)
    #: The serialized reusable voice-clone conditioning this run used, by
    #: digest — the identity anchor, not re-designed per utterance.
    clone_prompt_sha256: str = ""
    elapsed_seconds: float = 0.0
    #: Always 0.0 on an admitted local route, recorded rather than assumed.
    cost_usd: float = 0.0
    local: bool = True

    @property
    def audio_sha256(self) -> str:
        return digest_of(self.audio)


@runtime_checkable
class SpeechProvider(Protocol):
    """What a speech provider must do, and the little it is allowed to be."""

    def synthesize(self, request: SpeechRequest) -> SpeechResult:
        """Speak this exact text in this voice, or raise.

        One bounded recovery attempt belongs to the implementation; after it,
        `SpeechUnavailableError`. Never a partial result, never a silently
        substituted voice, and never a cloud service.
        """
        ...

    def available(self) -> str | None:
        """Why local speech cannot run at all, or `None`."""
        ...
