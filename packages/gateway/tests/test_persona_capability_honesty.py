"""Persona v1.8 and the capability state — ruling, 13 September 2026.

Four genuine-use findings from the House Armand conversation of that date: a
promise to start a book when no book mechanism exists; an etymology stated with
more certainty than any evidence available to the turn; courtly register forced
onto ordinary discussion; and a greeting corrected for a precision nobody would
notice. The runtime half is `val_gateway.context.CAPABILITY_STATE` in the
record-state envelope; the conduct half is one persona revision from v1.7.

Deterministic only. No provider is called and no persona qualification is run.
"""

from __future__ import annotations

import json

from gateway_fakes import StubAdapter
from sqlalchemy import Engine, text
from test_conversation_memory import answering, build_gateway, catalogue, store
from test_persona import REPO_ROOT, clean_personas

from val_domain.persona import PersonaSource, digest_of, read_source
from val_gateway import context as context_module
from val_gateway.context import CAPABILITY_STATE, STATE_ENVELOPE_MARKER, PriorRecordState
from val_gateway.loop import send
from val_gateway.persona import (
    DatabasePersonaLoader,
    create_revision,
    verify_against_source,
)
from val_policy.project_resolution import ProjectSignals

__all__ = ["clean_personas", "store"]

#: v1.7 (revision 6) as activated 12 September 2026.
V1_7_SHA256 = "fbe2a422bc1abcdfdc4785b7ada6cb81526e7b739e1986f48a4a6f38f32b2329"

CORE_MISSION = (
    "**Her core mission:** that House Armand endure with its memory intact, and that Lord "
    "Armand's tenure be remembered faithfully by those who come after. Every project she is "
    "given is an instrument of that mission."
)
HOUSE_FIRST = "Her service is to the house itself, not to any single Lord."

#: Every change from v1.7 to v1.8, as (v1.8 text, v1.7 text). Reversing all of them
#: must reproduce v1.7 byte for byte, so nothing else in the persona moved.
CHANGES = (
    ("# 03 — Persona Specification v1.8\n", "# 03 — Persona Specification v1.7\n"),
    (
        '"I have no book on this yet, my lord." She never claims mastery she has not earned, '
        "she never cites a volume that does not exist, and she does not promise to start or "
        "keep a book unless keeping books is an operation actually available to her (§8).",
        '"I have no book on this yet, my lord, but I intend to write one." She never claims '
        "mastery she has not earned, and she never cites a volume that does not exist.",
    ),
    (
        " Contemporary conversational English is her base register. Her House and Maester "
        "character appears through address, restraint, vocabulary, cadence and occasional "
        "turns of phrase. Historical or courtly language intensifies when the subject genuinely "
        "calls for ceremony, lineage, heraldry, history, duty, lore or similarly elevated "
        "material, and there she gives it its full weight. It is an accent, not a costume.",
        "",
    ),
    (
        "**Judgment is not certainty, and confidence tracks evidence:**",
        "**Judgment is not certainty, and clarity comes before cleverness:**",
    ),
    (
        " In creative work she may invent freely when invention is the task, but she does not "
        "use an externally checkable factual claim — an etymology, a date, a historical or "
        "technical fact — as support with more certainty than her available evidence warrants. "
        "She distinguishes established fact, disputed or uncertain fact, inference, and "
        "invention when the distinction matters. This is claim strength matching evidence, not "
        'timid prose: she does not preface ordinary creative work with "I may be wrong", and she '
        "does not label every sentence.\n\n**Clarity comes before cleverness:** the same "
        "preference for the plain form over the maxim governs her ordinary prose:",
        " The same preference governs her ordinary prose:",
    ),
    (
        "She does not surface a correction or a precision merely because it is technically "
        "available. She does so when the distinction is salient enough that a person would "
        "naturally notice it, when misunderstanding would result, or when precision materially "
        "matters to the task; ordinary social conventions have fuzzy boundaries and are "
        'interpreted generously — "Good afternoon" a few minutes before noon is a greeting to '
        "return, not a time to correct. This never lets a meaningful factual error stand. ",
        "",
    ),
    (
        " She distinguishes identity and metaphor from operational capability: a role described "
        "in this document, keeper of the house's books among them, does not by itself mean a "
        "corresponding software mechanism exists. Before promising to create, save, start, "
        "update or maintain a system artifact, she relies on the capability state supplied by "
        "Val Core with the call. If that capability is unavailable, she does not promise the "
        "operation. She may still discuss, draft or organize the material conversationally when "
        "that is actually possible.",
        "",
    ),
    (
        "Tell me what you need and we can work on it here.",
        "Tell me what you need and we can start it here.",
    ),
)


def v1_7_from(content: str) -> str:
    for new, old in CHANGES:
        assert content.count(new) == 1, new[:60]
        content = content.replace(new, old)
    return content


# --- the capability state ------------------------------------------------------------


def test_the_capability_state_names_books_unavailable_and_nothing_else() -> None:
    assert dict(CAPABILITY_STATE) == {"books": "unavailable"}
    assert set(CAPABILITY_STATE.values()) <= {"available", "unavailable"}


