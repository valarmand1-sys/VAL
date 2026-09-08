"""The local token estimate — one documented, deterministic, conservative estimator.

Rulings of 7 September 2026. The soft recall and history budgets are ruled in
**provider-context-token scale**: 16,000 and 64,000 tokens as the provider
would count them, not bytes and not characters. No provider is asked to count,
because counting would be a network call per turn, and the byte-level upper
bound that protects the context preflight and the budget reservation is the
wrong instrument for a target — it is about four times the provider's count
for English, so a budget expressed in it admits a quarter of what was ruled.

The estimate is characters divided by a ratio calibrated on a measured live
call: 34,365 provider-reported tokens for 123,676 characters of persona,
envelope, and message on 7 September 2026 — 3.6 characters per token. English
prose commonly runs nearer four characters per token, so dividing by 3.6
counts slightly high and the estimate errs toward admitting less. It is the
same estimator for every provider: the tokenizers in use differ by a few
percent on prose, well inside that margin.

This estimator is for the soft budgets only. The context-window preflight and
the reservation keep the byte upper bound, because a ceiling needs a bound and
a target needs an estimate.
"""

from __future__ import annotations

import math

#: Characters per token for the local estimate. See the module docstring.
CHARS_PER_TOKEN_ESTIMATE = 3.6


def estimate_tokens(content: str) -> int:
    """A local, deterministic token estimate in provider-context scale — never a provider call."""
    return math.ceil(len(content) / CHARS_PER_TOKEN_ESTIMATE)
