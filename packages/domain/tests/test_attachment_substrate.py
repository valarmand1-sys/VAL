"""Attachment Substrate v1.2 holds its own rules, in the database, not by good will.

`docs/contracts/VAL_Attachment_Substrate_v1.md` §5 enumerates the structural
integrity the migration is *bound* to provide. These tests are that enumeration
executed: every rule is attempted from the wrong side and must be refused by
PostgreSQL rather than by application care, because application care is exactly
what a durable record cannot depend on.

The shape of the contract they defend, in one line each:

- **§3.1** the key of a blob *is* the digest of its bytes;
- **§3.2** one content instance per distinct bytes;
- **§3.3** the act accompanies a user message, ordered, classified per act,
  and `restricted` cannot be written at all;
- **§3.4** a derived view resolves to one attachment, and to a parent within it;
- **§3.5** one `started` per attempt, at most one terminal event, matching;
- **§3.6** the binding names an act, a kind, and the exact transmitted digest.
"""

import hashlib
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError

PNG = b"\x89PNG\r\n\x1a\n" + b"pretend pixels, but real bytes"
OTHER = b"\x89PNG\r\n\x1a\n" + b"different pretend pixels"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def put_blob(connection: Connection, payload: bytes, media_type: str = "image/png") -> str:
    connection.execute(
        text("insert into blobs (sha256, byte_size, media_type, bytes) values (:s, :n, :t, :b)"),
        {"s": digest(payload), "n": len(payload), "t": media_type, "b": payload},
    )
    return digest(payload)


@pytest.fixture
def scene(connection: Connection) -> Iterator[dict[str, Any]]:
    """A conversation with a user turn, a Val turn, a call, and one admitted image."""
    project = connection.execute(
        text(
            "insert into projects (name, slug, description, status) "
            "values ('House Armand', 'house-armand', 'The first project.', 'active') "
            "returning id"
        )
    ).scalar_one()
    conversation = connection.execute(
        text("insert into conversations (project_id, title) values (:p, 'A look') returning id"),
        {"p": project},
    ).scalar_one()
    user_message, val_message = (
        connection.execute(
            text(
                "insert into messages (conversation_id, role, content, sequence) "
                "values (:c, :r, :t, :n) returning id"
            ),
            {"c": conversation, "r": role, "t": "Said.", "n": n},
        ).scalar_one()
        for role, n in (("user", 1), ("val", 2))
    )
    call = connection.execute(
        text(
            "insert into model_calls (model_config_id, provider, model_identifier, tokens_in, "
            "tokens_out, cost, project_id, task_type, conversation_id, message_id, latency_ms, "
            "status, cost_certainty, terminal_state, project_attribution, provider_request_id) "
            "values (:cfg, 'openai', 'gpt-5.6-sol', 10, 5, 0.01, :p, 'conversation', :c, :m, 100, "
            "'ok', 'known', 'complete', 'resolved', 'resp_seen') returning id"
        ),
        {"cfg": uuid4(), "p": project, "c": conversation, "m": val_message},
    ).scalar_one()
    sha = put_blob(connection, PNG)
    attachment = connection.execute(
        text("insert into attachments (sha256) values (:s) returning id"), {"s": sha}
    ).scalar_one()
    act = connection.execute(
        text(
            "insert into message_attachments (message_id, attachment_id, position, "
            "given_filename, stated_classification) "
            "values (:m, :a, 1, 'setting.png', 'protected') returning id"
        ),
        {"m": user_message, "a": attachment},
    ).scalar_one()
    yield {
        "project": project,
        "conversation": conversation,
        "user_message": user_message,
        "val_message": val_message,
        "call": call,
        "sha": sha,
        "attachment": attachment,
        "act": act,
    }


def representation(connection: Connection, scene: dict[str, Any], **overrides: Any) -> UUID:  # noqa: ANN401
    """A `model_input_image` derived view of the scene's attachment."""
    sha = overrides.pop("sha256", None) or put_blob(connection, OTHER)
    values: dict[str, Any] = {
        "a": overrides.pop("attachment_id", scene["attachment"]),
        "p": overrides.pop("parent_representation_id", None),
        "t": overrides.pop("representation_type", "model_input_image"),
        "s": sha,
        "d": overrides.pop("derived_by", "Pillow 11.4.0"),
    }
    assert not overrides, overrides
    return connection.execute(
        text(
            "insert into attachment_representations (attachment_id, parent_representation_id, "
            "representation_type, sha256, derived_by) values (:a, :p, :t, :s, :d) returning id"
        ),
        values,
    ).scalar_one()


