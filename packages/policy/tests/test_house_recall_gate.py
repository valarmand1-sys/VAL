"""The House Recall gate — ruling of 12 September 2026.

A second, independent gate: it runs only on an explicit cross-conversation
reference from the closed inventory, fails toward isolation on anything else,
defers to the retained thread when a quoted reference is demonstrably
satisfied there, and never alters `gate_recall`.
"""

from __future__ import annotations

from val_policy.recall_gate import (
    HOUSE_RECALL_PHRASES,
    ThreadContext,
    gate_house_recall,
    gate_recall,
)

EMPTY = ThreadContext(retained=())

LIVE_ONE = (
    "Good afternoon, Val. I want to return to something we have discussed before. "
    "Tell me what you remember about House Armand and the role you believe you hold within it."
)
LIVE_TWO = (
    "Some of those earlier conversations about House Armand are stored in conversations "
    "associated with other projects, and some may be unassigned. From this conversation, are "
    "you able to search across my prior conversations and retrieve those discussions, or is "
    "your access limited to the current conversation or project?"
)


def test_the_two_live_messages_of_12_september_run_house_recall() -> None:
    for message in (LIVE_ONE, LIVE_TWO):
        decision = gate_house_recall(message, EMPTY)
        assert decision.run and decision.reason is None, message
        assert "explicit cross-conversation reference" in decision.detail


def test_every_listed_example_runs() -> None:
    examples = (
        "We discussed this before.",
        "What did we decide about the harbour scene?",
        "You said earlier that the lens was cobalt.",
        "Remember when we settled the title?",
        "What do you remember about House Armand?",
        "This continues the work from another project.",
        "Please search your earlier conversations for the lighthouse notes.",
        "Look across my conversations for what we agreed.",
        "In a previous conversation you mentioned the workshop.",
        # "we settled" is an inventory form: the 11 September verification prompt that
        # found no record should, and now does, search the House.
        "Summarise what we settled last week about the harbour scene.",
    )
    for message in examples:
        assert gate_house_recall(message, EMPTY).run, message


def test_ordinary_messages_do_not_run_house_recall() -> None:
    ordinary = (
        "Good evening, Val.",
        "How are you feeling today?",
        "Draft the two-line note to the props department.",
        "Which opening for episode three do we commit to: the wide shot or the close-up?",
        "We have nine shooting days and two locations three hours apart. Sketch a schedule.",
        "Tell me about House Armand.",
        "I remember the harbour fondly.",  # 'remember' alone is not an inventory form
        "You said the lens was cobalt.",  # no temporal marker
    )
    for message in ordinary:
        decision = gate_house_recall(message, EMPTY)
        assert not decision.run, message
        assert decision.reason == "no_cross_conversation_reference"


def test_tier_one_forms_never_run() -> None:
    for message in ("Thanks, Val.", "Yes.", "Hello, my lord."):
        decision = gate_house_recall(message, EMPTY)
        assert not decision.run and decision.reason in (
            "no_cross_conversation_reference",
            "tier_one",
        )


def test_a_thread_grounded_quoted_reference_defers_to_the_thread() -> None:
    """'You said earlier "X"' where X is verbatim in the retained thread is thread-local."""
    context = ThreadContext(
        retained=(("user", "Which lens?"), ("val", "I would go long, my lord."))
    )
    grounded = 'You said earlier "I would go long, my lord." Why?'
    decision = gate_house_recall(grounded, context)
    assert not decision.run and decision.reason == "thread_grounded"
    # The same words with nothing in the thread to satisfy them: House Recall runs.
    assert gate_house_recall(grounded, EMPTY).run
    # A quoted span the thread does not contain runs too.
    ungrounded = 'You said earlier "the wide shot is right." Why?'
    assert gate_house_recall(ungrounded, context).run


def test_an_unmatched_message_is_not_run_never_ambiguous() -> None:
    decision = gate_house_recall("Something about earlier, maybe, I am not sure.", EMPTY)
    assert not decision.run
    assert decision.reason == "no_cross_conversation_reference"


def test_the_inventory_is_closed_and_version_controlled() -> None:
    assert all(all(token == token.lower() for token in phrase) for phrase in HOUSE_RECALL_PHRASES)
    assert ("we", "discussed") in HOUSE_RECALL_PHRASES
    assert ("what", "did", "we") in HOUSE_RECALL_PHRASES


def test_house_recall_never_alters_the_automatic_gate() -> None:
    """The automatic decision is the same whether or not House Recall would run."""
    for message in (LIVE_ONE, "Good evening, Val.", "We discussed this before."):
        for no_project in (True, False):
            before = gate_recall(message, no_project=no_project, context=EMPTY)
            gate_house_recall(message, EMPTY)
            after = gate_recall(message, no_project=no_project, context=EMPTY)
            assert before == after
    assert gate_recall(LIVE_ONE, no_project=True, context=EMPTY).reason == "no_project_scope"
