"""The reconciliation stream filter — Val Core Phase 1, 11 September 2026.

Her prose streams; the typed verdict block never does. The marker may arrive
split across deltas of any size, and a reply without a marker is released in
full when the stream closes.
"""

from __future__ import annotations

from val_policy.deliberation import RECONCILIATION_VERDICT_MARKER, ReconciliationStream

VERDICT = (
    f"\n{RECONCILIATION_VERDICT_MARKER}\n"
    '{"outcome": "held", "recorded_prior": "x", "final_position": "x"}'
)


def _run(deltas: list[str]) -> list[str]:
    seen: list[str] = []
    stream = ReconciliationStream(seen.append)
    for delta in deltas:
        stream.feed(delta)
    stream.close()
    return seen


def test_prose_streams_and_the_verdict_block_is_withheld() -> None:
    out = _run(["I hold, my lord. ", "The film is about her hands.", VERDICT])
    assert "".join(out) == "I hold, my lord. The film is about her hands.", (
        "the separator before the block is the block's, as split_reconciled reads it"
    )
    assert not any("outcome" in piece or RECONCILIATION_VERDICT_MARKER in piece for piece in out)


def test_a_marker_split_across_deltas_is_still_withheld_whole() -> None:
    text = "Prose first." + VERDICT
    for size in (1, 2, 3, 5, 7, 11):
        pieces = [text[i : i + size] for i in range(0, len(text), size)]
        out = _run(pieces)
        assert "".join(out) == "Prose first.", size
        assert all(RECONCILIATION_VERDICT_MARKER not in piece for piece in out)


def test_nothing_after_the_marker_is_ever_forwarded() -> None:
    out = _run(["Prose.", VERDICT, " trailing", " more"])
    assert "".join(out) == "Prose."


def test_a_reply_without_a_marker_is_released_in_full_on_close() -> None:
    # "VAL-" alone could begin the marker, so it is held until close releases it.
    out = _run(["Ends with a possible prefix VAL-"])
    assert "".join(out) == "Ends with a possible prefix VAL-"
    partial: list[str] = []
    stream = ReconciliationStream(partial.append)
    stream.feed("Ends with a possible prefix VAL-")
    assert "".join(partial) == "Ends with a possible prefix", (
        "the prefix and the whitespace before it are held, not shown"
    )
    stream.close()
    assert "".join(partial) == "Ends with a possible prefix VAL-"


def test_prose_is_forwarded_in_order_without_loss_or_duplication() -> None:
    deltas = ["a", "bc", "", "def", "g"]
    assert "".join(_run(deltas)) == "abcdefg"
    assert _run([]) == []
