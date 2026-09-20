# ruff: noqa: F401 - fixtures and helpers imported by name
"""Attaching an image through the API, and fetching it back to render.

Owner ruling, 19 September 2026 (Track C §13). The API contract stays
provider-neutral: base64 in, a content-addressed byte URL out, and no
provider's own image syntax anywhere in it. Proved here:

- a turn carries admitted images, and the message view reports the acts;
- unreadable bytes and bad base64 are refused with a reason, and nothing is
  written;
- the bytes are fetchable by digest, with their real media type;
- an image is never made addressable to anything outside this machine: the
  provider receives bytes inline, and this endpoint serves the house's own
  interface.
"""

from __future__ import annotations

import io
from base64 import b64encode

import pytest
from PIL import Image
from sqlalchemy import Engine, text
from test_service import ScriptedAdapter, classifier_says, client, ok


def png(width: int = 240, height: int = 180) -> bytes:
    buffer = io.BytesIO()
    image = Image.new("RGB", (width, height), "navy")
    image.paste(Image.new("RGB", (width // 3, height // 3), "white"), (0, 0))
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def attachment(content: bytes, name: str = "frame.png", classification: str = "protected") -> dict:
    return {
        "filename": name,
        "content_base64": b64encode(content).decode(),
        "classification": classification,
    }


def adapter() -> ScriptedAdapter:
    return ScriptedAdapter([classifier_says("not_consequential"), ok("A navy frame, my lord.")])


def test_a_turn_carries_an_image_and_the_view_reports_the_act(store: Engine) -> None:
    payload = png()
    api = client(store, adapter())
    reply = api.post(
        "/turns",
        json={
            "content": "What is in this frame?",
            "no_project": True,
            "attachments": [attachment(payload)],
        },
    )
    assert reply.status_code == 200, reply.text
    conversation = reply.json()["conversation"]["id"]

    detail = api.get(f"/conversations/{conversation}").json()
    user_message = next(m for m in detail["messages"] if m["role"] == "user")
    assert len(user_message["attachments"]) == 1
    act = user_message["attachments"][0]
    assert act["filename"] == "frame.png"
    assert act["classification"] == "protected"
    assert act["media_type"] == "image/png", "established from the bytes"
    assert (act["width"], act["height"]) == (240, 180)
    assert act["byte_size"] == len(payload)
    assert act["position"] == 1

    val_message = next(m for m in detail["messages"] if m["role"] == "val")
    assert val_message["attachments"] == [], "Val's own messages carry none"


def test_the_bytes_come_back_by_digest_with_their_real_media_type(store: Engine) -> None:
    payload = png()
    api = client(store, adapter())
    reply = api.post(
        "/turns",
        json={"content": "This one.", "no_project": True, "attachments": [attachment(payload)]},
    )
    conversation = reply.json()["conversation"]["id"]
    detail = api.get(f"/conversations/{conversation}").json()
    digest = next(m for m in detail["messages"] if m["role"] == "user")["attachments"][0]["sha256"]

    fetched = api.get(f"/attachments/{digest}/bytes")
    assert fetched.status_code == 200
    assert fetched.content == payload
    assert fetched.headers["content-type"] == "image/png"
    assert "immutable" in fetched.headers["cache-control"]


def test_an_unknown_digest_is_a_plain_404(store: Engine) -> None:
    api = client(store, adapter())
    assert api.get(f"/attachments/{'f' * 64}/bytes").status_code == 404


def test_bytes_that_are_not_an_image_are_refused_and_nothing_is_written(store: Engine) -> None:
    api = client(store, adapter())
    reply = api.post(
        "/turns",
        json={
            "content": "Look at this.",
            "no_project": True,
            "attachments": [attachment(b"%PDF-1.7 a document", "notes.pdf")],
        },
    )
    assert reply.status_code == 422
    assert "notes.pdf" in reply.json()["detail"]
    with store.connect() as connection:
        for table in ("blobs", "attachments", "message_attachments", "messages"):
            count = connection.execute(text(f"select count(*) from {table}")).scalar_one()  # noqa: S608
            assert count == 0, f"{table} must be untouched"


def test_base64_that_is_not_base64_is_refused_before_admission(store: Engine) -> None:
    api = client(store, adapter())
    reply = api.post(
        "/turns",
        json={
            "content": "Look at this.",
            "no_project": True,
            "attachments": [{"filename": "x.png", "content_base64": "not base64!!"}],
        },
    )
    assert reply.status_code == 422
    assert "base64" in reply.json()["detail"]


def test_restricted_cannot_be_stated_at_an_act_through_the_api(store: Engine) -> None:
    """§3.3 — the contract offers three values, and the fourth is not one of them."""
    api = client(store, adapter())
    reply = api.post(
        "/turns",
        json={
            "content": "Look at this.",
            "no_project": True,
            "attachments": [attachment(png(), classification="restricted")],
        },
    )
    assert reply.status_code == 422, "refused by the contract, before anything is decoded"


def test_a_text_turn_reports_no_attachments(store: Engine) -> None:
    api = client(store, adapter())
    reply = api.post("/turns", json={"content": "Good evening, Val.", "no_project": True})
    assert reply.status_code == 200
    detail = api.get(f"/conversations/{reply.json()['conversation']['id']}").json()
    assert all(message["attachments"] == [] for message in detail["messages"])
