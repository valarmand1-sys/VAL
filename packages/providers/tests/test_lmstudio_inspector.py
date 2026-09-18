"""The LM Studio context inspector — read-only by construction (ruling, 16 September 2026).

The SDK client is a fake here: no socket, no server. What is pinned is the
boundary — already-loaded enumeration only, deterministic selection or
refusal, measurement through the loaded instance's own template and
tokenizer, the credential passed programmatically and rendered nowhere — and
that nothing on the inspector can generate, load, unload or configure.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from types import SimpleNamespace

import lmstudio
import pytest

from val_domain.provider import ContextFeasibility, ContextInspectionUnavailableError
from val_providers.lmstudio_inspector import (
    SOURCE,
    LMStudioContextInspector,
    inspector_host_of,
    is_loopback_host,
)

SENTINEL = "sk-lm-sentinel-value-that-must-never-appear-anywhere"
MODEL = "openai/gpt-oss-20b"


@dataclass
class FakeHandle:
    identifier: str = MODEL
    model_key: str = MODEL
    context_length: int | None = 32_768
    rendered: list[object] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def get_info(self) -> object:
        self.calls.append("get_info")
        return SimpleNamespace(
            identifier=self.identifier,
            model_key=self.model_key,
            context_length=self.context_length,
            max_context_length=131_072,
            format="safetensors",
            architecture="gpt_oss",
            path=MODEL,
        )

    def get_context_length(self) -> int:
        self.calls.append("get_context_length")
        assert self.context_length is not None
        return self.context_length

    opts_seen: list[object] = field(default_factory=list)

    def apply_prompt_template(self, history: object, opts: object = None) -> str:
        self.calls.append("apply_prompt_template")
        self.rendered.append(history)
        self.opts_seen.append(opts)
        parts = [f"<|start|>{m.role}<|message|>{_text(m)}<|end|>" for m in history._messages]  # type: ignore[attr-defined]
        return "".join(parts) + "<|start|>assistant"

    def count_tokens(self, input: str) -> int:
        self.calls.append("count_tokens")
        return len(input) // 4 + 7

    # Anything generative or load-bearing on the SDK handle is a boundary violation.
    def respond(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("the inspector must never generate")

    complete = respond
    stream = respond
    unload = respond


def _text(message: object) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, list):
        return "".join(getattr(part, "text", "") for part in content)
    return str(content)


@dataclass
class FakeLLM:
    handles: list[FakeHandle]
    calls: list[str] = field(default_factory=list)

    def list_loaded(self) -> list[FakeHandle]:
        self.calls.append("list_loaded")
        return list(self.handles)

    def model(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("get-or-load must never be called: it would JIT-load a model")

    def load_new_instance(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("the inspector must never load")

    def unload(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("the inspector must never unload")


@dataclass
class FakeClient:
    llm: FakeLLM
    closed: bool = False

    def close(self) -> None:
        self.closed = True


def _inspector(handles: list[FakeHandle]) -> tuple[LMStudioContextInspector, FakeClient]:
    client = FakeClient(FakeLLM(handles))
    made: list[tuple[str, str]] = []

    def factory(api_host: str, token: str) -> FakeClient:
        made.append((api_host, token))
        return client

    inspector = LMStudioContextInspector("127.0.0.1:1234", SENTINEL, client_factory=factory)
    inspector._made = made  # type: ignore[attr-defined]
    return inspector, client


TURNS = [
    {"role": "system", "content": "persona, whole"},
    {"role": "user", "content": "first question"},
    {"role": "assistant", "content": "first answer"},
    {"role": "user", "content": "VAL-STATE-V1 {...}"},
    {"role": "user", "content": "the current question"},
]


# --- construction ------------------------------------------------------------------------


def test_the_host_must_be_loopback_and_the_token_is_required() -> None:
    assert inspector_host_of("http://127.0.0.1:1234/v1") == "127.0.0.1:1234"
    assert inspector_host_of("http://localhost:1234/v1") == "localhost:1234"
    assert is_loopback_host("127.0.0.1:1234") and is_loopback_host("[::1]:1234")
    assert not is_loopback_host("192.168.1.20:1234")
    with pytest.raises(ValueError, match="must name this machine"):
        LMStudioContextInspector("192.168.1.20:1234", SENTINEL)
    with pytest.raises(ValueError, match="VAL_LMSTUDIO_API_TOKEN"):
        LMStudioContextInspector("127.0.0.1:1234", "")


def test_the_credential_goes_to_the_scoped_client_and_appears_nowhere_else(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    caplog.set_level(logging.DEBUG)
    monkeypatch.delenv("LMSTUDIO_API_TOKEN", raising=False)
    inspector, _ = _inspector([FakeHandle()])
    result = inspector.measure(MODEL, TURNS)
    assert inspector._made == [("127.0.0.1:1234", SENTINEL)], "passed programmatically, once"  # type: ignore[attr-defined]
    rendered = repr(result) + repr(result.details) + caplog.text
    assert SENTINEL not in rendered


def test_the_default_factory_is_the_explicit_scoped_client_with_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from val_providers import lmstudio_inspector as module

    constructed: list[tuple[str, str | None]] = []

    class Recorder:
        def __init__(self, api_host: str, api_token: str | None = None) -> None:
            constructed.append((api_host, api_token))

    monkeypatch.setattr(lmstudio, "Client", Recorder)
    module._default_client("127.0.0.1:1234", SENTINEL)
    assert constructed == [("127.0.0.1:1234", SENTINEL)], "host and token, by keyword, once"
    assert not hasattr(module, "configure_default_client")


# --- the inspector cannot generate or load ---------------------------------------------------


def test_the_inspector_exposes_no_generative_or_load_bearing_method() -> None:
    forbidden = {
        "respond",
        "complete",
        "predict",
        "stream",
        "embed",
        "load",
        "unload",
        "reload",
        "load_new_instance",
        "model",
        "configure",
    }
    exposed = {name for name in dir(LMStudioContextInspector) if not name.startswith("_")}
    assert exposed & forbidden == set()
    assert exposed >= {"loaded_instance", "measure", "close"}
    inspector, _ = _inspector([FakeHandle()])
    assert inspector.sdk_version == lmstudio.__version__


def test_measurement_touches_only_enumeration_info_template_tokenizer_and_context() -> None:
    handle = FakeHandle()
    inspector, client = _inspector([handle])
    inspector.measure(MODEL, TURNS)
    assert client.llm.calls == ["list_loaded"], "never model(), never load, never unload"
    assert set(handle.calls) == {
        "get_info",
        "apply_prompt_template",
        "count_tokens",
        "get_context_length",
    }


# --- loaded-instance selection ---------------------------------------------------------------


def test_zero_matching_loaded_instances_fail_closed_without_loading() -> None:
    inspector, client = _inspector([])
    with pytest.raises(ContextInspectionUnavailableError, match="not resident"):
        inspector.loaded_instance(MODEL)
    assert client.llm.calls == ["list_loaded"]


def test_a_wrong_runtime_identity_fails_closed() -> None:
    inspector, _ = _inspector([FakeHandle(identifier="qwen/qwen3-8b", model_key="qwen/qwen3-8b")])
    with pytest.raises(ContextInspectionUnavailableError, match="not resident"):
        inspector.measure(MODEL, TURNS)


def test_two_indistinguishable_matching_instances_fail_closed() -> None:
    inspector, _ = _inspector([FakeHandle(), FakeHandle()])
    with pytest.raises(ContextInspectionUnavailableError, match="cannot be chosen unambiguously"):
        inspector.measure(MODEL, TURNS)


def test_a_missing_context_length_fails_closed() -> None:
    inspector, _ = _inspector([FakeHandle(context_length=None)])
    with pytest.raises(ContextInspectionUnavailableError, match="no context length"):
        inspector.measure(MODEL, TURNS)


def test_an_unreachable_runtime_fails_closed() -> None:
    def refusing(api_host: str, token: str) -> FakeClient:
        raise ConnectionRefusedError("no server")

    inspector = LMStudioContextInspector("127.0.0.1:1234", SENTINEL, client_factory=refusing)
    with pytest.raises(ContextInspectionUnavailableError, match="could not be opened"):
        inspector.measure(MODEL, TURNS)


def test_the_instance_is_selected_by_identifier_among_others() -> None:
    other = FakeHandle(identifier="text-embedding-nomic", model_key="text-embedding-nomic")
    wanted = FakeHandle(context_length=8_192)
    inspector, _ = _inspector([other, wanted])
    instance, handle = inspector.loaded_instance(MODEL)
    assert handle is wanted and instance.context_length == 8_192
    assert instance.max_context_length == 131_072 and instance.architecture == "gpt_oss"


# --- the measurement ---------------------------------------------------------------------------


def test_measure_uses_the_loaded_instances_template_and_tokenizer_on_the_exact_turns() -> None:
    handle = FakeHandle(context_length=32_768)
    inspector, _ = _inspector([handle])
    result = inspector.measure(MODEL, TURNS)
    assert isinstance(result, ContextFeasibility)
    assert result.source == SOURCE and result.context_tokens == 32_768
    (chat,) = handle.rendered
    roles = [m.role for m in chat._messages]  # type: ignore[attr-defined]
    # The SDK's Chat merges consecutive user messages — recorded here as the SDK's
    # behaviour, not the inspector's: nothing was split, merged or separated by us.
    assert roles == ["system", "user", "assistant", "user"]
    texts = [_text(m) for m in chat._messages]  # type: ignore[attr-defined]
    assert texts[0] == "persona, whole" and texts[2] == "first answer"
    assert "VAL-STATE-V1 {...}" in texts[3] and "the current question" in texts[3]
    rendered_chars = result.details["rendered_chars"]
    assert result.prompt_tokens == rendered_chars // 4 + 7, "the tokenizer's count of the rendering"
    assert result.details["sdk_version"] == lmstudio.__version__
    assert result.details["instance_identifier"] == MODEL and result.details["turns"] == 5


def test_a_runtime_refusing_the_measurement_fails_closed() -> None:
    class Refusing(FakeHandle):
        def apply_prompt_template(self, history: object, opts: object = None) -> str:
            raise RuntimeError("template failed")

    inspector, _ = _inspector([Refusing()])
    with pytest.raises(ContextInspectionUnavailableError, match="refused the measurement"):
        inspector.measure(MODEL, TURNS)


def test_the_session_is_opened_once_and_closed_on_request() -> None:
    inspector, client = _inspector([FakeHandle()])
    inspector.measure(MODEL, TURNS)
    inspector.measure(MODEL, TURNS)
    assert len(inspector._made) == 1  # type: ignore[attr-defined]
    inspector.close()
    assert client.closed


# --- the rendering matches the chat-completions ingress (owner ruling, 18 September 2026) ----


def test_the_preflight_renders_with_end_of_sequence_tokens_omitted_like_the_ingress() -> None:
    from val_providers.lmstudio_inspector import INGRESS_RENDER_OPTIONS

    handle = FakeHandle()
    inspector, _ = _inspector([handle])
    result = inspector.measure(MODEL, TURNS)
    # The one documented option and no more, spelled as the SDK names it.
    expected = [("omitEosToken", True)]
    assert list(INGRESS_RENDER_OPTIONS.items()) == expected
    passed_to_renderer = [list(o.items()) for o in handle.opts_seen]
    assert passed_to_renderer == [expected], "passed to the runtime's renderer"
    assert list(result.details["render_options"].items()) == expected, "recorded on the row"
