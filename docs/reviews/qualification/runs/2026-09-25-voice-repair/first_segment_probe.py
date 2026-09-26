"""What her first segment's length costs before she speaks — targeted latency order.

His 13-second turn (message 8 of conversation 01a0db46…) spent 3.85 s synthesising
a 121-character first sentence before any audio existed. This synthesises the actual
opening sentences of his session's answers whole, and cut at their first natural
pause, on the resident worker (no cognition running, so no contention), three times
each. Same provider, same governed voice. Local, $0; audio kept in memory only.

Usage: first_segment_probe.py OUT.json
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from val_domain.speech import SpeechRequest
from val_providers.qwen_tts_speech import VOICE_RECORD, QwenTTSSpeech, load_canonical_voice

CASES = [
    ("message 8 whole", "My lord, the voice model is tuned for a natural conversational pace – "
     "roughly the cadence of an ordinary spoken exchange."),
    ("message 8 to its pause", "My lord, the voice model is tuned for a natural conversational pace –"),
    ("message 12 whole", "My lord, the voice model is already tuned for a natural conversational "
     "cadence—roughly one second from receiving your message to the first sound it produces."),
    ("message 12 to its pause", "My lord, the voice model is already tuned for a natural "
     "conversational cadence—"),
    ("message 10 whole", "My lord, the delay you noted is not a fault of the voice model itself "
     "but rather a matter of processing latency."),
    ("message 10 to its pause", "My lord, the delay you noted is not a fault of the voice model itself,"),
]
voice = load_canonical_voice(VOICE_RECORD)
provider = QwenTTSSpeech()
provider.warm()
provider.synthesize(SpeechRequest(text="Good evening, my lord.", voice=voice))  # settle
rows = []
for _ in range(3):
    for label, text in CASES:
        started = time.monotonic()
        result = provider.synthesize(SpeechRequest(text=text, voice=voice))
        rows.append({"case": label, "characters": len(text),
                     "synthesis_seconds": round(time.monotonic() - started, 3),
                     "audio_seconds": result.duration_seconds})
        print(json.dumps(rows[-1]), flush=True)
provider.release()
Path(sys.argv[1]).write_text(json.dumps({"rows": rows}, indent=1) + "\n")
