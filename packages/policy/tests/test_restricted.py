"""Tests for the Restricted-content preflight.

The rule under test: obvious Restricted material never reaches a cloud provider,
whatever the caller believed about the content's classification. Every fake
credential here is assembled at runtime from harmless fragments, so this file
does not itself contain one.
"""

import pytest

from val_policy.restricted import (
    RestrictedFinding,
    find_restricted,
    preflight,
    refusal_message,
)


def fake(*fragments: str) -> str:
    """Build a credential-shaped string without writing one down."""
    return "".join(fragments)


# --- what must be caught ------------------------------------------------------


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (fake("-----BE", "GIN RSA PRIVATE KE", "Y-----"), "a private key"),
        (
            "here is my key " + fake("sk-", "ant-", "a1b2c3d4e5f6g7h8i9j0k1l2"),
            "an Anthropic API key",
        ),
        ("use " + fake("sk-", "proj-", "abcdefghij0123456789klmno"), "an OpenAI API key"),
        ("aws " + fake("AK", "IA") + "ABCDEFGHIJKLMNOP", "an AWS access key"),
        ("token " + fake("gh", "p_") + "a" * 36, "a GitHub token"),
        ("the db password = " + fake("hunter", "2hunter2"), "a labelled credential"),
        (
            "postgres://val:" + fake("s3cr", "etpass") + "@db.example.com/val",
            "a connection string with a password",
        ),
        ("his ssn is 123-45-6789", "government identification"),
        # 4111 1111 1111 1111 is the canonical Luhn-valid test card.
        ("card 4111 1111 1111 1111 expires soon", "a payment card number"),
    ],
)
def test_obvious_restricted_material_is_found(content: str, expected: str) -> None:
    """Each representative case the amendment names."""
    finding = find_restricted(content)
    assert finding is not None, f"missed: {expected}"
    assert finding.kind == expected


def test_preflight_scans_the_system_prompt_too() -> None:
    """Everything transmitted is scanned, not only the user's message."""
    finding = preflight(("A harmless question.", "context: password = " + fake("s3cr3t", "value")))
    assert finding is not None


# --- what must not be caught --------------------------------------------------
#
# A preflight that fires on ordinary creative work would be turned off, and a
# preflight that is off protects nothing.


@pytest.mark.parametrize(
    "content",
    [
        "Open on the wide shot, then cut to the close.",
        "The cold open runs long every time we are precious about the establishing shot.",
        "Episode 4 has 1234 frames of animation to review.",
        "My lord, the schedule has slipped past recovery on the current plan.",
        "Discuss how we handle passwords in the show's plot without naming any.",
        "Invoice number 2024-11-3087 for the storyboard artist.",
    ],
)
def test_ordinary_work_passes(content: str) -> None:
    """Creative and project language is not Restricted."""
    assert find_restricted(content) is None


def test_a_bare_long_number_is_not_a_card_unless_it_checksums() -> None:
    """Luhn is what separates a card from an identifier."""
    assert find_restricted("reference 1234567812345678") is None


# --- it fails closed ----------------------------------------------------------


def test_a_broken_scan_blocks_rather_than_sends(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the check cannot complete, the content is refused, never transmitted."""

    def explode(_: str) -> RestrictedFinding | None:
        raise RuntimeError("the scanner broke")

    monkeypatch.setattr("val_policy.restricted.find_restricted", explode)
    finding = preflight(("anything at all",))
    assert finding is not None
    assert "could not complete" in finding.explanation


def test_the_refusal_explains_and_does_not_offer_to_downgrade() -> None:
    """Val says what happened and why, and never offers to reclassify it."""
    message = refusal_message(RestrictedFinding("a private key", "the message contains a key"))
    assert "have not sent" in message
    assert "Restricted" in message
    assert "will not reclassify" in message
