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
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager

import pytest

from val_domain.provider import LocalRuntimeUnavailableError
from val_domain.registry import by_slug
from val_providers.lmstudio_runtime import IDLE_TTL_SECONDS, SERVING_PARALLEL, LMStudioRuntime

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
    # These tests drive the CLI residency path deliberately: they are about the
    # load/reload state machine, and the command-line tool is where its argument
    # vectors are observable. The HTTP observation is turned off explicitly rather
    # than left to fail by accident — on a developer machine with LM Studio running
    # it would otherwise answer with the real model and these fakes would describe
    # nothing (latency pass §12, when the HTTP source was added).
    engine._loaded_over_http = lambda: None  # type: ignore[method-assign]
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
                # Owner order, 25 September 2026: sequential serving, so the persona
                # prefix can be reused. A fixed constant of this module, not a value
                # anything outside it supplies — the set stays closed.
                "--parallel",
                str(SERVING_PARALLEL),
            }, f"unexpected argument {argument!r}"


def test_the_token_never_appears_in_the_provenance_it_returns() -> None:
    runner = FakeRunner(ps=[instance()])
    report = runtime(runner, serving=True).ensure_ready(CONFIG)
    assert "a-token" not in json.dumps(dict(report))


# --- residency over HTTP, and the fallback — latency pass §12 -------------------------


class FakeListing:
    """The server's native model listing, as an opener would return it.

    Takes a script, like `FakeRunner` does, because the supervisor reads residency
    again after a load and the second answer is not the first.
    """

    def __init__(self, *payloads: object, fails: bool = False) -> None:
        self._payloads = list(payloads)
        self._fails = fails
        self.requests: list[str] = []

    def open(self, request: object, timeout: float) -> object:
        self.requests.append(getattr(request, "full_url", ""))
        if self._fails:
            raise OSError("nothing is listening")
        return self

    def __enter__(self) -> FakeListing:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        payload = self._payloads.pop(0) if len(self._payloads) > 1 else self._payloads[0]
        return json.dumps(payload).encode()


@contextmanager
def listing_answers(listing: FakeListing) -> Iterator[None]:
    """Point the module's opener at a fake listing, and put the real one back."""
    import val_providers.lmstudio_runtime as module

    real = module.urllib.request.build_opener
    module.urllib.request.build_opener = lambda *a, **k: listing  # type: ignore[assignment]
    try:
        yield
    finally:
        module.urllib.request.build_opener = real


def test_residency_is_read_from_the_servers_own_listing_without_a_subprocess() -> None:
    """The change that took the readiness check from 145 ms to 8 ms."""
    runner = FakeRunner(ps=["[]"])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    engine.serving = lambda: True  # type: ignore[method-assign]
    listing = FakeListing(
        {
            "data": [
                {"id": "openai/gpt-oss-20b", "state": "loaded", "loaded_context_length": 32_768},
                {"id": "some/other-model", "state": "not-loaded"},
            ]
        }
    )
    with listing_answers(listing):
        readiness = engine.ensure_ready(CONFIG)
    assert readiness["model_found_loaded"] is True
    assert readiness["loaded_context_tokens"] == 32_768
    assert runner.verbs == [], "no subprocess was spawned at all"
    assert listing.requests and listing.requests[0].endswith("/api/v0/models")


def test_a_model_the_listing_does_not_call_loaded_is_not_treated_as_resident() -> None:
    """`state` is read, not assumed: a listed model is not a loaded model."""
    runner = FakeRunner(ps=[instance()])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    engine.serving = lambda: True  # type: ignore[method-assign]
    listing = FakeListing(
        {"data": [{"id": "openai/gpt-oss-20b", "state": "not-loaded"}]},
        {
            "data": [
                {"id": "openai/gpt-oss-20b", "state": "loaded", "loaded_context_length": 32_768}
            ]
        },
    )
    with listing_answers(listing):
        readiness = engine.ensure_ready(CONFIG)
    assert readiness["model_found_loaded"] is False, "it was not resident"
    assert readiness["model_loaded"] is True, "so it was loaded"
    assert "load" in runner.verbs


def test_a_listing_that_cannot_answer_falls_back_to_the_command_line_tool() -> None:
    """Nothing is weakened: the subprocess is still there when HTTP cannot answer."""
    runner = FakeRunner(ps=[instance()])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    engine.serving = lambda: True  # type: ignore[method-assign]
    listing = FakeListing(None, fails=True)
    with listing_answers(listing):
        readiness = engine.ensure_ready(CONFIG)
    assert readiness["model_found_loaded"] is True
    assert runner.verbs == ["ps"], "the CLI answered instead"


def test_a_listing_of_the_wrong_shape_falls_back_rather_than_reporting_nothing_loaded() -> None:
    """A malformed reply is a reason to ask the CLI, never a claim that nothing is loaded."""
    runner = FakeRunner(ps=[instance()])
    engine = LMStudioRuntime("http://127.0.0.1:1234/v1", "a-token", runner=runner)  # type: ignore[arg-type]
    engine.serving = lambda: True  # type: ignore[method-assign]
    listing = FakeListing({"unexpected": "shape"})
    with listing_answers(listing):
        readiness = engine.ensure_ready(CONFIG)
    assert readiness["model_found_loaded"] is True
    assert runner.verbs == ["ps"]


def test_two_callers_at_once_produce_one_load_and_not_two() -> None:
    """The defect this pass found, and the reason `ensure_ready` is serialised.

    Two callers used to issue two loads, LM Studio obliged, and the exact
    preflight then found two instances answering to one model identifier and
    failed closed onto the conservative byte bound — losing the exact measurement
    that is a hard gate. The second caller now waits and finds the model loaded.
    """
    started = threading.Event()
    release = threading.Event()

    class SlowLoad(FakeRunner):
        def run(self, argv: Sequence[str], timeout: float) -> tuple[int, str]:
            if argv[1] == "load":
                # Recorded before the wait, so the argument vector is observable
                # while this caller is still inside the load.
                self.calls.append(list(argv))
                started.set()
                release.wait(timeout=5)
                return self.load_code, ""
            return super().run(argv, timeout)

    # Not loaded, then loaded: the second observation finds what the first load did.
    runner = SlowLoad(ps=["[]", instance()])
    engine = runtime(runner, serving=True)

    results: list[Mapping[str, object]] = []

    def ask() -> None:
        results.append(engine.ensure_ready(CONFIG))

    first = threading.Thread(target=ask)
    first.start()
    assert started.wait(timeout=5), "the first caller is inside the load"
    second = threading.Thread(target=ask)
    second.start()
    # The second caller must be waiting on the lock, not issuing its own load.
    time.sleep(0.2)
    assert runner.verbs.count("load") == 1, "the second caller did not start a second load"
    release.set()
    first.join(timeout=10)
    second.join(timeout=10)

    assert runner.verbs.count("load") == 1, "exactly one load happened"
    assert len(results) == 2, "both callers were answered"
    assert results[0]["model_loaded"] is True, "the first caller did the loading"
    assert results[1]["model_loaded"] is False, "the second found it already resident"
