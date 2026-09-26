"""Per-turn figures from a measure.py report — reduce the wait before Val speaks."""
import json
import sys

for path in sys.argv[1:]:
    r = json.load(open(path))
    print("==", r["condition"], r["revision"][:8], "dirty" if r["dirty"] else "clean")
    comps = r["service_components"]
    k = 0
    for s in r["sessions"]:
        for i, t in enumerate(s["turns"]):
            c = comps[k] if k < len(comps) else {}
            k += 1
            e = t["speech_end_to"]
            segs = t["segments"]
            fp = e["first_playback_start"]
            ms = lambda a: None if a is None or fp is None else round(fp - a)  # noqa: E731
            gaps = [x["gap_after_previous_ms"] for x in segs[1:] if x.get("gap_after_previous_ms") is not None]
            under = [x.get("underrun_ms", 0) for x in segs]
            print(f"  t{i+1} end->play {fp:>8} commit->play {ms(e['committed_seen'])} msg->play {ms(e['owner_message_canonical'])}"
                  f" | seg1 {segs[0]['chars'] if segs else None}ch pieces {segs[0].get('pieces',1) if segs else None}"
                  f" | seg->audio {c.get('first_segment_to_first_audio_ms')} ready->out {c.get('request_ready_to_first_output_ms')} out->text {c.get('first_output_to_visible_text_ms')}"
                  f" | gaps>0 {sum(1 for g in gaps if g and g > 50)}/{len(gaps)} max {max(gaps) if gaps else None} underrun {round(sum(under))}")
    print("  machine", r["machine"])
