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


# --- labelled financial credentials — amendment, 17 August 2026 ---------------
#
# `01-architecture.md` §5.4 puts financial detail in Restricted, and until this
# amendment the only financial thing matched was a payment card. Each of these
# requires a label, a checksum, or both.


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        # 021000021 is a published, Luhn-independent ABA test/reference value
        # and satisfies the 3-7-1 check digit.
        ("my routing number is 021000021, please wire it", "a bank routing number"),
        ("ABA: 021000021", "a bank routing number"),
        ("account number: 12345678", "a bank account number"),
        ("bank acct no. 4455 6677 88", "a bank account number"),
        ("sort code 40-47-84 at the branch", "a bank sort code"),
        ("SWIFT code CHASGB2L for the transfer", "a bank identifier code"),
        # A published IBAN example that satisfies mod-97.
        ("send it to GB82WEST12345698765432", "a bank account number"),
    ],
)
def test_labelled_financial_credentials_are_found(content: str, expected: str) -> None:
    """The classes the coverage table claims, each demonstrated."""
    finding = find_restricted(content)
    assert finding is not None, f"missed: {content!r}"
    assert finding.kind == expected


@pytest.mark.parametrize(
    "content",
    [
        # A nine-digit number near the word "routing" that fails the ABA check.
        "the routing number is 123456789 for that lane",
        # A shape that looks like an IBAN but fails mod-97.
        "the ticket reference is GB82WEST12345698765433",
        # An unlabelled run of digits: an invoice, not an account.
        "invoice 4455667788 is outstanding",
        # Ordinary production talk that happens to use the words.
        "we should route the render through the account team on Tuesday",
        "the sort order in the shot list is wrong",
    ],
)
def test_financial_false_positives_are_not_raised(content: str) -> None:
    """A checksum or a label is required. Neither alone is a bank detail.

    This is the half that keeps the guard usable. A detector that fires on every
    nine-digit number gets turned off, and a guard that is off protects nothing.
    """
    assert find_restricted(content) is None, f"false positive on: {content!r}"


def test_a_label_cannot_reach_across_a_sentence() -> None:
    """The gap between a label and its value is bounded, deliberately."""
    content = "the account number was never recorded anywhere. Shot 021000021 is the plate id."
    assert find_restricted(content) is None


def test_the_coverage_claim_matches_what_is_implemented() -> None:
    """Guard on the documentation: every class the docstring names is detected.

    The module's docstring states exactly what it covers. If a class is listed
    there and nothing detects it, the claim is the defect.
    """
    import val_policy.restricted as module

    claimed = module.__doc__ or ""
    for phrase in (
        "Private key blocks",
        "Bank routing numbers",
        "IBANs",
        "Payment cards",
        "Social Security",
    ):
        assert phrase in claimed

    # And each is genuinely caught.
    assert find_restricted(fake("-----BE", "GIN EC PRIVATE KE", "Y-----")) is not None
    assert find_restricted("routing number 021000021") is not None
    assert find_restricted("GB82WEST12345698765432") is not None
    assert find_restricted("4111 1111 1111 1111") is not None
    assert find_restricted("123-45-6789") is not None


def test_the_docstring_does_not_claim_comprehensive_detection() -> None:
    """Part 8's requirement: state the mesh, do not claim the net catches all."""
    import val_policy.restricted as module

    claimed = module.__doc__ or ""
    assert "What it does not cover" in claimed
    assert "Layer 2" in claimed
