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
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from gateway_fakes import FakeLedger
from sqlalchemy import Engine, text
from test_persona import REPO_ROOT, clean_personas  # noqa: F401 - fixture reused

from val_domain.deliberation import DeliberationClassification, Ordering, Outcome
from val_domain.gateway import (
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
from val_gateway.deliberate import DeliberatedTurn
from val_gateway.deliberate import send as deliberated_send
from val_gateway.deliberation import blind_positions_for, deliberations_for
from val_gateway.gateway import Gateway
from val_gateway.loop import Turn, UnansweredTurn
from val_gateway.persistence import record_call, spend_by_task_type
from val_gateway.persona import DatabasePersonaLoader, seed
from val_gateway.projects import load_catalogue
from val_gateway.provenance import verifier
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
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
    *, present: bool = True, separable: bool = True, question: str = "", removed: str = ""
) -> ProviderResult:
    return ok(
        json.dumps(
            {
                "preference_present": present,
                "separable": separable,
                "question": question,
                "removed": removed,
            }
        )
    )


def blind_says(
    position: str, confidence: str = "medium", reasoning: str = "Brief."
) -> ProviderResult:
    return ok(json.dumps({"position": position, "confidence": confidence, "reasoning": reasoning}))


def reconciled(prose: str, outcome: str, what_changed: str | None = None) -> ProviderResult:
    verdict = json.dumps({"outcome": outcome, "what_changed_her_mind": what_changed})
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
        blind_says("Open on the close-up: the film is about her hands."),
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


def test_an_unparseable_classifier_reply_is_a_miss_not_a_guess(store: Engine) -> None:
    adapter = ScriptedAdapter([ok("perhaps??"), ok("As you say.")])
    outcome = deliberate(store, adapter)

    assert isinstance(outcome, DeliberatedTurn)
    assert outcome.captured_as is None, "a failed classification is a miss, never a verdict"
    assert isinstance(outcome.turn, Turn)


def test_the_classifier_runs_on_the_cheapest_eligible_route(store: Engine) -> None:
    """The ruling's 'cheapest eligible operational configuration', from routing."""
    adapter = ScriptedAdapter(full_script())
    deliberate(store, adapter)

    from val_domain.registry import active
    from val_policy.routing import candidates

    cheapest = candidates(
        active(),
        Classification.PROTECTED,
        is_ready=lambda config: True,
        is_affordable=lambda config: True,
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
    adapter_b = ScriptedAdapter(
        [reconciled("B must never be asked to say this.", "held")]
    )
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
            reconciled("It stays as one sequence, my lord.", "agreed_from_start"),
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
            reconciled("I hold, my lord.", "held"),
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
            reconciled("As you decided, my lord.", "overridden"),
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
            reconciled("We agree, my lord: the wide shot.", "agreed_from_start"),
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
