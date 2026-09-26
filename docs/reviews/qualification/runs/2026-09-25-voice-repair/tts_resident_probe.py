"""Resident speech worker against the one-shot runner — Voice-mode repair §5.

Same provider class, same governed voice, same phrases: one-shot first (the path
production used), then the resident worker. Records per-synthesis wall time, the
runner's own report, the conditioning prompt's digest, and the worker's memory.
Local, $0; the audio exists only in memory and is discarded.

Usage: tts_resident_probe.py OUT.json
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from val_domain.speech import SpeechRequest
from val_providers.qwen_tts_speech import VOICE_RECORD, QwenTTSSpeech, load_canonical_voice

PHRASES = [
    "Good evening, my lord.",
    "How may I assist you?",
    "I am ready to read aloud any passage you wish.",
    "Simply let me know what text you would like me to voice.",
]
voice = load_canonical_voice(VOICE_RECORD)


def run(provider: QwenTTSSpeech, label: str) -> list[dict]:
    rows = []
    for phrase in PHRASES:
        started = time.monotonic()
        result = provider.synthesize(SpeechRequest(text=phrase, voice=voice))
        rows.append({"path": label, "characters": len(phrase),
                     "seconds": round(time.monotonic() - started, 3),
                     "audio_seconds": result.duration_seconds,
                     "sample_rate": result.sample_rate,
                     "clone_prompt_sha256": result.clone_prompt_sha256[:16]})
        print(json.dumps(rows[-1]), flush=True)
    return rows


oneshot = run(QwenTTSSpeech(), "one-shot")
provider = QwenTTSSpeech()
began = time.monotonic()
warmed = provider.warm()
start_seconds = round(time.monotonic() - began, 3)
resident = run(provider, "resident")
pid = provider._resident.pid if provider._resident is not None else None
rss_mb = None
if pid:
    rss_kb = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout
    rss_mb = round(int(rss_kb.strip()) / 1024, 1)
released = provider.release()
Path(sys.argv[1]).write_text(json.dumps({
    "one_shot": oneshot, "resident_start": warmed | {"seconds": start_seconds},
    "resident": resident, "resident_rss_mb": rss_mb, "released": released}, indent=1) + "\n")
print("resident start", warmed, start_seconds, "rss MB", rss_mb, released)
