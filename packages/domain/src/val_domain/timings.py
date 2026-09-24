"""Monotonic marks for one turn — diagnostic only.

Pre-WP3 latency pass §8. A turn's latency could be measured at its ends and
nowhere in between, so "where does the time go" could only be answered by
guessing. This is the smallest thing that answers it: a recorder a caller may
install for one turn, and a handful of `mark` calls on the path.

**It is inert unless a recorder is installed.** `mark` with no recorder reads one
context variable and returns; nothing is allocated, nothing is stored, no clock is
read. Production turns install no recorder, so the live path is unchanged.

**It is not a durable schema.** Nothing here is written to the database, and
nothing here is evidence about what Val said or did. It is a stopwatch with
labelled buttons, thrown away when the turn ends.

Marks are `time.monotonic`, so an interval between two of them is a real elapsed
duration and never a wall-clock difference that a system clock adjustment could
corrupt.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class TurnTimings:
    """What happened when, on one turn, in the order it happened.

    A mark may be recorded more than once — a turn makes several provider calls,
    and each dispatches — so every mark keeps its whole series. A reader asking
    for "the first provider dispatch" gets the first; a reader asking how many
    there were gets the count. Neither has to be inferred.
    """

    started_at: float = field(default_factory=time.monotonic)
    marks: list[tuple[str, float]] = field(default_factory=list)

    def mark(self, name: str) -> float:
        """Note that `name` happened now. Returns the elapsed seconds since start."""
        at = time.monotonic()
        self.marks.append((name, at))
        return at - self.started_at

    # --- reading it back ---------------------------------------------------------

    def first(self, name: str) -> float | None:
        """Seconds from the turn's start to the first `name`, or `None`."""
        for recorded, at in self.marks:
            if recorded == name:
                return at - self.started_at
        return None

    def last(self, name: str) -> float | None:
        for recorded, at in reversed(self.marks):
            if recorded == name:
                return at - self.started_at
        return None

    def count(self, name: str) -> int:
        return sum(1 for recorded, _ in self.marks if recorded == name)

    def span(self, start: str, end: str) -> float | None:
        """The interval between the first `start` and the first `end` after it.

        `None` when either boundary was never reached — **never zero**, because a
        boundary that did not happen is not a boundary that took no time.
        """
        opened: float | None = None
        for recorded, at in self.marks:
            if recorded == start and opened is None:
                opened = at
            elif recorded == end and opened is not None:
                return at - opened
        return None

    def elapsed(self) -> float:
        return (self.marks[-1][1] - self.started_at) if self.marks else 0.0

    def as_record(self) -> dict[str, object]:
        """Every mark, in order, in seconds from the start of the turn."""
        return {
            "marks": [
                {"name": name, "at_s": round(at - self.started_at, 4)} for name, at in self.marks
            ],
            "elapsed_s": round(self.elapsed(), 4),
        }


_CURRENT: ContextVar[TurnTimings | None] = ContextVar("val_turn_timings", default=None)


def mark(name: str) -> None:
    """Note a boundary, if anyone is listening. Otherwise do nothing at all."""
    recorder = _CURRENT.get()
    if recorder is not None:
        recorder.mark(name)


def current() -> TurnTimings | None:
    """The recorder installed for this turn, if there is one."""
    return _CURRENT.get()


@contextmanager
def recording(recorder: TurnTimings | None = None) -> Iterator[TurnTimings]:
    """Install a recorder for the duration of this block.

    Context-local, so a turn on a worker thread records its own marks and two
    turns in flight together do not write into one another's stopwatch.
    """
    live = recorder if recorder is not None else TurnTimings()
    token = _CURRENT.set(live)
    try:
        yield live
    finally:
        _CURRENT.reset(token)
