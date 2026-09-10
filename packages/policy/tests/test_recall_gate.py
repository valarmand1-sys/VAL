"""The cross-conversation recall gate (ruled 10 September 2026): deterministic, whitelist
first, positively grounded second, failing toward recall everywhere else."""

from __future__ import annotations

import pytest

from val_policy.recall_gate import ThreadContext, gate_recall

EMPTY = ThreadContext(retained=())
PREVIOUS_VAL = (
    "Good evening, my lord. Welcome back.\n\nI have no conversation behind me this morning "
    "— only some retrieved excerpts of your earlier words. What shall we turn our "
    "attention to?"
)
THREAD = ThreadContext(
    retained=(("user", "Hello, Val!"), ("val", PREVIOUS_VAL)),
    envelope_facts=("Thursday 10 September 2026, 11:03", "11:03"),
)
CORRECTION = (
    "It is 10:49 in the morning, Val. You greeted me with “Good evening,” then "
    "immediately referred to “this morning.” Please correct that."
)


# --- Tier One: a finite grammar ------------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Hello, Val!",
        "Hello",
        "hi",
        "Hi Val",
        "Thanks",
        "Thank you",
        "Thank you, my lord.",
        "Yes",
        "No.",
        "Okay",
        "ok",
        "Val, hello",
        "My lord, thanks.",
    ],
)
def test_tier_one_admits_exactly_the_closed_forms(message: str) -> None:
    decision = gate_recall(message, no_project=False, context=EMPTY)
    assert decision.run is False and decision.reason == "tier_one"


@pytest.mark.parametrize(
    "message",
    [
        "sure",  # a synonym is not a form
        "sounds good",
        "got it",
        "perfect",
        "great",
        "Hello there",  # an unenumerated token
        "Hello Val, thanks for yesterday",  # a back-reference
        "Hello 2",  # a digit
        'Hello "Val"',  # quotation marks
        "Hello?",  # a question mark
        "Hello Tony",  # a capitalised token outside the safe vocabulary
        "continue where we left off",  # short and lowercase is not sufficient
        "carry on from where we stopped",
        "finish what we were working on",
        "Thanks again",  # 'again' is in the closed inventory
        "Thanks you",  # 'you' does not make an arbitrary message eligible
    ],
)
def test_tier_one_refuses_everything_outside_the_grammar(message: str) -> None:
    decision = gate_recall(message, no_project=False, context=EMPTY)
    assert decision.reason != "tier_one"


def test_tier_one_is_bounded_by_the_ruled_word_count() -> None:
    long_form = " ".join(["hello"] * 16)
    assert gate_recall(long_form, no_project=False, context=EMPTY).run is True


def test_sentence_initial_capitalisation_exempts_nothing_in_tier_one() -> None:
    assert gate_recall("Continue", no_project=False, context=EMPTY).run is True


# --- Tier Two: positively grounded thread-local -------------------------------


def test_the_captured_greeting_correction_qualifies_through_tier_two() -> None:
    """The quoted phrases occur verbatim in Val's immediately preceding message; the
    digits are new factual content inside that thread-local exchange."""
    decision = gate_recall(CORRECTION, no_project=False, context=THREAD)
    assert decision.run is False and decision.reason == "tier_two"
    assert "quote 'Good evening'" in decision.detail and "quote 'this morning'" in decision.detail


def test_an_ungrounded_quotation_recalls() -> None:
    decision = gate_recall("You greeted me with “Good morning.”", no_project=False, context=THREAD)
    assert decision.run is True


def test_immediate_thread_back_references_are_grounded_by_a_prior_val_message() -> None:
    thread = ThreadContext(retained=(("user", "Draft it."), ("val", "Here is a draft.")))
    assert gate_recall("try again", no_project=False, context=thread).reason == "tier_two"
    assert gate_recall("no, the other one", no_project=False, context=thread).reason == "tier_two"
    assert gate_recall("that one", no_project=False, context=thread).reason == "tier_two"


def test_immediate_thread_back_references_without_a_val_message_recall() -> None:
    thread = ThreadContext(retained=(("user", "Draft it."),))
    assert gate_recall("try again", no_project=False, context=thread).run is True


def test_other_back_references_are_cross_thread_signals_and_recall() -> None:
    for message in (
        "As we discussed, shorten it.",
        "Like last time.",
        "What you said earlier.",
        "The one we decided on.",
        "Remember the lens.",
    ):
        assert gate_recall(message, no_project=False, context=THREAD).run is True, message


