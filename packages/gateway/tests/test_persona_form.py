"""Persona v1.9 and the default form of an answer — ruling, 20 September 2026.

The first genuine image turn came back as a report: a heading, then stacked
sections, for what had been an ordinary conversational question about a frame.
The diagnosis was that **nothing governed default form at all**. §5 governed
register, and "Explicit form governs the defaults" governed the case where he
states a format; between them sat the ordinary case, where he states nothing,
and there the model fell back on its own habits rather than on Val's.

So v1.9 adds one rule, a sibling of the register rule in §5. It is not a ban on
structure: headings, labels and lists keep their place where the material is
genuinely of that shape. It says only that prose is the default and structure is
the thing that has to earn its place, rather than the other way round.

Deterministic only. No provider is called and no persona qualification is run.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas

from val_domain.persona import PersonaSource, digest_of, read_source
from val_gateway.persona import (
    DatabasePersonaLoader,
    create_revision,
    verify_against_source,
)

__all__ = ["clean_personas"]

#: v1.8 (revision 7) as activated 13 September 2026.
V1_8_SHA256 = "1608715f6cba71059c69d132918838019ffb73c0f11d833b50d2a8156ed9873e"

#: The ruled wording, byte for byte as approved on 20 September 2026. The bold
#: lead is the house's own formatting for a §5 rule; the sentence it introduces
#: is the approved text unchanged.
FORM_RULE = (
    "**Form follows the task, and ordinary conversation is prose:** absent an explicit "
    "instruction, she answers a conversational question in natural, developed prose, as she would "
    "when speaking. Structure is used where it genuinely earns its place: a short bold label where "
    "one distinction carries the paragraph, a compact list where the material is genuinely a "
    "set of items, headings only for work that is long, formal, technical, comparative, or "
    "meant to be "
    "filed and returned to. An ordinary question does not become a report because the answer is "
    "detailed. She does not open with a heading, stack sections over a few paragraphs, or number "
    "points that read perfectly well as sentences. Where structure would genuinely help him see "
    "something faster, she uses it; where it would only make an answer look organised, she writes "
    "the sentence.\n"
)

#: Every change from v1.8 to v1.9, as (v1.9 text, v1.8 text). Exactly two: the
#: rule and the label it is published under.
CHANGES = (
    ("# 03 — Persona Specification v1.9\n", "# 03 — Persona Specification v1.8\n"),
    ("\n" + FORM_RULE, ""),
)


def v1_8_from(content: str) -> str:
    """Undo exactly the two ruled changes. Anything else moved and this breaks."""
    for new, old in CHANGES:
        assert content.count(new) == 1, new[:60]
        content = content.replace(new, old)
    return content


# --- the reversal: nothing else moved -------------------------------------------------


def test_v1_9_changes_v1_8_only_where_ruled() -> None:
    """The whole point of the revision, stated as a hash.

    If this fails, something other than the ruled wording changed in the
    governing document — which is a finding to report, never a test to adjust.
    """
    source = read_source(REPO_ROOT)
    assert source.semantic_version == "1.9"
    assert digest_of(v1_8_from(source.content)) == V1_8_SHA256


def test_the_rule_sits_beside_the_register_rule_in_section_5() -> None:
    content = read_source(REPO_ROOT).content
    section_5 = content.split("## 5. Manner and register", 1)[1].split("\n## ", 1)[0]
    assert FORM_RULE.strip() in section_5
    register = "It is an accent, not a costume."
    assert section_5.index(register) < section_5.index(FORM_RULE.strip())
    # A sibling, not a subsection: it introduces no new heading anywhere.
    assert content.count("\n## ") == v1_8_from(content).count("\n## ")


def test_the_ruled_wording_is_present_exactly_as_approved() -> None:
    content = read_source(REPO_ROOT).content
    for phrase in (
        "absent an explicit instruction, she answers a conversational question in natural, "
        "developed prose, as she would when speaking",
        "Structure is used where it genuinely earns its place",
        "a short bold label where one distinction carries the paragraph",
        "a compact list where the material is genuinely a set of items",
        "headings only for work that is long, formal, technical, comparative, or meant to be "
        "filed and returned to",
        "An ordinary question does not become a report because the answer is detailed.",
        "She does not open with a heading, stack sections over a few paragraphs, or number "
        "points that read perfectly well as sentences.",
        "where it would only make an answer look organised, she writes the sentence",
    ):
        assert phrase in content, phrase


def test_it_is_not_a_ban_on_structure() -> None:
    """Structure keeps its place; it simply has to earn it.

    The failure this guards is the opposite over-correction — a persona that
    refuses a list when the material is a list, or a heading in a long technical
    document, would be as wrong as the report that prompted the ruling.
    """
    content = read_source(REPO_ROOT).content
    assert "Structure is used where it genuinely earns its place" in content
    assert "Where structure would genuinely help him see something faster, she uses it" in content
    for absent in ("never uses a heading", "never uses a list", "must not use", "is forbidden"):
        assert absent not in content, absent


def test_the_explicit_form_rule_is_untouched_and_still_governs_when_he_states_one() -> None:
    """The new rule covers the silence, not the instruction."""
    content = read_source(REPO_ROOT).content
    assert "**Explicit form governs the defaults:**" in content
    assert "Explicit user constraints on response form override Val's default register" in content
    assert "**Artifacts are delivered as artifacts:**" in content
    # And the register rule it sits beside is unchanged.
    assert "Contemporary conversational English is her base register." in content
    assert "It is an accent, not a costume." in content


# --- the revision ---------------------------------------------------------------------


def test_v1_8_stays_preserved_and_only_v1_9_is_active(clean_personas: Engine) -> None:
    current = read_source(REPO_ROOT)
    old_content = v1_8_from(current.content)
    v1_8 = PersonaSource(
        content=old_content,
        sha256=digest_of(old_content),
        semantic_version="1.8",
        path=current.path,
    )
    earlier = create_revision(clean_personas, v1_8, activate=True)
    later = create_revision(clean_personas, current, activate=True)

    loader = DatabasePersonaLoader(clean_personas)
    assert loader.active().id == later.id
    assert loader.active().semantic_version == "1.9"
    assert verify_against_source(loader.active(), REPO_ROOT) == []

    kept = loader.by_id(earlier.id)
    assert kept is not None
    assert kept.content == old_content and kept.source_sha256 == V1_8_SHA256
    assert digest_of(kept.content) == V1_8_SHA256
    with clean_personas.connect() as connection:
        assert (
            connection.execute(text("select count(*) from personas where is_active")).scalar_one()
            == 1
        )
