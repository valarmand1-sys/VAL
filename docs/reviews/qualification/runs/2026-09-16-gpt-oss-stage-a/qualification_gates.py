"""Qualification hard gates shared by the Stage A harness and the proof scripts.

Owner ruling, 18 September 2026 (§2, §9): any nonzero exact-preflight parity
difference halts a qualification run immediately; recording a warning and
continuing is a harness-control defect. `parity_halt` returns the STOP message
for a call's recorded parity, or None when the call may stand.
"""

from __future__ import annotations

from collections.abc import Mapping


def parity_halt(parity: Mapping[str, object] | None, *, label: str) -> str | None:
    """The STOP message when `parity` is missing or not exact; None when exact."""
    if not parity:
        return f"PARITY NOT RECORDED on {label}: the call cannot stand. STOP."
    if parity.get("exact") is not True or parity.get("difference") not in (0, None):
        return (
            f"PARITY NOT EXACT on {label}: preflight {parity.get('preflight_prompt_tokens')} vs "
            f"server {parity.get('server_prompt_tokens')} (difference {parity.get('difference')}). STOP."
        )
    return None