def test_a_question_mark_recalls_in_tier_two() -> None:
    assert gate_recall("Was it “Good evening”?", no_project=False, context=THREAD).run


def test_a_capitalised_token_not_grounded_in_the_thread_recalls() -> None:
    assert gate_recall("Send it to Faye.", no_project=False, context=THREAD).run is True


def test_a_capitalised_token_grounded_in_the_thread_is_an_anchor() -> None:
    thread = ThreadContext(retained=(("user", "Draft the note to Faye."), ("val", "Drafted.")))
    decision = gate_recall("Please send it to Faye.", no_project=False, context=thread)
    assert decision.reason == "tier_two" and "token 'Faye'" in decision.detail


# --- the corrected Tier Two reading (ruled 10 September 2026): no general
# sentence-initial exemption -------------------------------------------------


def test_the_captured_correction_beginning_it_is_still_qualifies() -> None:
    decision = gate_recall(CORRECTION, no_project=False, context=THREAD)
    assert decision.reason == "tier_two"


def test_a_grounded_quote_followed_by_an_ungrounded_sentence_initial_name_recalls() -> None:
    decision = gate_recall(
        "“Good evening” was wrong. Tony needs a change.", no_project=False, context=THREAD
    )
    assert decision.run is True, (
        "Tony is a new external referent; sentence position exempts nothing"
    )


def test_the_same_case_qualifies_when_the_name_is_in_retained_history() -> None:
    thread = ThreadContext(
        retained=(("user", "Hello, Val!"), ("val", PREVIOUS_VAL + " Tony is the lead."))
    )
    decision = gate_recall(
        "“Good evening” was wrong. Tony needs a change.", no_project=False, context=thread
    )
    assert decision.reason == "tier_two" and "token 'Tony'" in decision.detail


def test_a_sentence_initial_it_outside_the_time_form_recalls() -> None:
    decision = gate_recall(
        "“Good evening” was wrong. It needs revision.", no_project=False, context=THREAD
    )
    assert decision.run is True, "'It' is referential here; only the quote is grounded"


def test_it_is_exempt_only_at_the_head_of_the_time_assertion() -> None:
    thread = ThreadContext(
        retained=(("user", "Hello"), ("val", "Good morning.")), envelope_facts=("11:03",)
    )
    assert gate_recall("It is 11:03 now.", no_project=False, context=thread).reason == "tier_two"
    assert gate_recall("It is late now.", no_project=False, context=thread).run is True


def test_you_and_please_are_the_closed_orthographic_exemption() -> None:
    thread = ThreadContext(retained=(("user", "Draft it."), ("val", "Here is a draft.")))
    assert gate_recall("Please try again.", no_project=False, context=thread).reason == "tier_two"
    assert gate_recall("You try again.", no_project=False, context=thread).reason == "tier_two"
    assert gate_recall("Kindly try again.", no_project=False, context=thread).run is True


def test_an_envelope_fact_is_an_anchor() -> None:
    thread = ThreadContext(
        retained=(("user", "Hello"), ("val", "Good morning.")), envelope_facts=("11:03",)
    )
    decision = gate_recall("It is 11:03 now.", no_project=False, context=thread)
    assert decision.reason == "tier_two" and "envelope fact '11:03'" in decision.detail


def test_without_retained_history_tier_two_cannot_ground_anything() -> None:
    assert gate_recall(CORRECTION, no_project=False, context=EMPTY).run is True


def test_a_thread_dependent_command_without_an_enumerated_anchor_recalls() -> None:
    """'shorten that' has no form in the closed inventory ('that' alone is not listed), so
    under the ruled inventory it fails toward recall. Recorded, not widened."""
    thread = ThreadContext(retained=(("user", "Draft it."), ("val", "Here is a draft.")))
    assert gate_recall("shorten that", no_project=False, context=thread).run is True


# --- precedence and the clean room ---------------------------------------------


def test_no_project_scope_takes_precedence_over_every_tier() -> None:
    for message in ("Hello, Val!", CORRECTION, "What did we decide about the second unit?"):
        decision = gate_recall(message, no_project=True, context=THREAD)
        assert decision.run is False and decision.reason == "no_project_scope", message


def test_an_explicit_cross_thread_request_recalls() -> None:
    decision = gate_recall(
        "What did we say about the lighthouse lens?", no_project=False, context=THREAD
    )
    assert decision.run is True and decision.reason is None
