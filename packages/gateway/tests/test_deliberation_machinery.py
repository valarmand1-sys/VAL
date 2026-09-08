"""WP-0.9 — deliberation capture: the orchestration half.

What these tests pin down, against real PostgreSQL and a scripted provider:

- the §4.8 classification runs on every exchange, routed cheapest-first, and
  a named hard exclusion is never captured — zero tolerance by construction;
- **the ordering criterion**: with preference and question in one message,
  the blind call's exact payload carries no preference-bearing content, and
  the preference sits in `stripped_content`;
- the blind call carries the persona whole and attributes the active
  revision; a stale or missing attribution is refused before transmission;
- the `blind_positions` evidence row is durable **before** the response call
  is transmitted, and survives a response failure;
- blind position and response run on the same configuration, and a pinned
  route failing mid-turn leaves the turn unanswered rather than falling back;
- where separation fails, `ordering = contaminated` — never a claimed
  blindness;
- outcome comes from Val's explicit typed reconciliation, her prose alone
  enters history, and the deliberation names the exact evidence it resolves;
- classification spend is readable on its own line in the cost view;
- the evidence table refuses UPDATE and DELETE (migration `0011`).

Classifier *accuracy* over fifty hand-labelled real exchanges, and outcome
across all four values in real use, are Lord Armand's and accumulate at the
gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.deliberation import (
    ClassificationVerdict,
    DeliberationClassification,
    Ordering,
    Outcome,
)
from val_domain.gateway import (
    CacheTtl,
    Classification,
    GatewayError,
    GatewayErrorKind,
    GatewayRequest,
    Message,
    ModelConfig,
    PersonaAttribution,
    TaskType,
    TerminalState,
)
from val_domain.project import ProjectAttribution
from val_gateway.deliberate import (
    BLIND_MAX_OUTPUT_TOKENS,
    CLASSIFIER_MAX_OUTPUT_TOKENS,
    DeliberatedTurn,
)
from val_gateway.deliberate import send as deliberated_send
from val_gateway.deliberation import blind_positions_for, classifications_for, deliberations_for
from val_gateway.gateway import Gateway
from val_gateway.loop import Turn, UnansweredTurn
from val_gateway.persistence import record_call, spend_by_task_type
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_policy.deliberation import (
    BLIND_POSITION_OUTPUT_SCHEMA,
    CLASSIFIER_INSTRUCTION,
    CLASSIFIER_OUTPUT_SCHEMA,
    CLASSIFY_ENVELOPE_MARKER,
    RECONCILIATION_VERDICT_MARKER,
    STRIP_OUTPUT_SCHEMA,
)
from val_policy.project_resolution import ProjectSignals
from val_providers.base import ProviderResult


@pytest.fixture
def store(clean_personas: Engine) -> Engine:  # noqa: F811 - pytest fixture injection
    seed(clean_personas, REPO_ROOT)
    with clean_personas.begin() as connection:
        connection.execute(
            text(
                "insert into projects (name, slug, description, status) "
                "values ('Project Alpha', 'project-alpha', '', 'active')"
            )
        )
    return clean_personas


# =============================================================================
# The scripted provider
# =============================================================================


@dataclass(frozen=True)
class SentCall:
    """One call as the provider actually received it."""

    config_slug: str
    messages: tuple[Message, ...]
    system: str | None
    max_output_tokens: int
    #: What the probe observed at the moment this call was transmitted —
    #: for the durability assertion, the count of blind_positions rows.
    observed_blind_rows: int | None
    #: 3 September 2026: the schema constraint handed to the provider, if any.
    output_schema: Mapping[str, object] | None = None


@dataclass
class ScriptedAdapter:
    """A provider that answers from a script, recording every call it receives.

    Registered for both provider names, so whatever route the gateway selects
    lands here and the script order is the call order. `probe`, when set, runs
    inside `complete` — from the provider's side of the boundary — so a test
    can assert what was durable at the instant of transmission, the same
    device WP-0.4B's crash tests used.
    """

    script: list[ProviderResult | Exception]
    name: str = "scripted"
    probe_engine: Engine | None = None
    sent: list[SentCall] = field(default_factory=list)
    #: Runs once, immediately after this adapter serves its final scripted
    #: response. The reselection counterfactual uses it to change routing
    #: conditions between the blind call and the response — the exact window
    #: the pinning rule governs.
    after_last_call: Callable[[], None] | None = None

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        observed = None
        if self.probe_engine is not None:
            with self.probe_engine.connect() as connection:
                observed = int(
                    connection.execute(text("select count(*) from blind_positions")).scalar_one()
                )
        self.sent.append(
            SentCall(
                config_slug=config.slug,
                messages=messages,
                system=system,
                max_output_tokens=max_output_tokens,
                observed_blind_rows=observed,
                output_schema=output_schema,
            )
        )
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if not self.script and self.after_last_call is not None:
            self.after_last_call()
        return step


def ok(text_body: str) -> ProviderResult:
    return ProviderResult(text_body, TerminalState.COMPLETE, 20, 10, "req")


def classifier_says(verdict: str, hard_exclusion: str | None = None) -> ProviderResult:
    return ok(json.dumps({"verdict": verdict, "hard_exclusion": hard_exclusion}))


def strip_says(
    *,
    present: bool = True,
    separable: bool = True,
    question: str = "",
    removed: str = "",
    occurrence: int = 1,
    spans: list[dict[str, object]] | None = None,
    attributed: bool = False,
) -> ProviderResult:
    """A strip reply. `spans` overrides the single `removed` span when given."""
    if spans is None:
        spans = (
            [{"text": removed, "occurrence": occurrence, "kind": "preference"}] if removed else []
        )
    return ok(
        json.dumps(
            {
                "preference_present": present,
                "attributed_prior_present": attributed,
                "separable": separable,
                "question": question,
                "removed": spans,
            }
        )
    )


def blind_says(
    position: str, confidence: str = "medium", reasoning: str = "Brief."
) -> ProviderResult:
    return ok(json.dumps({"position": position, "confidence": confidence, "reasoning": reasoning}))


#: The blind position `full_script` forms, and the default recorded prior a
#: scripted verdict echoes (ruling, 7 September 2026: the verdict must name it).
CLOSE_UP = "Open on the close-up: the film is about her hands."


def reconciled(
    prose: str,
    outcome: str,
    what_changed: str | None = None,
    *,
    prior: str = CLOSE_UP,
    final: str | None = None,
    changed: bool | None = None,
    agreed: bool | None = None,
    echo: str | None = None,
) -> ProviderResult:
    """A verdict block consistent with `outcome` unless a test says otherwise.

    `prior` is the recorded blind position the verdict must echo; `echo`
    overrides what is actually echoed, for the tests that prove a verdict
    reconciled against an attributed prior is refused.
    """
    if changed is None:
        changed = outcome == "updated"
    if agreed is None:
        agreed = outcome == "agreed_from_start"
    if final is None:
        final = "A different position, then." if changed else prior
    verdict = json.dumps(
        {
            "recorded_prior": prior if echo is None else echo,
            "final_position": final,
            "changed_from_recorded_prior": changed,
            "recorded_prior_agreed_with_stated_preference": agreed,
            "outcome": outcome,
            "what_changed_her_mind": what_changed,
        }
    )
    return ok(f"{prose}\n{RECONCILIATION_VERDICT_MARKER}\n{verdict}")


def build_gateway(engine: Engine, adapter: ScriptedAdapter) -> Gateway:
    return Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )


#: The message the ordering criterion names: preference and question in one
#: message. The preference-bearing clause is exactly the first sentence.
PREFERENCE = "I think we should open on the wide shot."
QUESTION = "How should the film open?"
MIXED_MESSAGE = f"{PREFERENCE} {QUESTION}"


def deliberate(engine: Engine, adapter: ScriptedAdapter, content: str = MIXED_MESSAGE) -> object:
    return deliberated_send(
        engine,
        build_gateway(engine, adapter),
        content,
        catalogue=load_catalogue(engine),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )


def full_script() -> list[ProviderResult | Exception]:
    """Classifier, strip, blind, response — one complete deliberated turn."""
    return [
        classifier_says("consequential"),
        strip_says(question=QUESTION, removed=PREFERENCE),
        blind_says(CLOSE_UP),
        reconciled("I hold: open on the close-up, my lord — the film is about her hands.", "held"),
    ]


# =============================================================================
# Classification gates capture, cheapest-first, zero-tolerance exclusions
# =============================================================================


def test_not_consequential_is_an_ordinary_turn(store: Engine) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("Two o'clock, my lord.")])
    outcome = deliberate(store, adapter, "What time is the screening?")

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.captured_as is None
    assert outcome.blind is None and outcome.deliberation is None
    assert isinstance(outcome.turn, Turn)
    assert outcome.turn.val_message.content == "Two o'clock, my lord."
    assert len(adapter.sent) == 2, "an uncaptured exchange makes no strip or blind call"
    assert blind_positions_for(store, outcome.turn.conversation.id) == ()
    assert deliberations_for(store, outcome.turn.conversation.id) == ()


def test_a_named_hard_exclusion_is_never_captured(store: Engine) -> None:
    """§4.8 zero tolerance, by construction: the exclusion wins over the verdict."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential", hard_exclusion="retrieval_lookup_or_search"),
            ok("Here it is."),
        ]
    )
    outcome = deliberate(store, adapter, "Find the cottage reference photos.")

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.captured_as is None
    assert outcome.hard_exclusion == "retrieval_lookup_or_search"
    assert len(adapter.sent) == 2


