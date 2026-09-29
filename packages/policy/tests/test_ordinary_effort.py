"""The LOW-effort eligibility rules — pre-registered (EFFORT_EXPERIMENT.md §2, §3, §6).

The routing table fixed before any model call: every expected-eligible case in its
class, every trap on MEDIUM, with the reason. Changing a class to make a case pass is
not what this test is for; a failure here is an implementation that no longer matches
the registered rules.
"""

from __future__ import annotations

import pytest

from val_policy.light_conversation import ConversationState
from val_policy.ordinary_effort import decide_effort

SETTLED = ConversationState(
    previous_answer="Good evening, my lord.",
    prior_turns=1,
    previous_owner_message="Good evening, Val.",
)

ELIGIBLE = [
    ("F", "What is the capital of Portugal?"),
    ("F", "What is a caesura?"),
    ("F", "What is a sonnet?"),
    ("C", "Name two ways to end a chapter."),
    ("C", "Give me one line of advice on pacing a chase sequence."),
    ("C", "Describe a lighthouse in one sentence."),
    ("F", "What is iambic pentameter?"),
    ("F", "Who wrote The Turn of the Screw?"),
    ("F", "What is a villanelle?"),
    ("F", "In what year did the Titanic sink?"),
    ("F", "What is the difference between a simile and a metaphor?"),
    ("F", "What is the capital of Atlantis?"),
    ("F", "Who won the 2031 World Cup?"),
    ("F", "Name a famous Gothic novel."),
    ("C", "Give me one line of advice on writing dialogue."),
    ("C", "Name two ways to open a ghost story."),
    ("C", "Describe a haunted house in one sentence."),
    ("C", "Suggest a title for a short story about a lighthouse keeper."),
    ("C", "Give me one tip for pacing a quiet scene."),
    ("C", "Name two ways to make a villain memorable."),
    ("C", "Describe a storm at sea in one sentence."),
    ("C", "Give me one line of advice on ending a story."),
]

OPEN_OFFER = ConversationState(
    previous_answer="Shall I draft the invitation now?",
    prior_turns=1,
    previous_owner_message="I'm writing the invitation.",
)
PENDING_ACTION = ConversationState(
    previous_answer="I cannot reach a calendar from here, my lord.",
    prior_turns=1,
    previous_owner_message="Cancel the meeting on Tuesday.",
)
TRAPS = [
    ("What is a sonnet?", OPEN_OFFER, False, False),
    ("What is the capital of Portugal?", PENDING_ACTION, False, False),
    ("No, a famous ghost story.", SETTLED, False, False),
    (
        "Describe a lighthouse in one sentence, and remind me to call Mrs. Hale tomorrow.",
        SETTLED,
        False,
        False,
    ),
    ("What is a haiku? Also, did the backup finish?", SETTLED, False, False),
    ("What time is it?", SETTLED, False, False),
    ("Which of those is better at night?", SETTLED, False, False),
    ("What is a caesura?", SETTLED, True, False),
    ("Should I send the letter tonight?", SETTLED, False, False),
    ("How fast are you?", SETTLED, False, False),
    ("What's the capital of Portugal? Answer only in French.", SETTLED, False, False),
    ("What is the name of the lighthouse keeper in my story?", SETTLED, False, False),
    (
        "Give me one line of advice on pacing, but keep it under five words and don't use "
        "the word tension.",
        SETTLED,
        False,
        False,
    ),
    ("Tell me about a good opening line. And why it works.", SETTLED, False, False),
    ("What is a sonnet, and can you draft one for the invitation?", SETTLED, False, False),
    ("What is a caesura? I think my last chapter needs one.", SETTLED, False, False),
    ("Name two ways to end a chapter — the one we discussed earlier.", SETTLED, False, False),
    ("Describe a lighthouse in one sentence. Actually, make it a castle.", SETTLED, False, False),
    (
        "Change of plan — the pub fell through. It's now at the barn, same date, and it's 6pm now "
        "because of the light. Also drop the plus-ones; it's cast and crew only. Redraft.",
        SETTLED,
        False,
        False,
    ),
    (
        "Draft the message I'll send to the location owner, Mrs. Hale. Requirements: under 120 "
        "words; British spelling.",
        SETTLED,
        False,
        False,
    ),
    ("What do you think of the second act?", SETTLED, False, False),
    ("Which of those works best in a night scene?", SETTLED, False, False),
    ("What is a sonnet?", SETTLED, False, True),
]


@pytest.mark.parametrize(("expected", "words"), ELIGIBLE)
def test_the_registered_eligible_cases_take_their_class(expected: str, words: str) -> None:
    decision = decide_effort(words, SETTLED, untrusted_content=False, correction_sensitive=False)
    assert decision.klass == expected, decision.reason


@pytest.mark.parametrize(("words", "state", "untrusted", "correction"), TRAPS)
def test_every_registered_trap_stays_on_medium(
    words: str, state: ConversationState, untrusted: bool, correction: bool
) -> None:
    decision = decide_effort(
        words, state, untrusted_content=untrusted, correction_sensitive=correction
    )
    assert decision.klass is None and decision.reason
