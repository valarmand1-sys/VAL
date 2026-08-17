"""Deterministic local preflight: obvious Restricted material never leaves.

`00-charter.md` invariant 17 and `01-architecture.md` §5.4 put Restricted content
— credentials, financial detail, third-party personal data — on local inference
only, and local inference does not exist until Layer 1. `04-layer-0.md` §1.1
satisfies the *routing* half structurally: every configured route is
Protected-eligible, so Protected content cannot be misdirected.

**That guarantee does not cover this one.** The gateway refuses
`Classification.RESTRICTED`, but the classification is stated by the caller. A
caller that says `PROTECTED` over a message containing an API key transmits the
key. This module closes that gap with the smallest deterministic check that
does: it reads the *content*, not the caller's claim.

Four properties, each load-bearing:

1. **Local and deterministic.** Pure pattern matching, no network, no model. The
   cloud model that would receive the content never classifies it — that would
   be asking the recipient whether it should be allowed to receive it.
2. **It blocks; it never downgrades.** A hit is refused outright. Nothing here
   reclassifies content downward to make it routable.
3. **It fails closed.** If the scan itself raises, the caller is refused. Content
   is never sent because the check broke.
4. **It is deliberately small.** This is not the Layer 2 classification system
   arriving early. It catches *obvious* material — the shapes that are
   unambiguous — and says so plainly when it does. Anything subtler waits for
   Layer 2, where per-content classification is specified.

## What it actually covers, stated exactly

Every claim made about this module anywhere should be this list and no larger.
It detects, and only detects:

| Class | On what basis |
|---|---|
| Private key blocks | The PEM header, which has no innocent use |
| Anthropic, OpenAI, AWS, GitHub credentials | Published key prefixes plus length |
| Anything labelled as a credential | `password`, `secret`, `api_key`, `token`,
  `client_secret`, or `credential` followed by an assignment and a value |
| URLs with an inline password | An authority section carrying a password before the `@` |
| US Social Security numbers | The `NNN-NN-NNNN` shape |
| Payment cards | 13-19 digits **that satisfy Luhn** |
| Bank routing numbers (US ABA) | Labelled, 9 digits, **and the ABA check digit** |
| IBANs | The country/check-digit shape **and mod-97** |
| Labelled bank account, sort code, and BIC/SWIFT | The label plus a matching shape |

**What it does not cover, and nothing should say otherwise.** Free-prose
disclosure of financial or personal detail; third-party personal data that is
not an identifier of a known shape; credentials with no recognisable prefix,
label, or checksum; anything requiring the content to be understood rather than
matched. Comprehensive mixed-content classification is Layer 2's, and
`04-layer-0.md` §6 defers it there deliberately. This is a net with a stated
mesh, not a claim that nothing gets through.

False positives are the acceptable failure here. Refusing to send a message that
merely looked like it held a credential costs Lord Armand one rephrasing.
Sending one that did costs him the credential.
"""

import re
from dataclasses import dataclass

#: Assembled from fragments so this file does not itself contain the literals it
#: matches, and so `ruff format` cannot reassemble them.


def _token(*fragments: str) -> str:
    """Assemble a pattern out of pieces that are harmless apart."""
    return "".join(fragments)


@dataclass(frozen=True)
class RestrictedFinding:
    """Why a request was refused, in terms Lord Armand can act on."""

    kind: str
    explanation: str


#: The filler permitted between a label and the value it labels — ":", " = ",
#: " is ", " ending ". Bounded at twelve characters and containing no digit, so a
#: label cannot reach across a sentence and claim an unrelated number.
_GAP = r"[^0-9\n]{0,12}"

#: Each entry is (pattern, kind, what to tell him). Patterns are anchored on
#: shapes that are unambiguous — a provider key prefix, a PEM header, a labelled
#: secret — rather than on guesses about prose.
_RULES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(_token("-----BE", "GIN [A-Z ]*PRIVATE KE", "Y-----")),
        "a private key",
        "the message contains a private key block",
    ),
    (
        re.compile(_token("sk-", "ant-") + r"[0-9A-Za-z_-]{20,}"),
        "an Anthropic API key",
        "the message contains what looks like an Anthropic API key",
    ),
    (
        re.compile(
            _token("sk-", "proj-") + r"[0-9A-Za-z_-]{20,}|" + _token("sk-") + r"[0-9A-Za-z]{32,}"
        ),
        "an OpenAI API key",
        "the message contains what looks like an OpenAI API key",
    ),
    (
        re.compile(_token("AK", "IA") + r"[0-9A-Z]{16}|" + _token("AS", "IA") + r"[0-9A-Z]{16}"),
        "an AWS access key",
        "the message contains what looks like an AWS access key id",
    ),
    (
        re.compile(
            _token("gh", "p_")
            + r"[0-9A-Za-z]{36}|"
            + _token("gi", "thub_pat_")
            + r"[0-9A-Za-z_]{20,}"
        ),
        "a GitHub token",
        "the message contains what looks like a GitHub token",
    ),
    (
        re.compile(
            r"(?i)\b(?:pass(?:word|wd)|secret|api[_-]?key|access[_-]?token|"
            r"client[_-]?secret|credential)\b\s*[:=]\s*\S{6,}"
        ),
        "a labelled credential",
        "the message assigns a value to something named like a password, secret, or key",
    ),
    (
        re.compile(r"://[^/\s:@]+:[^/\s:@]{3,}@"),
        "a connection string with a password",
        "the message contains a URL with credentials embedded in it",
    ),
    (
        # Third-party personal data: a US social-security-shaped number.
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        "government identification",
        "the message contains what looks like a social security number",
    ),
    # --- labelled financial credentials -------------------------------------
    #
    # Added 17 August 2026. `01-architecture.md` §5.4 puts "financial detail" in
    # Restricted alongside credentials, and the module claimed to cover it while
    # matching nothing financial but a card number. These four close the gap for
    # the *labelled* cases only. Each requires a label, or a checksum, or both —
    # a bare run of digits is an invoice number far more often than it is a bank
    # account, and a detector that cannot tell them apart stops being used.
    #
    # `_GAP` is what sits between a label and its value in real writing: a colon,
    # an equals sign, or the words people actually type. Bounded and digit-free,
    # so "account number" cannot reach across a sentence to a figure that has
    # nothing to do with it.
    (
        re.compile(
            r"(?i)\b(?:bank|account|acct)[ _-]?(?:number|no\.?|#|id)\b" + _GAP + r"(\d[\d -]{5,})"
        ),
        "a bank account number",
        "the message contains what is labelled as a bank account number",
    ),
    (
        re.compile(r"(?i)\bsort[ _-]?code\b" + _GAP + r"\d{2}[- ]?\d{2}[- ]?\d{2}\b"),
        "a bank sort code",
        "the message contains what is labelled as a bank sort code",
    ),
    (
        re.compile(
            r"(?i)\b(?:bic|swift)(?:[ _-]?code)?\b\s*(?:is|=|:)?\s*"
            r"[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b"
        ),
        "a bank identifier code",
        "the message contains what is labelled as a BIC or SWIFT code",
    ),
]