def bind_image(connection: Connection, scene: dict[str, Any], **overrides: Any) -> None:  # noqa: ANN401
    """Bind an image input to the scene's call, overriding one field at a time."""
    values: dict[str, Any] = {
        "call": overrides.pop("model_call_id", scene["call"]),
        "act": overrides.pop("message_attachment_id", scene["act"]),
        "att": overrides.pop("attachment_id", scene["attachment"]),
        "kind": overrides.pop("input_kind", "original"),
        "rep": overrides.pop("representation_id", None),
        "sha": overrides.pop("transmitted_sha256", scene["sha"]),
        "w": overrides.pop("width", 1024),
        "h": overrides.pop("height", 768),
        "media": overrides.pop("media_type", "image/png"),
        "opts": overrides.pop("provider_options", "{}"),
        "cls": overrides.pop("stated_classification", "protected"),
        "pos": overrides.pop("position", 1),
    }
    assert not overrides, overrides
    connection.execute(
        text(
            "insert into model_call_image_inputs (model_call_id, message_attachment_id, "
            "attachment_id, input_kind, representation_id, transmitted_sha256, width, height, "
            "media_type, provider_options, stated_classification, position) "
            "values (:call, :act, :att, :kind, :rep, :sha, :w, :h, :media, cast(:opts as jsonb), "
            ":cls, :pos)"
        ),
        values,
    )


# --- §3.1 the byte store is content-addressed, and the database knows it ------


def test_a_blob_whose_key_is_not_its_digest_is_refused(connection: Connection) -> None:
    """Content addressing is a constraint, not a convention the writer honours."""
    with pytest.raises(DBAPIError, match="sha256_is_the_digest"):
        connection.execute(
            text(
                "insert into blobs (sha256, byte_size, media_type, bytes) values (:s, :n, :t, :b)"
            ),
            {"s": digest(OTHER), "n": len(PNG), "t": "image/png", "b": PNG},
        )


def test_a_blob_must_state_its_own_length_and_a_real_media_type(connection: Connection) -> None:
    for column, values, expected in (
        ("byte_size", {"n": len(PNG) + 1, "t": "image/png"}, "byte_size_is_the_length"),
        ("media_type", {"n": len(PNG), "t": "setting.png"}, "media_type_is_a_media_type"),
    ):
        with pytest.raises(DBAPIError, match=expected), connection.begin_nested():
            connection.execute(
                text(
                    "insert into blobs (sha256, byte_size, media_type, bytes) "
                    "values (:s, :n, :t, :b)"
                ),
                {"s": digest(PNG), "b": PNG, **values},
            )
        assert column  # the loop names what it is exercising


def test_the_same_bytes_are_one_row_reused_not_a_second_copy(connection: Connection) -> None:
    """Writing bytes whose digest already exists is reuse, not an update (§3.1)."""
    put_blob(connection, PNG)
    with pytest.raises(DBAPIError, match=r"pk_blobs|duplicate key"):
        put_blob(connection, PNG)


# --- §3.2 one content instance per distinct bytes ------------------------------


def test_one_attachment_per_distinct_bytes(connection: Connection, scene: dict[str, Any]) -> None:
    with pytest.raises(DBAPIError, match=r"uq_attachments_sha256|duplicate key"):
        connection.execute(
            text("insert into attachments (sha256) values (:s)"), {"s": scene["sha"]}
        )


# --- §3.3 the act ---------------------------------------------------------------


