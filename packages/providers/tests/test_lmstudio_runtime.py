"""Local cognition comes up by itself — owner ruling, 21 September 2026.

The requirement is stated in terms of what Lord Armand does, which is nothing:
he opens Val and Val thinks. No terminal, no server to start, no model to load,
no remembering which backend a question needs.

These drive the supervisor against a fake command runner, so every branch is
exercised without a twelve-gigabyte load: already serving and already loaded;
serving but unloaded, as after an idle unload; not serving at all; loaded at the
wrong window; and each way it can fail. The one thing they pin hardest is the
context length, because the recorded hazard is that a just-in-time reload
restores the model's own smaller default and the exact preflight would then
refuse ordinary turns — correctly, and uselessly.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from val_domain.provider import LocalRuntimeUnavailableError
from val_domain.registry import by_slug
from val_providers.lmstudio_runtime import IDLE_TTL_SECONDS, LMStudioRuntime

CONFIG = by_slug("gpt-oss-20b-mxfp4-mlx-lmstudio-partner")
assert CONFIG is not None


def instance(context: int = 32_768) -> str:
    return json.dumps(
        [{"modelKey": "openai/gpt-oss-20b", "identifier": "gpt-oss-20b", "contextLength": context}]
    )


class FakeRunner:
    """Answers `lms` invocations from a script, and records every argument vector."""

    def __init__(self, *, ps: list[str], start_code: int = 0, load_code: int = 0) -> None:
        self._ps = ps
        self.start_code = start_code
        self.load_code = load_code
        self.calls: list[list[str]] = []

    def run(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
        self.calls.append(list(argv))
        if argv[1:3] == ["server", "start"]:
            return self.start_code, "" if self.start_code == 0 else "could not start"
        if argv[1] == "load":
            return self.load_code, "" if self.load_code == 0 else "out of memory"
        if argv[1] == "ps":
            return 0, self._ps.pop(0) if len(self._ps) > 1 else self._ps[0]
        raise AssertionError(f"unexpected invocation {list(argv)}")

    @property
    def verbs(self) -> list[str]:
        return [call[1] for call in self.calls]


def runtime(runner: FakeRunner, *, serving: bool) -> LMStudioRuntime:
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    engine.serving = lambda: serving  # type: ignore[method-assign]
    return engine


# --- the ordinary cases --------------------------------------------------------------


def test_already_serving_and_already_loaded_does_nothing_at_all() -> None:
    runner = FakeRunner(ps=[instance()])
    report = runtime(runner, serving=True).ensure_ready(CONFIG)

    assert "start" not in " ".join(runner.verbs)
    assert "load" not in runner.verbs, "a loaded model is not reloaded"
    assert report["server_found_running"] is True
    assert report["model_found_loaded"] is True
    assert report["loaded_context_tokens"] == 32_768


def test_an_idle_unload_is_simply_loaded_again() -> None:
    """The whole point of allowing idle unloading: it costs memory, not attention."""
    runner = FakeRunner(ps=["[]", instance()])
    report = runtime(runner, serving=True).ensure_ready(CONFIG)

    assert "load" in runner.verbs
    assert report["model_loaded"] is True and report["model_found_loaded"] is False
    assert report["loaded_context_tokens"] == 32_768


def test_a_stopped_server_is_started_and_then_the_model_is_loaded() -> None:
    runner = FakeRunner(ps=["[]", instance()])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    answers = iter([False, True])
    engine.serving = lambda: next(answers, True)  # type: ignore[method-assign]

    report = engine.ensure_ready(CONFIG)
    assert runner.calls[0][1:3] == ["server", "start"]
    assert report["server_started"] is True and report["model_loaded"] is True


# --- the context length, which is the hazard -----------------------------------------


def test_the_load_names_the_registered_context_rather_than_inheriting_a_default() -> None:
    runner = FakeRunner(ps=["[]", instance()])
    runtime(runner, serving=True).ensure_ready(CONFIG)

    load = next(call for call in runner.calls if call[1] == "load")
    assert load[2] == CONFIG.model_identifier
    assert "--context-length" in load
    assert load[load.index("--context-length") + 1] == str(CONFIG.context_window_tokens) == "32768"
    assert load[load.index("--ttl") + 1] == str(IDLE_TTL_SECONDS)
    assert "--yes" in load, "no prompt to answer, because nobody is at the keyboard"


def test_a_model_loaded_at_a_smaller_window_is_loaded_again_at_the_registered_one() -> None:
    """A just-in-time reload restores the model's own default; that is not enough."""
    runner = FakeRunner(ps=[instance(context=8_192), instance()])
    report = runtime(runner, serving=True).ensure_ready(CONFIG)

    assert "load" in runner.verbs
    assert report["loaded_context_tokens"] == 32_768


