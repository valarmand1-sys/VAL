"""The llama.cpp inspector — read-only by construction (owner ruling, 18 September 2026)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

import pytest

from val_domain.provider import ContextFeasibility, ContextInspectionUnavailableError
from val_providers.llamacpp_inspector import (
    APPLY_TEMPLATE_PATH,
    INPUT_TOKENS_PATH,
    MODELS_PATH,
    PROPS_PATH,
    SOURCE,
    LlamaCppContextInspector,
    compare_with_pinned_template,
)

SENTINEL = "llamacpp-sentinel-value-that-must-never-appear-anywhere"
BASE = "http://127.0.0.1:8766/v1"
MODEL = "gemma-4-31b-it-q6_k"
TEMPLATE = "the official template text, byte for byte"
BODY = {
    "model": MODEL,
    "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
    "max_tokens": 6144,
    "chat_template_kwargs": {"enable_thinking": True, "preserve_thinking": False},
}


class Reply:
    def __init__(self, payload: object, fail: bool = False) -> None:
        self.payload, self.fail = payload, fail

    def raise_for_status(self) -> None:
        if self.fail:
            raise RuntimeError("http 500")

    def json(self) -> object:
        return self.payload


@dataclass
class FakeHttp:
    n_ctx: int | None = 32_768
    ids: tuple[str, ...] = (MODEL,)
    tokens: object = 5_400
    fail: str | None = None
    calls: list[tuple[str, str, object]] = field(default_factory=list)

    def get(self, url: str, *, headers: dict[str, str], timeout: float) -> Reply:
        path = url.removeprefix("http://127.0.0.1:8766")
        self.calls.append(("GET", path, None))
        assert headers["Authorization"].endswith(SENTINEL)
        if path == PROPS_PATH:
            return Reply(
                {
                    "default_generation_settings": {"n_ctx": self.n_ctx},
                    "total_slots": 1,
                    "model_path": "/models/gemma-4-31B-it-Q6_K.gguf",
                    "build_info": "b10360-48d22e295",
                    "chat_template": TEMPLATE,
                },
                fail=self.fail == path,
            )
        return Reply({"data": [{"id": i} for i in self.ids]}, fail=self.fail == path)

    def post(self, url: str, *, headers: dict[str, str], json: object, timeout: float) -> Reply:
        path = url.removeprefix("http://127.0.0.1:8766")
        self.calls.append(("POST", path, json))
        if path == INPUT_TOKENS_PATH:
            return Reply({"input_tokens": self.tokens}, fail=self.fail == path)
        return Reply({"prompt": "<bos>rendered"}, fail=self.fail == path)


def _inspector(http: FakeHttp) -> LlamaCppContextInspector:
    return LlamaCppContextInspector(BASE, SENTINEL, http=http)


def test_loopback_and_the_dedicated_key_are_required() -> None:
    with pytest.raises(ValueError, match="must name this machine"):
        LlamaCppContextInspector("http://192.168.1.20:8766/v1", SENTINEL)
    with pytest.raises(ValueError, match="VAL_LLAMACPP_API_KEY"):
        LlamaCppContextInspector(BASE, "")


def test_only_the_four_read_only_endpoints_are_ever_called() -> None:
    http = FakeHttp()
    inspector = _inspector(http)
    inspector.measure(MODEL, BODY)
    inspector.render(BODY)
    paths = {path for _, path, _ in http.calls}
    assert paths == {PROPS_PATH, MODELS_PATH, INPUT_TOKENS_PATH, APPLY_TEMPLATE_PATH}
    exposed = {n for n in dir(LlamaCppContextInspector) if not n.startswith("_")}
    assert exposed & {"complete", "stream", "respond", "generate", "load", "unload"} == set()


def test_the_body_counted_is_exactly_the_body_given() -> None:
    http = FakeHttp()
    result = _inspector(http).measure(MODEL, BODY)
    counted = [body for method, path, body in http.calls if path == INPUT_TOKENS_PATH]
    assert counted == [BODY]
    assert isinstance(result, ContextFeasibility)
    assert result.prompt_tokens == 5_400 and result.context_tokens == 32_768
    assert result.source == SOURCE
    assert result.details["chat_template_sha256"] == hashlib.sha256(TEMPLATE.encode()).hexdigest()
    assert result.details["build_info"] == "b10360-48d22e295" and result.details["total_slots"] == 1


def test_the_runtime_context_is_read_from_the_server_never_assumed() -> None:
    assert _inspector(FakeHttp(n_ctx=8_192)).measure(MODEL, BODY).context_tokens == 8_192
    with pytest.raises(ContextInspectionUnavailableError, match="no context length"):
        _inspector(FakeHttp(n_ctx=None)).measure(MODEL, BODY)


def test_a_server_that_does_not_answer_to_the_identifier_fails_closed() -> None:
    with pytest.raises(ContextInspectionUnavailableError, match="does not answer to"):
        _inspector(FakeHttp(ids=("another-model",))).measure(MODEL, BODY)


def test_an_unusable_count_or_a_failing_endpoint_fails_closed() -> None:
    with pytest.raises(ContextInspectionUnavailableError, match="no usable input-token count"):
        _inspector(FakeHttp(tokens=None)).measure(MODEL, BODY)
    for path in (PROPS_PATH, MODELS_PATH, INPUT_TOKENS_PATH):
        with pytest.raises(ContextInspectionUnavailableError, match="unavailable"):
            _inspector(FakeHttp(fail=path)).measure(MODEL, BODY)


def test_the_key_is_rendered_nowhere(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    result = _inspector(FakeHttp()).measure(MODEL, BODY)
    assert SENTINEL not in repr(result) + repr(result.details) + caplog.text


# --- the template pin: one terminal LF and nothing else (owner ruling, 18 September 2026) ----

OFFICIAL = b"{%- if x -%}\nbody\n{%- endif -%}\n"


def test_exact_raw_equality_passes() -> None:
    identity = compare_with_pinned_template(OFFICIAL, OFFICIAL.decode())
    assert identity.raw_equal and identity.accepted
    assert identity.raw_official_sha256 == identity.active_sha256


def test_the_one_terminal_lf_the_server_drops_is_accepted_and_all_three_hashes_are_kept() -> None:
    active = OFFICIAL[:-1].decode()
    identity = compare_with_pinned_template(OFFICIAL, active)
    assert not identity.raw_equal and identity.canonical_equal and identity.accepted
    assert identity.raw_official_sha256 == hashlib.sha256(OFFICIAL).hexdigest()
    assert identity.canonical_official_sha256 == hashlib.sha256(OFFICIAL[:-1]).hexdigest()
    assert identity.active_sha256 == identity.canonical_official_sha256
    assert identity.raw_official_sha256 != identity.active_sha256, (
        "the upstream hash is not rewritten"
    )


def test_two_terminal_lf_bytes_do_not_silently_pass() -> None:
    pinned = OFFICIAL + b"\n"
    assert not compare_with_pinned_template(pinned, OFFICIAL.decode()).accepted
    assert not compare_with_pinned_template(pinned, OFFICIAL[:-1].decode()).accepted
    assert compare_with_pinned_template(pinned, OFFICIAL.decode()).canonical_official_sha256 is None
    assert not compare_with_pinned_template(OFFICIAL, OFFICIAL[:-2].decode()).accepted


def test_trailing_spaces_do_not_pass() -> None:
    assert not compare_with_pinned_template(OFFICIAL, OFFICIAL[:-1].decode() + " ").accepted
    assert not compare_with_pinned_template(OFFICIAL[:-1] + b" \n", OFFICIAL[:-1].decode()).accepted


def test_crlf_changes_do_not_pass() -> None:
    crlf = OFFICIAL.replace(b"\n", b"\r\n")
    assert not compare_with_pinned_template(crlf, OFFICIAL[:-1].decode()).accepted
    assert not compare_with_pinned_template(OFFICIAL, crlf[:-1].decode()).accepted


def test_an_interior_byte_change_does_not_pass() -> None:
    changed = OFFICIAL[:-1].decode().replace("body", "bodY")
    identity = compare_with_pinned_template(OFFICIAL, changed)
    assert not identity.raw_equal and not identity.canonical_equal and not identity.accepted


def test_a_pinned_file_without_a_terminal_lf_has_no_canonical_form() -> None:
    pinned = OFFICIAL[:-1]
    assert compare_with_pinned_template(pinned, pinned.decode()).accepted, "raw equality"
    assert not compare_with_pinned_template(pinned, pinned[:-1].decode()).accepted
