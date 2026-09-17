"""The recall envelope byte bound, against its transmitting serializer — ruling, 13 September 2026.

Recall admission is governed by a conservative 16,000-byte limit over the exact
serialized recall envelope: in rank order, the envelope holding everything
already admitted plus the next whole candidate is serialized by
`val_gateway.context.recall_block` and its UTF-8 length compared with the limit.
Nothing is truncated, no provider is asked to count, and automatic recall and
House Recall share the one rule and the one envelope.

Every size here is measured on the real serializer, and the turn-level tests
measure the bytes the provider adapter was actually handed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from gateway_fakes import StubAdapter
from sqlalchemy import Engine
from test_conversation_memory import (
    ALPHA_SLUG,
    BETA_SLUG,
    build_gateway,
    catalogue,
    clean_personas,
    scope_of,
    seeded_conversation,
    store,
)

from val_domain.conversation import StoredRole
from val_domain.gateway import CacheTtl, Message, ModelConfig, TerminalState
from val_domain.project import ExplicitNoProject
from val_domain.provider import ProviderResult
from val_gateway.context import MEMORY_ENVELOPE_MARKER, STATE_ENVELOPE_MARKER, recall_block
from val_gateway.loop import Turn, send
from val_gateway.memory import (
    RecalledMessage,
    house_recall_with_state,
    recall_envelope_bytes,
    recall_with_state,
)
from val_policy.project_resolution import ProjectSignals
from val_policy.recall import RecallSelection, select_within_envelope
from val_policy.tokens import estimate_tokens

__all__ = ["clean_personas", "store"]

LIMIT = 16_000
REPO_ROOT = Path(__file__).resolve().parents[3]
SENT_AT = datetime(2026, 9, 12, 21, 4, tzinfo=UTC)

# --- the five kinds of material the ruling names ------------------------------------

PROSE = "The harbour lantern was relit at dusk, and the keeper wrote it in the log. "
DIALOGUE = 'MARGO: "Where did you put it?"\nDEV: "On the hook."\nMARGO: "Which hook?"\n'
SCREENPLAY = (
    "INT. KEEPER'S COTTAGE - NIGHT\n\n"
    "                         MARGO\n"
    "               (under her breath)\n"
    "          Where did you put the key?\n\n"
    "                         DEV\n"
    "          On the hook by the door.\n\n"
)
QUOTATION = 'She typed "C:\\\\logs\\\\keeper.txt" and wrote \\"done\\"\tthen "quoted" it.\n'
MULTIBYTE = "Café — naïve façade; 東京の灯台は夜に灯る 🌊🏮. "

KINDS = {
    "ordinary prose": PROSE,
    "dialogue-heavy": DIALOGUE,
    "screenplay-formatted": SCREENPLAY,
    "quotation-heavy and escaped": QUOTATION,
    "Unicode multibyte": MULTIBYTE,
}


def excerpt(content: str, number: int = 1, title: str = "Earlier conversation") -> RecalledMessage:
    return RecalledMessage(
        message_id=UUID(int=number),
        conversation_id=UUID(int=1_000 + number),
        conversation_title=title,
        project_id=None,
        role=StoredRole.USER,
        content=content,
        sequence=number,
        rank=1.0 / number,
        created_at=SENT_AT,
        retrieval_path="house_recall",
        sent_at=SENT_AT,
    )


def transmitted_bytes(items: Sequence[RecalledMessage]) -> int:
    """The envelope's size computed here, independently of the measure under test."""
    block = recall_block(tuple(items))
    assert block is not None
    return len(block.content.encode("utf-8"))