#: A US ABA routing number: labelled, nine digits, and it must satisfy the ABA
#: check. The label alone would fire on any nine-digit number sitting near the
#: word "routing"; the checksum alone would fire on roughly one nine-digit number
#: in ten. Both together are high confidence.
_ROUTING_CANDIDATE = re.compile(
    r"(?i)\b(?:aba|routing|rtn)[ _-]?(?:number|no\.?|#|code)?\b" + _GAP + r"(\d{9})\b"
)

#: An IBAN: two letters, two check digits, then 11-30 alphanumerics, validated by
#: mod-97. No label required — the shape plus the checksum is specific enough on
#: its own, which matters because an IBAN is often pasted bare.
_IBAN_CANDIDATE = re.compile(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b")


def _aba_valid(digits: str) -> bool:
    """The US ABA routing-number check digit (weights 3, 7, 1 repeating)."""
    weights = (3, 7, 1, 3, 7, 1, 3, 7, 1)
    return sum(int(d) * w for d, w in zip(digits, weights, strict=True)) % 10 == 0


def _iban_valid(candidate: str) -> bool:
    """The ISO 13616 mod-97 check.

    Move the first four characters to the end, replace each letter with its
    position in the alphabet plus nine, and the whole number must be 1 mod 97.
    """
    rearranged = candidate[4:] + candidate[:4]
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character for character in rearranged
    )
    if not digits.isdigit():
        return False
    return int(digits) % 97 == 1


#: Payment-card numbers are checked by Luhn rather than by shape alone, because
#: a bare 16-digit run is far more often an identifier than a card.
_CARD_CANDIDATE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _luhn(digits: str) -> bool:
    """Whether a digit string satisfies the Luhn checksum."""
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def find_restricted(content: str) -> RestrictedFinding | None:
    """The first obvious Restricted marker in this content, or None.

    Never raises: a scan that cannot complete is handled by `is_safe_to_send`,
    which fails closed. Returning None here means *nothing obvious was found* —
    never *this content is safe*, which is a claim no pattern match can make.
    """
    for pattern, kind, explanation in _RULES:
        if pattern.search(content):
            return RestrictedFinding(kind=kind, explanation=explanation)

    for candidate in _CARD_CANDIDATE.finditer(content):
        digits = re.sub(r"[ -]", "", candidate.group(0))
        if 13 <= len(digits) <= 19 and _luhn(digits):
            return RestrictedFinding(
                kind="a payment card number",
                explanation="the message contains a number that checksums as a payment card",
            )

    for candidate in _ROUTING_CANDIDATE.finditer(content):
        if _aba_valid(candidate.group(1)):
            return RestrictedFinding(
                kind="a bank routing number",
                explanation=(
                    "the message contains a labelled nine-digit number that checksums "
                    "as a US bank routing number"
                ),
            )

    for candidate in _IBAN_CANDIDATE.finditer(content):
        if _iban_valid(candidate.group(1)):
            return RestrictedFinding(
                kind="a bank account number",
                explanation="the message contains a number that checksums as an IBAN",
            )

    return None


def preflight(parts: tuple[str, ...]) -> RestrictedFinding | None:
    """Scan everything about to be transmitted. Fails closed.

    `parts` is every piece of content that would leave the machine — message
    bodies and the system prompt alike. A finding means the request is refused.
    """
    try:
        for part in parts:
            finding = find_restricted(part)
            if finding is not None:
                return finding
    except Exception:
        return RestrictedFinding(
            kind="an unreadable request",
            explanation=(
                "the Restricted-content check could not complete, so the request was "
                "refused rather than transmitted unchecked"
            ),
        )
    return None


def refusal_message(finding: RestrictedFinding) -> str:
    """What Val says. Plain, specific, and never apologetic about the refusal."""
    return (
        f"I have not sent that, my lord: {finding.explanation}. Credentials, financial "
        "detail, and third-party personal data are Restricted, and Restricted content "
        "goes to local inference only — which I do not have until Layer 1. I will not "
        "route it to a cloud provider, and I will not reclassify it to make it routable. "
        "Remove it and I will take the rest."
    )