def test_an_attachment_act_accompanies_a_user_message_only(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """Val's own messages carry no attachments in v1, and the store says so."""
    with pytest.raises(DBAPIError, match="accompanies a user message"):
        connection.execute(
            text(
                "insert into message_attachments (message_id, attachment_id, position, "
                "given_filename, stated_classification) values (:m, :a, 1, 'x.png', 'protected')"
            ),
            {"m": scene["val_message"], "a": scene["attachment"]},
        )


def test_restricted_cannot_be_stated_at_an_act(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§3.3 refuses `restricted` at the act — by it not being a value at all."""
    with pytest.raises(DBAPIError, match=r"invalid input value|attachment_act_classification"):
        connection.execute(
            text(
                "insert into message_attachments (message_id, attachment_id, position, "
                "given_filename, stated_classification) values (:m, :a, 2, 'x.png', 'restricted')"
            ),
            {"m": scene["user_message"], "a": scene["attachment"]},
        )


def test_two_acts_cannot_share_a_position_in_one_turn(
    connection: Connection, scene: dict[str, Any]
) -> None:
    second = put_blob(connection, OTHER)
    other = connection.execute(
        text("insert into attachments (sha256) values (:s) returning id"), {"s": second}
    ).scalar_one()
    with pytest.raises(DBAPIError, match=r"uq_message_attachments_message_position|duplicate key"):
        connection.execute(
            text(
                "insert into message_attachments (message_id, attachment_id, position, "
                "given_filename, stated_classification) values (:m, :a, 1, 'x.png', 'internal')"
            ),
            {"m": scene["user_message"], "a": other},
        )


def test_reuse_is_a_new_act_over_the_same_content_row(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§3.3 — a later turn re-associating the same attachment is a new act with its
    own classification statement, over one content row."""
    later = connection.execute(
        text(
            "insert into messages (conversation_id, role, content, sequence) "
            "values (:c, 'user', 'And this one again.', 3) returning id"
        ),
        {"c": scene["conversation"]},
    ).scalar_one()
    connection.execute(
        text(
            "insert into message_attachments (message_id, attachment_id, position, "
            "given_filename, stated_classification) "
            "values (:m, :a, 1, 'setting.png', 'protected')"
        ),
        {"m": later, "a": scene["attachment"]},
    )
    acts, contents = connection.execute(
        text(
            "select count(*), count(distinct attachment_id) from message_attachments "
            "where attachment_id = :a"
        ),
        {"a": scene["attachment"]},
    ).one()
    assert (acts, contents) == (2, 1), "two acts, one content row"


# --- §3.4 and §5.1 and §5.2 derived views ------------------------------------------


def test_a_parent_representation_must_belong_to_the_same_attachment(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§5.1 — the composite key is what keeps one file's tree one file's tree."""
    foreign_bytes = put_blob(connection, b"\x89PNG\r\n\x1a\nanother file entirely")
    foreign = connection.execute(
        text("insert into attachments (sha256) values (:s) returning id"), {"s": foreign_bytes}
    ).scalar_one()
    parent = representation(connection, scene)
    with pytest.raises(DBAPIError, match="fk_attachment_representations_parent"):
        representation(
            connection,
            scene,
            attachment_id=foreign,
            parent_representation_id=parent,
            sha256=put_blob(connection, b"\x89PNG\r\n\x1a\nderived from the wrong tree"),
        )


def test_a_representation_cannot_parent_itself(
    connection: Connection, scene: dict[str, Any]
) -> None:
    made = representation(connection, scene)
    with pytest.raises(DBAPIError, match=r"no_self_parent|rows are evidence"):
        connection.execute(
            text(
                "update attachment_representations set parent_representation_id = id where id = :r"
            ),
            {"r": made},
        )


def test_only_a_declared_representation_type_may_be_written(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§9 permits additive types — by deliberate migration, never by free text."""
    with pytest.raises(DBAPIError, match="representation_type_declared"):
        representation(connection, scene, representation_type="page_render")


def test_model_provenance_is_both_or_neither(connection: Connection, scene: dict[str, Any]) -> None:
    """§3.4 — non-null exactly when a model produced the representation."""
    with pytest.raises(DBAPIError, match="model_provenance_is_paired"):
        connection.execute(
            text(
                "insert into attachment_representations (attachment_id, representation_type, "
                "sha256, derived_by, model_config_id) "
                "values (:a, 'model_input_image', :s, 'Pillow 11.4.0', :cfg)"
            ),
            {"a": scene["attachment"], "s": put_blob(connection, OTHER), "cfg": uuid4()},
        )


# --- §3.5 attempts, honestly ----------------------------------------------------


def start(connection: Connection, scene: dict[str, Any], attempt: UUID, **overrides: Any) -> None:  # noqa: ANN401
    connection.execute(
        text(
            "insert into attachment_processing_events (attachment_id, attempt_id, intent, event) "
            "values (:a, :t, :i, 'started')"
        ),
        {
            "a": overrides.get("attachment_id", scene["attachment"]),
            "t": attempt,
            "i": overrides.get("intent", "derive:model_input_image"),
        },
    )


def test_one_started_per_attempt(connection: Connection, scene: dict[str, Any]) -> None:
    attempt = uuid4()
    start(connection, scene, attempt)
    with pytest.raises(DBAPIError, match=r"one_started|duplicate key"):
        start(connection, scene, attempt)


def test_at_most_one_terminal_event_per_attempt(
    connection: Connection, scene: dict[str, Any]
) -> None:
    attempt = uuid4()
    start(connection, scene, attempt)
    made = representation(connection, scene)
    connection.execute(
        text(
            "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
            "event, representation_id) "
            "values (:a, :t, 'derive:model_input_image', 'succeeded', :r)"
        ),
        {"a": scene["attachment"], "t": attempt, "r": made},
    )
    with pytest.raises(DBAPIError, match=r"one_terminal|duplicate key"):
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event, error) values (:a, :t, 'derive:model_input_image', 'failed', 'and then')"
            ),
            {"a": scene["attachment"], "t": attempt},
        )