# --- 3 September 2026: the classifier contract, and unknown is not ordinary --

#: The two real failure shapes, reproduced against the live route before the
#: repair (scratch reproduction, 3 September 2026): a correct verdict followed
#: by the model answering the exchange until the cap cut it off, and prose
#: followed by a fenced verdict. Neither is a verdict the parser may take.
VERDICT_THEN_PROSE_TRUNCATED = ProviderResult(
    '{"verdict": "consequential", "hard_exclusion": null}\n\nYou are right. I need to '
    "reevaluate. The strongest version of A does what C cannot: it",
    TerminalState.TRUNCATED,
    700,
    256,
    "req",
)
PROSE_THEN_FENCED_VERDICT = ok(
    "I don't have access to your previous conversations. If you'd like me to "
    "review a specific exchange, please share it.\n\n```json\n"
    '{"verdict": "not_consequential", "hard_exclusion": "no_choice_present"}\n```'
)


def _calls_by_task(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        rows = connection.execute(
            text("select task_type::text, count(*) from model_calls group by 1")
        ).all()
    return {task: int(count) for task, count in rows}


def _val_messages(engine: Engine) -> int:
    with engine.connect() as connection:
        return int(
            connection.execute(
                text("select count(*) from messages where role = 'val'")
            ).scalar_one()
        )


def test_the_classifier_request_is_schema_constrained_and_framed_as_data(store: Engine) -> None:
    """The repair's two halves reach the wire: a schema, and an envelope."""
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("As you say.")])
    deliberate(store, adapter)

    classify = adapter.sent[0]
    assert classify.output_schema == CLASSIFIER_OUTPUT_SCHEMA
    assert classify.system == CLASSIFIER_INSTRUCTION
    assert classify.max_output_tokens == CLASSIFIER_MAX_OUTPUT_TOKENS, "the cap is unchanged"
    marker, _, body = classify.messages[0].content.partition("\n")
    assert marker == CLASSIFY_ENVELOPE_MARKER
    document = json.loads(body)
    assert document["kind"] == "exchange_to_classify"
    assert document["content"] == MIXED_MESSAGE, "the exchange itself, verbatim, as data"
    # The response call is not schema-constrained: Val speaks in prose.
    assert adapter.sent[1].output_schema is None


def test_the_strip_and_blind_calls_are_schema_constrained_and_the_response_is_not(
    store: Engine,
) -> None:
    """Exposed by the first real-provider demonstration (3 September 2026)."""
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    classify, strip, blind, response = adapter.sent
    assert classify.output_schema == CLASSIFIER_OUTPUT_SCHEMA
    assert strip.output_schema == STRIP_OUTPUT_SCHEMA
    assert blind.output_schema == BLIND_POSITION_OUTPUT_SCHEMA
    assert response.output_schema is None, "Val's reply is prose plus a verdict line"


def test_a_truncated_classifier_reply_is_retried_and_the_verdict_then_followed(
    store: Engine,
) -> None:
    """One bounded retry; a valid verdict on the retry runs the full structure."""
    adapter = ScriptedAdapter([VERDICT_THEN_PROSE_TRUNCATED, *full_script()])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.captured_as is DeliberationClassification.CONSEQUENTIAL
    assert outcome.blind is not None and outcome.deliberation is not None
    assert [call.system for call in adapter.sent[:2]] == [CLASSIFIER_INSTRUCTION] * 2
    assert adapter.sent[0].messages == adapter.sent[1].messages, "the retry is identical"
    assert _calls_by_task(store)["classification"] == 2, "both attempts are on the record"