def test_a_window_that_comes_back_short_is_a_failure_not_a_shrug() -> None:
    runner = FakeRunner(ps=[instance(context=8_192), instance(context=8_192)])
    with pytest.raises(LocalRuntimeUnavailableError) as caught:
        runtime(runner, serving=True).ensure_ready(CONFIG)
    assert "short of the 32,768" in str(caught.value)


# --- the failures, said plainly -------------------------------------------------------


def test_a_server_that_will_not_start_is_reported_and_not_retried() -> None:
    runner = FakeRunner(ps=["[]"], start_code=1)
    with pytest.raises(LocalRuntimeUnavailableError) as caught:
        runtime(runner, serving=False).ensure_ready(CONFIG)
    assert "did not start" in str(caught.value)
    assert runner.verbs.count("server") == 1, "one bounded attempt, not a loop"


def test_a_model_that_will_not_load_is_reported_and_not_retried() -> None:
    runner = FakeRunner(ps=["[]"], load_code=1)
    with pytest.raises(LocalRuntimeUnavailableError) as caught:
        runtime(runner, serving=True).ensure_ready(CONFIG)
    assert "could not be loaded" in str(caught.value)
    assert "out of memory" in str(caught.value), "the runtime's own words, not a paraphrase"
    assert runner.verbs.count("load") == 1


def test_a_load_that_reports_success_but_no_instance_is_a_failure() -> None:
    runner = FakeRunner(ps=["[]", "[]"])
    with pytest.raises(LocalRuntimeUnavailableError) as caught:
        runtime(runner, serving=True).ensure_ready(CONFIG)
    assert "reports no loaded instance" in str(caught.value)


# --- what it is allowed to run --------------------------------------------------------


def test_nothing_but_the_runtime_s_own_documented_verbs_is_ever_run() -> None:
    """The invariant against arbitrary local command paths, checked mechanically.

    The executable is fixed, the verbs are a closed set, and the only value that
    varies is the model identifier the registry itself declares. No value from a
    model, a document or a tool result reaches any argument.
    """
    runner = FakeRunner(ps=["[]", instance()])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    answers = iter([False, True])
    engine.serving = lambda: next(answers, True)  # type: ignore[method-assign]
    engine.ensure_ready(CONFIG)

    for call in runner.calls:
        assert call[0].endswith("/.lmstudio/bin/lms"), "one fixed executable"
        assert call[1] in {"server", "ps", "load"}, "a closed set of verbs"
        for argument in call[2:]:
            assert argument in {
                "start",
                "--json",
                "--context-length",
                "--ttl",
                "--yes",
                CONFIG.model_identifier,
                str(CONFIG.context_window_tokens),
                str(IDLE_TTL_SECONDS),
            }, f"unexpected argument {argument!r}"


def test_the_token_never_appears_in_the_provenance_it_returns() -> None:
    runner = FakeRunner(ps=[instance()])
    report = runtime(runner, serving=True).ensure_ready(CONFIG)
    assert "a-token" not in json.dumps(dict(report))
