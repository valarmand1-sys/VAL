import json
import sys
import time

from val_domain.speech import SpeechRequest
from val_providers.qwen_tts_speech import VOICE_RECORD, QwenTTSSpeech, load_canonical_voice

provider = QwenTTSSpeech()
reports = []
original = provider._parse


def parse(code, out, err):
    report = original(code, out, err)
    reports.append(report)
    return report


provider._parse = parse
voice = load_canonical_voice(VOICE_RECORD)
rows = []
for i in range(3):
    t = time.monotonic()
    result = provider.synthesize(SpeechRequest(text="Good evening, my lord.", voice=voice))
    total = time.monotonic() - t
    r = reports[-1]
    rows.append(
        {
            "subprocess_total_s": round(total, 3),
            "runner_load_s": r.get("load_seconds"),
            "runner_load_to_written_s": r.get("elapsed_seconds"),
            "outside_runner_s (interpreter start, imports, workspace, wav read)": round(
                total - (r.get("elapsed_seconds") or 0), 3
            ),
            "audio_s": r.get("duration_seconds"),
        }
    )
print(json.dumps(rows, indent=1))
open(sys.argv[1], "w").write(json.dumps(rows, indent=1))