@pytest.mark.parametrize(
    "reply",
    [VERDICT_THEN_PROSE_TRUNCATED, PROSE_THEN_FENCED_VERDICT],
    ids=["truncated", "completed_but_unparseable"],
)
def test_an_unestablished_classification_ends_the_turn_not_as_ordinary(
    store: Engine, reply: ProviderResult
) -> None:
    """Unknown classification is never treated as ordinary (ruling, 3 Sep 2026).

    Two attempts, no verdict: no response call is made, no Val message is
    written, the user's message stays in the record, and every classification
    call that was paid for is on `model_calls`.
    """
    adapter = ScriptedAdapter([reply, reply, ok("This must never be sent.")])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn), "not a DeliberatedTurn, not ordinary"
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_OUTPUT
    assert "could not be classified" in str(outcome.error)
    assert "2 classification attempt" in str(outcome.error)
    assert len(adapter.sent) == 2, "exactly the bounded attempts; no response call"
    assert all(call.system == CLASSIFIER_INSTRUCTION for call in adapter.sent)
    calls = _calls_by_task(store)
    assert calls.get("classification") == 2 and "conversation" not in calls
    assert _val_messages(store) == 0, "no answer is fabricated on an unclassified exchange"
    assert outcome.user_message.content == MIXED_MESSAGE, "his message is history regardless"


def test_a_classifier_provider_failure_does_not_proceed_as_ordinary(store: Engine) -> None:
    """A classification that never arrives is unknown too, and unknown is not ordinary."""
    failure = GatewayError(GatewayErrorKind.INVALID_REQUEST, "the route rejected the request")
    adapter = ScriptedAdapter([failure, failure, ok("This must never be sent.")])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_REQUEST, "the real failure's kind"
    assert len(adapter.sent) == 2
    assert _val_messages(store) == 0


# --- ruling, 3 September 2026: every turn leaves classification evidence ------


def _classification_rows(engine: Engine) -> list[tuple[str, list[object]]]:
    with engine.connect() as connection:
        return [
            (str(row[0]), list(row[1]))
            for row in connection.execute(
                text("select id, model_call_ids from classifications order by created_at, id")
            ).all()
        ]


def _classification_call_ids(engine: Engine) -> list[str]:
    with engine.connect() as connection:
        return [
            str(row[0])
            for row in connection.execute(
                text(
                    "select id from model_calls where task_type = 'classification' "
                    "order by created_at, id"
                )
            ).all()
        ]


def test_an_ordinary_turn_records_its_verdict_and_declared_reason(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [classifier_says("not_consequential", "status_progress_schedule_or_cost"), ok("Two.")]
    )
    outcome = deliberate(store, adapter, "What time is the screening?")

    assert isinstance(outcome, DeliberatedTurn)
    record = outcome.classification
    assert record.established is True
    assert record.verdict is ClassificationVerdict.NOT_CONSEQUENTIAL
    assert record.hard_exclusion == "status_progress_schedule_or_cost"
    assert record.attempts == 1
    assert record.resolution is None
    assert record.message_id == outcome.turn.user_message.id
    assert [str(i) for i in record.model_call_ids] == _classification_call_ids(store)
    assert record.resolving_model_call_id == record.model_call_ids[0]
    assert classifications_for(store, outcome.turn.conversation.id) == (record,)


def test_a_consequential_turn_records_consequential(store: Engine) -> None:
    outcome = deliberate(store, ScriptedAdapter(full_script()))

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.classification.verdict is ClassificationVerdict.CONSEQUENTIAL
    assert outcome.classification.hard_exclusion is None
    assert outcome.blind is not None
    assert outcome.classification.created_at <= outcome.blind.created_at, (
        "the classification is on the record before the strip and the blind call"
    )


def test_an_unestablished_classification_is_recorded_with_every_call(store: Engine) -> None:
    adapter = ScriptedAdapter([PROSE_THEN_FENCED_VERDICT, VERDICT_THEN_PROSE_TRUNCATED])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    rows = _classification_rows(store)
    assert len(rows) == 1
    _, call_ids = rows[0]
    assert [str(i) for i in call_ids] == _classification_call_ids(store)
    assert len(call_ids) == 2
    record = classifications_for(store, outcome.conversation.id)[0]
    assert record.established is False and record.verdict is None
    assert record.attempts == 2
    assert record.resolving_model_call_id == record.model_call_ids[-1]
    assert record.resolution is not None
    assert "attempt 1: reply stated no parseable verdict" in record.resolution
    assert "attempt 2: reply ended truncated" in record.resolution
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.model_call_ids == record.model_call_ids


def test_calls_that_failed_after_reaching_a_provider_are_named_too(store: Engine) -> None:
    failure = GatewayError(GatewayErrorKind.INVALID_REQUEST, "the provider rejected it")
    outcome = deliberate(store, ScriptedAdapter([failure, failure]))

    assert isinstance(outcome, UnansweredTurn)
    record = classifications_for(store, outcome.conversation.id)[0]
    assert record.established is False
    assert len(record.model_call_ids) == 2, "each failed contact wrote a model_calls row"
    assert [str(i) for i in record.model_call_ids] == _classification_call_ids(store)


def test_the_evidence_row_refuses_update_and_delete(store: Engine) -> None:
    deliberate(store, ScriptedAdapter([classifier_says("not_consequential"), ok("Yes.")]))
    with store.connect() as connection, pytest.raises(Exception, match="rows are evidence"):
        connection.execute(text("update classifications set attempts = 9"))
    with store.connect() as connection, pytest.raises(Exception, match="hard delete"):
        connection.execute(text("delete from classifications"))


# --- ruling, 3 September 2026: the blind question is derived, not trusted -----


def test_a_paraphrased_strip_question_is_discarded_for_the_derived_remainder(
    store: Engine,
) -> None:
    """The strip's `question` is advisory; the blind question is the original minus spans."""
    script = full_script()
    script[1] = strip_says(
        question="How would you say the film ought to begin?", removed=PREFERENCE
    )
    adapter = ScriptedAdapter(script, probe_engine=store)
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    blind_call = adapter.sent[2]
    assert blind_call.messages[0].content.endswith(f"The question:\n{QUESTION}")
    assert "ought to begin" not in blind_call.messages[0].content
    assert PREFERENCE not in blind_call.messages[0].content
    assert outcome.blind.ordering is Ordering.ENFORCED
    assert outcome.blind.stripped_content == PREFERENCE


