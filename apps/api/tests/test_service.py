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
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from val_api.app import create_app
from val_domain.gateway import (
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
                "separable": True,
                "question": QUESTION,
                "removed": PREFERENCE,
            }
        )
    )


def blind_says(position: str) -> ProviderResult:
    return ok(json.dumps({"position": position, "confidence": "medium", "reasoning": "Brief."}))


def reconciled(prose: str, outcome: str) -> ProviderResult:
    verdict = json.dumps({"outcome": outcome, "what_changed_her_mind": None})
    return ok(f"{prose}\n{RECONCILIATION_VERDICT_MARKER}\n{verdict}")


def deliberated_script() -> list[ProviderResult | Exception]:
    return [
        classifier_says("consequential"),
        strip_separates(),
        blind_says("Open on the close-up: the film is about her hands."),
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
                            "separable": False,
                            "question": "",
                            "removed": "",
                        }
                    )
                ),
                blind_says("It should stay as one sequence."),
                reconciled("It stays as one sequence, my lord.", "agreed_from_start"),
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
