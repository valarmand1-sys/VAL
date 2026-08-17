"""The pre-call budget rule as arithmetic (`01-architecture.md` §5.7).

Pure functions, no database. The concurrency half is proved in
`packages/gateway/tests/test_budget_ledger.py` against a real PostgreSQL,
because it cannot be proved anywhere else.
"""

import pytest

from val_domain.registry import by_slug
from val_policy.budget import (
    CLOUD_CEILING_USD,
    admits,
    ceiling_message,
    maximum_cost,
    remaining_usd,
    upper_bound_input_tokens,
)


def config(slug: str = "opus-5") -> object:
    found = by_slug(slug)
    assert found is not None
    return found


# --- the ceiling is the architecture's figure --------------------------------


def test_the_ceiling_is_the_two_hundred_dollar_routing_ceiling() -> None:
    """§5.5. Unchanged by this correction, and not to be raised to make code pass."""
    assert CLOUD_CEILING_USD == 200.00


# --- the rule itself ---------------------------------------------------------


def test_the_old_rule_and_the_new_rule_disagree_exactly_where_it_matters() -> None:
    """The defect, stated as a test.

    `199.99 < 200` was the whole guard. It admits a $40 call. The corrected rule
    refuses it, and the difference between them is the ceiling being enforced.
    """
    committed, proposed = 199.99, 40.00
    assert committed < CLOUD_CEILING_USD, "the old rule admitted this"
    assert not admits(committed, proposed), "the new rule must refuse it"


def test_a_call_that_fits_exactly_is_admitted() -> None:
    """The comparison is `<=`. Spending the last cent is spending, not breaching."""
    assert admits(199.99, 0.01)


def test_a_call_one_hundredth_of_a_cent_too_large_is_refused() -> None:
    assert not admits(199.99, 0.0101)


def test_nothing_is_admitted_once_the_ceiling_is_passed() -> None:
    """Even a free-looking call: there is no such thing at a breached ceiling."""
    assert not admits(250.00, 0.000001)


def test_remaining_never_goes_negative() -> None:
    """A negative remainder read as a number would be worse than useless."""
    assert remaining_usd(250.00) == 0.0
    assert remaining_usd(150.00) == pytest.approx(50.00)


# --- the cost bound is a bound, not an estimate ------------------------------


def test_the_input_bound_is_at_least_the_byte_length() -> None:
    """A byte-level tokenizer never emits more tokens than there are bytes."""
    content = "Good evening, my lord. What shall we turn our attention to?"
    assert upper_bound_input_tokens([content], config()) >= len(content.encode("utf-8"))


def test_the_bound_holds_for_multibyte_content() -> None:
    """The characters-per-token rule of thumb breaks here; byte length does not."""
    content = "早晚安、我的大人。" * 50
    bound = upper_bound_input_tokens([content], config())
    assert bound >= len(content.encode("utf-8"))
    assert bound > len(content), "a character count would have under-reserved"


def test_the_bound_is_capped_at_the_context_window() -> None:
    """Content past the window is rejected by the provider, so it cannot cost more."""
    entry = config()
    huge = "x" * (entry.context_window_tokens * 2)  # type: ignore[attr-defined]
    assert upper_bound_input_tokens([huge], entry) == entry.context_window_tokens  # type: ignore[attr-defined]


def test_framing_is_counted_so_short_messages_are_still_bounded() -> None:
    """On a two-character message the framing is most of the cost."""
    assert upper_bound_input_tokens(["hi"], config()) > 2


def test_maximum_cost_rises_with_the_output_cap() -> None:
    """The output allowance is part of what a call is authorised to consume."""
    small = maximum_cost(config(), ["hello"], 100)
    large = maximum_cost(config(), ["hello"], 100_000)
    assert large > small


def test_maximum_cost_is_capped_by_the_configuration_output_limit() -> None:
    """A request asking for more than the model can emit is bounded by the model."""
    entry = config()
    at_limit = maximum_cost(entry, ["hello"], entry.max_output_tokens)  # type: ignore[attr-defined]
    beyond = maximum_cost(entry, ["hello"], entry.max_output_tokens * 10)  # type: ignore[attr-defined]
    assert at_limit == pytest.approx(beyond)


def test_the_cheaper_route_authorises_a_smaller_maximum() -> None:
    """Which is why an unaffordable frontier call can yield to an affordable one."""
    expensive = maximum_cost(config("opus-5"), ["hello"], 4096)
    cheap = maximum_cost(config("haiku-4-5"), ["hello"], 4096)
    assert cheap < expensive


# --- what Val says -----------------------------------------------------------


def test_the_refusal_states_the_arithmetic_not_a_policy() -> None:
    """Actionable: what is left, what was asked for, what is already committed."""
    message = ceiling_message(199.99, 4.00)
    assert "$0.01" in message
    assert "$4.00" in message
    assert "199.99" in message
    assert "before a call" in message


def test_the_refusal_does_not_offer_a_downgrade() -> None:
    """Budget never buys a way around eligibility."""
    message = ceiling_message(199.99, 4.00)
    assert "reclassif" not in message.lower()