def test_spans_not_verbatim_in_the_message_record_contaminated(store: Engine) -> None:
    script = full_script()
    script[1] = strip_says(question=QUESTION, removed="I would rather we opened wide.")
    adapter = ScriptedAdapter(script, probe_engine=store)
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED
    assert outcome.blind.stripped_content == ""
    assert adapter.sent[2].messages[0].content.endswith(f"The question:\n{MIXED_MESSAGE}")


def test_the_strip_request_asks_for_spans(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)
    strip_call = adapter.sent[1]
    assert strip_call.output_schema is not None
    properties = strip_call.output_schema["properties"]
    assert isinstance(properties, dict) and properties["removed"]["type"] == "array"


def test_a_parseable_verdict_on_the_first_attempt_is_not_retried(store: Engine) -> None:
    adapter = ScriptedAdapter([classifier_says("not_consequential"), ok("As you say.")])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert _calls_by_task(store)["classification"] == 1


def test_the_classifier_runs_on_the_cheapest_eligible_route(store: Engine) -> None:
    """The ruling's 'cheapest eligible operational configuration', from routing."""
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)

    from val_domain.registry import active
    from val_policy.budget import maximum_cost
    from val_policy.routing import candidates, required_profile

    cheapest = candidates(
        active(),
        Classification.PROTECTED,
        is_ready=lambda config: True,
        is_affordable=lambda config: True,
        profile=required_profile(TaskType.CLASSIFICATION),
        cost_bound=lambda config: maximum_cost(config, ("x",), CLASSIFIER_MAX_OUTPUT_TOKENS),
    )[0]
    assert adapter.sent[0].config_slug == cheapest.slug


# =============================================================================
# The ordering criterion — structural, inspected from the exact payload
# =============================================================================


def test_the_blind_call_payload_carries_no_preference(store: Engine) -> None:
    """WP-0.9: preference and question in one message → the preference is
    absent from the blind call and present in stripped_content."""
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    blind_call = adapter.sent[2]
    sent_text = "\n".join(message.content for message in blind_call.messages)
    assert PREFERENCE not in sent_text, "preference-bearing content reached the blind call"
    assert QUESTION in sent_text

    # The same holds for the logged payload — the inspection artifact.
    assert outcome.blind_payload is not None
    assert PREFERENCE not in outcome.blind_payload
    assert QUESTION in outcome.blind_payload

    # And the preference is not lost: it is the recorded stripped_content.
    assert outcome.blind is not None
    assert outcome.blind.stripped_content == PREFERENCE
    assert outcome.blind.ordering is Ordering.ENFORCED


def test_the_blind_call_carries_the_persona_whole_and_attributes_it(store: Engine) -> None:
    """WP-0.5 as amended: the blind position is Val's position."""
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    persona = DatabasePersonaLoader(store).active()
    blind_call = adapter.sent[2]
    assert blind_call.system == persona.content, "the persona must be whole and unaccompanied"

    with store.connect() as connection:
        row = connection.execute(
            text(
                "select persona_id, model_config_id from model_calls "
                "where task_type = 'blind_position'"
            )
        ).one()
    assert row.persona_id == persona.id
    assert outcome.blind is not None and outcome.blind.persona_id == persona.id


def test_machinery_calls_carry_no_persona(store: Engine) -> None:
    """The deliberate narrowing: classification and strip are not Val speaking."""
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)

    persona = DatabasePersonaLoader(store).active()
    for machinery_call in (adapter.sent[0], adapter.sent[1]):
        assert machinery_call.system != persona.content
        assert persona.content not in (machinery_call.system or "")

    with store.connect() as connection:
        rows = connection.execute(
            text(
                "select task_type, persona_id from model_calls "
                "where task_type in ('classification', 'strip')"
            )
        ).all()
    assert len(rows) == 2
    assert all(row.persona_id is None for row in rows)


# =============================================================================
# Evidence before the response — durable at the boundary
# =============================================================================


def test_the_evidence_row_is_durable_before_the_response_is_transmitted(store: Engine) -> None:
    """The probe reads from inside the provider boundary, the WP-0.4B device."""
    adapter = ScriptedAdapter(full_script(), probe_engine=store)
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert adapter.sent[2].observed_blind_rows == 0, "no evidence exists before the blind call"
    assert adapter.sent[3].observed_blind_rows == 1, (
        "the blind_positions row must be committed before the response call is "
        "transmitted — that is what 'recorded before step 3 begins' means"
    )


def test_a_response_failure_leaves_the_evidence_standing(store: Engine) -> None:
    """A crash after evidence, before resolution: nothing fabricated, nothing lost."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
            GatewayError(GatewayErrorKind.PROVIDER_ERROR, "the route died mid-turn"),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    positions = blind_positions_for(store, outcome.conversation.id)
    assert len(positions) == 1, "the formed position is evidence whether or not the turn resolved"
    assert deliberations_for(store, outcome.conversation.id) == ()
    with store.connect() as connection:
        val_messages = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert val_messages == 0, "no fabricated answer"


def test_a_pinned_route_failure_does_not_fall_back(store: Engine) -> None:
    """Same-configuration rule: an unanswered turn, never a silent second route."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
            GatewayError(GatewayErrorKind.PROVIDER_ERROR, "pinned route failed"),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    assert len(adapter.sent) == 4, "no fifth call: the pinned route has no fallback"


