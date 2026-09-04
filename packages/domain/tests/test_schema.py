"""The schema is exactly what 04-layer-0.md §2 specifies, and it holds its rules.

`SPECIFIED` below is §2 transcribed by hand. It is deliberately a second copy
rather than something derived from `val_domain.schema`: comparing the models
against themselves would pass no matter how far either drifted from the document.
Any divergence between §2, the models, and the migrated database fails here.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from val_domain.schema import SPECIFIED_TABLES

# --- 04-layer-0.md §2, transcribed -------------------------------------------

SPECIFIED: dict[str, tuple[str, ...]] = {
    # §2.1 Core
    "projects": (
        "id",
        "name",
        "slug",
        "description",
        "status",
        "created_at",
        "updated_at",
        "archived_at",
    ),
    "conversations": (
        "id",
        "project_id",
        "title",
        "started_at",
        "last_message_at",
        "archived_at",
    ),
    "messages": ("id", "conversation_id", "role", "content", "created_at", "sequence"),
    "personas": (
        "id",
        "version",
        "content",
        "is_active",
        "activated_at",
        "authored_by",
        # WP-0.5 amendment, 17 August 2026. The authored label, the document it
        # came from, and when the row was written — none of which the integer
        # persistence revision can express.
        "semantic_version",
        "source_sha256",
        "source_path",
        "created_at",
    ),
    # §2.2 Capture
    "model_calls": (
        "id",
        "created_at",
        "model_config_id",
        "provider",
        "model_identifier",
        "tokens_in",
        "tokens_out",
        "cost",
        "project_id",
        "task_type",
        "conversation_id",
        "message_id",
        "latency_ms",
        "provider_request_id",
        "status",
        # WP-0.5 amendment, 17 August 2026: which persona revision was assembled
        # into this call's context. A stable reference, never a copy.
        "persona_id",
        # §2.2 amendment, 18 August 2026, WP-0.6 corrective round: what the
        # stored `project_id` *means*. A NULL alone cannot distinguish a
        # deliberate no-project decision from a row that predates the decision
        # existing, and both are in this table.
        "project_attribution",
        # Independent-review correction, 18 August 2026 (migration 0010): how
        # the provider call actually ended, durably. NULL is reserved for rows
        # that predate the terminal-state contract.
        "terminal_state",
        # §2.2 amendment, 17 August 2026: `known` | `unknown`. A provider attempt
        # that reached the provider and returned no usage is recorded as unknown,
        # with NULL figures — never as a zero, which is a claim and a false one.
        "cost_certainty",
    ),
    # §2.5 Budget reservations — amendment, 17 August 2026
    "budget_reservations": (
        "id",
        "created_at",
        "updated_at",
        "state",
        "model_config_id",
        "slug",
        "provider",
        "model_identifier",
        "task_type",
        "project_id",
        "max_cost",
        "settled_cost",
        "cost_certainty",
        "model_call_id",
        "resolution",
    ),
    "execution_events": (
        "id",
        "created_at",
        "project_id",
        "conversation_id",
        "message_id",
        "event_type",
        "subject",
        "reason",
        "reason_source",
        "reaction",
    ),
    "deliberations": (
        "id",
        "created_at",
        "project_id",
        "conversation_id",
        "message_id",
        "position",
        "confidence",
        "reasoning",
        "stripped_content",
        "ordering",
        "user_response",
        "outcome",
        "what_changed_her_mind",
        "both_positions",
        "predictions",
        "classification",
        "classified_by",
        "blind_position_id",
    ),
    # §2.2 blind_positions — amendment, 19 August 2026: the blind position is
    # append-only evidence, persisted before step 3 of §4 begins.
    "blind_positions": (
        "id",
        "created_at",
        "project_id",
        "conversation_id",
        "message_id",
        "model_call_id",
        "persona_id",
        "position",
        "confidence",
        "reasoning",
        "stripped_content",
        "ordering",
        "classification",
        "classified_by",
    ),
    # §2.2 classifications — ruling, 3 September 2026: per-turn classification
    # evidence, established or not, written before any strip or response call.
    "classifications": (
        "id",
        "created_at",
        "project_id",
        "conversation_id",
        "message_id",
        "established",
        "verdict",
        "hard_exclusion",
        "attempts",
        "model_call_ids",
        "resolving_model_call_id",
        "resolution",
    ),
    # §2.4 Ideas — amendment, 15 August 2026
    "ideas": ("id", "project_id", "title", "lifecycle_state", "created_at", "updated_at"),
    "idea_state_changes": ("id", "idea_id", "from_state", "to_state", "changed_at"),
}

#: Columns §2 explicitly marks nullable. Everything else is required.
SPECIFIED_NULLABLE: frozenset[tuple[str, str]] = frozenset(
    {
        ("conversations", "project_id"),
        # Amendment, 31 August 2026: presentation scoping, no evidentiary
        # meaning. NULL is the ordinary state; set means hidden from default
        # listings and nothing else.
        ("conversations", "archived_at"),
        ("projects", "archived_at"),
        ("model_calls", "project_id"),
        ("model_calls", "conversation_id"),
        ("model_calls", "message_id"),
        ("execution_events", "reason"),
        ("deliberations", "what_changed_her_mind"),
        ("deliberations", "both_positions"),
        ("deliberations", "predictions"),
        # Nullable to match conversations.project_id; §2 is silent and NOT NULL
        # would make a no-project exchange unrecordable. Flagged for ruling.
        ("execution_events", "project_id"),
        ("deliberations", "project_id"),
        ("blind_positions", "project_id"),
        # Ruling, 3 September 2026: a verdict exists iff established; the
        # exclusion, the resolving call, and the failure resolution each
        # describe one branch of that.
        ("classifications", "project_id"),
        ("classifications", "verdict"),
        ("classifications", "hard_exclusion"),
        ("classifications", "resolving_model_call_id"),
        ("classifications", "resolution"),
        # Amendment, 19 August 2026: a deliberation recorded manually, or one
        # whose exchange carried no preference to strip, has no blind call.
        ("deliberations", "blind_position_id"),
        # Amendment, 15 August 2026: a reaction with no event is a real record,
        # and a reaction is nullable because most events carry none.
        ("execution_events", "event_type"),
        ("execution_events", "reaction"),
        # §2.4: "no project" is explicit; a null from_state marks creation.
        ("ideas", "project_id"),
        ("idea_state_changes", "from_state"),
        # Amendment, 17 August 2026. NULL on these four means one thing each:
        # `cost_certainty` NULL is a row written before the distinction existed;
        # the three figures are NULL exactly when the certainty is `unknown`.
        # Recording zero there would be recording a figure known to be wrong.
        ("model_calls", "cost_certainty"),
        ("model_calls", "terminal_state"),
        ("model_calls", "tokens_in"),
        ("model_calls", "tokens_out"),
        ("model_calls", "cost"),
        # §2.5: nothing is settled until it settles, and "no project" is explicit.
        ("budget_reservations", "project_id"),
        ("budget_reservations", "settled_cost"),
        ("budget_reservations", "cost_certainty"),
        ("budget_reservations", "model_call_id"),
        ("budget_reservations", "resolution"),
        # WP-0.5. NULL activated_at means *never activated* — a revision created
        # and not yet made live carries no activation instant, because inventing
        # one would put a time in the record for an event that did not happen.
        ("personas", "activated_at"),
        # NULL persona_id means either *written before a persona existed* or *a
        # path that legitimately assembles none*. Neither is a Val utterance to
        # attribute.
        ("model_calls", "persona_id"),
    }
)

#: Enumerated values §2 lists, by the type carrying them.
SPECIFIED_ENUMS: dict[str, tuple[str, ...]] = {
    "message_role": ("user", "val", "system"),
    "model_call_task_type": (
        "conversation",
        "classification",
        "strip",
        "blind_position",
        "title",
    ),
    "model_call_status": ("ok", "error", "refused"),
    # Amendments, 17 August 2026
    "model_call_cost_certainty": ("known", "unknown"),
    # Amendment, 18 August 2026
    "model_call_project_attribution": ("resolved", "explicit_none", "legacy_unknown"),
    "budget_reservation_state": ("reserved", "settled", "released", "expired"),
    "execution_event_type": ("accepted", "rejected", "revision_requested", "corrected"),
    "reason_source": ("stated", "inferred", "absent"),
    "deliberation_confidence": ("high", "medium", "low"),
    "deliberation_ordering": ("enforced", "contaminated"),
    "deliberation_outcome": ("updated", "held", "overridden", "agreed_from_start"),
    "deliberation_classification": ("consequential", "uncertain"),
    "deliberation_classified_by": ("automatic", "user", "val"),
    # Amendments, 15 August 2026
    "execution_event_reaction": (
        "negative",
        "neutral",
        "interested",
        "enthusiastic",
        "strongly_enthusiastic",
    ),
    "idea_lifecycle_state": (
        "mentioned",
        "discussed",
        "researching",
        "prototyped",
        "approved",
        "implemented",
        "superseded",
        "rejected",
        "abandoned",
    ),
}

# Alembic's own bookkeeping. Not part of §2 and not a table Val writes.
BOOKKEEPING = {"alembic_version"}


#: Views §2 names. The table checks filter on `BASE TABLE`, so a view would
#: otherwise be invisible to them — which is exactly how an unnamed one would
#: slip in. Named here so it cannot.
SPECIFIED_VIEWS: frozenset[str] = frozenset({"model_calls_accounted"})


def _views(connection: Connection) -> set[str]:
    """Every view in the public schema."""
    return {
        row[0]
        for row in connection.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_type = 'VIEW'"
            )
        )
    }


def _tables(connection: Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            text(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_type = 'BASE TABLE'"
            )
        )
    }


def _columns(connection: Connection, table: str) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        text(
            "select column_name, is_nullable, column_default, data_type, udt_name "
            "from information_schema.columns where table_schema = 'public' "
            "and table_name = :t"
        ),
        {"t": table},
    )
    return {
        row[0]: {
            "nullable": row[1] == "YES",
            "default": row[2],
            "data_type": row[3],
            "udt_name": row[4],
        }
        for row in rows
    }


# --- the migration set --------------------------------------------------------


def test_upgrade_from_empty_produces_the_full_schema(engine: Engine) -> None:
    """`alembic upgrade head` against an empty database produces §2's schema."""
    with engine.connect() as connection:
        assert _tables(connection) - BOOKKEEPING == set(SPECIFIED)


