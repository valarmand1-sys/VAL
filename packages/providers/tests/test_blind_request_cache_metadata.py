"""A blind-position request without cache metadata is the same request — ruling, 13 September 2026.

The gateway no longer asks for a prompt cache on `blind_position` calls. This
proves at the adapter that the only difference between the request sent with a
cache lifetime and the one sent without is cache-control metadata: the model,
effort, output ceiling, output schema, persona text, message and ordering are
identical. No provider is contacted; the SDK client is a recording fake.
"""

from __future__ import annotations

import copy

from test_anthropic_stream import _adapter, _final, _RecordingClient

from val_domain.gateway import CacheTtl, Message
from val_domain.registry import by_slug

PERSONA = "You are Val, Maester to House Armand. " * 400
BLIND_MESSAGE = Message(
    role="user",
    content="State your own position on the question you are given...\n\nThe question:\nWhich?",
)
#: A schema shaped like the blind position's. The adapter passes it through untouched.
SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "position": {"type": "string"},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "reasoning": {"type": "string"},
    },
    "required": ["position", "confidence", "reasoning"],
    "additionalProperties": False,
}


def _without_cache_metadata(request: dict[str, object]) -> dict[str, object]:
    """The request with every `cache_control` removed and a one-block system flattened."""
    stripped = copy.deepcopy(request)
    system = stripped["system"]
    if isinstance(system, list):
        assert len(system) == 1 and system[0]["type"] == "text"
        stripped["system"] = system[0]["text"]
    for turn in stripped["messages"]:  # type: ignore[attr-defined]
        content = turn["content"]
        if isinstance(content, list):
            for block in content:
                block.pop("cache_control", None)
            if len(content) == 1 and content[0]["type"] == "text":
                turn["content"] = content[0]["text"]
    return stripped


def test_the_uncached_blind_request_differs_only_in_cache_metadata() -> None:
    adapter = _adapter(_RecordingClient(_final(), []))
    config = by_slug("opus-5-medium")
    assert config is not None
    cached = adapter._request(config, (BLIND_MESSAGE,), PERSONA, 4096, SCHEMA, CacheTtl.ONE_HOUR)
    uncached = adapter._request(config, (BLIND_MESSAGE,), PERSONA, 4096, SCHEMA, None)

    assert uncached["system"] == PERSONA, "the persona is sent whole, as plain system text"
    assert cached["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}  # type: ignore[index]
    assert _without_cache_metadata(cached) == _without_cache_metadata(uncached) == uncached
    assert uncached["model"] == "claude-opus-5"
    assert uncached["output_config"] == {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": SCHEMA},
    }
    assert "cache_control" not in repr(uncached)
