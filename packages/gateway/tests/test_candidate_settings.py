"""The two candidate settings of 27 September 2026 — off unless set, refused when malformed."""

from __future__ import annotations

import pytest

from val_gateway.startup import configured_adaptive_endpoint, configured_request_construction


def test_both_are_off_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VAL_ADAPTIVE_ENDPOINT", raising=False)
    monkeypatch.delenv("VAL_REQUEST_CONSTRUCTION", raising=False)
    assert configured_adaptive_endpoint() == (False, None)
    assert configured_request_construction() == ("as_is", None)


def test_each_is_on_only_by_its_exact_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VAL_ADAPTIVE_ENDPOINT", "ON")
    monkeypatch.setenv("VAL_REQUEST_CONSTRUCTION", "envelope_in_system")
    assert configured_adaptive_endpoint() == (True, None)
    assert configured_request_construction() == ("envelope_in_system", None)


@pytest.mark.parametrize("value", ["yes", "1", "true", "adaptive"])
def test_a_malformed_endpoint_setting_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("VAL_ADAPTIVE_ENDPOINT", value)
    enabled, problem = configured_adaptive_endpoint()
    assert enabled is False and problem is not None


@pytest.mark.parametrize("value", ["developer", "system", "on"])
def test_a_malformed_construction_setting_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("VAL_REQUEST_CONSTRUCTION", value)
    construction, problem = configured_request_construction()
    assert construction == "as_is" and problem is not None


def test_the_speech_bound_is_off_unless_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from val_gateway.startup import configured_tts_bound

    monkeypatch.delenv("VAL_TTS_LENGTH_BOUND", raising=False)
    assert configured_tts_bound() == (False, None)
    monkeypatch.setenv("VAL_TTS_LENGTH_BOUND", "on")
    assert configured_tts_bound() == (True, None)
    monkeypatch.setenv("VAL_TTS_LENGTH_BOUND", "yes")
    assert configured_tts_bound()[1] is not None


def test_the_bound_never_clips_ordinary_speech_and_stops_a_runaway() -> None:
    """Her ordinary pace is ~13-15 characters per second; the bound allows 5 plus 4 s."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "infrastructure/speech/qwen_tts_speak_bounded.py"
    spec = importlib.util.spec_from_file_location("bounded", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    greeting = "Good evening, my lord."
    sentence = "A caesura is a pause within a line of verse, marked by sense or punctuation."
    for text in (greeting, sentence, sentence * 3):
        ordinary_seconds = len(text) / 13.0 + 0.5
        assert (
            module.max_speech_tokens(text) / module.CODEC_TOKENS_PER_SECOND > 2.5 * ordinary_seconds
        )
    assert module.max_speech_tokens(sentence) / module.CODEC_TOKENS_PER_SECOND < 30, (
        "a 128 s runaway is cut well short"
    )