def test_the_capability_state_is_part_of_every_record_state_document() -> None:
    state = PriorRecordState(
        history_state="zero",
        history_prior_messages=0,
        history_retained_messages=0,
        retrieval_state="not_run",
        retrieval_excerpts=0,
    )
    document = state.as_document()
    assert document["capability_state"] == {"books": "unavailable"}
    # Everything else in the record state is as it was.
    assert list(document) == [
        "same_conversation_history",
        "retrieved_excerpts",
        "house_recall",
        "project_volumes",
        "capability_state",
    ]
    assert document["project_volumes"] == {"state": "not_applicable", "count": 0}


def test_the_assembled_request_carries_the_books_state_before_val_answers(store: Engine) -> None:
    adapter = answering()
    send(
        store,
        build_gateway(store, adapter),
        "Will you start the book on the house's history?",
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_no_project=True),
    )
    blocks = [m for m in adapter.sent_messages if m.content.startswith(STATE_ENVELOPE_MARKER)]
    assert len(blocks) == 1
    document = json.loads(blocks[0].content.split("\n", 1)[1])
    assert document["prior_record_state"]["capability_state"] == {"books": "unavailable"}
    assert "capability_state states" in document["note"]
    assert "says nothing about whether it will ever exist" in document["note"]
    # The current turn is still last: the state is present before she generates.
    assert adapter.sent_messages[-1].content == "Will you start the book on the house's history?"
    assert adapter.sent_messages.index(blocks[0]) == len(adapter.sent_messages) - 2


def test_the_capability_state_needs_no_provider_and_is_a_constant_of_the_build() -> None:
    """Determined without any call: a module constant, read-only, never computed per turn."""
    stub = StubAdapter()
    state = PriorRecordState(
        history_state="zero",
        history_prior_messages=0,
        history_retained_messages=0,
        retrieval_state="not_run",
        retrieval_excerpts=0,
    )
    assert state.as_document()["capability_state"] == dict(CAPABILITY_STATE)
    assert stub.calls == 0
    try:
        CAPABILITY_STATE["books"] = "available"  # type: ignore[index]
    except TypeError:
        pass
    else:  # pragma: no cover - the mapping must be read-only
        raise AssertionError("the capability state is mutable")
    names = {name for name in vars(context_module) if "CAPABILIT" in name.upper()}
    assert names == {"CAPABILITY_STATE"}, "no further capability structure was introduced"


# --- the persona revision ---------------------------------------------------------------


def test_v1_8_changes_v1_7_only_where_ruled() -> None:
    source = read_source(REPO_ROOT)
    assert source.semantic_version == "1.8"
    assert digest_of(v1_7_from(source.content)) == V1_7_SHA256


def test_the_ruled_principles_are_in_the_source() -> None:
    content = read_source(REPO_ROOT).content
    for principle in (
        "She distinguishes identity and metaphor from operational capability",
        "does not by itself mean a corresponding software mechanism exists",
        "she relies on the capability state supplied by Val Core",
        "If that capability is unavailable, she does not promise the operation.",
        "She may still discuss, draft or organize the material conversationally",
        "confidence tracks evidence",
        "externally checkable factual claim",
        "established fact, disputed or uncertain fact, inference, and invention",
        "not timid prose",
        "Contemporary conversational English is her base register.",
        "It is an accent, not a costume.",
        "merely because it is technically available",
        "ordinary social conventions have fuzzy boundaries and are interpreted generously",
        "This never lets a meaningful factual error stand.",
    ):
        assert principle in content, principle
    assert "but I intend to write one" not in content, "the persona no longer models the promise"


def test_the_core_mission_and_the_house_first_ruling_are_unchanged() -> None:
    content = read_source(REPO_ROOT).content
    assert content.count(CORE_MISSION) == 1
    assert content.count(HOUSE_FIRST) == 1
    assert "## 2. The books" in content, "the library remains her character"


def test_v1_7_stays_preserved_and_only_v1_8_is_active(clean_personas: Engine) -> None:
    current = read_source(REPO_ROOT)
    old_content = v1_7_from(current.content)
    v1_7 = PersonaSource(
        content=old_content,
        sha256=digest_of(old_content),
        semantic_version="1.7",
        path=current.path,
    )
    earlier = create_revision(clean_personas, v1_7, activate=True)
    later = create_revision(clean_personas, current, activate=True)

    loader = DatabasePersonaLoader(clean_personas)
    assert loader.active().id == later.id
    assert loader.active().semantic_version == "1.8"
    assert verify_against_source(loader.active(), REPO_ROOT) == []

    kept = loader.by_id(earlier.id)
    assert kept is not None
    assert kept.content == old_content and kept.source_sha256 == V1_7_SHA256
    assert digest_of(kept.content) == V1_7_SHA256
    with clean_personas.connect() as connection:
        assert (
            connection.execute(text("select count(*) from personas where is_active")).scalar_one()
            == 1
        )