def test_a_terminal_event_requires_and_matches_its_started(
    connection: Connection, scene: dict[str, Any]
) -> None:
    orphan = uuid4()
    with pytest.raises(DBAPIError, match="has no started event"), connection.begin_nested():
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'derive:model_input_image', 'succeeded')"
            ),
            {"a": scene["attachment"], "t": orphan},
        )
    attempt = uuid4()
    start(connection, scene, attempt)
    with pytest.raises(DBAPIError, match="does not match its started"):
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'verify', 'succeeded')"
            ),
            {"a": scene["attachment"], "t": attempt},
        )


def test_a_failure_says_why_and_a_success_does_not_invent_one(
    connection: Connection, scene: dict[str, Any]
) -> None:
    attempt = uuid4()
    start(connection, scene, attempt)
    with pytest.raises(DBAPIError, match="failed_states_why"):
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'derive:model_input_image', 'failed')"
            ),
            {"a": scene["attachment"], "t": attempt},
        )


def test_a_succeeded_derivation_must_name_what_it_produced(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """Owner correction, 20 September 2026, applied before `0024` ever ran on live.

    The rule is now stated in both directions. A `started` may not name a
    representation, because nothing has been produced yet — and a **succeeded
    derivation may not omit one**, because recording that a derivation succeeded
    while producing nothing asserts an event that did not happen.
    """
    made = representation(connection, scene)
    attempt = uuid4()
    with (
        pytest.raises(DBAPIError, match="succeeded_derivation_produces"),
        connection.begin_nested(),
    ):
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event, representation_id) "
                "values (:a, :t, 'derive:model_input_image', 'started', :r)"
            ),
            {"a": scene["attachment"], "t": attempt, "r": made},
        )
    start(connection, scene, attempt)
    with pytest.raises(DBAPIError, match="succeeded_derivation_produces"):
        connection.execute(
            text(
                "insert into attachment_processing_events (attachment_id, attempt_id, intent, "
                "event) values (:a, :t, 'derive:model_input_image', 'succeeded')"
            ),
            {"a": scene["attachment"], "t": attempt},
        )


