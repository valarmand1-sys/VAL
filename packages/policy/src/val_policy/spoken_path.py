"""Does this turn ask about how her spoken replies reach him? — the gate for `spoken_path`.

Owner order, 26 September 2026 (reduce the wait before Val speaks). The record-state
`spoken_path` facts (targeted voice latency order, 25 September) are 470 tokens that
every spoken turn recomputed before her first output — about 0.6 s on this Mac —
whether or not he had asked about her speed. The per-turn necessity rule
(`01-architecture.md` §5.5) says such context must justify running on every turn, and
where a deterministic gate settles it, be gated, failing toward inclusion when
ambiguous. They matter only when he asks about her speed, timing, voice or the path
itself, so they are included then — and on anything that looks like it.

Deterministic and closed: word stems, no model, no inference. A false positive costs a
few hundred tokens; a false negative risks her inventing again, so the list is broad.
"""

from __future__ import annotations

import re

#: Stems that make a turn one about the spoken path. Broad on purpose.
_ASKS = re.compile(
    r"\b("
    r"fast\w*|quick\w*|slow\w*|speed\w*|pace|pacing|rapid\w*|prompt\w*|"
    r"lag\w*|laten\w*|delay\w*|wait\w*|seconds?|minutes?|long|took|take[sn]?|"
    r"respon\w*|repl\w*|answer\w*\s+(?:me\s+)?(?:faster|sooner|quicker)|"
    r"tim(?:e|es|ed|ing|er)|clock|stopwatch|measur\w*|record\w*|demonstrat\w*|benchmark\w*|"
    r"network\w*|internet|wi-?fi|connection|bandwidth|hardware|gpu|cpu|processor|"
    r"voice\w*|speak\w*|spoke|speech|talk\w*|hear\w*|sound\w*|audio|tun(?:e|ed|ing)"
    r")\b",
    re.IGNORECASE,
)


def asks_about_the_spoken_path(text: str) -> bool:
    """Whether the facts about her spoken path belong in this turn's record state."""
    return _ASKS.search(text) is not None
