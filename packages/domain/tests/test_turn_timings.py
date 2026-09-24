"""The diagnostic timing recorder — pre-WP3 latency pass §8 and §19.

Two properties matter more than the arithmetic. First, **it is inert unless
someone is listening**: a production turn installs no recorder, and `mark` must
then do nothing at all — not allocate, not read a clock, not store a name.
Second, **a boundary that did not happen reports as absent, never as zero**: a
stage that took no time and a stage that never ran are different facts, and
collapsing them would invent a measurement.
"""

from __future__ import annotations

import threading

from val_domain import timings
from val_domain.timings import current, mark, recording


def test_marking_with_nobody_listening_does_nothing() -> None:
    """The production case. No recorder, no record, no error."""
    assert current() is None
    mark("turn_start")
    mark("provider_dispatch")
    assert current() is None, "nothing was installed by marking"


def test_a_recorder_collects_marks_in_order() -> None:
    with recording() as recorder:
        mark("turn_start")
        mark("classification_start")
        mark("classification_end")
    names = [name for name, _ in recorder.marks]
    assert names == ["turn_start", "classification_start", "classification_end"]
    assert recorder.first("turn_start") is not None
    assert recorder.count("classification_start") == 1


def test_the_marks_are_monotonic_and_ordered_by_causality() -> None:
    with recording() as recorder:
        for name in ("turn_start", "classification_start", "classification_end", "dispatch"):
            mark(name)
    instants = [at for _, at in recorder.marks]
    assert instants == sorted(instants), "a monotonic clock never goes backwards"
    assert recorder.first("turn_start") <= recorder.first("classification_start")  # type: ignore[operator]
    assert recorder.first("classification_start") <= recorder.first("classification_end")  # type: ignore[operator]


def test_a_boundary_that_never_happened_is_absent_and_not_zero() -> None:
    """The rule that keeps a residual from being reported as a stage."""
    with recording() as recorder:
        mark("turn_start")
    assert recorder.first("classification_start") is None
    assert recorder.last("classification_start") is None
    assert recorder.span("classification_start", "classification_end") is None
    assert recorder.span("turn_start", "classification_end") is None, (
        "a span with only one end is not a duration"
    )
    assert recorder.count("classification_start") == 0


def test_a_span_measures_the_first_pair_and_not_a_later_one() -> None:
    with recording() as recorder:
        mark("open")
        mark("close")
        mark("open")
        mark("close")
    first = recorder.span("open", "close")
    assert first is not None and first >= 0
    assert recorder.count("open") == 2, "both are kept; the span names the first pair"


def test_a_repeated_mark_keeps_its_whole_series() -> None:
    """A turn makes several provider calls, and each dispatches."""
    with recording() as recorder:
        for _ in range(3):
            mark("provider_dispatch")
    assert recorder.count("provider_dispatch") == 3
    # `first` and `last` name the two ends of the series, not one entry twice.
    # Asserted against the recorded marks rather than against the clock:
    # comparing two instants for inequality would depend on the resolution of
    # `time.monotonic`, and the assertion originally written here escaped that
    # by ending in `or True`, which nothing could fail (replaced 24 September
    # 2026, WP3 §0.1).
    series = [
        at - recorder.started_at for name, at in recorder.marks if name == "provider_dispatch"
    ]
    assert len(series) == 3
    assert recorder.first("provider_dispatch") == series[0]
    assert recorder.last("provider_dispatch") == series[-1]
    assert recorder.last("provider_dispatch") >= recorder.first("provider_dispatch")


def test_two_turns_in_flight_do_not_write_into_one_recorder() -> None:
    """Context-local, so one turn's stopwatch is not another's."""
    seen: dict[str, list[str]] = {}

    def a_turn(label: str, marks: list[str]) -> None:
        with recording() as recorder:
            for name in marks:
                mark(name)
            seen[label] = [name for name, _ in recorder.marks]

    left = threading.Thread(target=a_turn, args=("left", ["turn_start", "left_only"]))
    right = threading.Thread(target=a_turn, args=("right", ["turn_start", "right_only"]))
    left.start(), right.start()
    left.join(), right.join()
    assert seen["left"] == ["turn_start", "left_only"]
    assert seen["right"] == ["turn_start", "right_only"]


def test_a_recorder_does_not_outlive_its_block() -> None:
    with recording():
        assert current() is not None
    assert current() is None, "the context is restored, not left installed"


def test_the_record_is_relative_seconds_and_carries_no_content() -> None:
    """A stopwatch, not evidence. Nothing here is about what was said."""
    with recording() as recorder:
        mark("turn_start")
        mark("provider_visible_text")
    document = recorder.as_record()
    assert set(document) == {"marks", "elapsed_s"}
    for entry in document["marks"]:  # type: ignore[union-attr]
        assert set(entry) == {"name", "at_s"}
        assert isinstance(entry["at_s"], float)
        assert entry["at_s"] >= 0.0


def test_nothing_in_the_module_persists_anything() -> None:
    """Not a durable schema: no database, no file, no table."""
    import inspect
    import io
    import tokenize

    code = "".join(
        token.string
        for token in tokenize.generate_tokens(io.StringIO(inspect.getsource(timings)).readline)
        if token.type not in (tokenize.COMMENT, tokenize.STRING)
    ).lower()
    for forbidden in ("insert", "engine", "session", "open(", "write_text", "write_bytes", "text("):
        assert forbidden not in code, f"{forbidden!r} must not appear: this is a stopwatch"
