"""WP-0.10 — the service behind the text interface.

What these tests pin down, against real PostgreSQL, a scripted provider, and
the real FastAPI application:

- project switching, conversation history, and marking an exchange
  consequential are all reachable through the HTTP surface — the WP-0.10
  criterion, verbatim;
- the deliberation machinery is visible where it happens: a consequential
  turn's response carries the recorded position, its confidence, and its
  outcome — and carries **no outcome** when no `deliberations` row exists,
  because pending means pending (invariant 29, Lord Armand's ruling on this
  package);
- a contaminated position is never presented as independently formed;
- recording an execution event is in-flow, and a missing reason surfaces as
  the WP-0.8 prompt rather than an opaque error;
- the cost view carries classification spend on its own line and says plainly
  when its figure is incomplete;
- an unanswered turn is a shape with no Val message in it, and Restricted
  content is a plain refusal, never a quiet failure.

The remaining WP-0.10 criterion — a full day of real work conducted entirely
through the interface — is Lord Armand's and accumulates through use.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from val_api.app import create_app
from val_domain.gateway import (
    CacheTtl,
    CostCertainty,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    TaskType,
    TerminalState,
)
from val_gateway.gateway import Gateway
from val_gateway.ledger import Refusal, Reservation
from val_gateway.persistence import record_call
from val_gateway.persona import DatabasePersonaLoader
from val_gateway.provenance import verifier
from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER
from val_providers.base import ProviderResult

# =============================================================================
# The scripted house
# =============================================================================


@dataclass
class ScriptedAdapter:
    """Answers from a script; registered for both provider names."""

    script: list[ProviderResult | Exception]
    name: str = "scripted"
    calls: int = 0

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
        output_schema: Mapping[str, object] | None = None,
        cache_ttl: CacheTtl | None = None,
    ) -> ProviderResult:
        self.calls += 1
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@dataclass
class OpenLedger:
    """A ledger that admits everything — budget behaviour is proved elsewhere."""

    entries: dict[UUID, float] = field(default_factory=dict)

    def committed_usd(self) -> float:
        return 0.0

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
    ) -> Reservation | Refusal:
        claim = uuid4()
        self.entries[claim] = max_cost_usd
        return Reservation(id=claim, max_cost_usd=max_cost_usd, committed_before_usd=0.0)

    def settle(
        self,
        reservation_id: UUID,
        actual_cost_usd: float | None,
        certainty: CostCertainty,
        model_call_id: UUID | None,
    ) -> None:
        self.entries.pop(reservation_id, None)

    def release(self, reservation_id: UUID, reason: str) -> None:
        self.entries.pop(reservation_id, None)


@dataclass
class RefusingLedger(OpenLedger):
    """A ledger at its ceiling: every route is unaffordable, nothing is admitted."""

    def committed_usd(self) -> float:
        return 1_000_000.0

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
    ) -> Reservation | Refusal:
        return Refusal(committed_usd=1_000_000.0, max_cost_usd=max_cost_usd)


def client(
    engine: Engine, adapter: ScriptedAdapter, ledger: OpenLedger | None = None
) -> TestClient:
    gateway = Gateway(
        adapters={"anthropic": adapter, "openai": adapter},
        recorder=lambda record: record_call(engine, record),
        ledger=ledger if ledger is not None else OpenLedger(),
        observe_block=lambda message: None,
        persona_loader=DatabasePersonaLoader(engine),
        verify_provenance=verifier(engine),
    )
    return TestClient(create_app(engine, gateway, warnings=["a startup warning"]))


def ok(text_body: str) -> ProviderResult:
    return ProviderResult(text_body, TerminalState.COMPLETE, 20, 10, "req")


def classifier_says(verdict: str) -> ProviderResult:
    return ok(json.dumps({"verdict": verdict, "hard_exclusion": None}))


PREFERENCE = "I think we should open on the wide shot."
QUESTION = "How should the film open?"
MIXED = f"{PREFERENCE} {QUESTION}"


def strip_separates() -> ProviderResult:
    return ok(
        json.dumps(
            {
                "preference_present": True,
                "attributed_prior_present": False,
                "separable": True,
                "question": QUESTION,
                "removed": [{"text": PREFERENCE, "occurrence": 1, "kind": "preference"}],
            }
        )
    )


def blind_says(position: str) -> ProviderResult:
    return ok(json.dumps({"position": position, "confidence": "medium", "reasoning": "Brief."}))


CLOSE_UP = "Open on the close-up: the film is about her hands."


def reconciled(prose: str, outcome: str, prior: str = CLOSE_UP) -> ProviderResult:
    verdict = json.dumps(
        {
            "recorded_prior": prior,
            "final_position": prior,
            "changed_from_recorded_prior": False,
            "recorded_prior_agreed_with_stated_preference": outcome == "agreed_from_start",
            "outcome": outcome,
            "what_changed_her_mind": None,
        }
    )
    return ok(f"{prose}\n{RECONCILIATION_VERDICT_MARKER}\n{verdict}")


def deliberated_script() -> list[ProviderResult | Exception]:
    return [
        classifier_says("consequential"),
        strip_separates(),
        blind_says(CLOSE_UP),
        reconciled("I hold: open on the close-up, my lord.", "held"),
    ]


def plain_script(answer: str = "Two o'clock, my lord.") -> list[ProviderResult | Exception]:
    return [classifier_says("not_consequential"), ok(answer)]


def a_turn(api: TestClient, content: str, **extra: object) -> dict:
    response = api.post("/turns", json={"content": content, "project": "Project Alpha", **extra})
    assert response.status_code == 200, response.text
    return response.json()


# =============================================================================
# Health, projects, history — the daily-use reads
# =============================================================================


def test_health_reports_running_and_carries_startup_warnings(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    body = api.get("/health").json()
    assert body["status"] == "running"
    assert body["warnings"] == ["a startup warning"]


def test_projects_are_listed(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    names = [p["name"] for p in api.get("/projects").json()]
    assert names == ["Project Alpha", "Project Beta"]


def test_conversation_history_is_reachable_and_scoped(store: Engine) -> None:
    """The WP-0.10 criterion: conversation history from the interface."""
    api = client(store, ScriptedAdapter([*plain_script(), *plain_script()]))
    first = a_turn(api, "What time is the screening?")
    api.post("/turns", json={"content": "And the runtime?", "no_project": True})

    everything = api.get("/conversations").json()
    assert len(everything) == 2

    alpha_id = first["conversation"]["project_id"]
    in_alpha = api.get("/conversations", params={"project_id": alpha_id}).json()
    assert [c["id"] for c in in_alpha] == [first["conversation"]["id"]]

    outside = api.get("/conversations", params={"scope": "none"}).json()
    assert len(outside) == 1 and outside[0]["project_id"] is None

    detail = api.get(f"/conversations/{first['conversation']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user", "val"]
    assert detail["messages"][1]["content"] == "Two o'clock, my lord."


def test_an_unknown_conversation_is_a_404_not_an_invention(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    assert api.get(f"/conversations/{uuid4()}").status_code == 404


# =============================================================================
# Project switching from the interface
# =============================================================================


def test_project_switching_starts_a_new_conversation_in_the_named_project(store: Engine) -> None:
    """The WP-0.10 criterion: project switching from the interface."""
    api = client(store, ScriptedAdapter([*plain_script(), *plain_script()]))
    first = a_turn(api, "Where were we on the lighthouse?")

    switched = api.post(
        "/turns",
        json={
            "content": "Switch to Project Beta: the harbour set.",
            "conversation_id": first["conversation"]["id"],
            "project": "Project Beta",
        },
    ).json()

    assert switched["kind"] == "answered"
    assert switched["conversation"]["id"] != first["conversation"]["id"]
    with store.connect() as connection:
        beta = connection.execute(
            text("select id from projects where slug = 'project-beta'")
        ).scalar_one()
    assert switched["conversation"]["project_id"] == str(beta)


def test_an_unknown_project_produces_a_clarification_not_a_guess(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    outcome = a_turn(api, "Anything.", project="Project Gamma")
    assert outcome["kind"] == "clarification"
    assert outcome["candidates"] == []
    # Nothing was created and nothing was sent.
    assert api.get("/conversations").json() == []


# =============================================================================
# Deliberation visibility where it happens — invariant 29 in the payload
# =============================================================================


def test_a_consequential_turn_shows_position_confidence_and_outcome(store: Engine) -> None:
    api = client(store, ScriptedAdapter(deliberated_script()))
    outcome = a_turn(api, MIXED)

    assert outcome["kind"] == "answered"
    glimpse = outcome["glimpse"]
    assert glimpse["captured_as"] == "consequential"
    blind = glimpse["blind"]
    assert blind["position"].startswith("Open on the close-up")
    assert blind["confidence"] == "medium"
    assert blind["ordering"] == "enforced"
    assert blind["independently_formed"] is True
    deliberation = glimpse["deliberation"]
    assert deliberation["outcome"] == "held"
    assert deliberation["blind_position_id"] == blind["id"]
    # Her message is the prose, not the verdict machinery.
    assert RECONCILIATION_VERDICT_MARKER not in outcome["val_message"]["content"]


def test_a_pending_outcome_is_pending_everywhere(store: Engine) -> None:
    """No deliberations row → no outcome anywhere in the surface. Pending
    means pending — invariant 29 applied to deliberation UI."""
    api = client(
        store,
        ScriptedAdapter(
            [
                classifier_says("consequential"),
                strip_separates(),
                blind_says("Open on the close-up."),
                ok("I hold, my lord."),  # no verdict block: outcome unresolved
            ]
        ),
    )
    outcome = a_turn(api, MIXED)

    assert outcome["glimpse"]["blind"] is not None, "the recorded position is shown"
    assert outcome["glimpse"]["deliberation"] is None, "no row, no outcome, no exception"

    detail = api.get(f"/conversations/{outcome['conversation']['id']}").json()
    assert len(detail["blind_positions"]) == 1
    assert detail["deliberations"] == []


def test_a_contaminated_position_is_never_presented_as_independent(store: Engine) -> None:
    api = client(
        store,
        ScriptedAdapter(
            [
                classifier_says("consequential"),
                ok(
                    json.dumps(
                        {
                            "preference_present": True,
                            "attributed_prior_present": False,
                            "separable": False,
                            "question": "",
                            "removed": [],
                        }
                    )
                ),
                blind_says("It should stay as one sequence."),
                reconciled(
                    "It stays as one sequence, my lord.",
                    "agreed_from_start",
                    prior="It should stay as one sequence.",
                ),
            ]
        ),
    )
    outcome = a_turn(api, MIXED)

    blind = outcome["glimpse"]["blind"]
    assert blind["ordering"] == "contaminated"
    assert blind["independently_formed"] is False
    deliberation = outcome["glimpse"]["deliberation"]
    assert deliberation["ordering"] == "contaminated"
    assert deliberation["independently_formed"] is False


def test_an_unanswered_turn_carries_no_val_message(store: Engine) -> None:
    api = client(
        store,
        ScriptedAdapter(
            [
                classifier_says("not_consequential"),
                # One failure per route in the declared fallback chain: the
                # routed path legitimately tries the declared fallback before
                # giving up, and both must fail for the turn to go unanswered.
                GatewayError(GatewayErrorKind.PROVIDER_ERROR, "the provider timed out"),
                GatewayError(GatewayErrorKind.PROVIDER_ERROR, "the provider timed out"),
            ]
        ),
    )
    outcome = a_turn(api, "What time is the screening?")

    assert outcome["kind"] == "unanswered"
    assert "val_message" not in outcome
    assert "provider_error" in outcome["error"] or "timed out" in outcome["error"]
    # The provider WAS contacted and failed: the record holds the call, so
    # the interface may say so (ruled 2 September 2026).
    assert outcome["provider_contacted"] is True
    assert outcome["error_kind"] == "provider_error"
    detail = api.get(f"/conversations/{outcome['conversation']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user"], "the question is history; no reply"


def test_a_pre_contact_refusal_does_not_claim_provider_contact(store: Engine) -> None:
    """Ruled 2 September 2026: a budget refusal must not say the provider did
    not answer when no provider was contacted — the CORS-banner class of
    defect. `provider_contacted` comes from the durable call lifecycle, and a
    refusal before contact leaves no conversation call in the record."""
    adapter = ScriptedAdapter([])  # nothing may reach a provider
    api = client(store, adapter, ledger=RefusingLedger())
    outcome = a_turn(api, "What time is the screening?")

    assert outcome["kind"] == "unanswered"
    assert outcome["provider_contacted"] is False
    assert outcome["error_kind"] in ("no_eligible_route", "budget_exceeded")
    assert "ceiling" in outcome["error"] or "afford" in outcome["error"]
    assert adapter.calls == 0, "no provider was contacted"
    with store.connect() as connection:
        recorded = connection.execute(text("select count(*) from model_calls")).scalar_one()
    assert recorded == 0, "the record supports no claim of contact"


def test_restricted_content_is_a_plain_refusal(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    credential = "".join(("-----BE", "GIN RSA PRIVATE KE", "Y-----"))
    response = api.post("/turns", json={"content": credential, "project": "Project Alpha"})
    assert response.status_code == 403
    assert api.get("/conversations").json() == [], "nothing was stored and nothing was sent"


# =============================================================================
# In-flow recording: execution events with the WP-0.8 prompt
# =============================================================================


def test_recording_a_judgment_with_its_reason(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain_script()))
    turn = a_turn(api, "Draft the summary.")

    recorded = api.post(
        "/execution-events",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["val_message"]["id"],
            "subject": "the draft summary",
            "event_type": "rejected",
            "reason": "The tone is wrong for the recipient.",
        },
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["reason_source"] == "stated"

    detail = api.get(f"/conversations/{turn['conversation']['id']}").json()
    assert len(detail["execution_events"]) == 1


def test_a_missing_reason_surfaces_the_prompt_in_place(store: Engine) -> None:
    """WP-0.8: a rejection without a stated reason prompts for one."""
    api = client(store, ScriptedAdapter(plain_script()))
    turn = a_turn(api, "Draft the summary.")

    refused = api.post(
        "/execution-events",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["val_message"]["id"],
            "subject": "the draft summary",
            "event_type": "rejected",
        },
    )
    assert refused.status_code == 422
    detail = refused.json()["detail"]
    assert detail["reason_required"] is True
    assert "Ask why" in detail["message"]

    declined = api.post(
        "/execution-events",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["val_message"]["id"],
            "subject": "the draft summary",
            "event_type": "rejected",
            "declined_to_give_reason": True,
        },
    )
    assert declined.status_code == 200
    assert declined.json()["reason_source"] == "absent"


# =============================================================================
# In-flow marking: the §4.8 manual channel
# =============================================================================


def test_an_unestablished_classification_is_an_unanswered_turn(store: Engine) -> None:
    """Ruling, 3 September 2026: unknown classification is not ordinary.

    Two unparseable classifier replies — the completed-but-unparseable shape
    seen in real use — end the turn honestly: no Val message, the error names
    the cause, and `provider_contacted` is False because no *response* call
    exists for this turn (the classification calls do, on `model_calls`).
    """
    unparseable = ok(
        'I cannot see that exchange.\n\n```json\n{"verdict": "not_consequential", '
        '"hard_exclusion": null}\n```'
    )
    api = client(store, ScriptedAdapter([unparseable, unparseable, ok("never sent")]))
    outcome = a_turn(api, MIXED)

    assert outcome["kind"] == "unanswered"
    assert outcome["error_kind"] == "invalid_output"
    assert "could not be classified" in outcome["error"]
    assert outcome["provider_contacted"] is False
    assert "val_message" not in outcome
    detail = api.get(f"/conversations/{outcome['conversation']['id']}").json()
    assert [m["role"] for m in detail["messages"]] == ["user"], "his message stands, unanswered"
    with store.connect() as connection:
        classification_calls = connection.execute(
            text("select count(*) from model_calls where task_type = 'classification'")
        ).scalar_one()
    assert classification_calls == 2, "both bounded attempts are on the record"


def test_marking_an_exchange_consequential_by_hand(store: Engine) -> None:
    """The WP-0.10 criterion: marking an exchange consequential, in flow."""
    api = client(store, ScriptedAdapter(plain_script()))
    turn = a_turn(api, MIXED)
    assert turn["glimpse"]["captured_as"] is None, "the classifier missed it"

    marked = api.post(
        "/deliberations",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["user_message"]["id"],
            "position": "Open on the close-up: the film is about her hands.",
            "confidence": "medium",
            "reasoning": "The wide shot delays meeting the subject.",
            "user_response": MIXED,
            "outcome": "held",
        },
    )
    assert marked.status_code == 200, marked.text
    body = marked.json()
    assert body["classified_by"] == "user"
    assert body["ordering"] == "contaminated", (
        "a retroactive record's position was not formed blind, and the default says so"
    )

    detail = api.get(f"/conversations/{turn['conversation']['id']}").json()
    assert len(detail["deliberations"]) == 1


def test_a_manual_record_cannot_claim_the_classifier_made_it(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain_script()))
    turn = a_turn(api, MIXED)
    refused = api.post(
        "/deliberations",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["user_message"]["id"],
            "position": "p",
            "confidence": "low",
            "reasoning": "r",
            "user_response": "u",
            "outcome": "held",
            "classified_by": "automatic",
        },
    )
    assert refused.status_code == 422
    assert "false record" in refused.json()["detail"]


def test_an_incoherent_manual_record_is_refused_with_the_writers_words(store: Engine) -> None:
    api = client(store, ScriptedAdapter(plain_script()))
    turn = a_turn(api, MIXED)
    refused = api.post(
        "/deliberations",
        json={
            "conversation_id": turn["conversation"]["id"],
            "message_id": turn["user_message"]["id"],
            "position": "p",
            "confidence": "low",
            "reasoning": "r",
            "user_response": "u",
            "outcome": "updated",
        },
    )
    assert refused.status_code == 422
    assert "what changed her mind" in refused.json()["detail"]


# =============================================================================
# The cost view and the drift signal, without a database client
# =============================================================================


def test_the_cost_view_carries_classification_on_its_own_line(store: Engine) -> None:
    api = client(store, ScriptedAdapter(deliberated_script()))
    a_turn(api, MIXED)

    costs = api.get("/costs").json()
    assert costs["by_task_type"]["classification"] > 0
    assert costs["by_task_type"]["conversation"] > 0
    assert costs["uncosted_calls"] == 0 and costs["complete"] is True
    assert costs["month_to_date_usd"] == pytest.approx(sum(costs["by_task_type"].values()))


def test_the_disagreement_signal_is_readable(store: Engine) -> None:
    api = client(store, ScriptedAdapter(deliberated_script()))
    assert api.get("/signals/disagreement").json()["last_disagreement_at"] is None
    a_turn(api, MIXED)  # resolves as held — a real disagreement
    assert api.get("/signals/disagreement").json()["last_disagreement_at"] is not None


def test_the_detail_says_how_each_turn_was_classified(store: Engine) -> None:
    """Ruling, 3 September 2026: the record answers "how was this turn classified?"."""
    unparseable = ok(
        'Cannot see it.\n```json\n{"verdict": "uncertain", "hard_exclusion": null}\n```'
    )
    api = client(
        store,
        ScriptedAdapter([*plain_script(), *deliberated_script(), unparseable, unparseable]),
    )
    first = a_turn(api, "What time is the screening?")
    conversation_id = first["conversation"]["id"]

    def continue_with(content: str) -> dict:
        # Resuming: no project stated, or the statement would start a new
        # conversation (WP-0.6: an explicit scope choice outranks resumption).
        response = api.post("/turns", json={"content": content, "conversation_id": conversation_id})
        assert response.status_code == 200, response.text
        return response.json()

    continue_with(MIXED)
    third = continue_with("Wide or close? I lean wide.")
    assert third["kind"] == "unanswered"

    detail = api.get(f"/conversations/{conversation_id}").json()
    rows = detail["classifications"]
    assert [row["verdict"] for row in rows] == ["not_consequential", "consequential", None]
    assert [row["established"] for row in rows] == [True, True, False]
    assert rows[2]["attempts"] == 2 and len(rows[2]["model_call_ids"]) == 2
    assert "no parseable verdict" in rows[2]["resolution"]
    user_messages = [m["id"] for m in detail["messages"] if m["role"] == "user"]
    assert [row["message_id"] for row in rows] == user_messages


# =============================================================================
# Project creation — ruled 7 September 2026
# =============================================================================


def test_a_project_is_created_by_name_and_a_conversation_is_attributed_to_it(
    store: Engine,
) -> None:
    api = client(store, ScriptedAdapter(plain_script()))

    created = api.post("/projects", json={"name": "Tony Spumoni"})
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["slug"] == "tony-spumoni" and project["status"] == "active"
    assert project["archived"] is False
    assert [p["name"] for p in api.get("/projects").json()].count("Tony Spumoni") == 1

    turn = a_turn(api, "What time is the screening?", project="Tony Spumoni")
    assert turn["kind"] == "answered"
    assert turn["conversation"]["project_id"] == project["id"]


def test_a_taken_project_name_is_refused_in_words(store: Engine) -> None:
    api = client(store, ScriptedAdapter([]))
    assert api.post("/projects", json={"name": "Tony Spumoni"}).status_code == 201
    refused = api.post("/projects", json={"name": "tony spumoni"})
    assert refused.status_code == 409
    assert "already exists" in refused.json()["detail"]
    empty = api.post("/projects", json={"name": "   "})
    assert empty.status_code in (409, 422)


# =============================================================================
# Classification review — ruling, 7 September 2026: blind before reveal
# =============================================================================


def _make_classification_eligible(store: Engine) -> None:
    """Live rows carry now(); the fixture rows here are made after the resume boundary."""
    with store.begin() as connection:
        connection.execute(text("update classifications set created_at = created_at where false"))


def test_the_queue_withholds_the_verdict_until_the_label_is_stored(store: Engine) -> None:
    api = client(store, ScriptedAdapter([*plain_script(), *deliberated_script()]))
    a_turn(api, "What time is the screening?")
    a_turn(api, MIXED)

    queue = api.get("/classification-review/queue").json()
    assert [q["content"] for q in queue] == ["What time is the screening?", MIXED]
    for item in queue:
        assert "verdict" not in item and "hard_exclusion" not in item, "blind by construction"
    assert api.get("/classification-review/progress").json()["eligible_unlabelled"] == 2

    first = queue[0]["classification_id"]
    omitted = api.post(
        "/classification-review/labels",
        json={"classification_id": first, "label": "not_consequential"},
    )
    assert omitted.status_code == 409 and "omitted answer" in omitted.json()["detail"]

    stored = api.post(
        "/classification-review/labels",
        json={
            "classification_id": first,
            "label": "not_consequential",
            "exclusion_determination": "status_progress_schedule_or_cost",
        },
    )
    assert stored.status_code == 201, stored.text
    revealed = stored.json()
    assert revealed["verdict"] == "not_consequential"
    assert revealed["agreement"] == "agree" and revealed["open_disagreement"] is False

    again = api.post(
        "/classification-review/labels",
        json={"classification_id": first, "label": "consequential"},
    )
    assert again.status_code == 409 and "never overwritten" in again.json()["detail"]

    second = queue[1]["classification_id"]
    mismatch = api.post(
        "/classification-review/labels",
        json={"classification_id": second, "label": "uncertain"},
    ).json()
    assert mismatch["verdict"] == "consequential"
    assert mismatch["agreement"] == "inclusion_disagreement"
    assert mismatch["open_disagreement"] is True

    progress = api.get("/classification-review/progress").json()
    assert progress["labelled"] == 2 and progress["target"] == 50
    assert progress["open_disagreements"] == 1 and progress["zero_tolerance_failures"] == 0
    assert api.get("/classification-review/queue").json() == []

    listed = api.get("/classification-review/disagreements").json()
    assert [d["classification_id"] for d in listed] == [second]

    review = api.post(
        "/classification-review/reviews",
        json={
            "classification_id": second,
            "conclusion": "classifier_upheld_label_wrong",
            "reason": "The outline decision binds later work; I was too cautious.",
        },
    )
    assert review.status_code == 201, review.text
    assert api.get("/classification-review/progress").json()["open_disagreements"] == 0
    assert (
        api.get(f"/classification-review/labelled/{second}").json()["label"]["label"] == "uncertain"
    )
