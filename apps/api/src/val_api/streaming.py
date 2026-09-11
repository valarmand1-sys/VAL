"""The streamed turn — Val's generated text to the interface as it is produced.

Responsiveness phase, 11 September 2026. The desktop asks for a turn on
`POST /turns/stream` and receives server-sent events:

    event: delta      data: {"text": "…"}            — generated text, in order
    event: settled    data: {…TurnResponse…, "timing": {…}}   — the same object
                                                           `POST /turns` returns
    event: refused    data: {"detail": "…"}          — a Restricted refusal (the
                                                       403 of the plain route)
    event: error      data: {"detail": "…"}          — an unexpected failure

**Every delta comes through Val Core.** The generator here owns the sink it
hands to `deliberate.send`; the gateway forwards the provider's text to that
sink and nothing else; the orchestrator withholds the reconciliation verdict
block on consequential turns before the sink ever sees it. Nothing here reads
a provider. The `settled` event is built by the same function that builds the
plain route's response, from the same outcome object, so what the desktop
finally shows is what was persisted — the deltas are presentation of the
generation in progress, and the settled text replaces them.

Timing, reported with the settled event and kept explicit about where it was
measured: `gateway_first_output_ms` and `gateway_latency_ms` are the provider
call as the gateway saw it (time to first generated-text delta, and the call's
completion); `api_first_delta_ms` and `api_total_ms` are measured here, from
the moment the request handler began to the moment the first delta and the
final event were handed to the response. Neither is what a person sees; the
user-visible figure is measured at the interface.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from pydantic import BaseModel
from sqlalchemy import Engine

from val_api.contracts import TurnRequest
from val_gateway.deliberate import DeliberatedOutcome
from val_gateway.deliberate import send as deliberated_send
from val_gateway.exchange import RestrictedContentRefusedError
from val_gateway.gateway import Gateway
from val_gateway.loop import TruncatedTurn, Turn
from val_gateway.projects import load_catalogue
from val_policy.project_resolution import ProjectSignals

_LOGGER = logging.getLogger("val.api.stream")


def sse(event: str, data: object) -> bytes:
    """One server-sent event frame. `data` is serialised as one JSON line."""
    body = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {body}\n\n".encode()


@dataclass(frozen=True)
class _Delta:
    text: str


@dataclass(frozen=True)
class _Done:
    outcome: DeliberatedOutcome


@dataclass(frozen=True)
class _Failed:
    error: BaseException


def turn_event_stream(
    engine: Engine,
    gateway: Gateway,
    request: TurnRequest,
    render: Callable[[DeliberatedOutcome], BaseModel],
) -> Iterator[bytes]:
    """Run one deliberated turn on a worker thread; yield its events as they happen.

    `render` is the plain route's own outcome-to-response function, so the
    settled payload is identical in shape and content to `POST /turns`.
    """
    started = time.monotonic()
    events: queue.Queue[_Delta | _Done | _Failed] = queue.Queue()

    def run() -> None:
        try:
            outcome = deliberated_send(
                engine,
                gateway,
                request.content,
                catalogue=load_catalogue(engine),
                signals=ProjectSignals(
                    explicit_selection=request.project,
                    explicit_no_project=request.no_project,
                ),
                conversation_id=request.conversation_id,
                title=request.title,
                max_output_tokens=request.max_output_tokens,
                on_delta=lambda text: events.put(_Delta(text)),
            )
        except BaseException as error:
            events.put(_Failed(error))
            return
        events.put(_Done(outcome))

    threading.Thread(target=run, name="val-turn-stream", daemon=True).start()

    first_delta_ms: int | None = None
    while True:
        item = events.get()
        if isinstance(item, _Delta):
            if first_delta_ms is None:
                first_delta_ms = int((time.monotonic() - started) * 1000)
            yield sse("delta", {"text": item.text})
            continue
        if isinstance(item, _Failed):
            if isinstance(item.error, RestrictedContentRefusedError):
                yield sse("refused", {"detail": str(item.error)})
            else:
                _LOGGER.exception("streamed turn failed", exc_info=item.error)
                yield sse("error", {"detail": str(item.error)})
            return
        outcome = item.outcome
        payload = render(outcome).model_dump(mode="json")
        payload["timing"] = _timing(outcome, first_delta_ms, started)
        yield sse("settled", payload)
        return


def _timing(
    outcome: DeliberatedOutcome, first_delta_ms: int | None, started: float
) -> dict[str, int | None]:
    gateway_first: int | None = None
    gateway_latency: int | None = None
    turn = getattr(outcome, "turn", None)
    if isinstance(turn, Turn | TruncatedTurn):
        gateway_first = turn.response.first_output_ms
        gateway_latency = turn.response.latency_ms
    return {
        "gateway_first_output_ms": gateway_first,
        "gateway_latency_ms": gateway_latency,
        "api_first_delta_ms": first_delta_ms,
        "api_total_ms": int((time.monotonic() - started) * 1000),
    }
