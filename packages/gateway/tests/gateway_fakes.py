"""Fakes and builders shared by the gateway tests.

Named distinctly rather than living in `conftest.py` so it can be imported by
name from the test modules without colliding with any other package's conftest.

Two kinds of test use this file and they prove different things:

- Tests driven by `FakeLedger` prove the **gateway** reserves before it calls,
  settles what it reserved, and never records a cost it does not have. They need
  no database and run everywhere.
- Tests in `test_budget_ledger.py` drive `DatabaseLedger` against a real
  PostgreSQL and prove the **ledger** is atomic under concurrency. A fake cannot
  prove that - an in-process fake is exactly the thing the design forbids
  relying on - so those tests take the `ledger_engine` fixture from `conftest.py`
  instead, and skip rather than pretend when no database is configured.
"""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from val_domain.gateway import (
    Classification,
    ConversationProvenance,
    CostCertainty,
    GatewayRequest,
    Message,
    ModelConfig,
    TaskType,
)
from val_domain.project import ProjectAttribution
from val_domain.registry import by_slug
from val_gateway.gateway import CallRecord, Gateway
from val_gateway.ledger import Refusal, Reservation
from val_policy.budget import admits
from val_providers.base import ProviderResult


class StubAdapter:
    """A provider that returns what the test tells it to."""

    def __init__(
        self,
        result: ProviderResult | None = None,
        error: Exception | None = None,
        name: str = "anthropic",
    ) -> None:
        self.name = name
        self._result = result
        self._error = error
        self.calls = 0
        #: What the adapter was actually handed, most recent call. WP-0.7 §16
        #: requires isolation to be checked against the payload that would leave
        #: the machine, not against what a repository function returned — those
        #: are different claims, and only the second one is cheap to fake.
        #: Recorded even when the call then raises, so a failure path can be
        #: inspected too.
        self.sent_messages: tuple[Message, ...] = ()
        self.sent_system: str | None = None

    def complete(
        self,
        config: ModelConfig,
        messages: tuple[Message, ...],
        system: str | None,
        max_output_tokens: int,
    ) -> ProviderResult:
        self.calls += 1
        self.sent_messages = messages
        self.sent_system = system
        if self._error is not None:
            raise self._error
        assert self._result is not None
        return self._result

    @property
    def sent_text(self) -> str:
        """Everything this adapter was given, as one string.

        The blunt instrument the isolation tests want: if a sentinel fact from
        another project appears anywhere in the outbound payload — a message, the
        system prompt, a quoted excerpt — this finds it, without the test having
        to know which component it would have arrived through.
        """
        parts = [message.content for message in self.sent_messages]
        if self.sent_system is not None:
            parts.append(self.sent_system)
        return "\n".join(parts)


@dataclass
class LedgerEntry:
    """One reservation as the fake holds it."""

    id: UUID
    max_cost_usd: float
    state: str = "reserved"
    settled_cost_usd: float | None = None
    certainty: CostCertainty | None = None
    resolution: str | None = None


@dataclass
class FakeLedger:
    """An in-memory stand-in with the real ledger's *accounting* semantics.

    It deliberately reproduces the arithmetic — reserved and expired count at
    their maximum, settled counts at its settled figure, released counts for
    nothing — so that a gateway test which passes here would pass against
    PostgreSQL. It reproduces none of the concurrency control, which is why it
    proves nothing about races and is never used for that.
    """

    opening_committed_usd: float = 0.0
    entries: dict[UUID, LedgerEntry] = field(default_factory=dict)

    def committed_usd(self) -> float:
        total = self.opening_committed_usd
        for entry in self.entries.values():
            if entry.state in {"reserved", "expired"}:
                total += entry.max_cost_usd
            elif entry.state == "settled":
                total += entry.settled_cost_usd or 0.0
        return total

    def reserve(
        self,
        config: ModelConfig,
        max_cost_usd: float,
        task_type: TaskType,
        project_id: UUID | None,
    ) -> Reservation | Refusal:
        committed = self.committed_usd()
        if not admits(committed, max_cost_usd):
            return Refusal(committed_usd=committed, max_cost_usd=max_cost_usd)
        entry = LedgerEntry(id=uuid4(), max_cost_usd=max_cost_usd)
        self.entries[entry.id] = entry
        return Reservation(id=entry.id, max_cost_usd=max_cost_usd, committed_before_usd=committed)

    def settle(
        self,
        reservation_id: UUID,
        actual_cost_usd: float | None,
        certainty: CostCertainty,
        model_call_id: UUID | None,
    ) -> None:
        entry = self.entries[reservation_id]
        entry.state = "settled"
        entry.certainty = certainty
        # Unknown settles at the full reserved maximum: the provider was reached
        # and would not say what it charged, so nothing is handed back.
        entry.settled_cost_usd = (
            entry.max_cost_usd if certainty is CostCertainty.UNKNOWN else actual_cost_usd
        )

    def release(self, reservation_id: UUID, reason: str) -> None:
        entry = self.entries[reservation_id]
        entry.state = "released"
        entry.resolution = reason

    # --- helpers the tests read ---------------------------------------------

    def outstanding(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.state == "reserved"]

    def settled(self) -> list[LedgerEntry]:
        return [e for e in self.entries.values() if e.state == "settled"]


def config(slug: str = "opus-5") -> ModelConfig:
    found = by_slug(slug)
    assert found is not None
    return found


def request(
    classification: Classification = Classification.PROTECTED,
    content: str = "Good evening.",
    max_output_tokens: int = 4096,
    task_type: TaskType = TaskType.CLASSIFICATION,
    conversation: ConversationProvenance | None = None,
) -> GatewayRequest:
    """A request for the routing, budget and recording tests.

    **`CLASSIFICATION` rather than `CONVERSATION`.** *WP-0.7 corrective round,
    18 August 2026.* A conversation call now has to carry the conversation and
    the persisted user message that caused it, and these tests have neither —
    they are about which route is chosen, what it costs, and what is recorded,
    none of which is conversation-specific. Giving them fabricated conversation
    ids would have been inventing provenance to satisfy a check, which is the
    opposite of what the check is for.

    `classification` here is the *data* classification (Protected, Internal);
    `task_type` is the kind of work. They are different axes that happen to
    share a word.

    A test that genuinely needs conversation semantics passes `task_type` and a
    real `conversation`.
    """
    return GatewayRequest(
        task_type=task_type,
        conversation=conversation,
        classification=classification,
        messages=(Message(role="user", content=content),),
        max_output_tokens=max_output_tokens,
        # A resolved scope: these tests are about routing, budget, and recording,
        # and they assert the project reaches the row. The pair must agree — the
        # request validator refuses `EXPLICIT_NONE` carrying an id, which is how
        # this was caught rather than shipped.
        project_id=uuid4(),
        project_attribution=ProjectAttribution.RESOLVED,
    )


def build(
    adapter: StubAdapter | None = None,
    committed: float = 0.0,
    adapters: dict[str, object] | None = None,
) -> tuple[Gateway, list[CallRecord], FakeLedger, list[str]]:
    """A gateway wired to fakes, plus the rows, ledger, and blocks it produces."""
    rows: list[CallRecord] = []
    blocks: list[str] = []
    ledger = FakeLedger(opening_committed_usd=committed)
    wired = adapters if adapters is not None else {"anthropic": adapter}
    gateway = Gateway(
        adapters=wired,  # type: ignore[arg-type]
        recorder=lambda record: (rows.append(record), uuid4())[1],
        ledger=ledger,
        observe_block=blocks.append,
    )
    return gateway, rows, ledger, blocks