def test_migrations_are_reversible(engine: Engine, alembic_config: Config) -> None:
    """`downgrade base` then `upgrade head` succeeds, and leaves nothing behind.

    Runs last-ish by design: it tears the schema down and rebuilds it, so it also
    proves a second upgrade over a previously-migrated database is clean.
    """
    command.downgrade(alembic_config, "base")
    with engine.connect() as connection:
        assert _tables(connection) - BOOKKEEPING == set()
        surviving_types = {
            row[0]
            for row in connection.execute(
                text(
                    "select t.typname from pg_type t join pg_namespace n "
                    "on n.oid = t.typnamespace where n.nspname = 'public' and t.typtype = 'e'"
                )
            )
        }
        assert surviving_types == set(), "enumerated types outlived the downgrade"
        functions = {
            row[0]
            for row in connection.execute(
                text(
                    "select p.proname from pg_proc p join pg_namespace n "
                    "on n.oid = p.pronamespace where n.nspname = 'public'"
                )
            )
        }
        assert functions == set(), "the delete guard outlived the downgrade"

    command.upgrade(alembic_config, "head")
    with engine.connect() as connection:
        assert _tables(connection) - BOOKKEEPING == set(SPECIFIED)


# --- the schema matches §2 ----------------------------------------------------


def test_no_table_exists_that_the_specification_does_not_name(engine: Engine) -> None:
    """§2's rule, stated as a test."""
    with engine.connect() as connection:
        assert _tables(connection) - BOOKKEEPING - set(SPECIFIED) == set()


