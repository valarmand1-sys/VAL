"""Whether this request may leave the machine — owner ruling, 24 September 2026.

Voice work package 3 §1.5. Live microphone transcripts never leave this Mac.
Not by the turn that produced them, not by a later typed turn in the same
conversation, and not by being recalled into another one.

This module holds the fact itself, deliberately small and provider-neutral. It
is **not** a classification. `Classification` answers *how sensitive is this
content*, and it governs eligibility, recall and handling. `Egress` answers a
narrower question — *may this request be transmitted off this machine* — and it
governs nothing else. The two are kept apart on purpose:

- The local cognition configurations were registered as **not** eligible for
  `Classification.RESTRICTED`. Marking voice content Restricted would either
  leave a spoken turn with no eligible route at all, or force local eligibility
  to be widened to Restricted — and whether local inference may carry Restricted
  content is a reserved owner ruling that has not been made. It must not be made
  implicitly, by this module or by a new registry entry (§2.2).
- Restricted also carries recall and handling protections. Applying them to
  voice would change how spoken conversations are remembered, and a spoken turn
  is an ordinary turn (§1.6). Only its egress differs.

So a voice turn keeps its ordinary classification — Protected, as a typed turn
of the same content would be — and carries this separate fact besides.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Egress(StrEnum):
    """Where this request may be transmitted.

    `ORDINARY`: the governed rules decide, exactly as they did before this
    ruling — an eligible cloud provider may carry it.

    `LOCAL_ONLY`: it may be carried only by a configuration whose inference runs
    on this machine. There is no approval prompt, no override and no fallback,
    because the ruling is that the transcript does not leave, not that leaving
    requires a confirmation.
    """

    ORDINARY = "ordinary"
    LOCAL_ONLY = "local_only"


#: Why a request is local-only. Each is a fact about the request, established
#: deterministically before routing and recorded as a positive state — never
#: inferred by a model and never a default.
class LocalOnlyReason(StrEnum):
    """The closed set of reasons the seal applies."""

    #: §2.1's transient layer: the owner has Voice on in this conversation, so
    #: every request it makes is local-only for as long as the session lasts —
    #: typed or spoken, and whether or not anything has been said yet.
    VOICE_SESSION_ACTIVE = "voice_session_active"
    #: §2.1's durable layer: live-microphone-derived text has become a canonical
    #: message in this conversation. The seal outlives the session and is not
    #: lifted by turning Voice off.
    CONVERSATION_SEALED = "conversation_sealed"
    #: §2.6: this request carries content recalled from a sealed conversation,
    #: so the request is local-only wherever it belongs.
    RECALLED_SEALED_CONTENT = "recalled_sealed_content"


class EgressDecision(BaseModel):
    """The answer, and what established it.

    Carried on the turn rather than recomputed per call, so every call one turn
    makes is governed by one decision. `reasons` may hold more than one: a turn
    spoken into an already-sealed conversation is local-only twice over, and
    both facts are true.
    """

    model_config = ConfigDict(frozen=True)

    egress: Egress
    reasons: tuple[LocalOnlyReason, ...] = ()

    @property
    def local_only(self) -> bool:
        return self.egress is Egress.LOCAL_ONLY

    def because(self) -> str:
        """One line naming the seal's grounds, for a refusal or a record."""
        if not self.local_only:
            return "ordinary egress"
        return ", ".join(reason.value for reason in self.reasons) or "local-only"


#: The ordinary answer, and the only default anything is allowed to have.
ORDINARY = EgressDecision(egress=Egress.ORDINARY)


def sealed(*reasons: LocalOnlyReason) -> EgressDecision:
    """A local-only decision on the named grounds. At least one is required."""
    if not reasons:
        raise ValueError("a local-only decision must name why: pass at least one reason")
    ordered = tuple(dict.fromkeys(reasons))
    return EgressDecision(egress=Egress.LOCAL_ONLY, reasons=ordered)
