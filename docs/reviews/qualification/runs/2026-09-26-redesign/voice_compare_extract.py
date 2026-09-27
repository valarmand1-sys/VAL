"""Per-turn intervals of the desktop Voice comparison, both constructions — §5, 27 Sept 2026.

Reads two desktop-integration records (as the request stands; envelope in the developer
block) and their service logs, and prints, per turn: speech end → canonical message
(desktop DOM and service commit), request dispatch → first visible text, first speech-safe
segment, first playable audio at the sink, desktop playback start, and the cold or
maintenance waits (exact preflight, primes in flight). Boundaries kept apart: service
marks are from the turn's endpoint; the desktop's own report is from speech end; the
harness's plan gives speech end → endpoint. Usage: voice_compare_extract.py A.json B.json
"""

from __future__ import annotations

import json
import sys


def turns(path: str) -> list[dict]:
    d = json.load(open(path))
    sc = d["service_clock"]
    out = []
    desktop = {r["utterance"]: r for r in sc["desktop_timing_reports"] if r.get("speech_end_to_playback_start_ms") is not None}
    routes = sc["fast_route"]
    for tl in sc["turn_timelines"]:
        m = tl["marks"]
        u = tl["utterance"]
        d_rep = desktop.get(u, {})
        speech_end_to_endpoint = (d_rep.get("speech_end_to_owner_message_dom_ms") or 0) - (m.get("owner_message_committed") or 0) if d_rep else None
        out.append({
            "utterance": u,
            "route": routes[u - 1]["tier"] if u - 1 < len(routes) else None,
            "speech_end_to_owner_message_dom_ms": d_rep.get("speech_end_to_owner_message_dom_ms"),
            "endpoint_to_committed_ms": m.get("owner_message_committed"),
            "exact_preflight_ms": None if m.get("exact_preflight_end") is None else round(m["exact_preflight_end"] - m["exact_preflight_start"], 1),
            "dispatch_to_first_visible_text_ms": None if m.get("provider_visible_text") is None or m.get("provider_dispatch") is None else round(m["provider_visible_text"] - m["provider_dispatch"], 1),
            "dispatch_to_first_chunk_ms": None if m.get("provider_chunk") is None or m.get("provider_dispatch") is None else round(m["provider_chunk"] - m["provider_dispatch"], 1),
            "endpoint_to_first_speech_safe_segment_ms": m.get("speech_segment_queued"),
            "endpoint_to_first_playable_audio_ms": m.get("audio_at_sink"),
            "speech_end_to_desktop_playback_start_ms": d_rep.get("speech_end_to_playback_start_ms"),
        })
    return out, sc["primes"], d["store"]["messages"], sc["voice_on_to_ready_s"]


for path in sys.argv[1:3]:
    rows, primes, messages, ready = turns(path)
    print(f"\n== {path.split('/')[-1]} (Voice On → Ready {ready} s)")
    for m in messages:
        print("  msg", m["role"], repr(m["content"][:90]))
    for r in rows:
        print("  turn", json.dumps(r))
    for p in primes:
        print("  prime", (str(p)[:120]))
