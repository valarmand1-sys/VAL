"""Reading the governing persona document, exactly once and exactly one way.

`04-layer-0.md` WP-0.5 requires **two independent proofs**, and they only stay
independent if the reading rule is single. If the seeder normalised newlines one
way and the verifier another, the two checks would be comparing different things
and both could pass while the record and the document disagreed.

**The canonical rule, stated once and used everywhere in this repository:**

> The governing document is read as **raw bytes**. Its SHA-256 is the digest of
> **those bytes**, unmodified. Its content is those same bytes decoded as strict
> UTF-8, stored verbatim. **No normalisation is applied** — not to newlines, not
> to trailing whitespace, not to Unicode form.

No normalisation *is* the normalisation, and it is the strongest available
choice: every other option requires trusting that the same transformation was
applied in both places, while this one has nothing to get wrong. Round-tripping
is exact because PostgreSQL stores `text` as UTF-8 and the document contains no
NUL byte, which is the only sequence it would refuse.

Nothing here touches a database or a provider. This module is pure so that
`read_source` can be called by the seeder, by the verifier, and by a test,
without any of them being able to disagree about what it did.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

#: The repository-relative path of the governing persona. Relative deliberately:
#: an absolute path is a fact about one machine, and a record that made one
#: authoritative would be unverifiable anywhere else (WP-0.5, §2.C).
GOVERNING_PERSONA_PATH = "docs/baselines/03-persona.md"

#: The document's authored label lives in its H1 and nowhere else:
#:
#:     # 03 — Persona Specification v1.2
#:
#: Anchored to the first line so a "v1.1" mentioned in a change log cannot be
#: mistaken for the document's own version. Deterministic and validated — the
#: version is never inferred, and never asked of a model, which would make the
#: record depend on the thing it exists to govern.
_TITLE_VERSION = re.compile(r"^#\s+.*?\bv(?P<label>[0-9]+(?:\.[0-9]+)*)\s*$")

#: What the database will accept: digits and dots, no leading "v".
_CANONICAL_VERSION = re.compile(r"^[0-9]+(\.[0-9]+)*$")


class PersonaSourceError(Exception):
    """The governing document cannot be read, or does not declare its version."""


@dataclass(frozen=True)
class PersonaSource:
    """One governing persona document, read under the canonical rule."""

    #: The document's text, byte-exact after strict UTF-8 decoding.
    content: str
    #: SHA-256 of the raw bytes on disk — not of `content` re-encoded, though the
    #: two are equal by construction and `verify` proves it.
    sha256: str
    #: The authored label, canonicalised without its "v": `1.2`, not `v1.2`.
    semantic_version: str
    #: Repository-relative, as stored.
    path: str

    def matches(self, content: str, sha256: str) -> bool:
        """Whether a stored record is byte-identical to this document.

        Both halves are checked. Content equality alone would pass if the stored
        digest were wrong; digest equality alone would pass if the digest had
        been computed over something other than the stored text.
        """
        return content == self.content and sha256 == self.sha256


def semantic_version_of(content: str) -> str:
    """The authored label the document declares, or raise.

    Raises rather than defaulting. A persona seeded under a guessed version is
    worse than one that failed to seed: the failure is noticed immediately, and
    the guess is noticed months later when someone asks which persona was live.
    """
    first_line = content.split("\n", 1)[0]
    found = _TITLE_VERSION.match(first_line)
    if found is None:
        raise PersonaSourceError(
            f"The persona document's first line does not declare a version: {first_line!r}. "
            "The authored label is read from the H1 and from nowhere else, deterministically. "
            "It is never inferred and never asked of a model."
        )
    version = found.group("label")
    if not _CANONICAL_VERSION.match(version):
        raise PersonaSourceError(f"{version!r} is not a canonical semantic version")
    return version


def read_source(root: Path, path: str = GOVERNING_PERSONA_PATH) -> PersonaSource:
    """Read the governing document under the canonical rule. The only reader.

    `root` is the repository root, so the stored path stays relative while the
    read is absolute. Nothing else in this repository opens the persona file.
    """
    absolute = root / path
    try:
        raw = absolute.read_bytes()
    except OSError as error:
        raise PersonaSourceError(f"cannot read the persona document at {path}: {error}") from error

    try:
        content = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise PersonaSourceError(
            f"{path} is not valid UTF-8, and the canonical rule decodes strictly rather "
            "than repairing: a persona that was silently repaired is not the authored one."
        ) from error

    return PersonaSource(
        content=content,
        sha256=hashlib.sha256(raw).hexdigest(),
        semantic_version=semantic_version_of(content),
        path=path,
    )


def digest_of(content: str) -> str:
    """The digest of text under the canonical rule.

    Re-encodes as UTF-8 and hashes, which is the same operation `read_source`
    performs on the bytes it read. Used to verify a *stored* record against its
    own recorded digest, where the original bytes are no longer to hand.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
