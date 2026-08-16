"""The schema is exactly what 04-layer-0.md §2 specifies, and it holds its rules.

`SPECIFIED` below is §2 transcribed by hand. It is deliberately a second copy
rather than something derived from `val_domain.schema`: comparing the models
against themselves would pass no matter how far either drifted from the document.
Any divergence between §2, the models, and the migrated database fails here.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text

from val_domain.schema import SPECIFIED_TABLES

# --- 04-layer-0.md §2, transcribed -------------------------------------------

SPECIFIED: dict[str, tuple[str, ...]] = {
    # §2.1 Core
    "projects": ("id", "name", "slug", "description", "status", "created_at", "updated_at"),
    "conversations": ("id", "project_id", "title", "started_at", "last_message_at"),
    "messages": ("id", "conversation_id", "role", "content", "created_at", "sequence"),
    "personas": ("id", "version", "content", "is_active", "activated_at", "authored_by"),
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
    ),
    # §2.4 Ideas — amendment, 15 August 2026
    "ideas": ("id", "project_id", "title", "lifecycle_state", "created_at", "updated_at"),
    "idea_state_changes": ("id", "idea_id", "from_state", "to_state", "changed_at"),
}

#: Columns §2 explicitly marks nullable. Everything else is required.
SPECIFIED_NULLABLE: frozenset[tuple[str, str]] = frozenset(
    {
        ("conversations", "project_id"),
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
        # Amendment, 15 August 2026: a reaction with no event is a real record,
        # and a reaction is nullable because most events carry none.
        ("execution_events", "event_type"),
        ("execution_events", "reaction"),
        # §2.4: "no project" is explicit; a null from_state marks creation.
        ("ideas", "project_id"),
        ("idea_state_changes", "from_state"),
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
            "insert into personas (version, content, is_active, activated_at, authored_by) "
            "values (1, 'First.', true, now(), 'Lord Armand')"
        )
    )
    with pytest.raises(Exception, match="uq_personas_single_active"):
        connection.execute(
            text(
                "insert into personas (version, content, is_active, activated_at, authored_by) "
                "values (2, 'Second.', true, now(), 'Lord Armand')"
            )
        )


def test_a_superseded_persona_version_remains(connection: Connection) -> None:
    """Editing creates a version; it never mutates a row, and prior rows survive."""
    connection.execute(
        text(
            "insert into personas (version, content, is_active, activated_at, authored_by) "
            "values (1, 'First.', false, now(), 'Lord Armand'), "
            "(2, 'Second.', true, now(), 'Lord Armand')"
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