def exactly(unit: str, target: int, title: str = "Earlier conversation") -> str:
    """Content of `unit` repeated, padded with ASCII so its lone envelope is `target` bytes.

    JSON escaping is per character, so each repetition adds the same number of
    envelope bytes and each ASCII letter adds exactly one.
    """
    empty = transmitted_bytes([excerpt("", title=title)])
    per_unit = transmitted_bytes([excerpt(unit, title=title)]) - empty
    body = unit * ((target - empty) // per_unit)
    return body + "x" * (target - transmitted_bytes([excerpt(body, title=title)]))


def select(
    candidates: Sequence[RecalledMessage], admitted_before: Sequence[RecalledMessage] = ()
) -> RecallSelection:
    return select_within_envelope(
        candidates,
        limit_bytes=LIMIT,
        measure=recall_envelope_bytes,
        admitted_before=admitted_before,
    )


# --- the measure is the transmitting serializer --------------------------------------


@pytest.mark.parametrize("kind", list(KINDS))
def test_the_measure_is_the_serialized_envelope_for_every_kind_of_material(kind: str) -> None:
    items = [excerpt(KINDS[kind] * 40, 1), excerpt(KINDS[kind] * 7, 2)]
    assert recall_envelope_bytes(items) == transmitted_bytes(items)
    assert recall_envelope_bytes(items) > sum(len(i.content.encode("utf-8")) for i in items)
    assert recall_envelope_bytes([]) == 0


@pytest.mark.parametrize("kind", list(KINDS))
def test_an_envelope_of_exactly_the_limit_is_admitted_and_one_byte_more_is_not(kind: str) -> None:
    at_limit = exactly(KINDS[kind], LIMIT)
    assert transmitted_bytes([excerpt(at_limit)]) == LIMIT

    admitted = select([excerpt(at_limit)])
    assert admitted.admitted_positions == (1,)
    assert admitted.envelope_bytes == LIMIT

    over = select([excerpt(at_limit + "x")])
    assert over.admitted_positions == ()
    assert over.decisions[0].envelope_bytes == LIMIT + 1
    assert over.top_candidate_exceeded is True


def test_raw_content_that_fits_but_serializes_over_the_limit_is_not_admitted() -> None:
    """Quotation marks, backslashes, tabs and newlines each serialize to two bytes."""
    empty = transmitted_bytes([excerpt("")])
    content = '"\\\n\t' * ((LIMIT - empty - 100) // 4)
    raw = len(content.encode("utf-8"))
    assert raw + empty <= LIMIT, "the raw content plus the envelope's framing would fit"
    assert transmitted_bytes([excerpt(content)]) > LIMIT, "the serialized envelope does not"

    selection = select([excerpt(content)])
    assert selection.admitted_positions == ()
    assert selection.top_candidate_exceeded is True


def test_multibyte_characters_are_counted_in_bytes_not_characters() -> None:
    content = "灯" * 5_000  # 5,000 characters, 15,000 bytes
    assert len(content) + transmitted_bytes([excerpt("")]) < LIMIT
    assert select([excerpt(content)]).admitted_positions == ()


def test_several_small_excerpts_stop_at_the_one_that_crosses_the_limit() -> None:
    candidates = [excerpt(PROSE * 30, number) for number in range(1, 7)]
    crossing = next(
        n for n in range(1, 7) if transmitted_bytes(candidates[:n]) > LIMIT
    )  # computed independently
    selection = select(candidates)
    assert selection.admitted_positions == tuple(range(1, crossing))
    assert selection.envelope_bytes == transmitted_bytes(candidates[: crossing - 1]) <= LIMIT
    assert selection.decisions[crossing - 1].envelope_bytes == transmitted_bytes(
        candidates[:crossing]
    )
    assert "does not fit" in selection.decisions[crossing - 1].reason


def test_admitted_excerpts_are_whole_and_carry_their_provenance() -> None:
    candidates = [excerpt(DIALOGUE * 20, 1), excerpt(MULTIBYTE * 30, 2)]
    selection = select(candidates)
    admitted = [candidates[p - 1] for p in selection.admitted_positions]
    assert len(admitted) == 2
    block = recall_block(tuple(admitted))
    assert block is not None
    document = json.loads(block.content.split("\n", 1)[1])
    for sent, original in zip(document["excerpts"], admitted, strict=True):
        assert sent["content"] == original.content, "never truncated"
        assert sent["message_id"] == str(original.message_id)
        assert sent["conversation_id"] == str(original.conversation_id)
        assert sent["retrieval_path"] == "house_recall"
        assert sent["source_scope"] == "unassigned"
        assert sent["created_at"] == SENT_AT.isoformat()


def test_provenance_counts_against_the_limit() -> None:
    """The same content fits under a short title and not under a long one."""
    content = exactly(PROSE, LIMIT)
    assert select([excerpt(content)]).admitted_positions == (1,)
    assert (
        select([excerpt(content, title="Earlier conversation, continued")]).admitted_positions == ()
    )


def test_ranking_and_the_first_misfit_are_unchanged() -> None:
    """A large second candidate stops selection; the small third is not promoted."""
    ranked = [excerpt(PROSE * 10, 1), excerpt(SCREENPLAY * 200, 2), excerpt(PROSE, 3)]
    selection = select(ranked)
    assert selection.admitted_positions == (1,)
    assert "does not fit" in selection.decisions[1].reason
    assert "not considered" in selection.decisions[2].reason
    assert selection.decisions[2].envelope_bytes is None


# --- the 13 September 2026 opening turn, deterministically -----------------------------


def screenplay_of(length: int, anchor: str = "") -> str:
    body = anchor + SCREENPLAY * (length // len(SCREENPLAY) + 1)
    return body[:length]


#: The six House Recall candidates of the 13 September opening turn, in rank order,
#: at their recorded lengths: two 166-character questions from 12 September, then
#: a 38,987-character screenplay draft and three further drafts. Synthetic text of
#: the recorded shape — no House record is copied into the repository.
SEP_13_LENGTHS = (166, 166, 38_987, 20_923, 19_662, 788)


def sep_13_candidates() -> list[RecalledMessage]:
    small = [
        excerpt(("Question of 12 September about the harbour lantern schedule. " * 3)[:166], 1),
        excerpt(("A second 12 September question about the lantern log entries. " * 3)[:166], 2),
    ]
    drafts = [
        excerpt(screenplay_of(length), number)
        for number, length in enumerate(SEP_13_LENGTHS[2:], start=3)
    ]
    return [*small, *drafts]


def test_the_13_september_screenplay_is_not_admitted_under_the_byte_bound() -> None:
    candidates = sep_13_candidates()
    assert tuple(len(c.content) for c in candidates) == SEP_13_LENGTHS
    screenplay = candidates[2]
    assert estimate_tokens(screenplay.content) <= 16_000, (
        "the retired estimator admitted this draft; that is the defect being corrected"
    )

    selection = select(candidates)
    assert selection.admitted_positions == (1, 2), "the two small leading excerpts fit"
    assert selection.envelope_bytes == transmitted_bytes(candidates[:2]) <= LIMIT
    third = selection.decisions[2]
    assert not third.admitted and "does not fit" in third.reason
    assert third.envelope_bytes == transmitted_bytes(candidates[:3]) > LIMIT, (
        "the screenplay pushes the envelope over"
    )
    assert all("not considered" in d.reason for d in selection.decisions[3:])


class RecordingAdapter(StubAdapter):
    """Every request the provider boundary was handed, not only the most recent."""

    def __init__(self) -> None:
        super().__init__(ProviderResult("Noted, my lord.", TerminalState.COMPLETE, 20, 10, "req"))
        self.requests: list[tuple[Message, ...]] = []

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.requests.append(messages)
        return super().complete(
            config, messages, system, max_output_tokens, output_schema, cache_ttl
        )


def memory_envelopes(adapter: RecordingAdapter) -> list[Message]:
    return [
        message
        for request in adapter.requests
        for message in request
        if message.content.startswith(MEMORY_ENVELOPE_MARKER)
    ]


def state_of(adapter: RecordingAdapter) -> dict[str, object]:
    block = next(m for m in adapter.requests[-1] if m.content.startswith(STATE_ENVELOPE_MARKER))
    state: dict[str, object] = json.loads(block.content.split("\n", 1)[1])["prior_record_state"]
    return state


ASK_HOUSE = "What do you remember from our earlier conversations about the harbour lantern?"


def test_the_13_september_turn_sends_no_oversized_envelope_and_no_count_request(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """The recorded shape through the real turn path, House Recall from an unassigned turn.

    The two small questions name the harbour lantern four times each, the
    screenplay twice and the other drafts once, so full-text ranking places them
    in the recorded order; the selection log below confirms it.
    """
    lantern = "harbour lantern"
    small = [
        f"On 12 September: the {lantern}, the {lantern} log, the {lantern} keeper, the {lantern}?",
        f"Also 12 September: the {lantern} hours, {lantern} oil, {lantern} glass, {lantern} wick?",
    ]
    small = [text.ljust(166, ".") for text in small]
    drafts = [
        screenplay_of(38_987, f"{lantern}. {lantern}.\n"),
        screenplay_of(20_923, f"{lantern}.\n"),
        screenplay_of(19_662, f"{lantern}.\n"),
        screenplay_of(788, f"{lantern}.\n"),
    ]
    for index, content in enumerate([*drafts[::-1], *small]):
        seeded_conversation(store, ExplicitNoProject(), f"Seed {index}", (StoredRole.USER, content))

    adapter = RecordingAdapter()
    with caplog.at_level("INFO", logger="val.recall"):
        outcome = send(
            store,
            build_gateway(store, adapter),
            ASK_HOUSE,
            catalogue=catalogue(store),
            signals=ProjectSignals(explicit_no_project=True),
        )
    assert isinstance(outcome, Turn)

    lines = [r.getMessage() for r in caplog.records if "house recall selection" in r.getMessage()]
    assert len(lines) == 1
    logged = json.loads(lines[0].split("house recall selection: ", 1)[1])
    assert [c["characters"] for c in logged["candidates"][:3]] == [166, 166, 38_987]
    assert [c["admitted"] for c in logged["candidates"]] == [True, True, False, False, False, False]
    assert logged["candidates"][2]["envelope_bytes"] > LIMIT
    assert "does not fit" in logged["candidates"][2]["reason"]

    state = state_of(adapter)
    assert state["house_recall"] == {"state": "returned", "count": 2}

    envelopes = memory_envelopes(adapter)
    assert envelopes, "the admitted excerpts reached the provider"
    for envelope in envelopes:
        assert len(envelope.content.encode("utf-8")) <= LIMIT
    for request in adapter.requests:
        assert not any(drafts[0] in m.content for m in request), "the screenplay never left"

    # No provider count is requested: the boundary offers only completion, the
    # stub would fail on any other call, and no runtime source names a counting
    # endpoint.
    assert len(adapter.requests) == adapter.calls
    assert not hasattr(adapter, "count_tokens")


# Amended under the ruling of 16 September 2026 (local context preflight): no
# *provider* counting endpoint is named anywhere — the cloud byte bound and the
# recall envelope bound are unchanged — and exactly one module may count tokens:
# the read-only LM Studio inspector, which asks the already-loaded local
# runtime's own tokenizer for the exact serialised prompt before a local call.
# That is a measurement on this machine, not a provider request; nothing else
# on the turn path may name a counting call.
LOCAL_TOKENIZER_MODULE = Path("packages/providers/src/val_providers/lmstudio_inspector.py")


def test_no_runtime_source_names_a_provider_token_counting_endpoint() -> None:
    provider_endpoints = re.compile(r"count-tokens|messages/count|countTokens")
    any_count = re.compile(r"count_tokens")
    sources = [
        path for root in ("packages", "apps") for path in (REPO_ROOT / root).glob("*/src/**/*.py")
    ]
    endpoint_offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in sources
        if provider_endpoints.search(path.read_text(encoding="utf-8"))
    ]
    assert endpoint_offenders == []
    counting = {
        path.relative_to(REPO_ROOT)
        for path in sources
        if any_count.search(path.read_text(encoding="utf-8"))
    }
    assert counting == {LOCAL_TOKENIZER_MODULE}, "only the ruled local inspector counts"


# --- automatic recall and House Recall: one rule, one envelope -----------------------


def test_automatic_and_house_recall_admit_by_the_same_rule(store: Engine) -> None:
    for index in range(3):
        seeded_conversation(
            store,
            ExplicitNoProject(),
            f"Lantern {index}",
            (StoredRole.USER, f"harbour lantern {index} " + PROSE * 65),
        )
    automatic = recall_with_state(
        store, scope=ExplicitNoProject(), query="harbour lantern", byte_limit=LIMIT
    )
    house = house_recall_with_state(store, query="harbour lantern", byte_limit=LIMIT)
    assert automatic.state == house.state == "returned"
    assert [i.message_id for i in automatic.items] == [i.message_id for i in house.items]
    assert len(house.items) == 2, "the third whole excerpt would cross the limit"
    assert recall_envelope_bytes(automatic.items) <= LIMIT
    assert recall_envelope_bytes(house.items) <= LIMIT


def test_house_recall_admits_only_what_still_fits_after_automatic_recall(store: Engine) -> None:
    """Both paths' excerpts travel in one envelope, and the envelope is what is bounded."""
    alpha = scope_of(store, ALPHA_SLUG)
    beta = scope_of(store, BETA_SLUG)
    lens = "lighthouse lens colour"
    alpha_conversation = seeded_conversation(
        store, alpha, "Alpha lens", (StoredRole.USER, f"Alpha {lens}. " + PROSE * 110)
    )
    seeded_conversation(store, beta, "Beta lens", (StoredRole.USER, f"Beta {lens}. " + PROSE * 110))
    ask = f"What did we decide about the {lens} in our earlier conversations?"

    adapter = RecordingAdapter()
    outcome = send(
        store,
        build_gateway(store, adapter),
        ask,
        catalogue=catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )
    assert isinstance(outcome, Turn)
    state = state_of(adapter)
    assert state["retrieved_excerpts"]["state"] == "returned"  # type: ignore[index]
    assert state["house_recall"] == {
        "state": "zero",
        "count": 0,
        "detail": "top_candidate_exceeds_budget",
    }
    envelopes = memory_envelopes(adapter)
    assert envelopes
    for envelope in envelopes:
        assert len(envelope.content.encode("utf-8")) <= LIMIT
        assert "Beta lighthouse" not in envelope.content

    # Alone, with no automatic excerpt ahead of it, the same Beta excerpt fits — it
    # was excluded by the shared envelope, not by its own size.
    alone = house_recall_with_state(
        store, query=ask, exclude_conversation=alpha_conversation.id, byte_limit=LIMIT
    )
    assert alone.state == "returned"
    assert any(item.content.startswith("Beta lighthouse") for item in alone.items)


# --- configuration: the unit is in the name, and the retired name is refused ----------


def test_startup_refuses_the_retired_token_budget_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """A value chosen in estimated tokens must never silently govern a limit in bytes."""
    from val_gateway.memory import RECALL_ENVELOPE_SETTING, RETIRED_RECALL_BUDGET_SETTING
    from val_gateway.startup import recall_envelope_problems

    monkeypatch.delenv(RETIRED_RECALL_BUDGET_SETTING, raising=False)
    monkeypatch.delenv(RECALL_ENVELOPE_SETTING, raising=False)
    assert recall_envelope_problems() == []

    monkeypatch.setenv(RECALL_ENVELOPE_SETTING, "12000")
    assert recall_envelope_problems() == []

    monkeypatch.setenv(RETIRED_RECALL_BUDGET_SETTING, "16000")
    problems = recall_envelope_problems()
    assert len(problems) == 1
    assert RETIRED_RECALL_BUDGET_SETTING in problems[0] and "retired" in problems[0]

    monkeypatch.delenv(RETIRED_RECALL_BUDGET_SETTING)
    monkeypatch.setenv(RECALL_ENVELOPE_SETTING, "0")
    assert ["positive integer" in problem for problem in recall_envelope_problems()] == [True]


def test_the_service_does_not_start_while_the_retired_setting_is_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy import create_engine

    from val_gateway.memory import RETIRED_RECALL_BUDGET_SETTING
    from val_gateway.startup import StartupRefusedError, start

    monkeypatch.setenv(RETIRED_RECALL_BUDGET_SETTING, "16000")
    # Refused before the store is ever touched; the engine is never connected.
    engine = create_engine("postgresql+psycopg://refused.invalid/none")
    with pytest.raises(StartupRefusedError) as refused:
        start(engine)
    assert any(RETIRED_RECALL_BUDGET_SETTING in v for v in refused.value.reasons)