def test_verify_succeeds_without_producing_anything(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """`verify` keeps its own meaning: it produces nothing, and that is legal."""
    attempt = uuid4()
    start(connection, scene, attempt, intent="verify")
    connection.execute(
        text(
            "insert into attachment_processing_events (attachment_id, attempt_id, intent, event) "
            "values (:a, :t, 'verify', 'succeeded')"
        ),
        {"a": scene["attachment"], "t": attempt},
    )
    events = (
        connection.execute(
            text(
                "select event::text from attachment_processing_events where attempt_id = :t "
                "order by created_at"
            ),
            {"t": attempt},
        )
        .scalars()
        .all()
    )
    assert events == ["started", "succeeded"]


def test_started_alone_is_a_readable_state_and_says_only_that(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """A crash after `started` leaves exactly what a live attempt leaves (§3.5)."""
    attempt = uuid4()
    start(connection, scene, attempt)
    events = (
        connection.execute(
            text("select event::text from attachment_processing_events where attempt_id = :t"),
            {"t": attempt},
        )
        .scalars()
        .all()
    )
    assert events == ["started"], "no terminal outcome is recorded, and none is implied"


# --- §3.6 and §5.3 and §5.4 the binding ---------------------------------------------


def test_the_transmitted_digest_must_be_the_bytes_it_names(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§5 rule 4 — one lookup is trustworthy only if it cannot drift at write time."""
    elsewhere = put_blob(connection, OTHER)
    with pytest.raises(DBAPIError, match="does not match the original"):
        bind_image(connection, scene, transmitted_sha256=elsewhere)


def test_a_representation_binding_states_its_representation_and_its_digest(
    connection: Connection, scene: dict[str, Any]
) -> None:
    derived_bytes = OTHER
    made = representation(connection, scene, sha256=put_blob(connection, derived_bytes))
    # The pairing rule: `representation` requires the id, `original` refuses it.
    with pytest.raises(DBAPIError, match="kind_matches_representation"), connection.begin_nested():
        bind_image(connection, scene, input_kind="representation")
    with pytest.raises(DBAPIError, match="kind_matches_representation"), connection.begin_nested():
        bind_image(connection, scene, representation_id=made)
    # And the digest must be the representation's, not the original's.
    with (
        pytest.raises(DBAPIError, match="does not match the representation"),
        connection.begin_nested(),
    ):
        bind_image(connection, scene, input_kind="representation", representation_id=made)
    bind_image(
        connection,
        scene,
        input_kind="representation",
        representation_id=made,
        transmitted_sha256=digest(derived_bytes),
    )
    kind, sha = connection.execute(
        text(
            "select input_kind::text, transmitted_sha256 from model_call_image_inputs "
            "where model_call_id = :c"
        ),
        {"c": scene["call"]},
    ).one()
    assert (kind, sha) == ("representation", digest(derived_bytes))


def test_the_act_a_binding_names_belongs_to_its_own_attachment(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§5.3a — the act linkage cannot quietly point at another file's act."""
    foreign_bytes = put_blob(connection, b"\x89PNG\r\n\x1a\nsomebody else's file")
    foreign = connection.execute(
        text("insert into attachments (sha256) values (:s) returning id"), {"s": foreign_bytes}
    ).scalar_one()
    foreign_act = connection.execute(
        text(
            "insert into message_attachments (message_id, attachment_id, position, "
            "given_filename, stated_classification) "
            "values (:m, :a, 2, 'other.png', 'internal') returning id"
        ),
        {"m": scene["user_message"], "a": foreign},
    ).scalar_one()
    with pytest.raises(DBAPIError, match="fk_model_call_image_inputs_act"):
        bind_image(connection, scene, message_attachment_id=foreign_act)


def test_two_images_cannot_share_a_position_in_one_call(
    connection: Connection, scene: dict[str, Any]
) -> None:
    bind_image(connection, scene)
    with pytest.raises(DBAPIError, match=r"model_call_position|duplicate key"):
        bind_image(connection, scene)


def test_the_chain_from_call_to_original_bytes_is_resolvable(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§3.6 — call → image input → act → attachment → original blob, in one join."""
    bind_image(connection, scene)
    row = connection.execute(
        text(
            "select i.position, a.given_filename, a.stated_classification::text, "
            "       b.media_type, b.byte_size, m.terminal_state::text "
            "  from model_call_image_inputs i "
            "  join message_attachments a on a.id = i.message_attachment_id "
            "  join attachments t on t.id = i.attachment_id "
            "  join blobs b on b.sha256 = i.transmitted_sha256 "
            "  join model_calls m on m.id = i.model_call_id "
            " where i.model_call_id = :c"
        ),
        {"c": scene["call"]},
    ).one()
    assert row == (1, "setting.png", "protected", "image/png", len(PNG), "complete")


def test_a_binding_is_not_a_claim_of_sight_on_its_own(
    connection: Connection, scene: dict[str, Any]
) -> None:
    """§4 — sight is the binding **and** `terminal_state = 'complete'`.

    A refusal can be produced by a safety layer that never ran vision, so the
    record keeps the two facts separate and a reader must ask for both.
    """
    refused = connection.execute(
        text(
            "insert into model_calls (model_config_id, provider, model_identifier, tokens_in, "
            "tokens_out, cost, project_id, task_type, conversation_id, message_id, latency_ms, "
            "status, cost_certainty, terminal_state, project_attribution, provider_request_id) "
            "values (:cfg, 'openai', 'gpt-5.6-sol', 10, 0, 0.01, :p, 'conversation', :c, :m, 80, "
            "'refused', 'known', 'refused', 'resolved', 'resp_refused') returning id"
        ),
        {
            "cfg": uuid4(),
            "p": scene["project"],
            "c": scene["conversation"],
            "m": scene["val_message"],
        },
    ).scalar_one()
    bind_image(connection, scene, model_call_id=refused)
    sighted = connection.execute(
        text(
            "select count(*) from model_call_image_inputs i join model_calls m "
            "on m.id = i.model_call_id where i.attachment_id = :a "
            "and m.terminal_state = 'complete'"
        ),
        {"a": scene["attachment"]},
    ).scalar_one()
    bound = connection.execute(
        text("select count(*) from model_call_image_inputs where attachment_id = :a"),
        {"a": scene["attachment"]},
    ).scalar_one()
    assert (bound, sighted) == (1, 0), "bound to a refused call is not sight"