def test_specified_tables_constant_matches_the_transcription() -> None:
    """The models' own table list agrees with §2 as transcribed here."""
    assert SPECIFIED_TABLES == set(SPECIFIED)


@pytest.mark.parametrize("table", sorted(SPECIFIED))
def test_columns_match_the_specification_exactly(engine: Engine, table: str) -> None:
    """Every column §2 lists exists, and no column it does not list."""
    with engine.connect() as connection:
        assert set(_columns(connection, table)) == set(SPECIFIED[table])


@pytest.mark.parametrize("table", sorted(SPECIFIED))
def test_only_specified_columns_are_nullable(engine: Engine, table: str) -> None:
    """§2 marks specific columns nullable; that marking means nothing unless the rest are not."""
    with engine.connect() as connection:
        actual = {name for name, info in _columns(connection, table).items() if info["nullable"]}
    assert actual == {column for owner, column in SPECIFIED_NULLABLE if owner == table}


@pytest.mark.parametrize(("type_name", "values"), sorted(SPECIFIED_ENUMS.items()))
def test_enumerated_values_match_the_specification(
    engine: Engine, type_name: str, values: tuple[str, ...]
) -> None:
    """No enumerated value is invented, and none §2 names is missing."""
    with engine.connect() as connection:
        actual = [
            row[0]
            for row in connection.execute(
                text(
                    "select e.enumlabel from pg_enum e join pg_type t on t.oid = e.enumtypid "
                    "where t.typname = :n order by e.enumsortorder"
                ),
                {"n": type_name},
            )
        ]
    assert tuple(actual) == values


def test_pgvector_is_installed(engine: Engine) -> None:
    """WP-0.2 requires PostgreSQL *with pgvector*, even though §2 names no vector column."""
    with engine.connect() as connection:
        installed = connection.execute(
            text("select extversion from pg_extension where extname = 'vector'")
        ).scalar()
    assert installed is not None


# --- reason_source and ordering are load-bearing ------------------------------
#
# A record that cannot distinguish a reason Lord Armand stated from one Val
# inferred, or a blind position from a contaminated one, is worse than no record.
# These are the tests that keep that true.


@pytest.mark.parametrize(
    ("table", "column"),
    [("execution_events", "reason_source"), ("deliberations", "ordering")],
)
def test_load_bearing_columns_are_required_and_have_no_default(
    engine: Engine, table: str, column: str
) -> None:
    """The writer must state them. A default would let the database guess."""
    with engine.connect() as connection:
        info = _columns(connection, table)[column]
    assert info["nullable"] is False, f"{table}.{column} must be required"
    assert info["default"] is None, f"{table}.{column} must not carry a default"


@pytest.fixture
def anchored(connection: Connection) -> Iterator[dict[str, Any]]:
    """A project, conversation, and message to hang capture records on."""
    project = connection.execute(
        text(
            "insert into projects (name, slug, description, status) "
            "values ('House Armand', 'house-armand', 'The first project.', 'active') "
            "returning id"
        )
    ).scalar_one()
    conversation = connection.execute(
        text(
            "insert into conversations (project_id, title) values (:p, 'An exchange') returning id"
        ),
        {"p": project},
    ).scalar_one()
    message = connection.execute(
        text(
            "insert into messages (conversation_id, role, content, sequence) "
            "values (:c, 'user', 'Something was said.', 1) returning id"
        ),
        {"c": conversation},
    ).scalar_one()
    yield {"project": project, "conversation": conversation, "message": message}


def _insert_event(
    connection: Connection, anchored: dict[str, Any], reason: str | None, source: str
) -> None:
    connection.execute(
        text(
            "insert into execution_events "
            "(project_id, conversation_id, message_id, event_type, subject, reason, reason_source) "
            "values (:p, :c, :m, 'rejected', 'A storyboard panel', :reason, :source)"
        ),
        {
            "p": anchored["project"],
            "c": anchored["conversation"],
            "m": anchored["message"],
            "reason": reason,
            "source": source,
        },
    )


@pytest.mark.parametrize(
    ("reason", "source"),
    [
        ("The staging reads flat.", "stated"),
        ("Inferred from the revision.", "inferred"),
        (None, "absent"),
    ],
)
def test_coherent_reasons_are_accepted(
    connection: Connection, anchored: dict[str, Any], reason: str | None, source: str
) -> None:
    """The three combinations that mean something are allowed."""
    _insert_event(connection, anchored, reason, source)


@pytest.mark.parametrize(
    ("reason", "source"),
    [
        # A reason recorded as absent that nonetheless has text.
        ("The staging reads flat.", "absent"),
        # A stated reason with nothing stated.
        (None, "stated"),
        (None, "inferred"),
    ],
)
def test_incoherent_reasons_are_refused(
    connection: Connection, anchored: dict[str, Any], reason: str | None, source: str
) -> None:
    """`reason` and `reason_source` cannot disagree, or the distinction is worthless."""
    with pytest.raises(Exception, match="ck_execution_events_reason_matches_source"):
        _insert_event(connection, anchored, reason, source)


# --- reaction is not intent (amendment, 15 August 2026) -----------------------
#
# "He loved the idea" and "he approved the work" are different facts. The schema
# must hold them apart, and a reaction-only record must be exactly as easy to
# write and to find as an event.