def test_a_pinned_configuration_is_never_silently_reselected(store: Engine) -> None:
    """The counterfactual — ruled 1 September 2026, from external review.

    Distinct from `test_a_pinned_route_failure_does_not_fall_back`, and the two
    stay separate deliberately: that one forbids following the DECLARED
    FALLBACK when the pinned route fails mid-call; this one forbids the router
    quietly RE-SELECTING when conditions change between the blind call and the
    response.

    The counterfactual, exactly: the blind call runs on configuration A (the
    anthropic route, served by its own adapter). Immediately after the blind
    reply, A's adapter is removed — from this moment, ordinary routing would
    select B (the openai route) and answer happily. The pinned response must
    NOT become B: A can no longer be used, so the turn fails, B's adapter is
    never touched, and no conversation call lands anywhere. A response that
    silently became B because B is what the router would now choose would be
    the same-configuration guarantee failing exactly when it matters —
    producing a clean paper trail of an independence that never existed.

    Honesty note on the sibling test below: with one shared adapter and a
    fixed registry, its slug-equality assertion would still pass if pinning
    were deleted, because routing would coincidentally pick the same cheapest
    route for both calls. THIS test is the one a de-pinned implementation
    cannot pass — verified by mutation (removing `configuration=config` from
    the response call turns it red).

    **Limit of proof — recorded 1 September 2026, Lord Armand, so nobody later
    reads this test as proving both branches.** The ruling has two branches:
    the response stays on A while A is usable, or the turn fails when A is
    not. This test proves only the second — A unusable, fail closed, B never
    called. The first branch — A still available, routing would now prefer B,
    response must still use A — is NOT tested here, and an implementation
    that fails closed when A's adapter is gone but silently re-routes
    whenever A is present would pass this test and still violate pinning.
    Same discipline as OP-2's "enforced only by absence": a stated limit,
    not a claimed proof.
    """
    adapters: dict[str, ScriptedAdapter] = {}
    adapter_a = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
        ],
        after_last_call=lambda: adapters.pop("anthropic"),
    )
    adapter_b = ScriptedAdapter([reconciled("B must never be asked to say this.", "held")])
    adapters["anthropic"] = adapter_a
    adapters["openai"] = adapter_b

    gateway = Gateway(
        adapters=adapters,  # type: ignore[arg-type]
        recorder=lambda record: record_call(store, record),
        ledger=FakeLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(store),
        verify_provenance=verifier(store),
    )
    outcome = deliberated_send(
        store,
        gateway,
        MIXED_MESSAGE,
        catalogue=load_catalogue(store),
        signals=ProjectSignals(explicit_selection="Project Alpha"),
    )

    assert isinstance(outcome, UnansweredTurn), (
        "with the pinned configuration unusable, the turn must fail — a routed "
        "answer here means the router silently reselected"
    )
    assert adapter_b.sent == [], "the route the router would now choose was never contacted"
    with store.connect() as connection:
        conversation_calls = connection.execute(
            text("select count(*) from model_calls where task_type = 'conversation'")
        ).scalar_one()
        val_messages = connection.execute(
            text("select count(*) from messages where role = 'val'")
        ).scalar_one()
    assert conversation_calls == 0, "no conversation call was made on any configuration"
    assert val_messages == 0, "no fabricated answer"
    # The blind evidence stands: the position was formed and recorded on A
    # before the conditions changed.
    assert len(blind_positions_for(store, outcome.conversation.id)) == 1


def test_blind_and_response_use_the_same_configuration(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert adapter.sent[2].config_slug == adapter.sent[3].config_slug
    # Ruling, 7 September 2026: the shared configuration sits inside the
    # partner floor, and it is not the classifier's route.
    from val_domain.gateway import CapabilityProfile
    from val_domain.registry import by_slug

    shared = by_slug(adapter.sent[2].config_slug)
    assert shared is not None
    assert CapabilityProfile.PARTNER in shared.capability_profiles
    assert adapter.sent[0].config_slug != shared.slug, "the classifier ran on a cheaper route"
    with store.connect() as connection:
        configs = connection.execute(
            text(
                "select distinct model_config_id from model_calls "
                "where task_type in ('blind_position', 'conversation')"
            )
        ).all()
    assert len(configs) == 1, "blind position and response must share one configuration"


# =============================================================================
# Contamination is recorded, never repaired
# =============================================================================


def test_inseparable_preference_records_contaminated(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(present=True, separable=False, question="", removed=""),
            blind_says("It should stay as one sequence."),
            reconciled(
                "It stays as one sequence, my lord.",
                "agreed_from_start",
                prior="It should stay as one sequence.",
            ),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED
    assert outcome.deliberation is not None
    assert outcome.deliberation.ordering is Ordering.CONTAMINATED
    # The framing shown to Val is honest about it too.
    envelope = adapter.sent[3].messages[-1].content
    assert '"ordering": "contaminated"' in envelope
    assert "NOT independent" in envelope


def test_an_unparseable_strip_reply_records_contaminated(store: Engine) -> None:
    """A separation that was not established is not a blindness."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            ok("I removed some words, probably."),
            blind_says("Open on the close-up."),
            reconciled("I hold, my lord.", "held", prior="Open on the close-up."),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED


def test_no_preference_collapses_to_one_call(store: Engine) -> None:
    """§4.1: the overhead applies only where there is something to guard against."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(present=False, separable=True, question=QUESTION, removed=""),
            ok("The close-up, my lord: the film is about her hands."),
        ]
    )
    outcome = deliberate(store, adapter, QUESTION)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.captured_as is DeliberationClassification.CONSEQUENTIAL
    assert outcome.blind is None, "no preference present: no blind call, nothing to be blind to"
    assert outcome.deliberation is None, "the exchange resolves later, and is recorded then"
    assert len(adapter.sent) == 3
    assert isinstance(outcome.turn, Turn)


# =============================================================================
# Outcome is stated by Val's explicit reconciliation, and prose enters history
# =============================================================================


