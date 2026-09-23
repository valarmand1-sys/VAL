"""Attachment evidence: admitted, committed atomically, derived once, bound to the call.

Owner ruling, 19 September 2026 (Track C). The gateway owns every decision the
Attachment Substrate v1.2 contract places outside the provider:

- **the atomic evidence commit** (§3.3). Blob, attachment, act and the user
  message land in one transaction, in the same motion that already persists a
  message before any provider is contacted. A failed admission writes nothing at
  all — no blob, no attachment, no association, no processing event, and no user
  message from that send — so remove-before-send leaves no immutable trace of a
  file that was never sent;
- **derive once, reuse** (§7). The transmitted representation is produced here,
  before the reservation, and the same bytes are bound to the blind-position
  call and to the final answer. If those two calls could resize independently,
  the deliberation ledger would be theatre;
- **the binding** (§3.6). Which exact bytes reached which call, through which
  act. A row here is never a claim of sight: §4 reads it together with the
  call's `terminal_state`.

Nothing in this module talks to a provider, and no provider adapter reaches any
of it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from val_domain.gateway import Classification, ImagePart
from val_domain.gateway import ModelConfig as Config
from val_policy.attachments import (
    AdmissionRefusedError,
    Transmission,
    admit_image,
    check_request_limits,
    derivation_required,
    plan_transmission,
    request_load,
)
from val_policy.media import AdmittedMedia, admit_media

#: §3.3 — `restricted` is refused at the act, and the type has no such value.
ACT_CLASSIFICATIONS = (Classification.PUBLIC, Classification.INTERNAL, Classification.PROTECTED)

#: §3.4 — the one representation type v1 declares.
MODEL_INPUT_IMAGE = "model_input_image"
DERIVE_INTENT = f"derive:{MODEL_INPUT_IMAGE}"

_STRICTNESS = {
    Classification.PUBLIC: 0,
    Classification.INTERNAL: 1,
    Classification.PROTECTED: 2,
    Classification.RESTRICTED: 3,
}


@dataclass(frozen=True)
class CandidateAttachment:
    """Ephemeral bytes a client offered with a turn, and what was said about them.

    Not evidence. Nothing about this is written unless every candidate of the
    send is admitted.
    """

    content: bytes
    given_filename: str
    stated_classification: Classification = Classification.PROTECTED


@dataclass(frozen=True)
class AttachmentAct:
    """One committed act: the identity, the association, and the admitted facts.

    Since the owner's execution order of 22 September 2026 an act can be an
    image, a video or a recording. `modality` is established from the bytes at
    admission and is what Core routes on; `width`/`height` stay the image facts
    and are 0 elsewhere, `duration_seconds` is the time-based fact and is None
    for a still image, and `verified` says how far admission actually went.
    """

    act_id: UUID
    attachment_id: UUID
    position: int
    given_filename: str
    stated_classification: Classification
    sha256: str
    media_type: str
    width: int
    height: int
    byte_size: int
    modality: str = "image"
    duration_seconds: float | None = None
    verified: str = "decoded"


@dataclass(frozen=True)
class BoundImage:
    """An act with the exact bytes selected for transmission, and their provenance."""

    act: AttachmentAct
    part: ImagePart
    input_kind: str
    representation_id: UUID | None


def strictest(
    text_classification: Classification, acts: tuple[AttachmentAct, ...]
) -> Classification:
    """§6 — the effective classification is the strictest of the text and every act.

    Ambiguity resolves upward, as it does everywhere else in the house. Cost and
    availability never enter: an image is external egress exactly as text is.
    """
    stated = [text_classification, *(act.stated_classification for act in acts)]
    return max(stated, key=lambda value: _STRICTNESS[value])


def admit_all(candidates: tuple[CandidateAttachment, ...]) -> tuple[AdmittedMedia, ...]:
    """§3.3's preflight over every candidate, before anything is written.

    All or nothing: one unreadable file refuses the whole send rather than
    quietly dropping an image the owner believed he had attached.
    """
    admitted = []
    for position, candidate in enumerate(candidates, start=1):
        if candidate.stated_classification not in ACT_CLASSIFICATIONS:
            raise AdmissionRefusedError(
                f"{candidate.given_filename!r}: {candidate.stated_classification.value} cannot be "
                "stated at an attachment act"
            )
        if not candidate.given_filename.strip():
            raise AdmissionRefusedError(f"attachment {position} was sent without a filename")
        try:
            admitted.append(admit_media(candidate.content))
        except AdmissionRefusedError as refused:
            raise AdmissionRefusedError(f"{candidate.given_filename!r}: {refused}") from refused
    return tuple(admitted)


_INSERT_BLOB = text(
    "insert into blobs (sha256, byte_size, media_type, bytes) values (:s, :n, :t, :b) "
    "on conflict (sha256) do nothing"
)
_INSERT_ATTACHMENT = text(
    "insert into attachments (sha256) values (:s) on conflict (sha256) do nothing returning id"
)
_FIND_ATTACHMENT = text("select id from attachments where sha256 = :s")
_INSERT_ACT = text(
    "insert into message_attachments (message_id, attachment_id, position, given_filename, "
    "stated_classification) values (:m, :a, :p, :f, :c) returning id"
)


def commit_acts(
    connection: object,
    message_id: UUID,
    candidates: tuple[CandidateAttachment, ...],
    admitted: tuple[AdmittedMedia, ...],
) -> tuple[AttachmentAct, ...]:
    """Write blob, attachment and act for each candidate, on an open connection.

    Takes a connection rather than an engine precisely so the caller can put
    this inside the transaction that also writes the user message: §3.3's
    "atomic evidence commit" is one motion or it is not evidence.

    Content addressing makes the blob and the attachment idempotent — the same
    bytes attached twice are one blob and one identity, reused. The **act** is
    always new, with its own classification statement.
    """
    execute = connection.execute  # type: ignore[attr-defined]
    acts: list[AttachmentAct] = []
    for position, (candidate, image) in enumerate(zip(candidates, admitted, strict=True), start=1):
        execute(
            _INSERT_BLOB,
            {
                "s": image.sha256,
                "n": image.byte_size,
                "t": image.media_type,
                "b": image.content,
            },
        )
        attachment_id = execute(_INSERT_ATTACHMENT, {"s": image.sha256}).scalar_one_or_none()
        if attachment_id is None:
            attachment_id = execute(_FIND_ATTACHMENT, {"s": image.sha256}).scalar_one()
        act_id = execute(
            _INSERT_ACT,
            {
                "m": message_id,
                "a": attachment_id,
                "p": position,
                "f": candidate.given_filename,
                "c": candidate.stated_classification.value,
            },
        ).scalar_one()
        acts.append(
            AttachmentAct(
                act_id=act_id,
                attachment_id=attachment_id,
                position=position,
                given_filename=candidate.given_filename,
                stated_classification=candidate.stated_classification,
                sha256=image.sha256,
                media_type=image.media_type,
                width=image.width,
                height=image.height,
                byte_size=image.byte_size,
                modality=image.modality,
                duration_seconds=image.duration_seconds,
                verified=image.verified,
            )
        )
    return tuple(acts)


_ACTS_FOR_MESSAGE = text(
    "select a.id, a.attachment_id, a.position, a.given_filename, "
    "       a.stated_classification::text, b.sha256, b.media_type, b.byte_size "
    "  from message_attachments a "
    "  join attachments t on t.id = a.attachment_id "
    "  join blobs b on b.sha256 = t.sha256 "
    " where a.message_id = :m order by a.position"
)
_BLOB_BYTES = text("select bytes, media_type, byte_size from blobs where sha256 = :s")
_EXISTING_REPRESENTATION = text(
    "select id from attachment_representations "
    " where attachment_id = :a and representation_type = :t and sha256 = :s"
)
_INSERT_REPRESENTATION = text(
    "insert into attachment_representations (attachment_id, representation_type, sha256, "
    "derived_by) values (:a, :t, :s, :d) returning id"
)
_INSERT_EVENT = text(
    "insert into attachment_processing_events (attachment_id, attempt_id, intent, event, "
    "representation_id, error) values (:a, :t, :i, :e, :r, :err)"
)


def acts_for_message(engine: Engine, message_id: UUID) -> tuple[AttachmentAct, ...]:
    """The committed acts of one user message, in the order they were attached.

    Dimensions are re-read from the stored bytes rather than remembered, so a
    view and a binding cannot disagree about what the file is.
    """
    with engine.connect() as connection:
        rows = connection.execute(_ACTS_FOR_MESSAGE, {"m": message_id}).all()
        acts = []
        for row in rows:
            payload = connection.execute(_BLOB_BYTES, {"s": row.sha256}).one()
            admitted = admit_media(payload.bytes)
            acts.append(
                AttachmentAct(
                    act_id=row.id,
                    attachment_id=row.attachment_id,
                    position=row.position,
                    given_filename=row.given_filename,
                    stated_classification=Classification(row.stated_classification),
                    sha256=row.sha256,
                    media_type=row.media_type,
                    width=admitted.width,
                    height=admitted.height,
                    byte_size=row.byte_size,
                    modality=admitted.modality,
                    duration_seconds=admitted.duration_seconds,
                    verified=admitted.verified,
                )
            )
    return tuple(acts)


def prepare(
    engine: Engine, acts: tuple[AttachmentAct, ...], config: Config
) -> tuple[BoundImage, ...]:
    """Select the bytes each act will transmit to this route, deriving once if needed.

    §8's order, binding: *admit → derive if needed → reserve from the dimensions
    of the bytes that will actually be sent → call.* This runs before the
    reservation, and its result is what both calls of a consequential turn bind.

    A derivation that produces bytes already derived reuses that representation
    (content addressing again) rather than writing a second row for identical
    output. **A processing attempt is recorded only when a derivation is
    actually attempted** (owner correction, 20 September 2026): an original
    transmitted unchanged writes no attempt, a real derivation writes `started`
    then `succeeded` naming what it produced, and a real failure writes
    `started` then `failed` with its reason.
    """
    support = config.image_input
    if support is None and acts:
        raise AdmissionRefusedError(
            f"{config.slug} declares no image input; this turn cannot be routed there"
        )
    bound: list[BoundImage] = []
    for act in acts:
        with engine.connect() as connection:
            payload = connection.execute(_BLOB_BYTES, {"s": act.sha256}).one()
        admitted = admit_image(payload.bytes)
        if support is None:  # unreachable: `acts` non-empty implies support above
            raise AdmissionRefusedError(f"{config.slug} declares no image input")
        # Owner correction, 20 September 2026: a processing attempt is recorded
        # only when a derivation is actually attempted. An original transmitted
        # unchanged produces no `derive:model_input_image` row at all — the
        # honest record of a derivation that did not happen is silence, not a
        # success. `verify` keeps its own separate meaning and is not invented
        # here to give an unchanged original something to point at.
        if not derivation_required(admitted, support):
            plan: Transmission = plan_transmission(admitted, support)
            representation_id: UUID | None = None
        else:
            attempt = uuid4()
            with engine.begin() as connection:
                connection.execute(
                    _INSERT_EVENT,
                    {
                        "a": act.attachment_id,
                        "t": attempt,
                        "i": DERIVE_INTENT,
                        "e": "started",
                        "r": None,
                        "err": None,
                    },
                )
            try:
                plan = plan_transmission(admitted, support)
            except AdmissionRefusedError as refused:
                # A real attempt that really failed, durably recorded with its
                # reason before the refusal travels on.
                with engine.begin() as connection:
                    connection.execute(
                        _INSERT_EVENT,
                        {
                            "a": act.attachment_id,
                            "t": attempt,
                            "i": DERIVE_INTENT,
                            "e": "failed",
                            "r": None,
                            "err": str(refused),
                        },
                    )
                raise
            representation_id = None
            with engine.begin() as connection:
                representation_id = connection.execute(
                    _EXISTING_REPRESENTATION,
                    {"a": act.attachment_id, "t": MODEL_INPUT_IMAGE, "s": plan.sha256},
                ).scalar_one_or_none()
                if representation_id is None:
                    connection.execute(
                        _INSERT_BLOB,
                        {
                            "s": plan.sha256,
                            "n": plan.byte_size,
                            "t": plan.media_type,
                            "b": plan.content,
                        },
                    )
                    representation_id = connection.execute(
                        _INSERT_REPRESENTATION,
                        {
                            "a": act.attachment_id,
                            "t": MODEL_INPUT_IMAGE,
                            "s": plan.sha256,
                            "d": plan.derived_by,
                        },
                    ).scalar_one()
                # The representation row and its `succeeded` event commit in ONE
                # transaction (§3.5 rule 6): otherwise the representation could
                # say *done* while the trail said only *started*.
                connection.execute(
                    _INSERT_EVENT,
                    {
                        "a": act.attachment_id,
                        "t": attempt,
                        "i": DERIVE_INTENT,
                        "e": "succeeded",
                        "r": representation_id,
                        "err": None,
                    },
                )
        bound.append(
            BoundImage(
                act=act,
                part=ImagePart(
                    sha256=plan.sha256,
                    media_type=plan.media_type,
                    width=plan.width,
                    height=plan.height,
                    content=plan.content,
                ),
                input_kind="representation" if plan.derived else "original",
                representation_id=representation_id,
            )
        )
    # Owner ruling, 20 September 2026: the aggregate request is verified here —
    # after every attachment is admitted and its exact transmitted
    # representation derived and measured, and BEFORE any of it reaches a
    # provider. A turn whose images are each individually valid can still be an
    # invalid request; discovering that at the provider means the pixels have
    # already left. Core owns this, not an adapter, and the refusal drops no
    # attachment and splits no turn to make it fit.
    if bound:
        if support is None:  # unreachable: `acts` non-empty implies support above
            raise AdmissionRefusedError(f"{config.slug} declares no image input")
        check_request_limits(
            request_load([(image.part.media_type, len(image.part.content)) for image in bound]),
            support,
        )
    return tuple(bound)


_INSERT_BINDING = text(
    "insert into model_call_image_inputs (model_call_id, message_attachment_id, attachment_id, "
    "input_kind, representation_id, transmitted_sha256, width, height, media_type, "
    "provider_options, stated_classification, position) "
    "values (:call, :act, :att, :kind, :rep, :sha, :w, :h, :media, "
    "cast(:opts as jsonb), :cls, :pos)"
)


def bind_to_call(
    engine: Engine, model_call_id: UUID, bound: tuple[BoundImage, ...], config: Config
) -> None:
    """§3.6 — record which bytes reached this call, through which act.

    Written after the call is recorded, from the same plan that was transmitted.
    `provider_options` carries the detail level, because it changes both pricing
    and interpretation and the record is meant to survive the day it was made.
    """
    if not bound:
        return
    support = config.image_input
    # Serialised rather than formatted: a provider option is data, and a hand-built
    # JSON literal is one escaping mistake away from a record that will not parse.
    options = json.dumps({} if support is None else {"detail": support.provider.detail})
    with engine.begin() as connection:
        for image in bound:
            connection.execute(
                _INSERT_BINDING,
                {
                    "call": model_call_id,
                    "act": image.act.act_id,
                    "att": image.act.attachment_id,
                    "kind": image.input_kind,
                    "rep": image.representation_id,
                    "sha": image.part.sha256,
                    "w": image.part.width,
                    "h": image.part.height,
                    "media": image.part.media_type,
                    "opts": options,
                    "cls": image.act.stated_classification.value,
                    "pos": image.act.position,
                },
            )


#: The same count, split by what the media actually are. The media type is on
#: the blob, established from the bytes at admission, so this asks the record
#: rather than the filename.
_EARLIER_BY_KIND = text(
    "select count(*) filter (where b.media_type like 'audio/%') as audio, "
    "       count(*) filter (where b.media_type not like 'audio/%') as visual "
    "  from message_attachments a "
    "  join messages m on m.id = a.message_id "
    "  join attachments t on t.id = a.attachment_id "
    "  join blobs b on b.sha256 = t.sha256 "
    " where m.conversation_id = :c and a.message_id <> :m"
)


def earlier_media_counts(
    engine: Engine, conversation_id: UUID, message_id: UUID
) -> tuple[int, int]:
    """(visual, audio) attachment acts this conversation holds outside this turn.

    Two numbers rather than one because they feed two different envelope fields,
    and because *we discussed a photograph* and *we discussed a recording* are
    different facts that must not be reported as one.
    """
    with engine.connect() as connection:
        row = connection.execute(_EARLIER_BY_KIND, {"c": conversation_id, "m": message_id}).one()
    return int(row.visual), int(row.audio)


def blob_bytes(engine: Engine, sha256: str) -> tuple[bytes, str] | None:
    """The stored bytes and their media type, by digest, or None.

    For the house's own interface to render what it already holds. An image is
    handed to a provider **inline**, never as a URL, so nothing here makes an
    attachment addressable to anything outside the machine.
    """
    with engine.connect() as connection:
        row = connection.execute(_BLOB_BYTES, {"s": sha256}).one_or_none()
    return None if row is None else (bytes(row.bytes), str(row.media_type))
