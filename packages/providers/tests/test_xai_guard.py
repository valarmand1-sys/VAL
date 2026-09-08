"""The xAI zero-data-retention guard — preparation only (ruling, 8 September 2026).

xAI is not admitted and nothing registers this adapter. These tests prove the
one structural condition of a future admission: without an affirmative
`x-zero-data-retention: true` on the response, the text is withheld and the
call is refused as a data-policy failure.
"""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest

from val_domain.gateway import (
    AdapterStatus,
    Admission,
    CapabilityProfile,
    Classification,
    GatewayError,
    GatewayErrorKind,
    Message,
    ModelConfig,
    ReasoningEffort,
    TerminalState,
)
from val_providers.xai_adapter import ZDR_HEADER, XAIAdapter, zdr_confirmed


def _config() -> ModelConfig:
    return ModelConfig(
        id=uuid4(),
        slug="xai-probe",
        provider="xai",
        model_identifier="grok-4.6",
        display_name="probe",
        context_window_tokens=500_000,
        max_output_tokens=32_000,
        reasoning_effort=ReasoningEffort.HIGH,
        cost_per_mtok_in_usd=2.0,
        cost_per_mtok_out_usd=6.0,
        eligible_classifications=frozenset({Classification.PUBLIC}),
        capability_profiles=frozenset({CapabilityProfile.STRUCTURED}),
        fallback_slug=None,
        admission=Admission.NOT_ADMITTED,
        adapter_status=AdapterStatus.IMPLEMENTED,
        activated_on=date(2026, 9, 8),
        rates_verified_on=date(2026, 9, 8),
    )


class _Raw:
    def __init__(self, headers: dict[str, str], body: object) -> None:
        self.headers = headers
        self._body = body

    def parse(self) -> object:
        return self._body


class _FakeClient:
    def __init__(self, raw: _Raw) -> None:
        self.kwargs: dict[str, object] = {}
        self._raw = raw
        self.chat = self
        self.completions = self
        self.with_raw_response = self

    def create(self, **kwargs: object) -> _Raw:
        self.kwargs = kwargs
        return self._raw


def _body(text: str = "an answer", finish: str = "stop") -> object:
    return SimpleNamespace(
        id="resp-x",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=text, refusal=None), finish_reason=finish
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5),
    )


def _adapter(raw: _Raw) -> tuple[XAIAdapter, _FakeClient]:
    adapter = XAIAdapter.__new__(XAIAdapter)
    fake = _FakeClient(raw)
    adapter._client = fake
    return adapter, fake


MESSAGES = (Message(role="user", content="Good evening."),)


def test_the_header_must_affirm_true() -> None:
    assert zdr_confirmed({ZDR_HEADER: "true"})
    assert zdr_confirmed({"X-Zero-Data-Retention": " TRUE "})
    assert not zdr_confirmed({ZDR_HEADER: "false"})
    assert not zdr_confirmed({})
    assert not zdr_confirmed({ZDR_HEADER: ""})


def test_an_affirmed_response_is_handed_onward() -> None:
    adapter, fake = _adapter(_Raw({ZDR_HEADER: "true"}, _body()))
    result = adapter.complete(_config(), MESSAGES, "persona", 64)
    assert result.text == "an answer" and result.terminal is TerminalState.COMPLETE
    assert result.tokens_in == 10 and result.tokens_out == 5
    assert fake.kwargs["messages"][0] == {"role": "system", "content": "persona"}
    assert fake.kwargs["reasoning_effort"] == "high"
    assert "prompt_cache_key" not in fake.kwargs and "extra_headers" not in fake.kwargs


def test_a_response_without_the_header_is_refused_and_its_text_withheld() -> None:
    adapter, _ = _adapter(_Raw({}, _body("must not be seen")))
    with pytest.raises(GatewayError) as caught:
        adapter.complete(_config(), MESSAGES, "persona", 64)
    assert caught.value.kind is GatewayErrorKind.NOT_ELIGIBLE
    assert "must not be seen" not in str(caught.value)
    assert "absent" in str(caught.value)


def test_a_response_denying_zdr_is_refused() -> None:
    adapter, _ = _adapter(_Raw({ZDR_HEADER: "false"}, _body("must not be seen")))
    with pytest.raises(GatewayError) as caught:
        adapter.complete(_config(), MESSAGES, "persona", 64)
    assert caught.value.kind is GatewayErrorKind.NOT_ELIGIBLE
    assert "false" in str(caught.value)


def test_the_schema_is_sent_strict_and_the_ttl_is_not_sent() -> None:
    from val_domain.gateway import CacheTtl

    adapter, fake = _adapter(_Raw({ZDR_HEADER: "true"}, _body('{"a": 1}')))
    adapter.complete(
        _config(),
        MESSAGES,
        "persona",
        64,
        output_schema={"type": "object"},
        cache_ttl=CacheTtl.ONE_HOUR,
    )
    assert fake.kwargs["response_format"]["json_schema"]["strict"] is True
    assert "cache_control" not in fake.kwargs


def test_nothing_registers_the_adapter() -> None:
    """Not admitted: no registry entry names the provider. (That startup builds no
    adapter for it is asserted on the gateway side, where startup lives.)"""
    from val_domain.registry import REGISTRY

    assert all(config.provider != "xai" for config in REGISTRY)