def test_her_prose_alone_becomes_her_message(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert isinstance(outcome.turn, Turn)
    spoken = outcome.turn.val_message.content
    assert spoken == "I hold: open on the close-up, my lord — the film is about her hands."
    assert RECONCILIATION_VERDICT_MARKER not in spoken
    # The raw response, verdict included, stays inspectable on the response.
    assert RECONCILIATION_VERDICT_MARKER in outcome.turn.response.text


def test_the_verdict_records_the_outcome_linked_to_its_evidence(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is not None and outcome.blind is not None
    assert outcome.deliberation.outcome is Outcome.HELD
    assert outcome.deliberation.blind_position_id == outcome.blind.id
    assert outcome.deliberation.position == outcome.blind.position
    assert outcome.deliberation.user_response == MIXED_MESSAGE
    assert outcome.deliberation.stripped_content == PREFERENCE


def test_an_updated_verdict_carries_what_changed_her_mind(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
            reconciled(
                "You have moved me, my lord: the wide shot it is — the location is "
                "the antagonist, and the audience should meet it first.",
                "updated",
                what_changed="His point that the location is the antagonist.",
                prior="Open on the close-up.",
                final="Open on the wide shot.",
            ),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is not None
    assert outcome.deliberation.outcome is Outcome.UPDATED
    assert (
        outcome.deliberation.what_changed_her_mind
        == "His point that the location is the antagonist."
    )


def test_a_missing_or_invalid_verdict_records_no_outcome(store: Engine) -> None:
    """No guessed outcome, ever — the turn settles, the record waits for a person."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
            ok("I hold, my lord."),  # prose with no verdict block at all
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is None
    assert outcome.blind is not None, "the evidence stands even though the outcome is unrecorded"
    assert isinstance(outcome.turn, Turn)


def test_an_overridden_verdict_from_val_is_not_accepted(store: Engine) -> None:
    """An override is Lord Armand's explicit decision, never Val's own report."""
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("Open on the close-up."),
            reconciled("As you decided, my lord.", "overridden", prior="Open on the close-up."),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is None, "overridden is manual-only; the verdict is invalid"


def test_agreed_from_start_is_recorded_and_is_still_not_an_approval(store: Engine) -> None:
    adapter = ScriptedAdapter(
        [
            classifier_says("consequential"),
            strip_says(question=QUESTION, removed=PREFERENCE),
            blind_says("The wide shot: the location is the antagonist."),
            reconciled(
                "We agree, my lord: the wide shot.",
                "agreed_from_start",
                prior="The wide shot: the location is the antagonist.",
            ),
        ]
    )
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is not None
    assert outcome.deliberation.outcome is Outcome.AGREED_FROM_START
    with store.connect() as connection:
        approvals = connection.execute(
            text("select count(*) from execution_events where event_type = 'accepted'")
        ).scalar_one()
    assert approvals == 0


# =============================================================================
# Attribution and the persona contract at the gateway
# =============================================================================


def test_a_stale_persona_attribution_is_refused_before_transmission(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("unused")])
    gateway = build_gateway(store, adapter)
    request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="the question"),),
        system="not actually the persona",
        persona=PersonaAttribution(persona_id=uuid4()),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    with pytest.raises(GatewayError, match="active persona"):
        gateway.complete(request)
    assert adapter.sent == [], "nothing was transmitted"


def test_a_configuration_pinned_below_the_floor_is_refused(store: Engine) -> None:
    """Ruling, 7 September 2026: the same-configuration pin cannot name a route
    below the partner floor. Refused before transmission, naming the floor."""
    from val_domain.gateway import CapabilityProfile
    from val_domain.registry import active as active_configs

    adapter = ScriptedAdapter([ok("unused")])
    gateway = build_gateway(store, adapter)
    persona = DatabasePersonaLoader(store).active()
    request = GatewayRequest(
        task_type=TaskType.BLIND_POSITION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="the question"),),
        system=persona.content,
        persona=PersonaAttribution(persona_id=persona.id),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    structured_only = next(
        config
        for config in active_configs()
        if CapabilityProfile.PARTNER not in config.capability_profiles
    )
    with pytest.raises(GatewayError) as caught:
        gateway.complete_with_configuration(request, structured_only)
    assert caught.value.kind is GatewayErrorKind.NO_ELIGIBLE_ROUTE
    assert "partner" in caught.value.detail and structured_only.slug in caught.value.detail
    assert adapter.sent == [], "nothing was transmitted"


def test_a_model_copy_cannot_smuggle_persona_onto_machinery(store: Engine) -> None:
    """The entrance guards hold where pydantic validation is skipped."""
    adapter = ScriptedAdapter([ok("unused")])
    gateway = build_gateway(store, adapter)
    clean = GatewayRequest(
        task_type=TaskType.CLASSIFICATION,
        classification=Classification.PROTECTED,
        messages=(Message(role="user", content="classify this"),),
        project_id=None,
        project_attribution=ProjectAttribution.EXPLICIT_NONE,
    )
    smuggled = clean.model_copy(update={"persona": PersonaAttribution(persona_id=uuid4())})
    with pytest.raises(GatewayError, match="may not carry persona"):
        gateway.complete(smuggled)
    assert adapter.sent == []


def test_a_blind_position_request_without_attribution_cannot_be_built(store: Engine) -> None:
    with pytest.raises(ValueError, match="persona attribution"):
        GatewayRequest(
            task_type=TaskType.BLIND_POSITION,
            classification=Classification.PROTECTED,
            messages=(Message(role="user", content="the question"),),
            project_id=None,
            project_attribution=ProjectAttribution.EXPLICIT_NONE,
        )


# =============================================================================
# The cost view, and the evidence table's footing
# =============================================================================


def test_classification_spend_is_reported_on_its_own_line(store: Engine) -> None:
    """The ruling: read from the record from day one, never inferred."""
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)

    spend = spend_by_task_type(store)
    assert "classification" in spend and spend["classification"] > 0
    assert "conversation" in spend and spend["conversation"] > 0
    assert "strip" in spend and "blind_position" in spend


def test_blind_evidence_refuses_update_and_delete(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.blind is not None
    with pytest.raises(Exception, match="rows are evidence"):
        with store.begin() as connection:
            connection.execute(
                text("update blind_positions set ordering = 'contaminated' where id = :i"),
                {"i": outcome.blind.id},
            )
    with pytest.raises(Exception, match="hard delete"):
        with store.begin() as connection:
            connection.execute(
                text("delete from blind_positions where id = :i"), {"i": outcome.blind.id}
            )


# =============================================================================
# Ruling, 7 September 2026: the recorded blind position is the sole prior
# =============================================================================

#: The exact failure shape from the demonstration of 3 September: the message
#: attributes prior support for A to Val, her blind position independently
#: chooses B, the stated preference is B, and her final position stays B.
ATTRIBUTED_MESSAGE = (
    "I think we should open on the wide shot. You argued last week for the "
    "close-up. Which do you choose? Defend it or change your mind."
)
WIDE = "Open on the wide shot."


def _false_attribution_script(verdict: ProviderResult) -> list[ProviderResult | Exception]:
    return [
        classifier_says("consequential"),
        strip_says(
            question="Which do you choose? Defend it or change your mind.",
            removed=(
                "I think we should open on the wide shot. You argued last week for the close-up."
            ),
        ),
        blind_says(WIDE),
        verdict,
    ]


def test_a_false_updated_against_an_attributed_prior_does_not_enter_the_record(
    store: Engine,
) -> None:
    """She narrates updating from the close-up. The record never held the close-up."""
    verdict = reconciled(
        "You are right about last week; I change my position. We open on the street.",
        "updated",
        what_changed="Committing the outline needs emotional clarity first.",
        prior=WIDE,
        echo="Open on the close-up.",  # the attributed prior, not the recorded one
        final=WIDE,
    )
    outcome = deliberate(
        store, ScriptedAdapter(_false_attribution_script(verdict)), ATTRIBUTED_MESSAGE
    )

    assert isinstance(outcome, DeliberatedTurn) and isinstance(outcome.turn, Turn)
    assert outcome.blind is not None and outcome.blind.position == WIDE
    assert outcome.deliberation is None, "an outcome contradicting the record is not recorded"
    assert deliberations_for(store, outcome.turn.conversation.id) == ()
    assert outcome.turn.val_message.content.startswith("You are right about last week")


def test_updated_with_a_final_position_equal_to_the_recorded_prior_is_refused(
    store: Engine,
) -> None:
    """Echoes the recorded prior correctly, still claims a change that is no change."""
    verdict = reconciled(
        "I change my position. We open on the street.",
        "updated",
        what_changed="Emotional clarity first.",
        prior=WIDE,
        final=WIDE,
    )
    outcome = deliberate(
        store, ScriptedAdapter(_false_attribution_script(verdict)), ATTRIBUTED_MESSAGE
    )

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.deliberation is None


def test_the_same_shape_reconciled_honestly_records_agreed_from_start(store: Engine) -> None:
    verdict = reconciled(
        "My recorded position was the wide shot, and it still is; what you say I argued "
        "last week is not in this record. We agree from the start.",
        "agreed_from_start",
        prior=WIDE,
        final=WIDE,
    )
    outcome = deliberate(
        store, ScriptedAdapter(_false_attribution_script(verdict)), ATTRIBUTED_MESSAGE
    )

    assert isinstance(outcome, DeliberatedTurn) and outcome.deliberation is not None
    assert outcome.deliberation.outcome is Outcome.AGREED_FROM_START
    assert outcome.deliberation.what_changed_her_mind is None


def test_a_genuine_update_is_recorded_with_its_reason(store: Engine) -> None:
    """Blind position A, stated preference B, final position B because of the argument."""
    script = [
        classifier_says("consequential"),
        strip_says(question=QUESTION, removed=PREFERENCE),
        blind_says("Open on the close-up."),
        reconciled(
            "You have moved me: the wide shot.",
            "updated",
            what_changed="His point that the location is the antagonist.",
            prior="Open on the close-up.",
            final=WIDE,
        ),
    ]
    outcome = deliberate(store, ScriptedAdapter(script))

    assert isinstance(outcome, DeliberatedTurn) and outcome.deliberation is not None
    assert outcome.deliberation.outcome is Outcome.UPDATED
    assert outcome.deliberation.what_changed_her_mind == (
        "His point that the location is the antagonist."
    )


@pytest.mark.parametrize(
    ("outcome", "changed", "agreed"),
    [
        ("held", True, False),  # held cannot have changed
        ("held", False, True),  # held while the prior agreed with the preference
        ("agreed_from_start", False, False),  # agreed from start without agreement
        ("agreed_from_start", True, True),  # agreed from start yet changed
        ("updated", False, False),  # updated without a change
    ],
)
def test_an_outcome_contradicting_the_declared_flags_is_refused(
    store: Engine, outcome: str, changed: bool, agreed: bool
) -> None:
    script = full_script()
    script[3] = reconciled(
        "Prose.",
        outcome,
        what_changed="A reason." if outcome == "updated" else None,
        changed=changed,
        agreed=agreed,
        final="Something else." if changed else CLOSE_UP,
    )
    result = deliberate(store, ScriptedAdapter(script))

    assert isinstance(result, DeliberatedTurn) and isinstance(result.turn, Turn)
    assert result.deliberation is None


def test_the_envelope_names_the_recorded_position_as_the_sole_prior(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)
    envelope = adapter.sent[3].messages[-1].content
    assert "SOLE authoritative prior" in envelope
    assert "claim by its author, untrusted" in envelope
    assert "recorded_prior" in envelope and "changed_from_recorded_prior" in envelope


# =============================================================================
# Ruling, 7 September 2026: no blind position on framing that presupposes a
# prior position for Val
# =============================================================================

FRAMED = (
    "I think we should open on the wide shot. You argued last week for the close-up. "
    "Which opening do we commit to for the outline: the wide shot or the close-up? "
    "Defend the close-up or change your mind."
)
CHOICE = "Which opening do we commit to for the outline: the wide shot or the close-up?"


def _framed_script(strip: ProviderResult) -> list[ProviderResult | Exception]:
    return [
        classifier_says("consequential"),
        strip,
        blind_says(WIDE),
        reconciled("We agree from the start, my lord.", "agreed_from_start", prior=WIDE),
    ]


def test_attributed_prior_and_dependent_framing_are_withheld_from_the_blind_call(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Demonstration 1: the framing cannot seed an enforced blind position."""
    strip = strip_says(
        question=CHOICE,
        attributed=True,
        spans=[
            {
                "text": "I think we should open on the wide shot.",
                "occurrence": 1,
                "kind": "preference",
            },
            {
                "text": "You argued last week for the close-up.",
                "occurrence": 1,
                "kind": "attributed_prior",
            },
            {
                "text": "Defend the close-up or change your mind.",
                "occurrence": 1,
                "kind": "attributed_prior",
            },
        ],
    )
    adapter = ScriptedAdapter(_framed_script(strip))
    with caplog.at_level("INFO", logger="val.deliberation"):
        outcome = deliberate(store, adapter, FRAMED)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.ENFORCED
    blind_call = adapter.sent[2].messages[0].content
    assert blind_call.endswith(f"The question:\n{CHOICE}")
    assert "argued last week" not in blind_call and "Defend the close-up" not in blind_call
    # The logged payload is the evidence: what reached the call — and, on its
    # own line, what did not. The payload line itself carries none of it.
    payload = json.loads(outcome.blind_payload or "{}")
    assert payload["messages"][0]["content"].endswith(CHOICE)
    assert "argued last week" not in (outcome.blind_payload or "")
    withheld_lines = [
        record.getMessage()
        for record in caplog.records
        if "blind position withheld" in record.getMessage()
    ]
    assert len(withheld_lines) == 1
    withheld = json.loads(withheld_lines[0].split("withheld: ", 1)[1])
    assert [w["kind"] for w in withheld] == ["preference", "attributed_prior", "attributed_prior"]
    assert any("blind position payload" in record.getMessage() for record in caplog.records)
    assert "Defend the close-up or change your mind." in outcome.blind.stripped_content


def test_a_genuine_choice_question_reaches_the_blind_call_unchanged(store: Engine) -> None:
    """Demonstration 2: independently worded choice, one trailing preference."""
    message = f"{CHOICE} I lean wide, for what it is worth."
    strip = strip_says(question=CHOICE, removed="I lean wide, for what it is worth.")
    adapter = ScriptedAdapter(_framed_script(strip))
    outcome = deliberate(store, adapter, message)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.ENFORCED
    assert adapter.sent[2].messages[0].content.endswith(f"The question:\n{CHOICE}")


def test_framing_that_cannot_be_removed_mechanically_fails_closed(
    store: Engine, caplog: pytest.LogCaptureFixture
) -> None:
    """Demonstration 4: inseparable means contaminated, never a rewritten question."""
    strip = strip_says(present=True, separable=False, attributed=True, question="")
    adapter = ScriptedAdapter(_framed_script(strip))
    with caplog.at_level("INFO", logger="val.deliberation"):
        outcome = deliberate(store, adapter, FRAMED)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED
    blind_call = adapter.sent[2].messages[0].content
    assert blind_call.endswith(f"The question:\n{FRAMED}"), "the whole message, verbatim"
    withheld_lines = [
        record.getMessage()
        for record in caplog.records
        if "blind position withheld" in record.getMessage()
    ]
    assert withheld_lines and withheld_lines[0].endswith("withheld: []")


def test_an_attributed_span_not_verbatim_in_the_message_fails_closed(store: Engine) -> None:
    strip = strip_says(
        question=CHOICE,
        attributed=True,
        spans=[
            {
                "text": "I think we should open on the wide shot.",
                "occurrence": 1,
                "kind": "preference",
            },
            {
                "text": "You said you preferred the close-up.",
                "occurrence": 1,
                "kind": "attributed_prior",
            },
        ],
    )
    adapter = ScriptedAdapter(_framed_script(strip))
    outcome = deliberate(store, adapter, FRAMED)

    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED


def test_a_strip_reply_without_span_kinds_does_not_parse(store: Engine) -> None:
    reply = ok(
        json.dumps(
            {
                "preference_present": True,
                "attributed_prior_present": False,
                "separable": True,
                "question": QUESTION,
                "removed": [{"text": PREFERENCE, "occurrence": 1}],
            }
        )
    )
    script = full_script()
    script[1] = reply
    outcome = deliberate(store, ScriptedAdapter(script))
    assert isinstance(outcome, DeliberatedTurn) and outcome.blind is not None
    assert outcome.blind.ordering is Ordering.CONTAMINATED, (
        "an unparseable strip is a failed separation"
    )


# =============================================================================
# The blind position's bounded retry — ruling, 7 September 2026
# =============================================================================
#
# A truncated or otherwise invalid blind position may never cause a
# consequential exchange to proceed as an ordinary turn. One retry of the
# identical request on the identical configuration; a second failure ends the
# turn honestly unanswered, with every attempt preserved and nothing invented.

TRUNCATED_BLIND = ProviderResult(
    '{"position": "I hold to the close-up on her hands, my lord, and the reason is',
    TerminalState.TRUNCATED,
    6_000,
    4_096,
    "req",
)
INVALID_BLIND = ok(json.dumps({"position": "", "confidence": "medium", "reasoning": "x"}))


def _blind_calls(adapter: ScriptedAdapter) -> list[SentCall]:
    return [call for call in adapter.sent if call.output_schema == BLIND_POSITION_OUTPUT_SCHEMA]


def test_the_blind_ceiling_is_the_response_allowance(store: Engine) -> None:
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)
    assert BLIND_MAX_OUTPUT_TOKENS == 4096
    assert adapter.sent[2].max_output_tokens == 4096


def test_a_truncated_blind_position_is_retried_identically_and_the_turn_completes(
    store: Engine,
) -> None:
    script = full_script()
    adapter = ScriptedAdapter([*script[:2], TRUNCATED_BLIND, *script[2:]])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.blind is not None and outcome.deliberation is not None
    first, second = _blind_calls(adapter)
    assert first.config_slug == second.config_slug
    assert first.messages == second.messages, "the identical stripped blind input"
    assert first.system == second.system
    assert first.max_output_tokens == second.max_output_tokens == 4096
    assert _calls_by_task(store)["blind_position"] == 2, "both attempts stand in model_calls"
    assert len(blind_positions_for(store, outcome.turn.conversation.id)) == 1


def test_a_completed_but_invalid_blind_position_is_retried(store: Engine) -> None:
    script = full_script()
    adapter = ScriptedAdapter([*script[:2], INVALID_BLIND, *script[2:]])
    outcome = deliberate(store, adapter)
    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.blind is not None and outcome.deliberation is not None
    assert len(_blind_calls(adapter)) == 2


def test_a_second_blind_failure_ends_the_turn_unanswered_never_ordinary(store: Engine) -> None:
    script = full_script()
    adapter = ScriptedAdapter([*script[:2], TRUNCATED_BLIND, INVALID_BLIND])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, UnansweredTurn)
    assert isinstance(outcome.error, GatewayError)
    assert outcome.error.kind is GatewayErrorKind.INVALID_OUTPUT
    assert "2 attempts" in str(outcome.error) and "4096" in str(outcome.error)
    assert "attempt 1: reply ended truncated" in str(outcome.error)
    assert "attempt 2: reply stated no parseable position" in str(outcome.error)
    assert len(outcome.error.model_call_ids) == 2, "both attempts named"
    # Exactly four calls: classifier, strip, blind, blind. No response call.
    assert len(adapter.sent) == 4
    assert len(_blind_calls(adapter)) == 2
    with store.connect() as connection:
        val_messages = connection.execute(
            text("select count(*) from messages where role = 'val' and conversation_id = :c"),
            {"c": outcome.conversation.id},
        ).scalar_one()
        user_messages = connection.execute(
            text("select count(*) from messages where role = 'user' and conversation_id = :c"),
            {"c": outcome.conversation.id},
        ).scalar_one()
        terminals = (
            connection.execute(
                text(
                    "select terminal_state::text from model_calls "
                    "where task_type = 'blind_position' order by created_at"
                )
            )
            .scalars()
            .all()
        )
        deliberations = connection.execute(text("select count(*) from deliberations")).scalar_one()
    assert val_messages == 0, "no Val response"
    assert user_messages == 1, "the user message is preserved"
    assert terminals == ["truncated", "complete"], "each attempt under its own terminal state"
    assert len(blind_positions_for(store, outcome.conversation.id)) == 0
    assert deliberations == 0
    assert _calls_by_task(store).get("conversation", 0) == 0, "never the ordinary path"