def test_a_reaction_without_an_acceptance_event_is_representable_and_queryable(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """The record the amendment names: strongly_enthusiastic, no acceptance event."""
    connection.execute(
        text(
            "insert into execution_events "
            "(project_id, conversation_id, message_id, event_type, subject, reason, "
            "reason_source, reaction) "
            "values (:p, :c, :m, null, 'The puppet-theatre episode idea', null, 'absent', "
            "'strongly_enthusiastic')"
        ),
        {"p": anchored["project"], "c": anchored["conversation"], "m": anchored["message"]},
    )
    found = connection.execute(
        text(
            "select count(*) from execution_events "
            "where reaction = 'strongly_enthusiastic' and event_type is null"
        )
    ).scalar_one()
    assert found == 1
    approvals = connection.execute(
        text("select count(*) from execution_events where event_type = 'accepted'")
    ).scalar_one()
    assert approvals == 0, "enthusiasm must never read back as approval"


def test_a_reaction_may_accompany_an_event(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """Approving warmly is one record carrying both facts, held separately."""
    connection.execute(
        text(
            "insert into execution_events "
            "(project_id, conversation_id, message_id, event_type, subject, reason, "
            "reason_source, reaction) "
            "values (:p, :c, :m, 'accepted', 'The cold open', 'It lands.', 'stated', "
            "'enthusiastic')"
        ),
        {"p": anchored["project"], "c": anchored["conversation"], "m": anchored["message"]},
    )


def test_a_record_saying_nothing_is_refused(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """Null event and null reaction together is noise wearing a record's shape."""
    with pytest.raises(Exception, match="ck_execution_events_event_or_reaction_present"):
        connection.execute(
            text(
                "insert into execution_events "
                "(project_id, conversation_id, message_id, event_type, subject, reason, "
                "reason_source, reaction) "
                "values (:p, :c, :m, null, 'Nothing', null, 'absent', null)"
            ),
            {"p": anchored["project"], "c": anchored["conversation"], "m": anchored["message"]},
        )


# --- §2.4 the idea lifecycle (amendment, 15 August 2026) ----------------------


def _create_idea(connection: Connection, project: object) -> object:
    idea = connection.execute(
        text(
            "insert into ideas (project_id, title, lifecycle_state) "
            "values (:p, 'A puppet-theatre episode', 'mentioned') returning id"
        ),
        {"p": project},
    ).scalar_one()
    connection.execute(
        text(
            "insert into idea_state_changes (idea_id, from_state, to_state) "
            "values (:i, null, 'mentioned')"
        ),
        {"i": idea},
    )
    return idea


def test_idea_state_history_is_preserved_not_overwritten(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """Lineage accumulates: every transition remains after the state moves on."""
    idea = _create_idea(connection, anchored["project"])
    connection.execute(
        text(
            "insert into idea_state_changes (idea_id, from_state, to_state) "
            "values (:i, 'mentioned', 'discussed')"
        ),
        {"i": idea},
    )
    connection.execute(
        text("update ideas set lifecycle_state = 'discussed', updated_at = now() where id = :i"),
        {"i": idea},
    )
    history = connection.execute(
        text(
            "select from_state, to_state from idea_state_changes "
            "where idea_id = :i order by changed_at, id"
        ),
        {"i": idea},
    ).all()
    assert [(row[0], row[1]) for row in history] == [
        (None, "mentioned"),
        ("mentioned", "discussed"),
    ]


def test_a_state_change_that_changes_nothing_is_refused(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """A no-op transition is not lineage."""
    idea = _create_idea(connection, anchored["project"])
    with pytest.raises(Exception, match="ck_idea_state_changes_state_change_changes_state"):
        connection.execute(
            text(
                "insert into idea_state_changes (idea_id, from_state, to_state) "
                "values (:i, 'mentioned', 'mentioned')"
            ),
            {"i": idea},
        )


def test_an_idea_may_belong_to_no_project(connection: Connection) -> None:
    """The same rule as everywhere: "no project" is explicit, not an accident."""
    idea = connection.execute(
        text(
            "insert into ideas (project_id, title, lifecycle_state) "
            "values (null, 'A notion with no home yet', 'mentioned') returning id"
        )
    ).scalar_one()
    assert idea is not None


def _insert_deliberation(
    connection: Connection, anchored: dict[str, Any], outcome: str, what_changed: str | None
) -> None:
    connection.execute(
        text(
            "insert into deliberations (project_id, conversation_id, message_id, position, "
            "confidence, reasoning, stripped_content, ordering, user_response, outcome, "
            "what_changed_her_mind, classification, classified_by) "
            "values (:p, :c, :m, 'Open on the close shot.', 'high', 'Staging.', "
            "'I think we should open wide.', 'enforced', 'I disagree.', :outcome, :what, "
            "'consequential', 'automatic')"
        ),
        {
            "p": anchored["project"],
            "c": anchored["conversation"],
            "m": anchored["message"],
            "outcome": outcome,
            "what": what_changed,
        },
    )


def test_an_updated_position_must_say_what_changed_her_mind(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """§2 states the rule: required when outcome = 'updated'."""
    with pytest.raises(Exception, match="ck_deliberations_updated_requires_what_changed_her_mind"):
        _insert_deliberation(connection, anchored, "updated", None)


@pytest.mark.parametrize("outcome", ["held", "overridden", "agreed_from_start"])
def test_other_outcomes_need_no_explanation(
    connection: Connection, anchored: dict[str, Any], outcome: str
) -> None:
    """Only an update requires an account of what moved her."""
    _insert_deliberation(connection, anchored, outcome, None)


def test_a_contaminated_ordering_is_recordable(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """Recording contamination honestly is the point; it must not be harder than lying."""
    connection.execute(
        text(
            "insert into deliberations (project_id, conversation_id, message_id, position, "
            "confidence, reasoning, stripped_content, ordering, user_response, outcome, "
            "classification, classified_by) "
            "values (:p, :c, :m, 'Open wide.', 'low', 'Preference was the question.', '', "
            "'contaminated', 'Agreed.', 'agreed_from_start', 'uncertain', 'val')"
        ),
        {"p": anchored["project"], "c": anchored["conversation"], "m": anchored["message"]},
    )


# --- §2.3 constraints ---------------------------------------------------------


@pytest.mark.parametrize("table", sorted(SPECIFIED))
def test_no_table_permits_hard_delete(connection: Connection, table: str) -> None:
    """§2.3 — no table permits hard delete at Layer 0."""
    # The table name is one of SPECIFIED's fixed keys, never input.
    with pytest.raises(Exception, match="hard delete is not permitted"):
        connection.execute(text(f"delete from {table}"))  # noqa: S608


@pytest.mark.parametrize("table", sorted(SPECIFIED))
def test_no_table_permits_truncate(connection: Connection, table: str) -> None:
    """Truncation is deletion by another name.

    Two different refusals are correct here. On a table nothing references, the
    guard trigger fires. On a table a foreign key points at, PostgreSQL refuses
    first, before any trigger runs. Both are refusals; asserting only the trigger
    message would fail on tables that are in fact better protected.
    """
    with pytest.raises(
        Exception,
        match=r"hard delete is not permitted|cannot truncate a table referenced",
    ):
        connection.execute(text(f"truncate {table}"))


@pytest.mark.parametrize("table", sorted(SPECIFIED))
def test_every_table_carries_the_delete_guard(engine: Engine, table: str) -> None:
    """The guard exists on all seven tables, for DELETE and for TRUNCATE.

    This is what `test_no_table_permits_truncate` cannot show on its own: that
    the protection is present everywhere and not merely implied by a foreign key
    that a later migration might drop.
    """
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select t.tgtype from pg_trigger t join pg_class c on c.oid = t.tgrelid "
                "where c.relname = :table and t.tgname = :name and not t.tgisinternal"
            ),
            {"table": table, "name": f"{table}_forbid_hard_delete"},
        ).one_or_none()
    assert row is not None, f"{table} has no delete guard"
    # pg_trigger.tgtype bit 3 is DELETE, bit 5 is TRUNCATE.
    tgtype = int(row[0])
    assert tgtype & (1 << 3), f"{table}'s guard does not cover DELETE"
    assert tgtype & (1 << 5), f"{table}'s guard does not cover TRUNCATE"


def test_nothing_cascades(engine: Engine) -> None:
    """§2.3 — capture records outlive the conversation that produced them."""
    with engine.connect() as connection:
        cascading = [
            (row[0], row[1])
            for row in connection.execute(
                text(
                    "select c.conname, c.confdeltype from pg_constraint c "
                    "join pg_namespace n on n.oid = c.connamespace "
                    "where c.contype = 'f' and n.nspname = 'public' and c.confdeltype <> 'a'"
                )
            )
        ]
    assert cascading == [], f"foreign keys with a delete action: {cascading}"


def test_a_message_must_resolve_to_a_conversation(connection: Connection) -> None:
    """§2.3 — every message resolves to a conversation."""
    with pytest.raises(Exception, match="null value in column"):
        connection.execute(
            text(
                "insert into messages (conversation_id, role, content, sequence) "
                "values (null, 'user', 'Orphaned.', 1)"
            )
        )


def test_a_conversation_may_resolve_explicitly_to_no_project(connection: Connection) -> None:
    """§2.1 — "no project" is a real, explicit state, not a null accident."""
    identifier = connection.execute(
        text(
            "insert into conversations (project_id, title) values (null, 'No project') returning id"
        )
    ).scalar_one()
    assert identifier is not None


def test_message_sequence_is_unique_within_a_conversation(
    connection: Connection, anchored: dict[str, Any]
) -> None:
    """What makes gapless, stable ordering provable at WP-0.7."""
    with pytest.raises(Exception, match="uq_messages_conversation_id_sequence"):
        connection.execute(
            text(
                "insert into messages (conversation_id, role, content, sequence) "
                "values (:c, 'val', 'Second message, same sequence.', 1)"
            ),
            {"c": anchored["conversation"]},
        )


def test_at_most_one_persona_is_active(connection: Connection) -> None:
    """WP-0.5 loads "the active personas row", singular."""
    connection.execute(
        text(
            "insert into personas (version, semantic_version, content, source_sha256, "
            "source_path, is_active, activated_at, authored_by) "
            "values (1, '1.0', 'First.', repeat('a', 64), 'fixture.md', true, now(), "
            "'Lord Armand')"
        )
    )
    with pytest.raises(Exception, match="uq_personas_single_active"):
        connection.execute(
            text(
                "insert into personas (version, semantic_version, content, source_sha256, "
                "source_path, is_active, activated_at, authored_by) "
                "values (2, '1.1', 'Second.', repeat('b', 64), 'fixture.md', true, now(), "
                "'Lord Armand')"
            )
        )


def test_a_superseded_persona_version_remains(connection: Connection) -> None:
    """Editing creates a version; it never mutates a row, and prior rows survive."""
    connection.execute(
        text(
            "insert into personas (version, semantic_version, content, source_sha256, "
            "source_path, is_active, activated_at, authored_by) values "
            "(1, '1.0', 'First.', repeat('a', 64), 'fixture.md', false, now(), 'Lord Armand'), "
            "(2, '1.1', 'Second.', repeat('b', 64), 'fixture.md', true, now(), 'Lord Armand')"
        )
    )
    count = connection.execute(text("select count(*) from personas")).scalar_one()
    assert count == 2


def test_models_and_migration_agree(engine: Engine) -> None:
    """The declarative models describe the database the migration actually built.

    Without this, `schema.py` and the migration set can drift apart silently: the
    models would keep passing their own tests while the store diverged from them.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from val_domain.schema import Base

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)
    assert differences == [], f"models and migration disagree: {differences}"


def test_postgres_major_version_is_18(engine: Engine) -> None:
    """The major version matches everywhere the store runs.

    Patch drift between the local instance, CI, and the always-on box is expected
    and recorded. Major drift is not: it would mean the schema is exercised
    against a different database from the one that holds the records.
    """
    with engine.connect() as connection:
        setting = connection.execute(text("show server_version_num")).scalar_one()
    major = int(setting) // 10000
    assert major == 18, f"expected PostgreSQL 18, found major version {major}"


# --- the accounting view — §2.2 amendment, 17 August 2026 --------------------


def test_no_view_exists_that_the_specification_does_not_name(engine: Engine) -> None:
    """The table checks filter on BASE TABLE; without this a view would be unseen."""
    with engine.connect() as connection:
        assert _views(connection) == SPECIFIED_VIEWS


def test_the_accounting_view_exposes_every_base_column(engine: Engine) -> None:
    """It is the base table read through a rule, not a curated subset.

    A view that dropped columns would quietly become a second, lesser record,
    and readers would have to know which one to ask.
    """
    with engine.connect() as connection:
        base = set(_columns(connection, "model_calls"))
        view = set(_columns(connection, "model_calls_accounted"))
    assert base <= view
    assert view - base == {"effective_cost_certainty", "accounted_cost", "accounting_note"}


def _fabricating_history(connection: Connection) -> None:
    """Suspend the `legacy_unknown` guard for this rolled-back transaction.

    Migration `0007` closed `legacy_unknown` to new rows: it describes
    `model_calls` written before project attribution existed, and that set was
    backfilled once and is finished. A test that needs such a row is therefore
    asking for something the database is built to refuse, and it has to say so
    out loud rather than find a way in.

    Two tests below genuinely need one, because what they exercise *is* the
    handling of pre-amendment rows — the accounting view's treatment of a NULL
    `cost_certainty`, which only historical rows carry. They fabricate the row,
    and this function is where that admission lives.

    Safe here for reasons that do not generalise: the `connection` fixture rolls
    everything back, and Postgres makes DDL transactional, so the trigger is
    restored with the rest. Nothing in `val_gateway` or the application may do
    this — a writer that disables the guard has simply chosen not to decide
    scope, which is the exact failure `0007` exists to prevent.
    """
    connection.execute(
        text("ALTER TABLE model_calls DISABLE TRIGGER model_calls_legacy_attribution_is_closed")
    )
    # And the terminal-state guard (migration 0010): a fabricated historical row
    # carries NULL terminal_state, the legacy shape reserved to history.
    connection.execute(
        text("ALTER TABLE model_calls DISABLE TRIGGER model_calls_terminal_state_is_required")
    )


def test_a_new_legacy_unknown_row_is_refused_however_it_is_dated(
    engine: Engine, connection: Connection
) -> None:
    """The finding from independent review, as a test.

    `0006` reserved `legacy_unknown` with a check constraint on `created_at`,
    and `created_at` is supplied by whoever writes the row. Backdating it walked
    straight through. This asserts the row is refused *because of what it does*,
    not because of when it claims to have happened — so all three dates fail:
    today, before the old cutoff, and long before the system existed.
    """
    attempt = text(
        "insert into model_calls (created_at, model_config_id, provider, model_identifier, "
        "tokens_in, tokens_out, cost, cost_certainty, project_id, project_attribution, "
        "terminal_state, task_type, latency_ms, provider_request_id, status) values "
        "(:dated, gen_random_uuid(), 'anthropic', 'x', 1, 1, 0.01, 'known', null, "
        "'legacy_unknown', 'complete', 'conversation', 1, '', 'ok')"
    )
    dates = (
        datetime.now(UTC),
        datetime(2026, 8, 15, tzinfo=UTC),  # before `0006`'s cutoff — the demonstrated bypass
        datetime(2001, 1, 1, tzinfo=UTC),  # long before the system existed
    )
    for dated in dates:
        # A savepoint per attempt: a refused statement aborts the surrounding
        # transaction, and the fixture still needs a live one to roll back.
        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError) as raised:
            connection.execute(attempt, {"dated": dated})
        assert "closed to new rows" in str(raised.value)
        savepoint.rollback()


def test_an_existing_row_cannot_be_turned_into_a_legacy_one(
    engine: Engine, connection: Connection
) -> None:
    """The other half of the rule, and the half a check constraint cannot state.

    Refusing the INSERT alone would leave the obvious way round it: write the
    row honestly, then update it to `legacy_unknown` afterwards. The guard is on
    the transition, so it catches that too.
    """
    connection.execute(
        text(
            "insert into model_calls (model_config_id, provider, model_identifier, "
            "tokens_in, tokens_out, cost, cost_certainty, project_id, "
            "project_attribution, terminal_state, task_type, latency_ms, "
            "provider_request_id, status) "
            "values (gen_random_uuid(), 'anthropic', 'x', 1, 1, 0.01, 'known', null, "
            "'explicit_none', 'complete', 'conversation', 1, '', 'ok') returning id"
        )
    )
    with pytest.raises(DBAPIError) as raised:
        connection.execute(text("update model_calls set project_attribution = 'legacy_unknown'"))
    assert "closed to new rows" in str(raised.value)


def test_a_historical_row_is_frozen_evidence(engine: Engine, connection: Connection) -> None:
    """Closed to new members, and — closure pass, 18 August 2026 — frozen too.

    This test used to assert the opposite: that a legacy row's `latency_ms`
    remained correctable in place, per `0007`'s "closed to new members, not
    frozen". The closure audit's mutation review superseded that stance:
    a completed call is evidence in all its columns, and a wrong figure is
    corrected by a superseding record (the `0004` view is the worked example),
    never by editing the original. Migration `0009` enforces it.
    """
    _fabricating_history(connection)
    call = connection.execute(
        text(
            "insert into model_calls (created_at, model_config_id, provider, "
            "model_identifier, tokens_in, tokens_out, cost, cost_certainty, "
            "project_attribution, task_type, latency_ms, provider_request_id, status) "
            "values (timestamptz '2026-08-15 12:00:00+00', gen_random_uuid(), 'anthropic', "
            "'x', 1, 1, 0.01, 'known', 'legacy_unknown', 'conversation', 1, '', 'ok') "
            "returning id"
        )
    ).scalar_one()
    connection.execute(
        text("ALTER TABLE model_calls ENABLE TRIGGER model_calls_legacy_attribution_is_closed")
    )
    connection.execute(
        text("ALTER TABLE model_calls ENABLE TRIGGER model_calls_terminal_state_is_required")
    )

    with pytest.raises(DBAPIError) as raised:
        connection.execute(
            text("update model_calls set latency_ms = 42 where id = :i"), {"i": call}
        )
    assert "rows are evidence" in str(raised.value)


def test_the_view_never_leaves_effective_certainty_null(
    engine: Engine, connection: Connection
) -> None:
    """Every row resolves to known or unknown. There is no third state."""
    _fabricating_history(connection)
    connection.execute(
        text(
            "insert into model_calls (created_at, model_config_id, provider, "
            "model_identifier, tokens_in, tokens_out, cost, cost_certainty, "
            "task_type, project_attribution, latency_ms, provider_request_id, status) values "
            "(timestamptz '2026-08-15 12:00:00+00', gen_random_uuid(), 'anthropic', 'x', "
            "0, 0, 0, null, 'conversation', 'legacy_unknown', 1, '', 'error')"
        )
    )
    missing = connection.execute(
        text("select count(*) from model_calls_accounted where effective_cost_certainty is null")
    ).scalar_one()
    assert missing == 0


def test_the_superseding_rule_is_exact_not_a_blanket(
    engine: Engine, connection: Connection
) -> None:
    """Only the superseded *error* rows are reinterpreted.

    The implementation being superseded wrote real usage on success and refusal
    and fabricated figures only on error. A rule that distrusted every legacy row
    would be discarding good evidence to be safe, which is its own kind of wrong.
    """
    _fabricating_history(connection)
    legacy_insert = text(
        "insert into model_calls (created_at, model_config_id, provider, "
        "model_identifier, tokens_in, tokens_out, cost, cost_certainty, "
        "task_type, project_attribution, latency_ms, provider_request_id, status) values "
        "(timestamptz '2026-08-15 12:00:00+00', gen_random_uuid(), 'anthropic', "
        "'x', 1, 1, :cost, null, 'conversation', 'legacy_unknown', 1, '', :status)"
    )
    for status, cost in (("error", 0.0), ("ok", 0.000905), ("refused", 0.0004)):
        connection.execute(legacy_insert, {"cost": cost, "status": status})
    rows = connection.execute(
        text(
            "select status, effective_cost_certainty, accounted_cost "
            "from model_calls_accounted where cost_certainty is null"
        )
    ).all()
    by_status = {row.status: row for row in rows}
    assert by_status["error"].effective_cost_certainty == "unknown"
    assert by_status["error"].accounted_cost is None
    assert by_status["ok"].effective_cost_certainty == "known"
    assert by_status["ok"].accounted_cost is not None
    assert by_status["refused"].effective_cost_certainty == "known"


def test_the_view_holds_no_state_of_its_own(engine: Engine) -> None:
    """It is a rule over the base table, so it cannot drift from it."""
    with engine.connect() as connection:
        kind = connection.execute(
            text(
                "select table_type from information_schema.tables "
                "where table_schema = 'public' and table_name = 'model_calls_accounted'"
            )
        ).scalar_one()
    assert kind == "VIEW"


# =========================================================================
# Migration reversibility — WP-0.6 corrective round two, 18 August 2026
# =========================================================================
#
# `0006` originally claimed its downgrade was clean unconditionally, on the
# reasoning that `project_attribution` "adds interpretation but stores no fact
# of its own". True until the first `explicit_none` row exists; false forever
# after. These two tests are the before and the after.


@contextmanager
def _restored_to_head(engine: Engine, alembic_config: Config) -> Iterator[None]:
    """Run a migration test, leaving the scratch database back at head.

    The session `engine` fixture builds head once and every other test assumes
    it. A test that deliberately downgrades therefore has to put it back, and
    has to do so even when it fails — otherwise one failure here reports itself
    as a cascade of unrelated ones.
    """
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
        command.upgrade(alembic_config, "head")


def test_the_attribution_downgrade_is_clean_when_nothing_was_decided(
    engine: Engine, alembic_config: Config
) -> None:
    """A fresh checkout can roll back freely.

    With no `explicit_none` row, every attribution is derivable from
    `project_id` again, so dropping the column loses an interpretation and no
    evidence. This is the state CI is always in.
    """
    with _restored_to_head(engine, alembic_config):
        command.downgrade(alembic_config, "0005_persona_provenance")

        with engine.connect() as connection:
            columns = connection.execute(
                text(
                    "select column_name from information_schema.columns "
                    "where table_name = 'model_calls'"
                )
            ).scalars()
            assert "project_attribution" not in set(columns)

        # And forward again, so the pair is reversible rather than merely
        # droppable — a downgrade that cannot be re-applied is a dead end.
        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(text("select count(*) from model_calls_accounted")).scalar_one()
                == 0
            )


def test_the_attribution_downgrade_refuses_once_a_decision_is_recorded(
    engine: Engine, alembic_config: Config
) -> None:
    """One deliberate no-project row is enough to make the rollback destructive.

    `project_id` NULL + `explicit_none` and `project_id` NULL + `legacy_unknown`
    become the *same row* when the column goes, and nothing left in the table
    distinguishes them afterwards. So the migration refuses, rather than
    quietly turning a decision into a gap — the doctrine `0002`, `0003` and
    `0005` already follow.
    """
    with _restored_to_head(engine, alembic_config):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "insert into model_calls (model_config_id, provider, model_identifier, "
                    "tokens_in, tokens_out, cost, cost_certainty, project_id, "
                    "project_attribution, terminal_state, task_type, latency_ms, "
                    "provider_request_id, status) "
                    "values (gen_random_uuid(), 'anthropic', 'x', 1, 1, 0.01, 'known', null, "
                    "'explicit_none', 'complete', 'conversation', 1, '', 'ok')"
                )
            )

        with pytest.raises(RuntimeError) as raised:
            command.downgrade(alembic_config, "0005_persona_provenance")
        assert "Refusing to downgrade" in str(raised.value)
        # *Closure pass, 18 August 2026:* the refusal chain now begins at
        # `0009`, whose evidence-freeze guard refuses first because the
        # `explicit_none` row exists at all. `0006`'s own narrower refusal
        # stands beneath it as defence in depth — reachable only on a database
        # where every guarded table is empty except for the decision row, a
        # state `0009` itself refuses to pass through.

        # Refused, not half-applied: the column and the decision are both still
        # there. A migration that raises after dropping something is worse than
        # one that never checked.
        with engine.connect() as connection:
            surviving = connection.execute(
                text("select count(*) from model_calls where project_attribution = 'explicit_none'")
            ).scalar_one()
            assert surviving == 1


def test_the_legacy_guard_downgrade_restores_the_earlier_constraint(
    engine: Engine, alembic_config: Config
) -> None:
    """`0007` swapped enforcement for stronger enforcement and captured nothing.

    So its downgrade is clean in both directions, and puts `0006`'s constraint
    back rather than leaving the column unguarded.
    """
    with _restored_to_head(engine, alembic_config):
        command.downgrade(alembic_config, "0006_project_attribution")

        with engine.connect() as connection:
            triggers = connection.execute(
                text("select tgname from pg_trigger where not tgisinternal")
            ).scalars()
            assert "model_calls_legacy_attribution_is_closed" not in set(triggers)

            constraints = connection.execute(
                text("select conname from pg_constraint where conrelid = 'model_calls'::regclass")
            ).scalars()
            assert "ck_model_calls_legacy_attribution_is_reserved_to_history" in set(constraints)

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            triggers = connection.execute(
                text("select tgname from pg_trigger where not tgisinternal")
            ).scalars()
            assert "model_calls_legacy_attribution_is_closed" in set(triggers)


# =========================================================================
# WP-0.7 — conversation scope and recall, migration 0008
# =========================================================================


def test_the_conversation_scope_downgrade_is_clean_when_none_were_held(
    engine: Engine, alembic_config: Config
) -> None:
    """`0008` reverses freely while there is no conversation to unprotect."""
    with _restored_to_head(engine, alembic_config):
        command.downgrade(alembic_config, "0007_legacy_attribution_closed")

        with engine.connect() as connection:
            triggers = set(
                connection.execute(
                    text("select tgname from pg_trigger where not tgisinternal")
                ).scalars()
            )
            assert "conversations_scope_is_immutable" not in triggers
            indexes = set(connection.execute(text("select indexname from pg_indexes")).scalars())
            assert "ix_messages_content_fts" not in indexes

        command.upgrade(alembic_config, "head")
        with engine.connect() as connection:
            indexes = set(connection.execute(text("select indexname from pg_indexes")).scalars())
            assert {"ix_messages_content_fts", "ix_conversations_project_id"} <= indexes


def test_the_conversation_scope_downgrade_refuses_once_conversations_exist(
    engine: Engine, alembic_config: Config
) -> None:
    """One held conversation is enough to make the rollback destructive.

    Not of the conversation itself — the rows would survive — but of the
    guarantee its scope carries. Every message inside it and every `model_calls`
    row attributed to it depends on that `project_id` being the one it was
    recorded under; leaving the column writable again removes the only thing
    keeping that true.
    """
    with _restored_to_head(engine, alembic_config):
        with engine.begin() as connection:
            connection.execute(
                text("insert into conversations (project_id, title) values (null, 'held')")
            )

        with pytest.raises(RuntimeError) as raised:
            command.downgrade(alembic_config, "0007_legacy_attribution_closed")
        assert "Refusing to downgrade" in str(raised.value)
        assert "conversation" in str(raised.value)

        # Refused, not half-applied: the guard is still in place afterwards.
        with engine.connect() as connection:
            triggers = set(
                connection.execute(
                    text("select tgname from pg_trigger where not tgisinternal")
                ).scalars()
            )
            assert "conversations_scope_is_immutable" in triggers


def test_the_message_sequence_guarantees_predate_wp_0_7(engine: Engine) -> None:
    """Audited before `0008` was written, and asserted so it stays true.

    WP-0.7 needs unique, positive, per-conversation sequences. `0001` already
    provided all three, so `0008` added no constraint for them. This records that
    the audit happened and would fail if a later migration dropped what it found.
    """
    with engine.connect() as connection:
        constraints = set(
            connection.execute(
                text("select conname from pg_constraint where conrelid = 'messages'::regclass")
            ).scalars()
        )

    assert "uq_messages_conversation_id_sequence" in constraints
    assert "ck_messages_sequence_positive" in constraints
