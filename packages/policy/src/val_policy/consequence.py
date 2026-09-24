"""Whether a consequential action may execute — owner ruling, 24 September 2026.

Voice work package 3 §2.3.1. The live-voice seal removes a sealed conversation's
access to the cloud consequentiality classifier and, with it, to the blind-position
machinery. **Absence of that machinery is not permission to execute.**

§2.3.1 required the finding to be established from the code before the rule was
written, so here it is, as of this date:

    **The consequentiality classification gates the reasoning path of the
    response, and nothing else. It gates no action with effects outside the
    conversation, because Layer 0 has no such action.**

The evidence for that is narrow and checkable. `TaskType` has exactly five
members — conversation, classification, strip, blind_position, title — and every
one of them is a model call. There is no tool contract, no MCP client, no web
search, no filesystem writer and no external side effect anywhere on the turn
path; MCP stays Layer 2 by the standing sequencing ruling. What the verdict
decides today is whether a blind position is formed before the final answer and
whether a deliberation is recorded — a matter of *how Val reasons*, not of what
she does to the world.

So there is nothing for this module to block today, and saying otherwise would be
theatre. What it does instead is install the guard §2.3.1 asks for, so that the
first executor to arrive fails closed rather than inheriting a default of yes:

- `EXECUTION_GATED_ON_CLASSIFICATION` is the registry of executors whose
  execution depends on the classification. It is empty, and a test asserts it is,
  which is how the finding above stays true rather than becoming stale.
- `execution_refusal` is the gate itself. Any executor added later consults it
  before acting, and a turn whose classification did not run is refused.

Owner confirmation is untouched by all of this. A NOT RUN classification never
waives a confirmation the owner would otherwise have been asked for.
"""

from __future__ import annotations

from val_domain.deliberation import ClassificationRecord

__all__ = [
    "EXECUTION_GATED_ON_CLASSIFICATION",
    "execution_refusal",
]


#: Executors whose execution depends on the consequentiality classification.
#: **Empty, deliberately and truthfully**: as of 24 September 2026 nothing on the
#: turn path has effects outside the conversation. An executor added here must
#: call `execution_refusal` before it acts.
EXECUTION_GATED_ON_CLASSIFICATION: tuple[str, ...] = ()


def execution_refusal(classification: ClassificationRecord | None) -> str | None:
    """Why an action with effects outside the conversation may not execute, or None.

    The three refusing states are deliberately one rule rather than three:

    - **no record at all** — nothing established anything, so nothing is permitted;
    - **the classification did not run** — a sealed conversation, where the owner
      has knowingly traded this machinery for the guarantee that no live-voice
      transcript leaves the Mac (§1.7);
    - **the classification ran and established no verdict** — the 3 September
      ruling's state, where an unknown classification is never treated as ordinary.

    Only an established verdict permits execution, and even then any existing
    owner-confirmation requirement still applies: this function answers whether
    the safety gate is available, never whether the owner has agreed.
    """
    if classification is None:
        return (
            "consequential execution: BLOCKED. reason: no classification record exists for "
            "this turn, so the required safety gate was never established."
        )
    if not classification.ran:
        return (
            "consequential execution: BLOCKED. reason: required safety gate unavailable "
            f"under local-only policy ({classification.not_run_reason}). The consequentiality "
            "classification did not run, and a classification that did not run is not a "
            "finding that the turn is ordinary."
        )
    if not classification.established:
        return (
            "consequential execution: BLOCKED. reason: the consequentiality classification "
            "ran and established no verdict. An unknown classification is never treated as "
            "ordinary (ruling, 3 September 2026)."
        )
    return None
