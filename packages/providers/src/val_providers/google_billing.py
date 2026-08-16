"""Verify that a Gemini key is attached to a paid billing account.

`01-architecture.md` §5.4, amended 15 August 2026: Gemini is Protected-eligible
**only** on paid billing, because Google uses free-tier content to improve its
products and human reviewers may see it. A billed and an unbilled key are
indistinguishable in code, so the distinction is enforced structurally — startup
verifies it and fails if it cannot confirm it. Configuration claiming it is not
acceptance.

**This fails closed, and today it always fails.** Google's Generative Language
API exposes no endpoint that reports the billing status of a key. Absent a
definitive positive signal, `verify_paid_billing` returns False, so a Gemini
configuration cannot start. That is the ruling applied literally: *fail startup
if it cannot confirm it*. It is deliberately not a heuristic — inferring "paid"
from a rate limit that did not fire would be exactly the configuration-claims-it
failure the ruling forbids, and getting it wrong sends Protected creative IP
somewhere human reviewers can read it.

The consequence, stated plainly: **Gemini is unusable until a positive signal
exists.** Restoring it means finding an authoritative check — a Cloud Billing
API call against the project behind the key is the likely candidate — and
implementing it here. No Gemini entry is in the registry, so nothing is blocked
by this today.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BillingVerification:
    """The outcome of a billing check, with the reason it came out that way."""

    confirmed: bool
    detail: str


def verify_paid_billing(api_key: str) -> BillingVerification:
    """Confirm the key is attached to a paid billing account.

    Returns a negative verification rather than raising, so startup can report
    every eligibility problem at once instead of failing on the first.
    """
    if not api_key:
        return BillingVerification(
            confirmed=False,
            detail="no Google API key is configured",
        )
    return BillingVerification(
        confirmed=False,
        detail=(
            "Google exposes no API that reports whether a key is attached to paid "
            "billing, and this check fails closed rather than inferring it. Until an "
            "authoritative check exists here, a Gemini configuration cannot start "
            "(01-architecture.md §5.4, amended 15 August 2026)."
        ),
    )
